"""MQTT Realtime Coordinator for Mysa."""
import logging
import asyncio
import json
import time
from typing import Any, Callable, Dict, List, Optional, cast
from homeassistant.core import HomeAssistant

from . import mqtt
from .mysa_mqtt import (
    build_subscription_topics, parse_mqtt_packet,
    connect_websocket, create_connect_packet,
)
from .const import MQTT_PING_INTERVAL

# Type hint for callback
# on_update_callback(device_id, state_update, resolve_safe_id=False)
UpdateCallback = Callable[[str, Dict[str, Any], Optional[bool]], Any]
SignedUrlCallback = Callable[[], Any]

_LOGGER = logging.getLogger(__name__)


class MysaRealtime:
    """Mysa MQTT Realtime Coordinator."""
    # pylint: disable=too-many-instance-attributes
    # Justification: Class maintains complex MQTT state and connection parameters.

    def __init__(
        self,
        hass: HomeAssistant,
        get_signed_url_callback: SignedUrlCallback,
        on_update_callback: UpdateCallback
    ) -> None:
        """Initialize the MQTT coordinator."""
        self.hass = hass
        self._get_signed_url = get_signed_url_callback
        self._on_update = on_update_callback

        self._mqtt_listener_task: Optional[asyncio.Task[None]] = None
        self._mqtt_connected = asyncio.Event()
        self._mqtt_ws: Any = None  # ws object from `connect_websocket`
        self._mqtt_should_reconnect = True
        self._mqtt_reconnect_delay = 1.0
        self._devices_ids: List[str] = []  # List of device IDs to subscribe to

    @property
    def is_running(self) -> bool:
        """Return if MQTT listener is running."""
        return bool(self._mqtt_listener_task and not self._mqtt_listener_task.done())

    async def wait_until_connected(self, timeout: float = 10.0) -> bool:
        """Wait for MQTT connection to be established."""
        try:
            await asyncio.wait_for(self._mqtt_connected.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    def set_devices(self, device_ids: List[str]) -> None:
        """Update list of devices to subscribe to."""
        self._devices_ids = device_ids

    async def start(self) -> None:
        """Start the persistent MQTT listener."""
        if self._mqtt_listener_task is not None:
            _LOGGER.debug("MQTT listener already running")
            return

        self._mqtt_should_reconnect = True
        self._mqtt_listener_task = asyncio.create_task(self._mqtt_listener_loop())
        _LOGGER.info("Started MQTT listener task")

    async def stop(self) -> None:
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

    async def _close_websocket(self) -> None:
        """Close the WebSocket connection cleanly."""
        if self._mqtt_ws:
            try:
                disconnect_pkt = mqtt.disconnect()
                await self._mqtt_ws.send(disconnect_pkt)
                await self._mqtt_ws.close()
            except Exception:
                pass
            self._mqtt_ws = None

    async def _mqtt_listener_loop(self) -> None:
        """Main MQTT listener loop with automatic reconnection."""
        reconnect_delay = self._mqtt_reconnect_delay
        prev_delay = 0.0
        first_failure_logged = False

        while self._mqtt_should_reconnect:
            try:
                await self._mqtt_listen()
                _LOGGER.info("MQTT connection closed normally")
                reconnect_delay = self._mqtt_reconnect_delay
                prev_delay = 0.0
                first_failure_logged = False  # Reset on normal closure (if ever)
            except asyncio.CancelledError:
                _LOGGER.debug("MQTT listener task cancelled")
                raise
            except Exception as e:  # pylint: disable=broad-except
                # Justification: Catch-all to ensure the listener loop keeps running despite
                # unexpected errors.
                if not first_failure_logged:
                    _LOGGER.warning(
                        "MQTT connection lost: %s. Will retry in background (reconnecting in %ds)",
                        e,
                        int(reconnect_delay),
                    )
                    first_failure_logged = True
                else:
                    _LOGGER.debug(
                        "MQTT connection lost: %s, reconnecting in %ds", e, int(reconnect_delay)
                    )

                self._mqtt_connected.clear()
                await asyncio.sleep(reconnect_delay)

                # Fibonacci backoff
                next_delay = reconnect_delay + (prev_delay if 'prev_delay' in locals() else 0)
                prev_delay = reconnect_delay
                reconnect_delay = min(next_delay, 60.0)

    async def _mqtt_listen(self) -> None:
        """Establish MQTT connection and listen for updates."""
        # Get signed URL via callback
        signed_url = await self._get_signed_url()

        # If we are here, we are attempting to connect.
        _LOGGER.debug("Connecting to MQTT for persistent listening...")

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
            # Make sure we re-raise so the loop handles retry logic
            raise listen_error
        finally:
            self._mqtt_ws = None
            self._mqtt_connected.clear()
            try:
                await ws.close()
            except Exception:
                pass

    async def _perform_mqtt_handshake(self, ws: Any) -> None:
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

    async def _run_mqtt_loop(self, ws: Any) -> None:
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
                    if pkt:
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

    async def _process_mqtt_publish(self, pkt: Any) -> None:
        """Process an MQTT publish packet."""
        try:
            payload = json.loads(pkt.payload, strict=False)
            topic = pkt.topic

            # Extract Device ID logic -- maybe move to utility or keep here
            # Topic format: /v1/dev/{device_id}/out
            topic_parts = topic.split('/')
            device_id = None
            if len(topic_parts) >= 4:
                safe_id = topic_parts[3]
                # We need to map safe_id back to real ID if they differ (colons)
                # Currently simple normalization is done in api.py.
                # Here we default to safe_id.
                device_id = safe_id

            if device_id:
                # Extract state
                state_update = self._extract_state_update(payload)
                if state_update:
                    await self._on_update(device_id, state_update, True)

        except Exception as e:
            _LOGGER.error("Error processing MQTT publish: %s", e, exc_info=True)

    def _extract_state_update(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract state update from payload."""
        msg_type_raw = payload.get('msg') or payload.get('MsgType')
        try:
            msg_type = int(msg_type_raw) if msg_type_raw is not None else None
        except (ValueError, TypeError):
            msg_type = None

        if msg_type == 10:
            return self._extract_boot_info(payload)
        if msg_type == 4:
            return self._extract_log_info(payload)
        if msg_type == 61:
            return {"FirmwareVersion": str(payload.get("version", ""))}

        msg_ts = payload.get('time') or payload.get('Timestamp')
        update: Dict[str, Any] = {}

        if msg_type == 30 and payload.get('body'):
            update = self._extract_body_state(payload['body']) or {}
        else:
            body = payload.get('body')
            if body:
                update = self._extract_body_state(body) or {}

        # Timestamp and metadata
        if msg_ts:
            try:
                update['Timestamp'] = int(msg_ts)
            except (ValueError, TypeError):
                pass

        # Merge top-level metadata
        if (ip := payload.get('ip')) and 'ip' not in update:
            update['ip'] = ip
        if not update.get('FirmwareVersion'):
            if (ver := payload.get('version') or payload.get('ver')):
                update['FirmwareVersion'] = str(ver)

        return update if update else None

    def _extract_boot_info(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Extract info from MsgType 10."""
        update = {}
        if payload.get('ip'):
            update['ip'] = payload.get('ip')
        if payload.get('version'):
            update['FirmwareVersion'] = str(payload.get('version'))
        elif payload.get('ver'):
            update['FirmwareVersion'] = str(payload.get('ver'))

        return update

    def _extract_log_info(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract info from MsgType 4."""
        message = payload.get('Message', '')
        update = {}
        if "Local IP:" in message:
            temp = message.split("Local IP:")[-1]
            if "Device Serial:" in temp:
                temp = temp.split("Device Serial:")[0]
            update["ip"] = temp.strip()
        if "Device Serial:" in message:
            temp = message.split("Device Serial:")[-1]
            if "Local IP:" in temp:
                temp = temp.split("Local IP:")[0]
            update["serial_number"] = temp.strip()

        return update if update else None

    def _extract_body_state(self, body: Any) -> Optional[Dict[str, Any]]:
        """Extract state from body."""
        if not isinstance(body, dict):
            return None

        state_update = body.get('state', {})
        if state_update:
            return cast(Dict[str, Any], state_update)

        cmd_list = body.get('cmd')
        if isinstance(cmd_list, list):
            combined = {}
            for item in cmd_list:
                if isinstance(item, dict):
                    combined.update(item)
            return combined

        # Fallback: if no state/cmd, use body itself
        return cast(Dict[str, Any], body)

    async def send_command(
        self,
        device_id: str,
        payload: Dict[str, Any],
        user_id: Optional[str] = None,
        msg_type: int = 44,
        src_type: int = 100,
        wrap: bool = True
    ) -> None:
        """Send a command to a device."""
        if not user_id:
            _LOGGER.error("Cannot send MQTT command: User ID missing")
            return

        # If we have a persistent connection, use it!
        if self._mqtt_ws:
            _LOGGER.debug("Sending MQTT command via persistent connection to %s", device_id)
            try:
                # 1. Prepare message
                timestamp = int(time.time())
                timestamp_ms = int(time.time() * 1000)

                if wrap:
                    outer_payload = {
                        "Timestamp": timestamp,
                        "body": payload,
                        "dest": {"ref": device_id, "type": 1},
                        "id": timestamp_ms,
                        "msg": msg_type,
                        "resp": 2,  # Request response
                        "src": {"ref": user_id, "type": src_type},
                        "time": timestamp,
                        "ver": "1.0"
                    }
                else:
                    outer_payload = payload

                json_payload = json.dumps(outer_payload)
                safe_device_id = device_id.replace(":", "").lower()
                topic = f"/v1/dev/{safe_device_id}/in"

                # 2. Publish
                # Note: We use QoS 1 for commands to ensure delivery
                pub_pkt = mqtt.publish(
                    topic, False, 1, False, packet_id=7, payload=json_payload.encode()
                )
                await self._mqtt_ws.send(pub_pkt)
                return  # Success
            except Exception as e:
                _LOGGER.warning(
                    "Failed to send via persistent connection, falling back to one-off: %s", e
                )
                # Fall through to one-off fallback

        # Fallback to one-off
        await self._send_one_off_command(device_id, payload, user_id, msg_type, src_type, wrap)

    async def _send_one_off_command(
        self,
        device_id: str,
        payload: Dict[str, Any],
        user_id: Optional[str],
        msg_type: int,
        src_type: int,
        wrap: bool
    ) -> None:
        # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
        # Justification: Internal helper method requiring all connection parameters.
        """Connect, send, disconnect."""
        if not user_id:
            _LOGGER.error("Cannot send MQTT command: User ID missing")
            return

        signed_url = await self._get_signed_url()

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
                "resp": 2,  # Request response
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

        try:
            ws = await connect_websocket(signed_url)
            try:
                # 1. Connect
                await ws.send(create_connect_packet())
                await ws.recv()  # Connack

                # 2. Subscribe (to get response)
                sub_topics = [
                    mqtt.SubscriptionSpec(f'/v1/dev/{safe_device_id}/out', 0x01),
                    mqtt.SubscriptionSpec(f'/v1/dev/{safe_device_id}/in', 0x01),
                ]
                await ws.send(mqtt.subscribe(1, sub_topics))
                await ws.recv()  # Suback

                # 3. Publish
                pub_pkt = mqtt.publish(
                    topic, False, 1, False, packet_id=2, payload=json_payload.encode()
                )
                await ws.send(pub_pkt)
                await ws.recv()  # Puback

                # 4. Wait for response
                try:
                    resp = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    if isinstance(resp, str):
                        resp = resp.encode()
                    pkt = parse_mqtt_packet(resp)
                    if isinstance(pkt, mqtt.PublishPacket):
                        resp_payload = json.loads(pkt.payload, strict=False)
                        # Process response
                        state_update = self._extract_state_update(resp_payload)
                        if state_update:
                            await self._on_update(device_id, state_update, True)
                except asyncio.TimeoutError:
                    pass

            finally:
                await ws.close()

        except Exception as e:
            _LOGGER.error("Failed to send mqtt command: %s", e)
