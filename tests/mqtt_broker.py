"""
Mock MQTT Broker for Mysa E2E testing.

Provides a lightweight in-process MQTT broker for testing real-time updates
without connecting to actual Mysa servers.
"""
import asyncio
import json
import logging
import time
from typing import Dict, List, Optional
from dataclasses import dataclass, field

_LOGGER = logging.getLogger(__name__)


@dataclass
class MockMqttMessage:
    """Represents an MQTT message."""
    topic: str
    payload: bytes
    qos: int = 0
    retain: bool = False


@dataclass
class MockMqttClient:
    """Mock MQTT client that connects to MockMqttBroker."""
    client_id: str
    broker: "MockMqttBroker"
    subscriptions: List[str] = field(default_factory=list)
    message_queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    connected: bool = False

    async def connect(self):
        """Connect to the mock broker."""
        self.connected = True
        self.broker.clients[self.client_id] = self
        _LOGGER.debug("MockMqttClient %s connected", self.client_id)

    async def disconnect(self):
        """Disconnect from the mock broker."""
        self.connected = False
        if self.client_id in self.broker.clients:
            del self.broker.clients[self.client_id]
        _LOGGER.debug("MockMqttClient %s disconnected", self.client_id)

    async def subscribe(self, topic: str):
        """Subscribe to a topic."""
        self.subscriptions.append(topic)
        _LOGGER.debug("MockMqttClient %s subscribed to %s", self.client_id, topic)

    async def publish(self, topic: str, payload: bytes, qos: int = 0, retain: bool = False):
        """Publish a message."""
        msg = MockMqttMessage(topic=topic, payload=payload, qos=qos, retain=retain)
        await self.broker.route_message(msg, sender=self.client_id)

    async def receive(self, timeout: float = 5.0) -> Optional[MockMqttMessage]:
        """Receive a message from subscribed topics."""
        try:
            return await asyncio.wait_for(self.message_queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None


class MockMqttBroker:
    """
    In-memory MQTT broker for testing.

    Supports:
    - Multiple clients
    - Topic subscriptions with wildcards
    - Message routing
    - Programmatic message injection for testing
    """

    def __init__(self):
        self.clients: Dict[str, MockMqttClient] = {}
        self.retained_messages: Dict[str, MockMqttMessage] = {}
        self._running = False
        self._message_log: List[MockMqttMessage] = []

    async def start(self):
        """Start the mock broker."""
        self._running = True
        _LOGGER.info("MockMqttBroker started")

    async def stop(self):
        """Stop the mock broker and disconnect all clients."""
        self._running = False
        for client in list(self.clients.values()):
            await client.disconnect()
        _LOGGER.info("MockMqttBroker stopped")

    def create_client(self, client_id: str) -> MockMqttClient:
        """Create a new client connected to this broker."""
        return MockMqttClient(client_id=client_id, broker=self)

    async def route_message(self, msg: MockMqttMessage, sender: str = "broker"):
        """Route a message to all matching subscribers."""
        self._message_log.append(msg)
        payload_preview = msg.payload[:100] if msg.payload else b""
        _LOGGER.debug("Routing message: %s -> %s", msg.topic, payload_preview)

        if msg.retain:
            self.retained_messages[msg.topic] = msg

        for client_id, client in self.clients.items():
            if client_id == sender:
                continue  # Don't echo back to sender

            for sub_topic in client.subscriptions:
                if self._topic_matches(sub_topic, msg.topic):
                    await client.message_queue.put(msg)
                    break

    async def inject_message(self, topic: str, payload: dict, device_id: Optional[str] = None):
        """
        Inject a message into the broker for testing.

        This simulates a message coming from a Mysa device.

        Args:
            topic: MQTT topic (or None to auto-generate from device_id)
            payload: Message payload as dict
            device_id: Device ID for auto-generating topic
        """
        if topic is None and device_id:
            # Generate Mysa-style topic
            safe_id = device_id.replace(":", "").lower()
            topic = f"/v1/dev/{safe_id}/out"

        msg = MockMqttMessage(
            topic=topic,
            payload=json.dumps(payload).encode(),
            qos=1
        )
        await self.route_message(msg, sender="broker_inject")

    def get_message_log(self) -> List[MockMqttMessage]:
        """Get all messages that have been routed through the broker."""
        return self._message_log.copy()

    def clear_message_log(self):
        """Clear the message log."""
        self._message_log.clear()

    @staticmethod
    def _topic_matches(pattern: str, topic: str) -> bool:
        """Check if a topic matches a subscription pattern."""
        pattern_parts = pattern.split("/")
        topic_parts = topic.split("/")

        for i, p in enumerate(pattern_parts):
            if p == "#":
                return True  # Multi-level wildcard matches rest
            if i >= len(topic_parts):
                return False
            if p == "+":
                continue  # Single-level wildcard
            if p != topic_parts[i]:
                return False

        return len(pattern_parts) == len(topic_parts)


# ===========================================================================
# Mysa-specific helpers
# ===========================================================================

def create_mysa_state_update(device_id: str, **kwargs) -> dict:
    """
    Create a Mysa-style state update message.

    Args:
        device_id: Device ID
        **kwargs: State updates (sp, stpt, ambTemp, hum, md, etc.)

    Returns:
        Mysa state update payload
    """
    return {
        "msg": 44,
        "ver": "1.0",
        "time": int(time.time()),
        "src": {"ref": device_id, "type": 1},
        "body": {
            "state": kwargs
        }
    }


def create_mysa_command(device_id: str, user_id: str, **kwargs) -> dict:
    """
    Create a Mysa-style command message.

    Args:
        device_id: Target device ID
        user_id: User ID sending the command
        **kwargs: Command parameters (sp, stpt, md, lk, etc.)

    Returns:
        Mysa command payload
    """
    timestamp = int(time.time())
    return {
        "msg": 44,
        "ver": "1.0",
        "time": timestamp,
        "Timestamp": timestamp,
        "id": int(time.time() * 1000),
        "src": {"ref": user_id, "type": 100},
        "dest": {"ref": device_id, "type": 1},
        "resp": 2,
        "body": {
            "cmd": [dict(kwargs, tm=-1)],
            "type": 4,  # BB-V2
            "ver": 1
        }
    }
