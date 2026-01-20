"""
Mysa MQTT Module

Shared MQTT utilities for Mysa devices.
Used by both the Home Assistant integration and debug tool.
"""
from __future__ import annotations

import ssl
import logging
import asyncio
from typing import TYPE_CHECKING, Any, Optional, List, Union
from types import TracebackType
from urllib.parse import urlparse
from uuid import uuid1

import websockets
if TYPE_CHECKING:
    # Use Any to avoid version mismatch issues with websockets library
    WebSocketClientProtocol = Any

# Support both package imports (for HA) and direct imports (for debug tool)
try:
    from . import mqtt
    from .const import MQTT_KEEPALIVE, MQTT_USER_AGENT
except ImportError:
    # Support direct execution of this file (outside Home Assistant context)
    import mqtt  # type: ignore[no-redef]
    from const import MQTT_KEEPALIVE, MQTT_USER_AGENT  # type: ignore[no-redef]

if TYPE_CHECKING:
    pass


_LOGGER = logging.getLogger(__name__)


def build_subscription_topics(device_ids: List[str]) -> List[mqtt.SubscriptionSpec]:
    """
    Build MQTT subscription topic list for devices.

    Args:
        device_ids: List of device IDs (MAC addresses)

    Returns:
        List of mqtt.SubscriptionSpec objects
    """
    sub_topics: List[mqtt.SubscriptionSpec] = []
    for device_id in device_ids:
        safe_device_id = device_id.replace(":", "").lower()
        sub_topics.extend([
            mqtt.SubscriptionSpec(f'/v1/dev/{safe_device_id}/out', 0x01),
            mqtt.SubscriptionSpec(f'/v1/dev/{safe_device_id}/in', 0x01),
        ])
    return sub_topics


def parse_mqtt_packet(data: Union[bytes, bytearray]) -> Optional[Any]:
    """
    Parse MQTT packet from raw data.

    Args:
        data: Raw bytes from WebSocket

    Returns:
        Parsed MQTT packet or None if parsing failed
    """
    if not isinstance(data, bytearray):
        data = bytearray(data)
    msgs: List[Any] = []
    mqtt.parse(data, msgs)
    return msgs[0] if msgs else None


def get_websocket_url(signed_url: str) -> str:
    """
    Convert signed HTTPS URL to WSS URL.

    Args:
        signed_url: AWS SigV4 signed HTTPS URL

    Returns:
        WSS URL for WebSocket connection
    """
    url_parts = urlparse(signed_url)
    return url_parts._replace(scheme='wss').geturl()


async def connect_websocket(signed_url: str) -> WebSocketClientProtocol:
    """
    Create WebSocket connection to MQTT broker.

    Args:
        signed_url: AWS SigV4 signed MQTT URL

    Returns:
        WebSocket connection object
    """
    ws_url = get_websocket_url(signed_url)

    # Run synchronous SSL context creation in executor to avoid blocking event loop
    loop = asyncio.get_running_loop()
    ssl_context = await loop.run_in_executor(None, ssl.create_default_context)

    headers = {'user-agent': MQTT_USER_AGENT}

    try:
        ws = await websockets.connect(
            ws_url,
            subprotocols=[websockets.Subprotocol('mqtt')],
            ssl=ssl_context,
            additional_headers=headers,
            ping_interval=None,
            ping_timeout=None
        )
    except TypeError:
        # Fallback for older websockets versions
        ws = await websockets.connect(
            ws_url,
            subprotocols=[websockets.Subprotocol('mqtt')],
            ssl=ssl_context,
            extra_headers=headers,
            ping_interval=None,
            ping_timeout=None
        )

    return ws


def create_connect_packet(keepalive: int = MQTT_KEEPALIVE) -> bytes:
    """
    Create MQTT CONNECT packet with unique client ID.

    Args:
        keepalive: Keepalive interval in seconds

    Returns:
        MQTT CONNECT packet bytes
    """
    return mqtt.connect(str(uuid1()), keepalive)


def create_subscribe_packet(device_ids: List[str], packet_id: int = 1) -> bytes:
    """
    Create MQTT SUBSCRIBE packet for device topics.

    Args:
        device_ids: List of device IDs to subscribe to
        packet_id: MQTT packet ID

    Returns:
        MQTT SUBSCRIBE packet bytes
    """
    topics = build_subscription_topics(device_ids)
    return mqtt.subscribe(packet_id, topics)


