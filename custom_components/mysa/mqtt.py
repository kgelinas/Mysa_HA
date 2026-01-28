"""MQTT 3.1.1 Packet Builders and Parsers.

Simplified implementation for Home Assistant integration.
Only includes the functions needed for Mysa cloud communication.

Original implementation by Jason Litzinger (jlitzingerdev/mqttpacket)
Copyright 2018 Jason Litzinger - MIT License
https://github.com/jlitzingerdev/mqttpacket

Adapted and simplified for the Mysa Home Assistant integration.
"""

import struct
from dataclasses import dataclass
from typing import Any

# MQTT 3.1.1 Packet Types
MQTT_PACKET_CONNECT = 1
MQTT_PACKET_CONNACK = 2
MQTT_PACKET_PUBLISH = 3
MQTT_PACKET_PUBACK = 4
MQTT_PACKET_SUBSCRIBE = 8
MQTT_PACKET_SUBACK = 9
MQTT_PACKET_PINGREQ = 12
MQTT_PACKET_PINGRESP = 13
MQTT_PACKET_DISCONNECT = 14

PROTOCOL_LEVEL = 4  # MQTT 3.1.1
VALID_QOS = (0x00, 0x01, 0x02)
PROTOCOL_NAME = b"MQTT"


# --- Packet Data Classes ---


@dataclass
class ConnackPacket:
    """Parsed CONNACK packet."""

    return_code: int
    session_present: int
    pkt_type: int = MQTT_PACKET_CONNACK


@dataclass
class SubackPacket:
    """Parsed SUBACK packet."""

    packet_id: int
    return_codes: list[int]
    pkt_type: int = MQTT_PACKET_SUBACK


@dataclass
class PublishPacket:
    """Parsed PUBLISH packet."""

    dup: int
    qos: int
    retain: int
    topic: str
    packetid: int | None
    payload: bytes
    pkt_type: int = MQTT_PACKET_PUBLISH


@dataclass
class PubackPacket:
    """Parsed PUBACK packet."""

    packet_id: int
    pkt_type: int = MQTT_PACKET_PUBACK


@dataclass
class PingrespPacket:
    """Parsed PINGRESP packet."""

    pkt_type: int = MQTT_PACKET_PINGRESP


@dataclass
class SubscriptionSpec:
    """Subscription topic/QoS pair."""

    topicfilter: str
    qos: int

    def remaining_len(self) -> int:
        """Calculate the remaining length for this subscription spec."""
        return 3 + len(self.topicfilter.encode("utf-8"))

    def to_bytes(self) -> bytes:
        """Convert the subscription spec to bytes."""
        encoded = self.topicfilter.encode("utf-8")
        return struct.pack("!H", len(encoded)) + encoded + struct.pack("!B", self.qos)


# --- Helper Functions ---


def _encode_remaining_length(remaining_length: int) -> bytes:
    """Encode the remaining length for the packet."""
    encoded_bytes = bytearray()
    while True:
        encoded_byte = remaining_length % 128
        remaining_length //= 128
        if remaining_length:
            encoded_byte |= 0x80
        encoded_bytes.append(encoded_byte)
        if not remaining_length:
            break
    return bytes(encoded_bytes)


def _encode_string(text: str) -> bytes:
    """Encode a string as per MQTT spec: two byte length, UTF-8 data."""
    encoded_text = text.encode("utf-8")
    return struct.pack("!H", len(encoded_text)) + encoded_text


# --- Packet Builders ---


def connect(client_id: str, keepalive: int = 60) -> bytes:
    """Create a CONNECT packet."""
    msg = bytes([MQTT_PACKET_CONNECT << 4])
    meta = struct.pack(
        "!H4sBBH", 0x0004, PROTOCOL_NAME, PROTOCOL_LEVEL, 0x02, keepalive
    )
    encoded_client_id = _encode_string(client_id) if client_id else b""
    remaining_length = len(meta) + len(encoded_client_id)
    return msg + _encode_remaining_length(remaining_length) + meta + encoded_client_id


def pingreq() -> bytes:
    """Create a PINGREQ packet."""
    return b"\xc0\x00"


def disconnect() -> bytes:
    """Create a DISCONNECT packet."""
    return struct.pack("!BB", MQTT_PACKET_DISCONNECT << 4, 0)


def subscribe(packetid: int, topicspecs: list[SubscriptionSpec]) -> bytes:
    """Create a SUBSCRIBE packet."""
    remaining_len = 2  # packetid
    for spec in topicspecs:
        remaining_len += spec.remaining_len()

    msg = bytes([(MQTT_PACKET_SUBSCRIBE << 4) | 0x02])
    parts = [msg, _encode_remaining_length(remaining_len), struct.pack("!H", packetid)]
    parts.extend(s.to_bytes() for s in topicspecs)
    return b"".join(parts)


