"""API Client for Mysa."""
import logging
import asyncio
import json
import time
from urllib.parse import urlparse
from uuid import uuid1
import ssl

import requests
import websockets
import boto3
from homeassistant.helpers.storage import Store
from .mysa_auth import (
    Cognito, login, auther, sigv4_sign_mqtt_url,
    REGION, USER_POOL_ID, CLIENT_ID, JWKS, IDENTITY_POOL_ID,
    CLIENT_HEADERS, BASE_URL,
)
from . import mqtt
from .const import (
    AC_MODE_OFF, AC_MODE_AUTO, AC_MODE_HEAT, AC_MODE_COOL, AC_MODE_FAN_ONLY, AC_MODE_DRY,
    AC_FAN_MODES, AC_FAN_MODES_REVERSE,
    AC_SWING_MODES, AC_SWING_MODES_REVERSE,
    AC_PAYLOAD_TYPE,
)

_LOGGER = logging.getLogger(__name__)

STORAGE_KEY = "mysa.auth"
STORAGE_VERSION = 1

class MysaApi:
    """Mysa API Client."""

    def __init__(self, username, password, hass, coordinator_callback=None, upgraded_lite_devices=None):
        """Initialize the API."""
        self.username = username
        self.password = password
        self.hass = hass
        self.coordinator_callback = coordinator_callback
        self._user_obj = None
        self._session = None
        self._user_id = None # Mysa User UUID
        self.devices = {}
        self.upgraded_lite_devices = upgraded_lite_devices or []
        self.homes = []
        self.zones = {} # zone_id -> zone_name
        self.states = {}
        self._last_command_time = {}  # device_id: timestamp
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        
        # MQTT Listener attributes
        self._mqtt_listener_task = None
        self._mqtt_connected = asyncio.Event()
        self._mqtt_ws = None
        self._mqtt_should_reconnect = True
        self._mqtt_reconnect_delay = 5  # Start with 5 seconds

    async def authenticate(self):
        """Authenticate with Mysa (Async)."""
        # 1. Load cached tokens
        cached_data = await self._store.async_load()
        
        def do_sync_login():
            bsess = boto3.session.Session(region_name=REGION)
            
            # Try to restore session
            if cached_data and isinstance(cached_data, dict):
                id_token = cached_data.get("id_token")
                refresh_token = cached_data.get("refresh_token")
                if id_token and refresh_token:
                    try:
                        u = Cognito(
                            user_pool_id=USER_POOL_ID,
                            client_id=CLIENT_ID,
                            id_token=id_token,
                            refresh_token=refresh_token,
                            username=self.username,
                            session=bsess,
                            pool_jwk=JWKS
                        )
                        # Verify logic (similar to auth.load_credentials)
                        try:
                            u.verify_token(u.id_token, "id_token", "id")
                        except Exception:
                            # Try refresh
                            u.renew_access_token()
                        
                        _LOGGER.debug("Restored credentials from storage")
                        return u
                    except Exception as e:
                        _LOGGER.debug("Failed to restore credentials: %s", e)
            
            # Fallback to Password Login
            _LOGGER.debug("Logging in with password...")
            return login(self.username, self.password, bsess=bsess)

        try:
            self._user_obj = await self.hass.async_add_executor_job(do_sync_login)
        except Exception as e:
            _LOGGER.error("Authentication failed: %s", e)
            raise

        # 2. Save tokens back to Store
        if self._user_obj:
            await self._store.async_save({
                "id_token": self._user_obj.id_token,
                "refresh_token": self._user_obj.refresh_token
            })

        # 3. Setup Requests Session
        self._session = requests.Session()
        self._session.headers.update(CLIENT_HEADERS)
        self._session.auth = auther(self._user_obj)
        
        # 4. Fetch User ID (needed for MQTT commands)
        try:
           r = await self.hass.async_add_executor_job(
               lambda: self._session.get(f"{BASE_URL}/users")
           )
           r.raise_for_status()
           user_data = r.json()
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
            raise RuntimeError("Session not initialized")
            
        url = f"{BASE_URL}/devices"
        r = self._session.get(url)
        r.raise_for_status()
        
        # Store as a dict indexed by Id for efficient lookups
        # Handle both list and dict responses for robustness
        devices_raw = r.json().get('DevicesObj', [])
        if isinstance(devices_raw, list):
             self.devices = {d['Id']: d for d in devices_raw}
        else:
             self.devices = devices_raw
             
        # Auto-fetch homes/zones to populate mapping
        try:
             self._fetch_homes_sync()
        except Exception as e:
             _LOGGER.warning("Failed to fetch homes/zones: %s", e)

        return self.devices

    async def fetch_homes(self):
        """Fetch homes and zones."""
        return await self.hass.async_add_executor_job(self._fetch_homes_sync)

    def _fetch_homes_sync(self):
        """Fetch homes synchronously from HTTP API."""
        if not self._session:
             raise RuntimeError("Session not initialized")
        
        url = f"{BASE_URL}/homes"
        r = self._session.get(url)
        r.raise_for_status()
        
        
        data = r.json()
        self.homes = data.get('Homes', data.get('homes', []))
        
        # Populate zone mapping
        self.zones = {}
        for home in self.homes:
             for zone in home.get('Zones', []):
                 z_id = zone.get('Id')
                 z_name = zone.get('Name')
                 if z_id and z_name:
                     self.zones[z_id] = z_name
                     
        return self.homes

    def get_zone_name(self, zone_id):
        """Get friendly name for a zone ID."""
        return self.zones.get(zone_id)

    def fetch_firmware_info(self, device_id):
        """Fetch firmware update info (Sync)."""
        if not self._session:
             raise RuntimeError("Session not initialized")
        
        url = f"{BASE_URL}/devices/update_available/{device_id}"
        try:
            r = self._session.get(url, timeout=10)
            r.raise_for_status()
            # Response: {"update": bool, "installedVersion": "...", "allowedVersion": "..."}
            return r.json()
        except Exception as e:
            _LOGGER.debug("Failed to fetch firmware info for %s: %s", device_id, e)
            return None

    async def get_state(self):
        """Get full state of all devices."""
        return await self.hass.async_add_executor_job(self._get_state_sync)

    def _get_state_sync(self):
        """Get full state (settings + live data) from HTTP API."""
        if not self._session:
            raise RuntimeError("Session not initialized")
            
        # 1. Fetch live metrics (temp, humidity, duty, etc.)
        r_state = self._session.get(f"{BASE_URL}/devices/state")
        r_state.raise_for_status()
        state_json = r_state.json()
        new_states_raw = state_json.get('DeviceStatesObj', state_json.get('DeviceStates', []))
        if isinstance(new_states_raw, list):
            new_states = {d['Id']: d for d in new_states_raw}
        else:
            new_states = new_states_raw

        # 2. Fetch device settings (Lock, Brightness, AutoBrightness, Proximity, etc.)
        r_devices = self._session.get(f"{BASE_URL}/devices")
        r_devices.raise_for_status()
        devices_json = r_devices.json()
        
        devices_raw = devices_json.get('DevicesObj', devices_json.get('Devices', []))
        if isinstance(devices_raw, list):
            self.devices = {d['Id']: d for d in devices_raw}
        else:
            self.devices = devices_raw
            
        # Merge settings into states
        now = time.time()
        for device_id, live_data in new_states.items():
            # Add information from /devices to a merged object
            if device_id in self.devices:
                # Start with static settings, then overlay live data (sensors)
                new_data = self.devices[device_id].copy()
                
                # If there's an Attributes dict, flatten it first
                if "Attributes" in new_data and isinstance(new_data["Attributes"], dict):
                     new_data.update(new_data["Attributes"])
                
                # Now overlay live sensors/state (this ensures live 'Lock' wins)
                new_data.update(live_data)
            else:
                new_data = live_data

            # Normalize keys before updating
            self._normalize_state(new_data)

            if device_id not in self.states:
                self.states[device_id] = new_data
            else:
                # If we recently sent a command, ignore stale cloud status for a bit
                if now - self._last_command_time.get(device_id, 0) < 90:  # Extended to 90 seconds
                    _LOGGER.debug("Ignoring potentially stale HTTP state for %s", device_id)
                    stale_keys = [
                        'Mode', 'md', 'TstatMode', 'SetPoint', 'sp', 'stpt',
                        'Lock', 'lc', 'lk', 'ButtonState',
                        'Brightness', 'br', 'MinBrightness', 'MaxBrightness',
                        'AutoBrightness', 'ab', 'ProximityMode', 'pr', 'Proximity'
                    ]
                    filtered_data = {k: v for k, v in new_data.items() if k not in stale_keys}
                    self.states[device_id].update(filtered_data)
                else:
                    self.states[device_id].update(new_data)
            
            _LOGGER.debug("Merged state for %s. Keys: %s", device_id, list(self.states[device_id].keys()))

        return self.states

    def _normalize_state(self, state):
        """Standardize keys across HTTP and MQTT responses."""
        # Helper to get first available value that isn't None
        def get_v(keys, prefer_v=True):
            for k in keys:
                val = state.get(k)
                if val is not None:
                    if isinstance(val, dict):
                        extracted = val.get('v')
                        if extracted is not None:
                            return extracted
                        # V2 Brightness logic: prefer active_brightness (a_br)
                        if k == 'Brightness':
                             v2_br = val.get('a_br')
                             if v2_br is not None: return v2_br
                        # If no 'v' and it's a dict, we might want to continue to next key 
                        if prefer_v: continue 
                    return val
            return None

        # Basic mappings - only set if value exists
        # For V2, sp and md are often more reliable than the long names
        mode_val = get_v(['md', 'TstatMode', 'Mode'])
        if mode_val is not None:
            state['Mode'] = mode_val
        sp_val = get_v(['sp', 'stpt', 'SetPoint'])
        if sp_val is not None:
            state['SetPoint'] = sp_val
        duty_val = get_v(['dc', 'Duty', 'DutyCycle'])
        if duty_val is not None:
            state['Duty'] = duty_val
        rssi_val = get_v(['rssi', 'Rssi', 'RSSI'])
        if rssi_val is not None:
            state['Rssi'] = rssi_val
        voltage_val = get_v(['volts', 'Voltage', 'LineVoltage'])
        if voltage_val is not None:
            state['Voltage'] = voltage_val
        current_val = get_v(['amps', 'Current'])
        if current_val is not None:
            state['Current'] = current_val
        hs_val = get_v(['hs', 'HeatSink'])
        if hs_val is not None:
            state['HeatSink'] = hs_val
        if 'if' in state: 
            state['Infloor'] = get_v(['if', 'Infloor'])
            
        # Brightness variants
        # prefer 'br' then 'MaxBrightness' then complex 'Brightness' dict
        br_val = get_v(['br', 'MaxBrightness', 'Brightness'])
        if br_val is not None:
            state['Brightness'] = int(br_val)
            
        # Lock variants
        lock_val = get_v(['ButtonState', 'alk', 'lc', 'lk', 'Lock'])
        if lock_val is not None:
            # Handle int/string/bool
            state['Lock'] = 1 if (str(lock_val).lower() in ['1', 'true', 'on', 'locked']) else 0
        
        # Zone identification
        zone_val = get_v(['Zone', 'zone_id', 'zn'])
        if zone_val is not None:
             state['Zone'] = zone_val
             
        # Proximity variants
        px_val = get_v(['px', 'ProximityMode'])
        if px_val is not None:
             state['ProximityMode'] = str(px_val).lower() in ['1', 'true', 'on']

        # AutoBrightness variants
        ab_val = get_v(['ab', 'AutoBrightness'])
        if ab_val is not None:
             state['AutoBrightness'] = str(ab_val).lower() in ['1', 'true', 'on']
             
        # EcoMode variants (0=On, 1=Off)
        eco_val = get_v(['ecoMode', 'eco'])
        if eco_val is not None:
             state['EcoMode'] = (str(eco_val) == '0')
             
        # New Diagnostic mappings - only set if value exists
        min_br = get_v(['MinBrightness', 'mnbr'])
        if min_br is not None:
            state['MinBrightness'] = min_br
        max_br = get_v(['MaxBrightness', 'mxbr'])
        if max_br is not None:
            state['MaxBrightness'] = max_br
        max_current = get_v(['MaxCurrent', 'mxc'])
        if max_current is not None:
            state['MaxCurrent'] = max_current
        max_setpoint = get_v(['MaxSetpoint', 'mxs'])
        if max_setpoint is not None:
            state['MaxSetpoint'] = max_setpoint
        timezone = get_v(['TimeZone', 'tz'])
        if timezone is not None:
            state['TimeZone'] = timezone

        # =================================================================
        # AC Controller specific mappings
        # =================================================================
        
        # Fan Speed (AC)
        fan_val = get_v(['fn', 'FanSpeed'])
        if fan_val is not None:
            state['FanSpeed'] = int(fan_val)
            # Also store the HA-friendly name
            state['FanMode'] = AC_FAN_MODES.get(int(fan_val), 'unknown')
        
        # Vertical Swing (AC)
        swing_val = get_v(['ss', 'SwingState'])
        if swing_val is not None:
            state['SwingState'] = int(swing_val)
            state['SwingMode'] = AC_SWING_MODES.get(int(swing_val), 'unknown')
        
        # Horizontal Swing (AC)
        hswing_val = get_v(['ssh', 'SwingStateHorizontal'])
        if hswing_val is not None:
            state['SwingStateHorizontal'] = int(hswing_val)
        
        # TstatMode for AC (maps to HVAC mode)
        tstat_val = get_v(['TstatMode'])
        if tstat_val is not None:
            state['TstatMode'] = int(tstat_val) if isinstance(tstat_val, (int, float)) else tstat_val
        
        # ACState object (contains mode, temp, fan, swing as numbered keys)
        acstate = state.get('ACState')
        if isinstance(acstate, dict):
            acstate_v = acstate.get('v', acstate)
            if isinstance(acstate_v, dict):
                # Extract values from ACState numbered keys
                if '1' in acstate_v:  # Power state
                    state['ACPower'] = int(acstate_v['1'])
                if '2' in acstate_v:  # Mode
                    state['ACMode'] = int(acstate_v['2'])
                if '3' in acstate_v:  # Temperature
                    state['ACTemp'] = float(acstate_v['3'])
                if '4' in acstate_v:  # Fan speed
                    if 'FanSpeed' not in state:
                        state['FanSpeed'] = int(acstate_v['4'])
                        state['FanMode'] = AC_FAN_MODES.get(int(acstate_v['4']), 'unknown')
                if '5' in acstate_v:  # Vertical swing
                    if 'SwingState' not in state:
                        state['SwingState'] = int(acstate_v['5'])
                        state['SwingMode'] = AC_SWING_MODES.get(int(acstate_v['5']), 'unknown')

    async def _get_signed_mqtt_url(self):
        """Get signed MQTT URL."""
        def _sign():
            # Proactively check and refresh Cognito tokens if expired
            try:
                self._user_obj.check_token()
            except Exception as e:
                _LOGGER.debug("Token refresh failed or not needed: %s", e)
                
            cred = self._user_obj.get_credentials(identity_pool_id=IDENTITY_POOL_ID)
            return sigv4_sign_mqtt_url(cred)
        return await self.hass.async_add_executor_job(_sign)

    async def _send_mqtt_command(self, device_id, payload, msg_type=44, src_type=100, wrap=True):
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
            
            if wrap:
                # Outer payload wrapper (Modern Envelope)
                outer_payload = {
                    "Timestamp": timestamp,
                    "body": payload,
                    "dest": {"ref": device_id, "type": 1},
                    "id": timestamp_ms,
                    "msg": msg_type,
                    "resp": 2,
                    "src": {"ref": self._user_id, "type": src_type},
                    "time": timestamp,
                    "ver": "1.0"
                }
            else:
                outer_payload = payload
            
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
                    connect_pkt = mqtt.connect(str(uuid1()), 60)
                    await ws.send(connect_pkt)
                    
                    # Wait for Connack
                    resp = await ws.recv()

                    # Subscribe to topics to establish "active" presence?
                    # liten_up subscribes to /out, /in, /batch
                    # Packet ID 1 for subscribe
                    sub_topics = [
                        mqtt.SubscriptionSpec(f'/v1/dev/{safe_device_id}/out', 0x01),
                        mqtt.SubscriptionSpec(f'/v1/dev/{safe_device_id}/in', 0x01),
                        mqtt.SubscriptionSpec(f'/v1/dev/{safe_device_id}/batch', 0x01)
                    ]
                    sub_pkt = mqtt.subscribe(1, sub_topics)
                    await ws.send(sub_pkt)
                    
                    # Wait for Suback
                    resp = await ws.recv()
                    
                    # Publish
                    _LOGGER.debug("Sending MQTT command to %s: %s", topic, json_payload)
                    # Packet ID 2 for publish
                    pub_pkt = mqtt.publish(topic, False, 1, False, packet_id=2, payload=json_payload.encode())
                    await ws.send(pub_pkt)
                    
                    # Wait for Puback
                    resp = await ws.recv()
                    _LOGGER.debug("Received response (likely PUBACK)")
                    
                    # Wait for device response (PUBLISH on /out)
                    # We give it a small timeout to not hang if the device is slow
                    try:
                         # Wait for up to 2 seconds for a response from the device
                         resp = await asyncio.wait_for(ws.recv(), timeout=2.0)
                         pkt = mqtt.parse_one(resp)
                         if isinstance(pkt, mqtt.PublishPacket):
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
                                   if 'dc' in state_update:
                                        state_update['Duty'] = state_update['dc']
                                   if 'rssi' in state_update:
                                        state_update['Rssi'] = state_update['rssi']
                                   if 'br' in state_update:
                                        state_update['Brightness'] = state_update['br']
                                   if 'lc' in state_update or 'lk' in state_update:
                                        state_update['Lock'] = state_update.get('lc', state_update.get('lk'))

                                   # Update our internal state cache for this device
                                   if device_id not in self.states:
                                        self.states[device_id] = state_update
                                   else:
                                        self.states[device_id].update(state_update)
                                        
                                   _LOGGER.debug("Updated state for %s from MQTT: %s", device_id, self.states[device_id])
                    except asyncio.TimeoutError:
                         _LOGGER.debug("Timed out waiting for device status response")
                    except Exception as e:
                         _LOGGER.debug("Error parsing device status response: %s", e)

                    # Sleep briefly to ensure server processes it before we disconnect?
                    await asyncio.sleep(0.5)
            except TypeError as te:
                # Fallback for older websockets versions that use extra_headers
                if 'additional_headers' in str(te):
                    _LOGGER.debug("Falling back to extra_headers for websockets compatibility")
                    async with websockets.connect(
                        ws_url,
                        subprotocols=['mqtt'],
                        ssl=ssl_context,
                        extra_headers=headers
                    ) as ws:
                        connect_pkt = mqtt.connect(str(uuid1()), 60)
                        await ws.send(connect_pkt)
                        resp = await ws.recv()
                        
                        sub_topics = [
                            mqtt.SubscriptionSpec(f'/v1/dev/{safe_device_id}/out', 0x01),
                            mqtt.SubscriptionSpec(f'/v1/dev/{safe_device_id}/in', 0x01),
                            mqtt.SubscriptionSpec(f'/v1/dev/{safe_device_id}/batch', 0x01)
                        ]
                        sub_pkt = mqtt.subscribe(1, sub_topics)
                        await ws.send(sub_pkt)
                        resp = await ws.recv()
                        
                        _LOGGER.debug("Sending MQTT command to %s: %s", topic, json_payload)
                        pub_pkt = mqtt.publish(topic, False, 1, False, packet_id=2, payload=json_payload.encode())
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
        # Temperature as float for 0.5 degree precision
        target_val = float(temperature)
        
        # Determine Payload Type based on Model
        payload_type = self._get_payload_type(device_id)
        _LOGGER.debug("Sending temp %s (type: %s) to device %s. Payload Type: %s", 
                     target_val, type(target_val), device_id, payload_type)
        # Proven payload structure from debug session
        body = {"cmd": [{"sp": target_val, "stpt": target_val, "a_sp": target_val, "tm": -1}], "type": payload_type, "ver": 1}
        await self._send_mqtt_command(device_id, body)
        await self.notify_settings_changed(device_id)
    
    def _get_payload_type(self, device_id):
        """Determine MQTT payload type based on device model."""
        # Force Type 5 for Manually Upgraded Lite Devices
        # Normalize for comparison (remove colons, lowercase)
        normalized_id = device_id.replace(":", "").lower()
        for upgraded_id in self.upgraded_lite_devices:
            if upgraded_id.replace(":", "").lower() == normalized_id:
                _LOGGER.info("Device %s is marked as Upgraded Lite - forcing type 5", device_id)
                return 5
            
        device = self.devices.get(device_id)
        if not device:
             return 1
             
        model = (device.get("Model") or device.get("ProductModel") or device.get("productModel") or "")
        fw = device.get("FirmwareVersion", "")
        
        # AC controllers use payload type 2
        if model.startswith("AC-"):
             return AC_PAYLOAD_TYPE
        
        if "BB-V2" in model or "V2" in model:
             if "Lite" in model or "-L" in model:
                  return 5
             return 4
        if "INF-V1" in model or "Floor" in model:
             return 3
        if "BB-V1" in model or "Baseboard" in model:
             return 1
             
        if "V2" in fw:
             return 4
        
        return 1

    def is_ac_device(self, device_id) -> bool:
        """Check if device is an AC controller."""
        device = self.devices.get(device_id, {})
        model = device.get("Model", "")
        return model.startswith("AC-")

    def get_ac_supported_caps(self, device_id) -> dict:
        """Get SupportedCaps for an AC device."""
        device = self.devices.get(device_id, {})
        return device.get("SupportedCaps", {})

    async def set_hvac_mode(self, device_id, hvac_mode):
        """Set HVAC mode via MQTT."""
        self._last_command_time[device_id] = time.time()
        mode_str = str(hvac_mode).lower()
        
        # Map Home Assistant HVAC mode to Mysa mode value
        if self.is_ac_device(device_id):
            # AC mode mapping
            if "off" in mode_str:
                mode_val = AC_MODE_OFF
            elif "cool" in mode_str:
                mode_val = AC_MODE_COOL
            elif "heat_cool" in mode_str or "auto" in mode_str:
                mode_val = AC_MODE_AUTO
            elif "heat" in mode_str:
                mode_val = AC_MODE_HEAT
            elif "dry" in mode_str:
                mode_val = AC_MODE_DRY
            elif "fan" in mode_str:
                mode_val = AC_MODE_FAN_ONLY
            else:
                mode_val = AC_MODE_OFF
        else:
            # Heating thermostat: only heat (3) or off (1)
            mode_val = 1 if "off" in mode_str else 3
        
        payload_type = self._get_payload_type(device_id)
        _LOGGER.debug("Using type %s for mode %s (val=%s)", payload_type, hvac_mode, mode_val)
        body = {"cmd": [{"md": mode_val, "tm": -1}], "type": payload_type, "ver": 1}
        await self._send_mqtt_command(device_id, body)
        await self.notify_settings_changed(device_id)

    async def set_ac_climate_plus(self, device_id, enabled: bool):
        """Set AC Climate+ (IsThermostatic) mode via MQTT.
        
        When enabled, Mysa uses its temperature sensor to control the AC.
        When disabled, it acts as a simple IR remote.
        """
        self._last_command_time[device_id] = time.time()
        it_val = 1 if enabled else 0
        
        payload_type = self._get_payload_type(device_id)
        _LOGGER.debug("Setting AC Climate+ to %s (val=%s)", enabled, it_val)
        body = {"cmd": [{"it": it_val, "tm": -1}], "type": payload_type, "ver": 1}
        await self._send_mqtt_command(device_id, body)
        
        # Optimistic update
        self._update_state_cache(device_id, {"IsThermostatic": {"v": it_val}, "it": it_val})
        await self.notify_settings_changed(device_id)


    async def set_ac_fan_speed(self, device_id, fan_mode: str):
        """Set AC fan speed via MQTT."""
        self._last_command_time[device_id] = time.time()
        
        # Convert HA fan mode name to Mysa value
        fan_val = AC_FAN_MODES_REVERSE.get(fan_mode.lower())
        if fan_val is None:
            _LOGGER.error("Unknown fan mode: %s", fan_mode)
            return
        
        payload_type = self._get_payload_type(device_id)
        _LOGGER.debug("Setting AC fan speed to %s (val=%s)", fan_mode, fan_val)
        body = {"cmd": [{"fn": fan_val, "tm": -1}], "type": payload_type, "ver": 1}
        await self._send_mqtt_command(device_id, body)
        
        # Optimistic update
        self._update_state_cache(device_id, {"FanSpeed": {"v": fan_val}, "fn": fan_val})
        await self.notify_settings_changed(device_id)

    async def set_ac_swing_mode(self, device_id, swing_mode: str):
        """Set AC vertical swing mode via MQTT."""
        self._last_command_time[device_id] = time.time()
        
        # Convert HA swing mode name to Mysa value
        swing_val = AC_SWING_MODES_REVERSE.get(swing_mode.lower())
        if swing_val is None:
            _LOGGER.error("Unknown swing mode: %s", swing_mode)
            return
        
        payload_type = self._get_payload_type(device_id)
        _LOGGER.debug("Setting AC vertical swing to %s (val=%s)", swing_mode, swing_val)
        body = {"cmd": [{"ss": swing_val, "tm": -1}], "type": payload_type, "ver": 1}
        await self._send_mqtt_command(device_id, body)
        
        # Optimistic update
        self._update_state_cache(device_id, {"SwingState": {"v": swing_val}, "ss": swing_val})
        await self.notify_settings_changed(device_id)

    async def set_ac_horizontal_swing(self, device_id, position: int):
        """Set AC horizontal swing position via MQTT."""
        self._last_command_time[device_id] = time.time()
        
        payload_type = self._get_payload_type(device_id)
        _LOGGER.debug("Setting AC horizontal swing to position %s", position)
        body = {"cmd": [{"ssh": position, "tm": -1}], "type": payload_type, "ver": 1}
        await self._send_mqtt_command(device_id, body)
        
        # Optimistic update
        self._update_state_cache(device_id, {"SwingStateHorizontal": {"v": position}, "ssh": position})
        await self.notify_settings_changed(device_id)

    async def set_lock(self, device_id, locked: bool):
        """Set thermostat button lock via MQTT + HTTP."""
        self._last_command_time[device_id] = time.time()
        lock_val = 1 if locked else 0
        payload_type = self._get_payload_type(device_id)
        # MQTT - instant device update
        body = {"cmd": [{"lk": lock_val, "tm": -1}], "type": payload_type, "ver": 1}
        await self._send_mqtt_command(device_id, body)
        # HTTP - sync cloud/app
        await self._set_device_setting_silent(device_id, {"Lock": lock_val})
        # Optimistic update
        self._update_state_cache(device_id, {"Lock": {"v": lock_val}})
        await self.notify_settings_changed(device_id)

    async def set_proximity(self, device_id, enabled: bool):
        """Set proximity mode (wake on approach) via MQTT + HTTP."""
        self._last_command_time[device_id] = time.time()
        pr_val = 1 if enabled else 0
        payload_type = self._get_payload_type(device_id)
        # MQTT - instant device update
        body = {"cmd": [{"pr": pr_val, "tm": -1}], "type": payload_type, "ver": 1}
        await self._send_mqtt_command(device_id, body)
        # HTTP - sync cloud/app
        await self._set_device_setting_silent(device_id, {"ProximityMode": enabled})
        # Optimistic update
        self._update_state_cache(device_id, {"ProximityMode": enabled})
        await self.notify_settings_changed(device_id)

    async def set_auto_brightness(self, device_id, enabled: bool):
        """Set auto brightness via MQTT + HTTP (V2)."""
        self._last_command_time[device_id] = time.time()
        payload_type = self._get_payload_type(device_id)
        br_obj = self._get_brightness_object(device_id)
        br_obj["a_b"] = 1 if enabled else 0
        # MQTT - instant device update
        body = {"cmd": [{"tm": -1, "br": br_obj}], "type": payload_type, "ver": 1}
        await self._send_mqtt_command(device_id, body)
        # HTTP - sync cloud/app
        await self._set_device_setting_silent(device_id, {"AutoBrightness": enabled})
        # Optimistic update
        self._update_state_cache(device_id, {"AutoBrightness": enabled})
        await self.notify_settings_changed(device_id)

    async def set_min_brightness(self, device_id, value: int):
        """Set idle (min) brightness via MQTT + HTTP (V2)."""
        self._last_command_time[device_id] = time.time()
        payload_type = self._get_payload_type(device_id)
        br_obj = self._get_brightness_object(device_id)
        br_obj["i_br"] = value
        # MQTT - instant device update
        body = {"cmd": [{"tm": -1, "br": br_obj}], "type": payload_type, "ver": 1}
        await self._send_mqtt_command(device_id, body)
        # HTTP - sync cloud/app
        await self._set_device_setting_silent(device_id, {"MinBrightness": value})
        # Optimistic update - update both top-level AND nested Brightness object
        self._update_brightness_cache(device_id, "i_br", value)
        self._update_state_cache(device_id, {"MinBrightness": value})
        await self.notify_settings_changed(device_id)

    async def set_max_brightness(self, device_id, value: int):
        """Set active (max) brightness via MQTT + HTTP (V2)."""
        self._last_command_time[device_id] = time.time()
        payload_type = self._get_payload_type(device_id)
        br_obj = self._get_brightness_object(device_id)
        br_obj["a_br"] = value
        # MQTT - instant device update
        body = {"cmd": [{"tm": -1, "br": br_obj}], "type": payload_type, "ver": 1}
        await self._send_mqtt_command(device_id, body)
        # HTTP - sync cloud/app
        await self._set_device_setting_silent(device_id, {"MaxBrightness": value})
        # Optimistic update - update both top-level AND nested Brightness object
        self._update_brightness_cache(device_id, "a_br", value)
        self._update_state_cache(device_id, {"MaxBrightness": value})
        await self.notify_settings_changed(device_id)

    def _get_brightness_object(self, device_id):
        """Build brightness object from current state, or defaults."""
        state = self.states.get(device_id, {})
        br = state.get("Brightness", {})
        if isinstance(br, dict):
            return {
                "a_b": br.get("a_b", 1),       # Auto brightness
                "a_br": br.get("a_br", 100),   # Active brightness
                "i_br": br.get("i_br", 50),    # Idle brightness
                "a_dr": br.get("a_dr", 60),    # Active duration
                "i_dr": br.get("i_dr", 30),    # Idle duration
            }
        # Fallback defaults for V1 or unknown structure
        return {"a_b": 1, "a_br": 100, "i_br": 50, "a_dr": 60, "i_dr": 30}

    def _update_state_cache(self, device_id, updates: dict):
        """Optimistically update local state cache after MQTT command."""
        if device_id not in self.states:
            self.states[device_id] = {}
        self.states[device_id].update(updates)
        _LOGGER.debug("Optimistic state update for %s: %s", device_id, updates)

    def _update_brightness_cache(self, device_id, key, value):
        """Update nested Brightness object in state cache."""
        if device_id not in self.states:
            self.states[device_id] = {}
        if "Brightness" not in self.states[device_id]:
            self.states[device_id]["Brightness"] = self._get_brightness_object(device_id)
        if isinstance(self.states[device_id]["Brightness"], dict):
            self.states[device_id]["Brightness"][key] = value
        _LOGGER.debug("Brightness cache update for %s: %s=%s", device_id, key, value)

    async def _set_device_setting_silent(self, device_id, settings: dict):
        """Set device settings via HTTP POST without triggering coordinator refresh."""
        def do_post():
            url = f"{BASE_URL}/devices/{device_id}"
            r = self._session.post(url, json=settings)
            r.raise_for_status()
            return r.json()
        
        try:
            result = await self.hass.async_add_executor_job(do_post)
            _LOGGER.debug("HTTP sync for %s: %s -> %s", device_id, settings, result)
        except Exception as e:
            _LOGGER.warning("HTTP sync failed for %s: %s (MQTT already sent)", device_id, e)
            # Don't raise - MQTT already handled the device update

    async def _set_device_setting(self, device_id, settings: dict):
        """Set device settings via HTTP POST."""
        def do_post():
            url = f"{BASE_URL}/devices/{device_id}"
            r = self._session.post(url, json=settings)
            r.raise_for_status()
            return r.json()
        
        try:
            result = await self.hass.async_add_executor_job(do_post)
            _LOGGER.debug("Set device %s settings %s: %s", device_id, settings, result)
            # Update local state cache
            if device_id in self.states:
                self.states[device_id].update(settings)
            # Trigger coordinator refresh
            if self.coordinator_callback:
                await self.coordinator_callback()
        except Exception as e:
            _LOGGER.error("Failed to set device %s settings: %s", device_id, e)
            raise

    async def notify_settings_changed(self, device_id):
        """Notify the thermostat to check its settings via MQTT (MsgType 6)."""
        timestamp = int(time.time())
        body = {
            "Device": device_id.upper(),
            "EventType": 0,
            "MsgType": 6,
            "Timestamp": timestamp
        }
        await self._send_mqtt_command(device_id, body, msg_type=6, wrap=False)

    async def start_mqtt_listener(self):
        """Start the persistent MQTT listener for real-time device updates."""
        if self._mqtt_listener_task is not None:
            _LOGGER.debug("MQTT listener already running")
            return
        
        self._mqtt_should_reconnect = True
        self._mqtt_listener_task = asyncio.create_task(self._mqtt_listener_loop())
        _LOGGER.info("Started MQTT listener task")

    async def stop_mqtt_listener(self):
        """Stop the persistent MQTT listener."""
        self._mqtt_should_reconnect = False
        
        if self._mqtt_listener_task:
            self._mqtt_listener_task.cancel()
            try:
                await self._mqtt_listener_task
            except asyncio.CancelledError:
                pass
            self._mqtt_listener_task = None
        
        if self._mqtt_ws:
            try:
                # Send MQTT DISCONNECT packet before closing
                disconnect_pkt = mqtt.disconnect()
                await self._mqtt_ws.send(disconnect_pkt)
                await self._mqtt_ws.close()
            except Exception:
                pass
            self._mqtt_ws = None
        
        self._mqtt_connected.clear()
        _LOGGER.info("Stopped MQTT listener")

    async def _mqtt_listener_loop(self):
        """Main MQTT listener loop with automatic reconnection."""
        reconnect_delay = self._mqtt_reconnect_delay
        
        while self._mqtt_should_reconnect:
            try:
                await self._mqtt_listen()
                # If we get here, connection closed normally
                _LOGGER.info("MQTT connection closed normally")
                reconnect_delay = self._mqtt_reconnect_delay  # Reset delay
            except asyncio.CancelledError:
                _LOGGER.debug("MQTT listener task cancelled")
                raise
            except Exception as e:
                # Expected disconnections (keepalive timeout) are normal - log at debug level
                _LOGGER.debug("MQTT connection lost: %s, reconnecting in %ds", e, reconnect_delay)
                self._mqtt_connected.clear()
                await asyncio.sleep(reconnect_delay)
                # Exponential backoff up to 60 seconds
                reconnect_delay = min(reconnect_delay * 2, 60)

    async def _mqtt_listen(self):
        """Establish MQTT connection and listen for device updates."""
        # Helper function to parse MQTT packets
        def parse_mqtt_packet(data):
            if not isinstance(data, bytearray):
                data = bytearray(data)
            msgs = []
            mqtt.parse(data, msgs)
            return msgs[0] if msgs else None
        
        # Get signed URL
        signed_url = await self._get_signed_mqtt_url()
        url_parts = urlparse(signed_url)
        ws_url = url_parts._replace(scheme='wss').geturl()
        
        _LOGGER.info("Connecting to MQTT for persistent listening...")
        
        # Create SSL context
        ssl_context = await self.hass.async_add_executor_job(ssl.create_default_context)
        headers = {'user-agent': 'okhttp/4.11.0'}
        
        # Connect with proper error handling for websockets version
        # Disable websockets' built-in ping/pong since we handle keepalive via MQTT PINGREQ/PINGRESP
        try:
            ws = await websockets.connect(
                ws_url,
                subprotocols=['mqtt'],
                ssl=ssl_context,
                additional_headers=headers,
                ping_interval=None,  # Disable WebSocket pings
                ping_timeout=None    # Disable WebSocket ping timeout
            )
        except TypeError:
            # Fallback for older websockets versions
            ws = await websockets.connect(
                ws_url,
                subprotocols=['mqtt'],
                ssl=ssl_context,
                extra_headers=headers,
                ping_interval=None,
                ping_timeout=None
            )
        
        self._mqtt_ws = ws
        
        try:
            # MQTT Connect
            connect_pkt = mqtt.connect(str(uuid1()), 60)
            await ws.send(connect_pkt)
            
            # Wait for Connack
            resp = await ws.recv()
            pkt = parse_mqtt_packet(resp)
            if not isinstance(pkt, mqtt.ConnackPacket):
                raise RuntimeError(f"Expected CONNACK, got {pkt}")
            
            _LOGGER.info("MQTT connected successfully")
            
            # Subscribe to all device topics
            if not self.devices:
                await self.get_devices()
            
            sub_topics = []
            for device_id in self.devices:
                safe_device_id = device_id.replace(":", "").lower()
                sub_topics.extend([
                    mqtt.SubscriptionSpec(f'/v1/dev/{safe_device_id}/out', 0x01),
                    mqtt.SubscriptionSpec(f'/v1/dev/{safe_device_id}/in', 0x01),
                    mqtt.SubscriptionSpec(f'/v1/dev/{safe_device_id}/batch', 0x01)
                ])
            
            if sub_topics:
                sub_pkt = mqtt.subscribe(1, sub_topics)
                await ws.send(sub_pkt)
                
                # Wait for Suback
                resp = await ws.recv()
                pkt = parse_mqtt_packet(resp)
                if not isinstance(pkt, mqtt.SubackPacket):
                    raise RuntimeError(f"Expected SUBACK, got {pkt}")
                
                _LOGGER.info("Subscribed to %d device topics", len(self.devices))
            
            self._mqtt_connected.set()
            
            # Main message loop with proactive keepalive
            last_ping = time.time()
            ping_interval = 25  # Send ping every 25 seconds (less than 60s keepalive)
            
            _LOGGER.info("MQTT message loop started, waiting for updates...")
            
            while True:
                try:
                    # Calculate time until next ping
                    elapsed = time.time() - last_ping
                    time_until_ping = max(0.1, ping_interval - elapsed)
                    
                    # Wait for message with timeout set to next ping time
                    msg = await asyncio.wait_for(ws.recv(), timeout=min(time_until_ping, 20.0))
                    
                    try:
                        pkt = parse_mqtt_packet(msg)
                        
                        if isinstance(pkt, mqtt.PublishPacket):
                            # Process device state update
                            await self._process_mqtt_publish(pkt)
                        elif hasattr(pkt, 'pkt_type') and pkt.pkt_type == mqtt.MQTT_PACKET_PINGRESP:
                            _LOGGER.debug("Received PINGRESP")
                        elif pkt:
                            _LOGGER.debug("Received MQTT packet type: %s", type(pkt).__name__)
                    except Exception as parse_error:
                        _LOGGER.warning("Error parsing MQTT packet: %s", parse_error, exc_info=True)
                        # Continue despite parse errors
                    
                except asyncio.TimeoutError:
                    # Timeout is normal - we use it to check if ping is needed
                    pass
                except Exception as recv_error:
                    _LOGGER.error("Error receiving MQTT message: %s", recv_error, exc_info=True)
                    raise  # Re-raise to trigger reconnection
                
                # Send ping if needed (proactive keepalive)
                if time.time() - last_ping >= ping_interval:
                    try:
                        await ws.send(mqtt.pingreq())
                        last_ping = time.time()
                        _LOGGER.debug("Sent PINGREQ keepalive")
                    except Exception as e:
                        _LOGGER.error("Failed to send keepalive ping: %s", e, exc_info=True)
                        raise  # Re-raise to trigger reconnection
                        
        except Exception as listen_error:
            _LOGGER.debug("MQTT listen error (will reconnect): %s", listen_error, exc_info=True)
            raise
        finally:
            self._mqtt_ws = None
            self._mqtt_connected.clear()
            try:
                await ws.close()
            except Exception:
                pass

    async def _process_mqtt_publish(self, pkt):
        """Process an MQTT publish packet containing device state update."""
        try:
            payload = json.loads(pkt.payload)
            
            # Extract device ID from topic: /v1/dev/{device_id}/out
            topic_parts = pkt.topic.split('/')
            if len(topic_parts) >= 4:
                safe_device_id = topic_parts[3]
                # Convert back to format with colons (find matching device)
                device_id = None
                for did in self.devices:
                    if did.replace(":", "").lower() == safe_device_id:
                        device_id = did
                        break
                
                if not device_id:
                    _LOGGER.debug("Received MQTT message for unknown device: %s", safe_device_id)
                    return
                
                # Process message types 40 (state update) and 44 (command response)
                msg_type = payload.get('msg')
                if msg_type in [40, 44]:
                    body = payload.get('body', {})
                    state_update = body.get('state', body)
                    
                    if state_update:
                        # Normalize the state data
                        self._normalize_state(state_update)
                        
                        # Update internal state cache
                        if device_id not in self.states:
                            self.states[device_id] = state_update
                        else:
                            self.states[device_id].update(state_update)
                        
                        _LOGGER.info("MQTT state update for %s: %s", device_id, state_update)
                        
                        # Trigger coordinator refresh to update HA entities
                        if self.coordinator_callback:
                            await self.coordinator_callback()
                
        except Exception as e:
            _LOGGER.error("Error processing MQTT publish: %s", e, exc_info=True)