class MqttConnection:
    """
    Async context manager for MQTT connections.

    Handles WebSocket connection, MQTT handshake, and device subscription
    in a clean, reusable way.

    Usage:
        async with MqttConnection(signed_url, device_ids) as conn:
            while True:
                packet = await conn.receive()
                if packet:
                    process(packet)
    """

    def __init__(
        self,
        signed_url: str,
        device_ids: List[str],
        keepalive: int = MQTT_KEEPALIVE
    ):
        """
        Initialize MQTT connection.

        Args:
            signed_url: AWS SigV4 signed MQTT URL
            device_ids: List of device IDs to subscribe to
            keepalive: MQTT keepalive interval in seconds
        """
        self.signed_url = signed_url
        self.device_ids = device_ids
        self.keepalive = keepalive
        self._ws: Optional[WebSocketClientProtocol] = None
        self._connected: bool = False

    async def __aenter__(self) -> 'MqttConnection':
        """Connect to MQTT broker and subscribe to device topics."""
        # Connect WebSocket
        self._ws = await connect_websocket(self.signed_url)

        # Send MQTT CONNECT
        connect_pkt = create_connect_packet(self.keepalive)
        await self._ws.send(connect_pkt)

        # Wait for CONNACK
        resp = await self._ws.recv()
        pkt = parse_mqtt_packet(resp)
        if not isinstance(pkt, mqtt.ConnackPacket):
            await self._ws.close()
            raise RuntimeError(f"Expected CONNACK, got {pkt}")

        _LOGGER.info("MQTT connected successfully")

        # Subscribe to device topics
        if self.device_ids:
            sub_topics = build_subscription_topics(self.device_ids)
            sub_pkt = mqtt.subscribe(1, sub_topics)
            await self._ws.send(sub_pkt)

            # Wait for SUBACK
            resp = await self._ws.recv()
            pkt = parse_mqtt_packet(resp)
            if not isinstance(pkt, mqtt.SubackPacket):
                await self._ws.close()
                raise RuntimeError(f"Expected SUBACK, got {pkt}")

            _LOGGER.info("Subscribed to %d device topics", len(self.device_ids))

        self._connected = True
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType]
    ) -> bool:
        """Disconnect from MQTT broker."""
        self._connected = False
        if self._ws:
            try:
                # Send MQTT DISCONNECT
                disconnect_pkt = mqtt.disconnect()
                await self._ws.send(disconnect_pkt)
            except Exception:  # pylint: disable=broad-except
                # Justification: Ensure listener loop continues despite parsing errors.
                # Swallow exceptions during disconnect (e.g. network down)
                # to ensure finally block runs and socket is closed.
                pass
            finally:
                await self._ws.close()
            self._ws = None
        return False  # Don't suppress exceptions

    @property
    def connected(self) -> bool:
        """Check if connection is active."""
        return self._connected and self._ws is not None

    @property
    def websocket(self) -> Optional[WebSocketClientProtocol]:
        """Get underlying WebSocket connection."""
        return self._ws

    async def receive(self, timeout: Optional[float] = None) -> Optional[Any]:
        """
        Receive and parse an MQTT packet.

        Args:
            timeout: Optional timeout in seconds

        Returns:
            Parsed MQTT packet or None on timeout
        """
        if not self._ws:
            raise RuntimeError("Not connected")

        try:
            if timeout:
                data = await asyncio.wait_for(self._ws.recv(), timeout=timeout)
            else:
                data = await self._ws.recv()
            return parse_mqtt_packet(data)
        except asyncio.TimeoutError:
            return None

    async def send_ping(self) -> None:
        """Send MQTT PINGREQ packet."""
        if not self._ws:
            raise RuntimeError("Not connected")
        await self._ws.send(mqtt.pingreq())
        _LOGGER.debug("Sent PINGREQ keepalive")

    async def send(self, data: bytes) -> None:
        """
        Send raw data to MQTT broker.

        Args:
            data: MQTT packet bytes to send
        """
        if not self._ws:
            raise RuntimeError("Not connected")
        await self._ws.send(data)
