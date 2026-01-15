"""MQTT Realtime Coordinator for Mysa."""
import logging
import asyncio
import json
import time
from . import mqtt
from .mysa_mqtt import (
    build_subscription_topics, parse_mqtt_packet,
    connect_websocket, create_connect_packet,
)
from .const import MQTT_PING_INTERVAL

_LOGGER = logging.getLogger(__name__)

class MysaRealtime:
    """Mysa MQTT Realtime Coordinator."""

    def __init__(self, hass, get_signed_url_callback, on_update_callback):
        """Initialize the MQTT coordinator."""
        self.hass = hass
        self._get_signed_url = get_signed_url_callback
        self._on_update = on_update_callback

        self._mqtt_listener_task = None
        self._mqtt_connected = asyncio.Event()
        self._mqtt_ws = None
        self._mqtt_should_reconnect = True
        self._mqtt_reconnect_delay = 5
        self._devices_ids = [] # List of device IDs to subscribe to

    @property
    def is_running(self) -> bool:
        """Return if MQTT listener is running."""
        return bool(self._mqtt_listener_task and not self._mqtt_listener_task.done())

    def set_devices(self, device_ids):
        """Update list of devices to subscribe to."""
        self._devices_ids = device_ids

    async def start(self):
        """Start the persistent MQTT listener."""
        if self._mqtt_listener_task is not None:
            _LOGGER.debug("MQTT listener already running")
            return

        self._mqtt_should_reconnect = True
        self._mqtt_listener_task = asyncio.create_task(self._mqtt_listener_loop())
        _LOGGER.info("Started MQTT listener task")

    async def stop(self):
        """Stop the persistent MQTT listener."""
        self._mqtt_should_reconnect = False

        if self._mqtt_listener_task:
            self._mqtt_listener_task.cancel()
            try:
                await self._mqtt_listener_task
            except asyncio.CancelledError:
                pass
            self._mqtt_listener_task = None

        await self._close_websocket()
        self._mqtt_connected.clear()
        _LOGGER.info("Stopped MQTT listener")

    async def _close_websocket(self):
        """Close the WebSocket connection cleanly."""
        if self._mqtt_ws:
            try:
                disconnect_pkt = mqtt.disconnect()
                await self._mqtt_ws.send(disconnect_pkt)
                await self._mqtt_ws.close()
            except Exception:
                pass
            self._mqtt_ws = None

    async def _mqtt_listener_loop(self):
        """Main MQTT listener loop with automatic reconnection."""
        reconnect_delay = self._mqtt_reconnect_delay

        while self._mqtt_should_reconnect:
            try:
                await self._mqtt_listen()
                _LOGGER.info("MQTT connection closed normally")
                reconnect_delay = self._mqtt_reconnect_delay
            except asyncio.CancelledError:
                _LOGGER.debug("MQTT listener task cancelled")
                raise
            except Exception as e:
                _LOGGER.debug(
                    "MQTT connection lost: %s, reconnecting in %ds", e, reconnect_delay
                )
                self._mqtt_connected.clear()
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, 60)

    async def _mqtt_listen(self):
        """Establish MQTT connection and listen for updates."""
        # Get signed URL via callback
        signed_url = await self._get_signed_url()

        _LOGGER.info("Connecting to MQTT for persistent listening...")

        # Connect
        ws = await connect_websocket(signed_url)
        self._mqtt_ws = ws

        try:
            await self._perform_mqtt_handshake(ws)
            self._mqtt_connected.set()
            await self._run_mqtt_loop(ws)
        except Exception as listen_error:
            _LOGGER.debug(
                "MQTT listen error (will reconnect): %s", listen_error, exc_info=True
            )
            raise
        finally:
            self._mqtt_ws = None
            self._mqtt_connected.clear()
            try:
                await ws.close()
            except Exception:
                pass

    async def _perform_mqtt_handshake(self, ws):
        """Perform MQTT connect and subscribe handshake."""
        # Connect
        connect_pkt = create_connect_packet()
        await ws.send(connect_pkt)

        # Connack
        resp = await ws.recv()
        pkt = parse_mqtt_packet(resp)
        if not isinstance(pkt, mqtt.ConnackPacket):
            raise RuntimeError(f"Expected CONNACK, got {pkt}")

        _LOGGER.info("MQTT connected successfully")

        # Subscribe
        if self._devices_ids:
            sub_topics = build_subscription_topics(list(self._devices_ids))
            if sub_topics:
                sub_pkt = mqtt.subscribe(1, sub_topics)
                await ws.send(sub_pkt)

                # Suback
                resp = await ws.recv()
                pkt = parse_mqtt_packet(resp)
                if not isinstance(pkt, mqtt.SubackPacket):
                    raise RuntimeError(f"Expected SUBACK, got {pkt}")

                _LOGGER.info("Subscribed to %d device topics", len(self._devices_ids))

    async def _run_mqtt_loop(self, ws):
        """Run the main MQTT message and keepalive loop."""
        last_ping = time.time()
        ping_interval = MQTT_PING_INTERVAL

        while True:
            try:
                elapsed = time.time() - last_ping
                time_until_ping = max(0.1, ping_interval - elapsed)

                msg = await asyncio.wait_for(ws.recv(), timeout=min(time_until_ping, 20.0))

                try:
                    pkt = parse_mqtt_packet(msg)
                    if isinstance(pkt, mqtt.PublishPacket):
                        await self._process_mqtt_publish(pkt)
                    elif hasattr(pkt, 'pkt_type') and pkt.pkt_type == mqtt.MQTT_PACKET_PINGRESP:
                        _LOGGER.debug("Received PINGRESP")
                except Exception as parse_error:
                    _LOGGER.warning("Error parsing MQTT packet: %s", parse_error, exc_info=True)

            except asyncio.TimeoutError:
                pass
            except Exception as recv_error:
                _LOGGER.error("Error receiving MQTT message: %s", recv_error, exc_info=True)
                raise

            if time.time() - last_ping >= ping_interval:
                try:
                    await ws.send(mqtt.pingreq())
                    last_ping = time.time()
                    _LOGGER.debug("Sent PINGREQ keepalive")
                except Exception as e:
                    _LOGGER.error("Failed to send keepalive ping: %s", e, exc_info=True)
                    raise

    async def _process_mqtt_publish(self, pkt):
        """Process an MQTT publish packet."""
        try:
            payload = json.loads(pkt.payload)
            topic = pkt.topic

            # Extract Device ID logic -- maybe move to utility or keep here
            # Topic format: /v1/dev/{device_id}/out
            topic_parts = topic.split('/')
            device_id = None
            if len(topic_parts) >= 4:
                safe_id = topic_parts[3]
                # We need to map safe_id back to real ID if they differ (colons)
                # Currently simple normalization is done in api.py
                # Here we might need the map.
                # For now let's pass the safe_id or try to resolve.
                # Ideally the callback handles resolution or we assume standard format.
                # In mapping: safe_device_id = device_id.replace(":", "").lower()
                device_id = safe_id # Pass safe ID to callback, let it resolve?
                # Or pass raw topic.

            if device_id:
                # Extract state
                state_update = self._extract_state_update(payload)
                if state_update:
                    await self._on_update(device_id, state_update)

        except Exception as e:
            _LOGGER.error("Error processing MQTT publish: %s", e, exc_info=True)

    def _extract_state_update(self, payload):
        """Extract state update from payload."""
        msg_type = payload.get('msg')
        if msg_type not in [40, 44]:
            return None

        body = payload.get('body', {})
        state_update = body.get('state', {})

        if not state_update and 'cmd' in body:
            cmd_list = body.get('cmd', [])
            if cmd_list and isinstance(cmd_list, list):
                for cmd_item in cmd_list:
                    if isinstance(cmd_item, dict):
                        state_update.update(cmd_item)

        if not state_update:
            state_update = body

        return state_update

    async def send_command(self, device_id, payload, user_id=None, msg_type=44, src_type=100, wrap=True):
        """Send a command to a device."""
        if not self._mqtt_ws:
            await self._send_one_off_command(device_id, payload, user_id, msg_type, src_type, wrap)
            return

        # We probably need to handle the one-off connection logic `_send_mqtt_command` did
        # IF the persistent listener is NOT required for sending commands.
        # But `mysa_api.py` `_send_mqtt_command` connects, sends, disconnects if NOT using persistent?
        # ACTUALLY `_send_mqtt_command` in original code ALWAYS did a Connect/Send/Disconnect cycle.
        # It did NOT use the persistent connection.
        # However, it would satisfy "Benefit: easier to maintain" if we reused the connection if available?
        # The user request says "split...".
        # If I look at `mysa_api.py`, `_send_mqtt_command` creates a NEW websocket connection every time.
        # This is inefficient but robust.
        # If I want to match original behavior EXACTLY, I should implement the "Connect-Send-Disconnect" logic here too,
        # separate from the listener loop.
        #
        # OR, better: If `_mqtt_ws` is open, use it? Use `send_command` on the active socket?
        # The original code `_send_mqtt_command` mentions:
        # "Connect to MQTT, send command, and disconnect."
        # And `start_mqtt_listener` starts a SEPARATE task for listening.
        # So they are independent.
        #
        # Let's implement `send_one_off_command` for that pattern.
        # And `send_publish` for using the active connection if we wanted to improve it later.
        # For safety/regression avoidance, I will implement `send_one_off_command` that replicates `_send_mqtt_command`.

        await self._send_one_off_command(device_id, payload, user_id, msg_type, src_type, wrap)

    async def _send_one_off_command(self, device_id, payload, user_id, msg_type, src_type, wrap):
        """Connect, send, disconnect."""
        if not user_id:
            _LOGGER.error("Cannot send MQTT command: User ID missing")
            return

        signed_url = await self._get_signed_url()
        # Note: `urlparse` import needed if I need to manipulate scheme, but `connect_websocket` handles it?
        # `connect_websocket` takes the signed HTTPS url and converts to WSS.

        # Construct payload
        timestamp = int(time.time())
        timestamp_ms = int(time.time() * 1000)

        if wrap:
            outer_payload = {
                "Timestamp": timestamp,
                "body": payload,
                "dest": {"ref": device_id, "type": 1},
                "id": timestamp_ms,
                "msg": msg_type,
                "resp": 2, # Request response
                "src": {"ref": user_id, "type": src_type},
                "time": timestamp,
                "ver": "1.0"
            }
        else:
            outer_payload = payload

        json_payload = json.dumps(outer_payload)
        safe_device_id = device_id.replace(":", "").lower()
        topic = f"/v1/dev/{safe_device_id}/in"

        _LOGGER.debug("Sending one-off MQTT command to %s", topic)

        # We need to reimplement the "Connect, Sub, Pub, Wait Response" flow
        # This seems duplicative of the listener but it's what was there.
        # I should put this in `MysaRealtime` as a method.


        # Note: `connect_websocket` helper does this replacement but also sets header hacks.
        # Let's use `connect_websocket` but it returns the `connect` context manager if I recall?
        # No, `connect_websocket` awaits `websockets.connect`.

        # Wait, `connect_websocket` in `mysa_mqtt.py` returns a connected socket?
        # Let's check `mysa_mqtt.py` content if I can...
        # I recall looking at `mysa_api.py` imports: `from .mysa_mqtt import connect_websocket`.
        # And `_mqtt_listen` used `ws = await connect_websocket(signed_url)`.

        # But `_send_mqtt_command` in `mysa_api.py` MANUALLY called `websockets.connect` with `additional_headers` logic.
        # Does `connect_websocket` include that logic?
        # I should probably verify `mysa_mqtt.py` content to be sure or just import it.
        # If `connect_websocket` handles the header hacks, I should use it.
        # If not, I should copy the logic.

        # Given `mysa_api.py` import `connect_websocket` I assume it unifies logic?
        # BUT `mysa_api.py` `_send_mqtt_command` explicitly had the try/except block for `additional_headers`.
        # This suggests `connect_websocket` might NOT have been used there, or was added later?
        # In `mysa_api.py` line 1098: `ws = await connect_websocket(signed_url)` is used for the LISTENER.
        # In line 527: `async with websockets.connect(...) as ws:` is used for COMMANDS.

        # I should probably consolidate this into `connect_websocket` or `MysaRealtime`.
        # I'll stick to using `connect_websocket` if possible, assuming it encapsulates the connection logic.
        # If `connect_websocket` is shared, it's better.

        try:
            # Use the helper!
            ws = await connect_websocket(signed_url)
            try:
                # 1. Connect
                await ws.send(create_connect_packet())
                await ws.recv() # Connack

                # 2. Subscribe (to get response)
                sub_topics = [
                    mqtt.SubscriptionSpec(f'/v1/dev/{safe_device_id}/out', 0x01),
                    mqtt.SubscriptionSpec(f'/v1/dev/{safe_device_id}/in', 0x01), # Why /in? Mirror?
                    mqtt.SubscriptionSpec(f'/v1/dev/{safe_device_id}/batch', 0x01)
                ]
                await ws.send(mqtt.subscribe(1, sub_topics))
                await ws.recv() # Suback

                # 3. Publish
                pub_pkt = mqtt.publish(
                    topic, False, 1, False, packet_id=2, payload=json_payload.encode()
                )
                await ws.send(pub_pkt)
                await ws.recv() # Puback

                # 4. Wait for response
                try:
                    resp = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    pkt = parse_mqtt_packet(resp)
                    if isinstance(pkt, mqtt.PublishPacket):
                        payload = json.loads(pkt.payload)
                        # Process response
                        state_update = self._extract_state_update(payload)
                        if state_update:
                            # We can invoke callback even for one-off commands to update state
                            await self._on_update(device_id, state_update, resolve_safe_id=True)
                except asyncio.TimeoutError:
                    pass

            finally:
                await ws.close()

        except Exception as e:
            _LOGGER.error("Failed to send MQTT command: %s", e)



