"""MQTT Realtime Coordinator for Mysa."""

import asyncio
import base64
import json
import logging
import time
from collections.abc import Callable
from typing import Any, cast

import websockets
from homeassistant.core import HomeAssistant

from . import mqtt
from .const import MQTT_PING_INTERVAL
from .mysa_mqtt import (
    build_subscription_topics,
    connect_websocket,
    create_connect_packet,
    parse_mqtt_packet,
)
from .readings import parse_batch_readings

# Type hint for callback
# on_update_callback(device_id, state_update, resolve_safe_id=False)
UpdateCallback = Callable[[str, dict[str, Any], bool | None], Any]
SignedUrlCallback = Callable[[], Any]

_LOGGER = logging.getLogger(__name__)


class MysaRealtime:
    """Mysa MQTT Realtime Coordinator."""

    # pylint: disable=too-many-instance-attributes
    # Justification: Manages complex websocket state and authentication.
    # Justification: Class maintains complex MQTT state and connection parameters.

    def __init__(
        self,
        hass: HomeAssistant,
        get_signed_url_callback: SignedUrlCallback,
        on_update_callback: UpdateCallback,
    ) -> None:
        """Initialize the MQTT coordinator."""
        self.hass = hass
        self._get_signed_url = get_signed_url_callback
        self._on_update = on_update_callback

        self._mqtt_listener_task: asyncio.Task[None] | None = None
        self._mqtt_connected = asyncio.Event()
        self._mqtt_ws: Any = None  # ws object from `connect_websocket`
        self._mqtt_should_reconnect = True
        self._mqtt_reconnect_delay = 1.0
        self._devices_ids: list[str] = []  # List of device IDs to subscribe to
        self._stv10_devices: list[str] = []  # List of ST-V1-0 device IDs
        self._use_batch = False  # Disabled in Core (not needed for history)
        self._batch_retry_time = 0.0
        self._last_packet_time = 0.0  # Time of last received MQTT packet

    @property
    def is_running(self) -> bool:
        """Return if MQTT listener is running."""
        return bool(self._mqtt_listener_task and not self._mqtt_listener_task.done())

    @property
    def last_packet_time(self) -> float:
        """Return timestamp of last received packet."""
        return self._last_packet_time

    @property
    def is_connected(self) -> bool:
        """Return if MQTT is currently connected and authenticated."""
        return bool(self._mqtt_connected.is_set() and self._mqtt_ws is not None)

    async def wait_until_connected(self, timeout: float = 10.0) -> bool:
        """Wait for MQTT connection to be established."""
        try:
            await asyncio.wait_for(self._mqtt_connected.wait(), timeout=timeout)
            return True
        except TimeoutError:
            return False

    def set_devices(
        self, device_ids: list[str], stv10_devices: list[str] | None = None
    ) -> None:
        """Update list of devices to subscribe to."""
        if self._devices_ids != device_ids or self._stv10_devices != (
            stv10_devices or []
        ):
            _LOGGER.debug(
                "Updating device list (connected=%s): %d devices -> %d devices",
                self._mqtt_connected.is_set(),
                len(self._devices_ids),
                len(device_ids),
            )
            self._devices_ids = device_ids
            self._stv10_devices = stv10_devices or []

            # If connected, force a reconnect to update subscriptions
            if self._mqtt_connected.is_set() and self._mqtt_ws:
                _LOGGER.info(
                    "Device list changed, forcing MQTT reconnect to update subscriptions"
                )
                asyncio.create_task(self._close_websocket())

    async def start(self) -> None:
        """Start the persistent MQTT listener."""
        if self._mqtt_listener_task is not None:
            _LOGGER.debug("MQTT listener already running")
            return

        self._mqtt_should_reconnect = True
        self._mqtt_listener_task = asyncio.create_task(self._mqtt_listener_loop())
        _LOGGER.debug("Started MQTT listener task")

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
                # Justification: Must catch all errors to keep the keep-alive loop running.
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
                        "MQTT connection lost: %s, reconnecting in %ds",
                        e,
                        int(reconnect_delay),
                    )

                self._mqtt_connected.clear()
                await asyncio.sleep(reconnect_delay)

                # Fibonacci backoff
                next_delay = reconnect_delay + (
                    prev_delay if "prev_delay" in locals() else 0
                )
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
            self._last_packet_time = time.time()  # Initialize on connect
            await self._run_mqtt_loop(ws)
        except Exception as listen_error:
            # If we failed during subscription/handshake specifically, and batch was on,
            # this might be the 'causes disconnects' issue. Fallback for next time.

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
        # pylint: disable=too-many-locals,too-many-branches
        # Justification: Handles complex message routing and error handling.
        # Justification: Handles complex ST-V1-0 shadow subscriptions
        """Perform MQTT connect and subscribe handshake."""
        # Connect
        connect_pkt = create_connect_packet()
        await ws.send(connect_pkt)

        # Connack
        resp = await ws.recv()
        pkt = parse_mqtt_packet(resp)
        if not isinstance(pkt, mqtt.ConnackPacket):
            raise RuntimeError(f"Expected CONNACK, got {pkt}")

        _LOGGER.debug("MQTT connected successfully")

        # Subscribe
        if self._devices_ids:
            # Chunk subscriptions to avoid broker limits (e.g. AWS IoT limit is 8 topics per packet)
            # We chunk by device to keep it simple and safe.
            chunk_size = 2
            device_ids_list = list(self._devices_ids)

            for i in range(0, len(device_ids_list), chunk_size):
                chunk_devs = device_ids_list[i : i + chunk_size]
                sub_topics = build_subscription_topics(
                    chunk_devs,
                    include_batch=self._use_batch,
                    stv10_devices=self._stv10_devices,
                )
                if not sub_topics:
                    continue

                # Packet ID starting at 1 and incrementing
                sub_pkt = mqtt.subscribe(i // chunk_size + 1, sub_topics)
                await ws.send(sub_pkt)

                # Wait for SUBACK, ignoring any intervening PUBLISH packets
                while True:
                    resp = await ws.recv()
                    pkt = parse_mqtt_packet(resp)
                    if isinstance(pkt, mqtt.SubackPacket):
                        break
                    if not isinstance(pkt, mqtt.PublishPacket):
                        raise RuntimeError(f"Expected SUBACK, got {pkt}")
                    # Ignore PUBLISH packets during handshake

                # Verify individual return codes (MQTT 3.1.1 spec: 0x80 is failure)
                # Topics for this chunk: [Out, In, Batch (optional), Shadow (for ST-V1-0)]
                for j, device_id in enumerate(chunk_devs):
                    # Count topics for this device
                    topics_for_device = 2  # Out, In (always present)
                    if self._use_batch:
                        topics_for_device += 1
                    is_stv10 = device_id in self._stv10_devices
                    if is_stv10:
                        topics_for_device += 1  # Shadow wildcard

                    # Calculate offset in return_codes for this device
                    offset = sum(
                        2
                        + (1 if self._use_batch else 0)
                        + (1 if dev_id in self._stv10_devices else 0)
                        for k, dev_id in enumerate(chunk_devs)
                        if k < j
                    )

                    # Check Out/In topics (required)
                    if (
                        pkt.return_codes[offset] == 0x80
                        or pkt.return_codes[offset + 1] == 0x80
                    ):
                        raise RuntimeError(
                            f"Broker rejected standard topics for device {device_id}"
                        )

                    # Check Batch topic (optional fallback)
                    if self._use_batch:
                        if pkt.return_codes[offset + 2] == 0x80:
                            _LOGGER.warning(
                                "Broker rejected batch topic for device %s. Monitoring "
                                "will continue without high-precision data.",
                                device_id,
                            )

                    # Check Shadow wildcard for ST-V1-0 devices
                    if is_stv10:
                        shadow_offset = offset + 2 + (1 if self._use_batch else 0)
                        if pkt.return_codes[shadow_offset] == 0x80:
                            raise RuntimeError(
                                f"Broker rejected shadow wildcard topic for "
                                f"ST-V1-0 device {device_id}"
                            )
                        _LOGGER.info(
                            "ST-V1-0 device %s: Subscribed to shadow topic $aws/things/%s/shadow/#",
                            device_id,
                            device_id,
                        )
            _LOGGER.debug("Subscribed to %d device topics", len(self._devices_ids))

    async def _run_mqtt_loop(self, ws: Any) -> None:
        """Run the main MQTT message and keepalive loop."""
        last_ping = time.time()
        ping_interval = MQTT_PING_INTERVAL

        while True:
            try:
                elapsed = time.time() - last_ping
                time_until_ping = max(0.1, ping_interval - elapsed)

                msg = await asyncio.wait_for(
                    ws.recv(), timeout=min(time_until_ping, 20.0)
                )
                self._last_packet_time = time.time()  # Got some bytes!

                try:
                    pkt = parse_mqtt_packet(msg)
                    if pkt:
                        if isinstance(pkt, mqtt.PublishPacket):
                            await self._process_mqtt_publish(pkt)
                        elif (
                            hasattr(pkt, "pkt_type")
                            and pkt.pkt_type == mqtt.MQTT_PACKET_PINGRESP
                        ):
                            _LOGGER.debug("Received PINGRESP")
                except Exception as parse_error:
                    _LOGGER.warning(
                        "Error parsing MQTT packet: %s", parse_error, exc_info=True
                    )

            except TimeoutError:
                pass
            except websockets.exceptions.ConnectionClosedOK:
                _LOGGER.debug("MQTT connection closed gracefully (1000 OK)")
                raise
            except websockets.exceptions.ConnectionClosedError as recv_error:
                _LOGGER.warning("MQTT connection closed with error: %s", recv_error)
                raise
            except Exception as recv_error:
                _LOGGER.error(
                    "Error receiving MQTT message: %s", recv_error, exc_info=True
                )
                raise

            if time.time() - last_ping >= ping_interval:
                try:
                    await ws.send(mqtt.pingreq())
                    last_ping = time.time()
                    _LOGGER.debug("Sent PINGREQ keepalive")
                except Exception as e:
                    _LOGGER.error("Failed to send keepalive ping: %s", e, exc_info=True)
                    raise

            # Check for silent (zombie) connection: If no packet received for 10 minutes,
            # force a reconnect. AWS session expiry is 12h, but we want faster recovery.
            if time.time() - self._last_packet_time > 600:
                _LOGGER.warning(
                    "MQTT heartbeat watchdog: No traffic received for 600s, forcing reconnection..."
                )
                raise RuntimeError("MQTT silence watchdog triggered")

    async def _process_mqtt_publish(self, packet: mqtt.PublishPacket) -> None:
        # pylint: disable=too-many-branches
        # Justification: Handles various MQTT topics including AWS shadows and legacy messages
        """Process an MQTT publish packet."""
        try:
            payload = json.loads(packet.payload, strict=False)
            topic = packet.topic
            _LOGGER.debug("Received MQTT message on %s: %s", topic, payload)

            # Extract Device ID logic
            topic_parts = topic.split("/")
            device_id = None

            if topic.startswith("$aws/things/"):
                # Topic format: $aws/things/{device_id}/shadow/...
                if len(topic_parts) >= 3:
                    device_id = topic_parts[2]
            elif len(topic_parts) >= 4 and topic_parts[3]:
                # Topic format: /v1/dev/{device_id}/out
                device_id = topic_parts[3]

            if device_id:
                # Extract shadow name from topic if applicable
                shadow_name = None
                if topic.startswith("$aws/things/") and "shadow/name/" in topic:
                    # format: $aws/things/{id}/shadow/name/{shadow_name}/update/...
                    # or: $aws/things/{id}/shadow/name/{shadow_name}/get/accepted
                    if len(topic_parts) > 5 and topic_parts[5]:
                        shadow_name = topic_parts[5]
                        _LOGGER.debug(
                            "_process_mqtt_publish: Extracted shadow_name=%s from topic=%s",
                            shadow_name,
                            topic,
                        )
                    else:
                        _LOGGER.warning(
                            "Malformed shadow topic (missing shadow name): %s",
                            topic,
                        )
                        return

                # Extract state
                state_update = self._extract_state_update(payload, shadow_name)
                if state_update:
                    await self._on_update(device_id, state_update, True)

        except Exception as e:
            _LOGGER.error("Error processing MQTT publish: %s", e, exc_info=True)

    def _extract_state_update(
        self, payload: dict[str, Any], shadow_name: str | None = None
    ) -> dict[str, Any] | None:
        # pylint: disable=too-many-branches
        # Justification: Handles various message types and shadow formats
        """Extract state update from MQTT payload."""
        # Special handlers (MsgType 1, 40, etc.)
        msg_type_raw = payload.get("msg") or payload.get("MsgType")
        try:
            msg_type = int(msg_type_raw) if msg_type_raw is not None else None
        except (ValueError, TypeError):
            msg_type = None

        # Dispatch based on special message types
        special_handlers: dict[
            int, Callable[[dict[str, Any]], dict[str, Any] | None]
        ] = {
            10: self._extract_boot_info,
            4: self._extract_log_info,
            3: self._extract_batch_info,
            61: lambda p: cast(
                dict[str, Any] | None,
                {
                    "FirmwareVersion": str(p.get("version", "")),
                    **({"_shadow_name": shadow_name} if shadow_name else {}),
                },
            ),
        }
        if msg_type is not None and msg_type in special_handlers:
            handler = special_handlers[msg_type]
            return handler(payload)

        # Special handling for AWS IoT Device Shadow messages
        if shadow_name or ("state" in payload and "version" in payload):
            # Skip delta messages - they only contain differences, not full state
            # We get the full state from /update/accepted and /get/accepted topics
            if shadow_name and "delta" in str(payload.get("metadata", {})):
                _LOGGER.debug("Skipping shadow delta message for %s", shadow_name)
                return None

            _LOGGER.debug(
                "_extract_state_update: Detected shadow document (shadow_name=%s)",
                shadow_name,
            )
            shadow_upd = self._extract_shadow_state(payload)
            if shadow_upd:
                if shadow_name:
                    shadow_upd["_shadow_name"] = shadow_name
                _LOGGER.debug(
                    "_extract_state_update: Extracted shadow state: %s", shadow_upd
                )
            else:
                _LOGGER.debug(
                    "_extract_state_update: No reported/desired state in shadow document"
                )
            return shadow_upd

        # Standard processing
        msg_ts = payload.get("time") or payload.get("Timestamp")
        update: dict[str, Any] = {}
        body = payload.get("body")

        if msg_type == 30 and body or body:
            update = self._extract_body_state(body) or {}

        # Timestamp and metadata
        if msg_ts:
            try:
                update["Timestamp"] = int(msg_ts)
            except (ValueError, TypeError):
                pass

        # Merge top-level metadata
        if (ip := payload.get("ip")) and "ip" not in update:
            update["ip"] = ip
        if not update.get("FirmwareVersion"):
            if ver := payload.get("version") or payload.get("ver"):
                update["FirmwareVersion"] = str(ver)

        return update if update else None

    def _extract_boot_info(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Extract info from MsgType 10."""
        update = {}
        if payload.get("ip"):
            update["ip"] = payload.get("ip")
        if payload.get("version"):
            update["FirmwareVersion"] = str(payload.get("version"))
        elif payload.get("ver"):
            update["FirmwareVersion"] = str(payload.get("ver"))

        return update

    def _extract_log_info(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Extract info from MsgType 4."""
        message = payload.get("Message", "")
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

    def _extract_batch_info(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Extract info from MsgType 3 (Batch Data)."""
        body = payload.get("body")
        if not body:
            return None

        readings_b64 = body.get("readings")
        if not readings_b64:
            return None

        try:
            readings_raw = base64.b64decode(readings_b64)
            parsed = parse_batch_readings(readings_raw)
            if not parsed:
                return None

            # We don't extract history or perform live updates in Core anymore
            # Batch data is redundant with standard messages.
            return {}
        except Exception as e:
            _LOGGER.warning("Error parsing batch readings: %s", e)
            return None

    def _extract_shadow_state(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Extract state from AWS Shadow document."""
        # Save root level timestamp/version before handling nested structure
        root_timestamp = payload.get("timestamp")
        root_version = payload.get("version")

        # Handle 'documents' topic structure which nests everything under 'current'
        if "current" in payload and isinstance(payload["current"], dict):
            payload = payload["current"]

        state = payload.get("state", {})
        reported = state.get("reported", {})
        desired = state.get("desired", {})

        # Merge reported and desired, prioritizing desired
        # This provides immediate feedback for commands (optimistic UI)
        combined = {}
        combined.update(reported)
        combined.update(desired)

        if not combined:
            return None

        update = {}
        update.update(combined)

        # Timestamp (prioritize nested if present, otherwise root)
        if ts := payload.get("timestamp", root_timestamp):
            update["Timestamp"] = int(ts)

        # Version (prioritize nested if present, otherwise root)
        if version := payload.get("version", root_version):
            update["version"] = int(version)

        return update

    def _extract_body_state(self, body: Any) -> dict[str, Any] | None:
        """Extract state from body."""
        if not isinstance(body, dict):
            return None

        state_update = body.get("state", {})
        if state_update:
            return cast(dict[str, Any], state_update)

        cmd_list = body.get("cmd")
        if isinstance(cmd_list, list):
            combined = {}
            for item in cmd_list:
                if isinstance(item, dict):
                    combined.update(item)
            return combined

        # Fallback: if no state/cmd, use body itself
        return cast(dict[str, Any], body)

    # Justification: Complex signature required to form varied command payloads and types.
    async def send_command(  # pylint: disable=too-many-locals
        self,
        device_id: str,
        payload: dict[str, Any],
        user_id: str | None = None,
        msg_type: int = 44,
        src_type: int = 100,
        wrap: bool = True,
        use_persistent_only: bool = False,
    ) -> None:
        """Send a command to a device."""
        if not user_id:
            _LOGGER.error("Cannot send MQTT command: User ID missing")
            return

        # If we have a persistent connection, use it!
        if self._mqtt_ws:
            _LOGGER.debug(
                "Sending MQTT command via persistent connection to %s: %s",
                device_id,
                payload,
            )
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
                        "ver": "1.0",
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
                    "Failed to send via persistent connection, falling back to one-off: %s",
                    e,
                )
                # Fall through to one-off fallback

        # If caller only wants persistent (e.g. periodic polls to avoid AWS rate limits)
        if use_persistent_only:
            _LOGGER.debug(
                "Skipping one-off fallback for %s (use_persistent_only=True)", device_id
            )
            return

        # Fallback to one-off
        await self._send_one_off_command(
            device_id, payload, user_id, msg_type, src_type, wrap
        )

    async def publish(self, topic: str, payload: dict[str, Any] | str) -> None:
        """Publish arbitrary message to a specific topic (e.g. AWS Shadow)."""
        if not self._mqtt_ws:
            _LOGGER.warning(
                "Attempted to publish to %s but MQTT is not connected", topic
            )
            return

        if isinstance(payload, dict):
            json_payload = json.dumps(payload)
        else:
            json_payload = str(payload)

        try:
            # QoS 1 for control messages
            pub_pkt = mqtt.publish(
                topic, False, 1, False, packet_id=10, payload=json_payload.encode()
            )
            await self._mqtt_ws.send(pub_pkt)
            _LOGGER.debug("Published to %s: %s", topic, json_payload)
        except Exception as e:
            _LOGGER.error("Failed to publish to %s: %s", topic, e)

    async def _send_one_off_command(
        self,
        device_id: str,
        payload: dict[str, Any],
        user_id: str | None,
        msg_type: int,
        src_type: int,
        wrap: bool,
    ) -> None:
        # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
        # Justification: Low-level command sender requiring all protocol arguments.
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
                "ver": "1.0",
            }
        else:
            outer_payload = payload

        json_payload = json.dumps(outer_payload)
        safe_device_id = device_id.replace(":", "").lower()
        topic = f"/v1/dev/{safe_device_id}/in"

        _LOGGER.debug("Sending one-off MQTT command to %s: %s", topic, json_payload)

        try:
            ws = await connect_websocket(signed_url)
            try:
                # 1. Connect
                await ws.send(create_connect_packet())
                await ws.recv()  # Connack

                # 2. Subscribe (to get response)
                sub_topics = [
                    mqtt.SubscriptionSpec(f"/v1/dev/{safe_device_id}/out", 0x01),
                    mqtt.SubscriptionSpec(f"/v1/dev/{safe_device_id}/in", 0x01),
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
                except TimeoutError:
                    pass

            finally:
                await ws.close()

        except Exception as e:
            _LOGGER.error("Failed to send mqtt command: %s", e)