def publish(  # TODO: Refactor to reduce arguments
    topic: str,
    dup: bool,
    qos: int,
    retain: bool,
    payload: bytes,
    packet_id: int | None = None,
) -> bytes:
    """Create a PUBLISH packet."""
    # pylint: disable=too-many-arguments,too-many-positional-arguments
    # Justification: Helper function used internally for packet construction.
    if qos > 0 and packet_id is None:
        raise ValueError("QoS > 0 requires a packet_id")

    remaining_len = len(payload)
    encoded_packet_id = b""
    if qos > 0:
        remaining_len += 2
        encoded_packet_id = struct.pack("!H", packet_id)

    encoded_topic = _encode_string(topic)
    remaining_len += len(encoded_topic)

    byte1 = (MQTT_PACKET_PUBLISH << 4) | (int(dup) << 3) | (qos << 1) | int(retain)
    return (
        bytes([byte1])
        + _encode_remaining_length(remaining_len)
        + encoded_topic
        + encoded_packet_id
        + payload
    )


# --- Packet Parsers ---

_MULTIPLIERS = (1, 128, 128 * 128, 128 * 128 * 128, 0)


def parse(data: bytearray, output: list[Any]) -> int:
    """Parse packets from data into output list. Returns bytes consumed."""
    if not isinstance(data, bytearray):
        raise TypeError("data must be a bytearray")

    consumed = 0
    offset = 0

    while offset < len(data):
        first_byte = data[offset]
        pkt_type = first_byte >> 4
        variable_begin = offset + 1
        remaining_length = 0
        nb = 0

        while True:
            if variable_begin >= len(data):
                return consumed
            remaining_length += (data[variable_begin] & 127) * _MULTIPLIERS[nb]
            nb += 1
            if nb >= 5 or (data[variable_begin] & 128) == 0:
                break
            variable_begin += 1

        variable_begin += 1
        size_rem_len = variable_begin - offset - 1

        if (len(data) - offset) < (remaining_length + 1 + size_rem_len):
            return consumed

        pkt = _parse_packet(
            pkt_type, first_byte, data, remaining_length, variable_begin
        )
        if pkt:
            output.append(pkt)

        consumed += size_rem_len + 1 + remaining_length
        offset = consumed

    return consumed


def parse_one(
    data: bytes | bytearray,
) -> (
    ConnackPacket | SubackPacket | PublishPacket | PubackPacket | PingrespPacket | None
):
    """Parse a single packet from data."""
    if not isinstance(data, bytearray):
        data = bytearray(data)
    output: list[Any] = []
    parse(data, output)
    return output[0] if output else None


def parse_mqtt_packet(
    data: bytes | bytearray,
) -> (
    ConnackPacket | SubackPacket | PublishPacket | PubackPacket | PingrespPacket | None
):
    """Parse a single packet from data (legacy alias)."""
    return parse_one(data)


def _parse_packet(
    pkt_type: int,
    first_byte: int,
    data: bytearray,
    remaining_length: int,
    variable_begin: int,
) -> (
    ConnackPacket | SubackPacket | PublishPacket | PubackPacket | PingrespPacket | None
):
    """Parse a single packet based on type."""
    if pkt_type == MQTT_PACKET_CONNACK:
        return ConnackPacket(data[variable_begin + 1], data[variable_begin])

    if pkt_type == MQTT_PACKET_SUBACK:
        end_payload = remaining_length + variable_begin
        packet_id = (data[variable_begin] << 8) | data[variable_begin + 1]
        return SubackPacket(packet_id, list(data[variable_begin + 2 : end_payload]))

    if pkt_type == MQTT_PACKET_PUBLISH:
        flags = first_byte & 0x0F
        qos = (flags & 0x06) >> 1
        end_packet = remaining_length + variable_begin
        topic_len = (data[variable_begin] << 8) | data[variable_begin + 1]
        topic_start = variable_begin + 2
        topic = data[topic_start : topic_start + topic_len].decode("utf-8")
        payload_start = topic_start + topic_len
        packetid = None
        if qos:
            packetid = (data[payload_start] << 8) | data[payload_start + 1]
            payload_start += 2
        return PublishPacket(
            (flags & 0x08) >> 3,
            qos,
            flags & 0x1,
            topic,
            packetid,
            bytes(data[payload_start:end_packet]),
        )

    if pkt_type == MQTT_PACKET_PUBACK:
        return PubackPacket((data[variable_begin] << 8) | data[variable_begin + 1])

    if pkt_type == MQTT_PACKET_PINGRESP:
        return PingrespPacket()

    return None
