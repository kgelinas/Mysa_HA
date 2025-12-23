"""API Client for Mysa."""
import logging
import asyncio
import json
import time
from urllib.parse import urlparse
from uuid import uuid1
import ssl

import websockets
from .lib.mysotherm import auth, mysa_stuff, aws
from .lib.mqttpacket import v311 as mqttpacket

_LOGGER = logging.getLogger(__name__)

class MysaApi:
    """Mysa API Client."""

    def __init__(self, username, password, hass):
        """Initialize the API."""
        self.username = username
        self.password = password
        self.hass = hass
        self._user_obj = None
        self._session = None
        self._user_id = None # Mysa User UUID
        self.devices = {}
        self.states = {}
        self._last_command_time = {}  # device_id: timestamp

    async def authenticate(self):
        """Authenticate with Mysa."""
        return await self.hass.async_add_executor_job(self._authenticate_sync)

    def _authenticate_sync(self):
        """Synchronous authentication."""
        bsess = aws.boto3.session.Session(region_name=mysa_stuff.REGION)
        config_path = self.hass.config.path("mysa_auth.json")
        
        try:
            _LOGGER.debug("Attempting to load cached credentials from %s", config_path)
            self._user_obj = auth.load_credentials(self.username, cf=config_path, bsess=bsess)
        except (NotImplementedError, Exception) as e:
            _LOGGER.debug("Could not load cached credentials (%s), logging in with password", e)
            try:
                self._user_obj = auth.login(self.username, self.password, bsess=bsess, cf=config_path)
            except Exception as e:
                 _LOGGER.error("Authentication failed: %s", e)
                 raise

        self._session = import_requests_session(self._user_obj)
        
        # Fetch User ID (needed for MQTT commands)
        try:
           # Based on mysotherm: (r := sess.get(f'{BASE_URL}/users')).json().User.Id
           r = self._session.get(f"{mysa_stuff.BASE_URL}/users")
           r.raise_for_status()
           user_data = r.json()
           # Structure seems to be {"User": {"Id": "..."}}
           self._user_id = user_data.get("User", {}).get("Id")
           _LOGGER.debug("Fetched User ID: %s", self._user_id)
        except Exception as e:
           _LOGGER.error("Failed to fetch User ID: %s", e)

        return True

    async def get_devices(self):
        """Get devices."""
        return await self.hass.async_add_executor_job(self._get_devices_sync)

    def _get_devices_sync(self):
        """Get devices synchronously from HTTP API."""
        if not self._session:
            self._authenticate_sync()
            
        url = f"{mysa_stuff.BASE_URL}/devices"
        r = self._session.get(url)
        r.raise_for_status()
        
        # Store as a dict indexed by Id for efficient lookups
        # Handle both list and dict responses for robustness
        devices_raw = r.json().get('DevicesObj', [])
        if isinstance(devices_raw, list):
             self.devices = {d['Id']: d for d in devices_raw}
        else:
             self.devices = devices_raw
             
        return self.devices

    async def get_state(self):
        """Get full state of all devices."""
        return await self.hass.async_add_executor_job(self._get_state_sync)

    def _get_state_sync(self):
        """Get state synchronously from HTTP API."""
        if not self._session:
            self._authenticate_sync()
            
        url = f"{mysa_stuff.BASE_URL}/devices/state"
        r = self._session.get(url)
        r.raise_for_status()
        
        # Handle both list and dict responses for robustness
        new_states_raw = r.json().get('DeviceStatesObj', [])
        if isinstance(new_states_raw, list):
            new_states = {d['Id']: d for d in new_states_raw}
        else:
            new_states = new_states_raw
            
        # Merge new states into our existing cache
        now = time.time()
        for device_id, new_data in new_states.items():
            if device_id not in self.states:
                self.states[device_id] = new_data
            else:
                # If we recently sent a command, ignore stale cloud status for a bit
                if now - self._last_command_time.get(device_id, 0) < 15:
                    _LOGGER.debug("Ignoring potentially stale HTTP state for %s", device_id)
                    # Filter out keys that we likely changed
                    stale_keys = ['Mode', 'md', 'TstatMode', 'SetPoint', 'sp', 'stpt']
                    filtered_data = {k: v for k, v in new_data.items() if k not in stale_keys}
                    self.states[device_id].update(filtered_data)
                else:
                    self.states[device_id].update(new_data)

        return self.states

    async def _get_signed_mqtt_url(self):
        """Get signed MQTT URL."""
        def _sign():
            cred = self._user_obj.get_credentials(identity_pool_id=mysa_stuff.IDENTITY_POOL_ID)
            return mysa_stuff.sigv4_sign_mqtt_url(cred)
        return await self.hass.async_add_executor_job(_sign)

    async def _send_mqtt_command(self, device_id, payload_body):
        """Connect to MQTT, send command, and disconnect."""
        if not self._user_id:
             await self.authenticate()
             if not self._user_id:
                 _LOGGER.error("Cannot send MQTT command: User ID not found")
                 return

        try:
            signed_url = await self._get_signed_mqtt_url()
            url_parts = urlparse(signed_url)
            ws_url = url_parts._replace(scheme='wss').geturl()
            
            # Construct MQTT payload
            timestamp = int(time.time())
            timestamp_ms = int(time.time() * 1000)
            
            # Outer payload wrapper
            outer_payload = {
                "Timestamp": timestamp,
                "body": payload_body,
                "dest": {"ref": device_id, "type": 1},
                "id": timestamp_ms,
                "msg": 44,
                "resp": 2,
                "src": {"ref": self._user_id, "type": 100},
                "time": timestamp,
                "ver": "1.0"
            }
            
            json_payload = json.dumps(outer_payload)
            
            # Sanitize device ID for MQTT topic (no colons, lowercase)
            safe_device_id = device_id.replace(":", "").lower()
            topic = f"/v1/dev/{safe_device_id}/in"

            _LOGGER.info("Sending MQTT command to %s: %s", topic, json_payload)
            _LOGGER.debug("Connecting to MQTT: %s", ws_url)
            
            # Create SSL context in executor to avoid blocking the loop
            ssl_context = await self.hass.async_add_executor_job(ssl.create_default_context)
            
            # Critical: Server/device requires proper User-Agent header
            # The official Mysa app uses okhttp/4.11.0
            headers = {'user-agent': 'okhttp/4.11.0'}
            
            # Try additional_headers first (websockets 14+), fallback to extra_headers
            try:
                async with websockets.connect(
                    ws_url,
                    subprotocols=['mqtt'],
                    ssl=ssl_context,
                    additional_headers=headers
                ) as ws:
                    # MQTT Connect
                    connect_pkt = mqttpacket.connect(str(uuid1()), 60)
                    await ws.send(connect_pkt)
                    
                    # Wait for Connack
                    resp = await ws.recv()
                    # Could assert isinstance(mqttpacket.parse_one(resp), mqttpacket.ConnackPacket)

                    # Subscribe to topics to establish "active" presence?
                    # liten_up subscribes to /out, /in, /batch
                    # Packet ID 1 for subscribe
                    sub_topics = [
                        mqttpacket.SubscriptionSpec(f'/v1/dev/{safe_device_id}/out', 0x01),
                        mqttpacket.SubscriptionSpec(f'/v1/dev/{safe_device_id}/in', 0x01),
                        mqttpacket.SubscriptionSpec(f'/v1/dev/{safe_device_id}/batch', 0x01)
                    ]
                    sub_pkt = mqttpacket.subscribe(1, sub_topics)
                    await ws.send(sub_pkt)
                    
                    # Wait for Suback
                    resp = await ws.recv()
                    # pkt = mqttpacket.parse_one(resp)
                    # assert isinstance(pkt, mqttpacket.SubackPacket)
                    
                    # Publish
                    _LOGGER.debug("Sending MQTT command to %s: %s", topic, json_payload)
                    # Packet ID 2 for publish
                    pub_pkt = mqttpacket.publish(topic, False, 1, False, packet_id=2, payload=json_payload.encode())
                    await ws.send(pub_pkt)
                    
                    # Wait for Puback
                    resp = await ws.recv()
                    _LOGGER.debug("Received response (likely PUBACK)")
                    
                    # Wait for device response (PUBLISH on /out)
                    # We give it a small timeout to not hang if the device is slow
                    try:
                         # Wait for up to 2 seconds for a response from the device
                         resp = await asyncio.wait_for(ws.recv(), timeout=2.0)
                         pkt = mqttpacket.parse_one(resp)
                         if isinstance(pkt, mqttpacket.PublishPacket):
                              _LOGGER.debug("Received status update from device: %s", pkt.payload)
                              payload = json.loads(pkt.payload)
                              # If it's a response to our command (msg 44) or a state update (msg 40)
                              if payload.get('msg') in [40, 44]:
                                   body = payload.get('body', {})
                                   state_update = body.get('state', body)
                                   
                                   # Ensure HTTP-style keys are synced with MQTT-style keys
                                   if 'md' in state_update:
                                        state_update['Mode'] = state_update['md']
                                   if 'sp' in state_update:
                                        state_update['SetPoint'] = state_update['sp']

                                   # Update our internal state cache for this device
                                   if device_id not in self.states:
                                        self.states[device_id] = state_update
                                   else:
                                        self.states[device_id].update(state_update)
                                        
                                   _LOGGER.info("Updated state for %s from MQTT: %s", device_id, self.states[device_id])
                    except asyncio.TimeoutError:
                         _LOGGER.debug("Timed out waiting for device status response")
                    except Exception as e:
                         _LOGGER.debug("Error parsing device status response: %s", e)

                    # Sleep briefly to ensure server processes it before we disconnect?
                    await asyncio.sleep(0.5)
            except TypeError as te:
                # Fallback for older websockets versions that use extra_headers
                if 'additional_headers' in str(te):
                    _LOGGER.info("Falling back to extra_headers for websockets compatibility")
                    async with websockets.connect(
                        ws_url,
                        subprotocols=['mqtt'],
                        ssl=ssl_context,
                        extra_headers=headers
                    ) as ws:
                        connect_pkt = mqttpacket.connect(str(uuid1()), 60)
                        await ws.send(connect_pkt)
                        resp = await ws.recv()
                        
                        sub_topics = [
                            mqttpacket.SubscriptionSpec(f'/v1/dev/{safe_device_id}/out', 0x01),
                            mqttpacket.SubscriptionSpec(f'/v1/dev/{safe_device_id}/in', 0x01),
                            mqttpacket.SubscriptionSpec(f'/v1/dev/{safe_device_id}/batch', 0x01)
                        ]
                        sub_pkt = mqttpacket.subscribe(1, sub_topics)
                        await ws.send(sub_pkt)
                        resp = await ws.recv()
                        
                        _LOGGER.debug("Sending MQTT command to %s: %s", topic, json_payload)
                        pub_pkt = mqttpacket.publish(topic, False, 1, False, packet_id=2, payload=json_payload.encode())
                        await ws.send(pub_pkt)
                        resp = await ws.recv()
                        _LOGGER.debug("Received response (likely PUBACK)")
                        await asyncio.sleep(0.5)
                else:
                    raise
        except Exception as e:
            _LOGGER.error("Failed to send MQTT command: %s", e)

    async def set_target_temperature(self, device_id, temperature):
        """Set target temperature via MQTT."""
        self._last_command_time[device_id] = time.time()
        # Temperature as unscaled integer per mysa_messages.md
        target_int = int(temperature)
        
        # Determine Payload Type based on Model
        payload_type = self._get_payload_type(device_id)
        _LOGGER.debug("Using type %s for temp %s", payload_type, target_int)
        body = {"cmd": [{"sp": target_int, "tm": -1}], "type": payload_type, "ver": 1}
        await self._send_mqtt_command(device_id, body)
    
    def _get_payload_type(self, device_id):
        """Determine MQTT payload type (1, 3, 4, 5) based on device model."""
        device = self.devices.get(device_id)
        if not device:
             return 1 # Default to V1
             
        # Check various common model keys
        model = (device.get("Model") or device.get("ProductModel") or device.get("productModel") or "")
        fw = device.get("FirmwareVersion", "")
        _LOGGER.info("Device %s detected model: '%s', FW: '%s'", device_id, model, fw)
        
        # 1. Direct Model match
        if "BB-V2" in model:
             if "Lite" in model or "-L" in model:
                  return 5
             return 4
        if "INF-V1" in model:
             return 3
        if "BB-V1" in model:
             return 1
             
        # 2. Firmware-based fallback
        if "V2" in fw:
             return 4 # High probability of BB-V2
             
        # 3. Last resort: If model is missing, it's often a V2 on newer accounts
        # but we'll stick to 1 (V1) for safety unless we have a reason to change.
        # However, for this user, we know it's a V2. 
        # I'll add a debug log to help them confirm.
        if not model:
             _LOGGER.warning("Device %s has NO model info. Defaulting to Type 1 (V1). If this is a V2, commands may fail.", device_id)
        
        return 1 # Keep 1 as safe default for now

    async def set_hvac_mode(self, device_id, hvac_mode):
        """Set HVAC mode via MQTT."""
        self._last_command_time[device_id] = time.time()
        # Handle both string and Enum values
        mode_str = str(hvac_mode).lower()
        # Mode per documentation: md=1 for off, md=3 for heat
        mode_val = 1 if "off" in mode_str else 3
        
        payload_type = self._get_payload_type(device_id)
        _LOGGER.debug("Using type %s for mode %s (val=%s)", payload_type, hvac_mode, mode_val)
        
        body = {"cmd": [{"md": mode_val, "tm": -1}], "type": payload_type, "ver": 1}
        await self._send_mqtt_command(device_id, body)


import requests
def import_requests_session(user_obj):
    """Create a requests session from the user object."""
    sess = requests.Session()
    sess.auth = mysa_stuff.auther(user_obj)
    sess.headers.update(mysa_stuff.CLIENT_HEADERS)
    return sess
