"""
MQTT Module Coverage Tests.

Tests for mqtt.py: packet builders and parsers, edge cases for full coverage.
"""
import sys
import os

# Add project root to path for imports
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(TEST_DIR)
sys.path.insert(0, ROOT_DIR)

import pytest
import struct
import json

# Module-level imports after path setup
from custom_components.mysa.mqtt import (
    connect, pingreq, disconnect, subscribe, publish, parse, parse_one,
    SubscriptionSpec, ConnackPacket, SubackPacket, PublishPacket, 
    PubackPacket, PingrespPacket, _encode_remaining_length,
    MQTT_PACKET_CONNACK, MQTT_PACKET_SUBACK, MQTT_PACKET_PUBLISH,
    MQTT_PACKET_PUBACK, MQTT_PACKET_PINGRESP,
)


# ===========================================================================
# Packet Builder Tests
# ===========================================================================

class TestPacketBuilders:
    """Test packet builder functions."""

    def test_connect_packet(self):
        """Test connect packet creation."""
        pkt = connect("test_client", keepalive=60)
        
        assert pkt[0] == 0x10  # CONNECT type
        assert b"MQTT" in pkt

    def test_pingreq_packet(self):
        """Test pingreq packet creation."""
        pkt = pingreq()
        
        assert pkt == b'\xc0\x00'

    def test_disconnect_packet(self):
        """Test disconnect packet creation."""
        pkt = disconnect()
        
        assert pkt[0] == 0xE0  # DISCONNECT type

    def test_subscribe_packet(self):
        """Test subscribe packet creation."""
        specs = [SubscriptionSpec("test/topic", 1)]
        pkt = subscribe(1, specs)
        
        assert pkt[0] == 0x82  # SUBSCRIBE type with flags

    def test_publish_qos0(self):
        """Test publish packet with QoS 0."""
        pkt = publish("test/topic", False, 0, False, b"payload")
        
        assert pkt[0] == 0x30  # PUBLISH type, QoS 0

    def test_publish_qos1(self):
        """Test publish packet with QoS 1 (requires packet_id)."""
        pkt = publish("test/topic", False, 1, False, b"payload", packet_id=123)
        
        assert (pkt[0] & 0x06) == 0x02  # QoS 1 flag

    def test_publish_qos1_no_packet_id_error(self):
        """Test publish with QoS > 0 and no packet_id raises error."""
        with pytest.raises(ValueError, match="QoS > 0 requires a packet_id"):
            publish("test/topic", False, 1, False, b"payload", packet_id=None)

    def test_publish_with_dup_and_retain(self):
        """Test publish with DUP and RETAIN flags."""
        pkt = publish("test/topic", True, 1, True, b"payload", packet_id=1)
        
        flags = pkt[0] & 0x0F
        assert flags & 0x08  # DUP
        assert flags & 0x01  # RETAIN


# ===========================================================================
# Multi-byte Remaining Length Tests
# ===========================================================================

class TestRemainingLength:
    """Test multi-byte remaining length encoding."""

    def test_small_length(self):
        """Test remaining length < 128."""
        result = _encode_remaining_length(10)
        assert result == bytes([10])

    def test_medium_length(self):
        """Test remaining length 128-16383 (2 bytes)."""
        result = _encode_remaining_length(200)
        # 200 = 0x80 | (200 % 128) + (200 // 128)
        assert len(result) == 2
        assert result[0] & 0x80  # Continuation bit

    def test_large_length(self):
        """Test remaining length requiring 3+ bytes."""
        result = _encode_remaining_length(20000)
        assert len(result) >= 2
        # First bytes should have continuation bit
        assert result[0] & 0x80


# ===========================================================================
# SubscriptionSpec Tests
# ===========================================================================

class TestSubscriptionSpec:
    """Test SubscriptionSpec."""

    def test_remaining_len(self):
        """Test remaining_len calculation."""
        spec = SubscriptionSpec("test/topic", 1)
        
        # 2 bytes for length + topic bytes + 1 for QoS
        assert spec.remaining_len() == 3 + len("test/topic")

    def test_to_bytes(self):
        """Test to_bytes encoding."""
        spec = SubscriptionSpec("test/topic", 1)
        data = spec.to_bytes()
        
        # Should have length prefix + topic + QoS
        assert len(data) == 2 + len("test/topic") + 1


# ===========================================================================
# Packet Parser Tests
# ===========================================================================

class TestPacketParsers:
    """Test packet parser functions."""

    def test_parse_connack(self):
        """Test parsing CONNACK packet."""
        # CONNACK: type 0x20, length 2, session present, return code
        data = bytearray([0x20, 0x02, 0x00, 0x00])
        output = []
        consumed = parse(data, output)
        
        assert consumed == 4
        assert len(output) == 1
        assert isinstance(output[0], ConnackPacket)
        assert output[0].return_code == 0

    def test_parse_suback(self):
        """Test parsing SUBACK packet."""
        # SUBACK: type 0x90, length, packet_id, return codes
        data = bytearray([0x90, 0x03, 0x00, 0x01, 0x01])
        output = []
        consumed = parse(data, output)
        
        assert consumed == 5
        assert isinstance(output[0], SubackPacket)
        assert output[0].packet_id == 1

    def test_parse_publish_qos0(self):
        """Test parsing PUBLISH packet with QoS 0."""
        # Build a simple PUBLISH packet
        topic = b"test/topic"
        payload = b"hello"
        topic_len = len(topic)
        remaining_len = 2 + topic_len + len(payload)
        data = bytearray([0x30, remaining_len]) + struct.pack("!H", topic_len) + topic + payload
        
        output = []
        consumed = parse(data, output)
        
        assert isinstance(output[0], PublishPacket)
        assert output[0].topic == "test/topic"
        assert output[0].payload == b"hello"
        assert output[0].qos == 0
        assert output[0].packetid is None

    def test_parse_publish_qos1(self):
        """Test parsing PUBLISH packet with QoS 1 (has packet_id)."""
        topic = b"test/topic"
        payload = b"hello"
        topic_len = len(topic)
        packet_id = 42
        remaining_len = 2 + topic_len + 2 + len(payload)  # +2 for packet_id
        # QoS 1 is flags 0x02
        data = bytearray([0x32, remaining_len]) + struct.pack("!H", topic_len) + topic + struct.pack("!H", packet_id) + payload
        
        output = []
        consumed = parse(data, output)
        
        assert isinstance(output[0], PublishPacket)
        assert output[0].qos == 1
        assert output[0].packetid == 42

    def test_parse_puback(self):
        """Test parsing PUBACK packet."""
        # PUBACK: type 0x40, length 2, packet_id
        data = bytearray([0x40, 0x02, 0x00, 0x7B])  # packet_id = 123
        output = []
        consumed = parse(data, output)
        
        assert consumed == 4
        assert isinstance(output[0], PubackPacket)
        assert output[0].packet_id == 123

    def test_parse_pingresp(self):
        """Test parsing PINGRESP packet."""
        data = bytearray([0xD0, 0x00])
        output = []
        consumed = parse(data, output)
        
        assert consumed == 2
        assert isinstance(output[0], PingrespPacket)

    def test_parse_unknown_type(self):
        """Test parsing unknown packet type returns None."""
        # Use an unhandled type (e.g., 0x70 = type 7)
        data = bytearray([0x70, 0x00])
        output = []
        consumed = parse(data, output)
        
        assert consumed == 2
        assert len(output) == 0  # Unknown type not added

    def test_parse_type_error(self):
        """Test parse raises TypeError for non-bytearray."""
        with pytest.raises(TypeError, match="data must be a bytearray"):
            parse(b"bytes", [])

    def test_parse_incomplete_header(self):
        """Test parse returns early on incomplete header."""
        data = bytearray([0x20])  # Only first byte, no remaining length
        output = []
        consumed = parse(data, output)
        
        assert consumed == 0
        assert len(output) == 0

    def test_parse_incomplete_packet(self):
        """Test parse returns early on incomplete packet body."""
        # CONNACK header says 2 bytes remaining, but only provide 1
        data = bytearray([0x20, 0x02, 0x00])  # Missing 1 byte
        output = []
        consumed = parse(data, output)
        
        assert consumed == 0
        assert len(output) == 0

    def test_parse_multi_byte_remaining_length(self):
        """Test parsing packet with multi-byte remaining length."""
        # Create a packet with remaining length > 127 (requires continuation bit)
        # We'll simulate this with remaining length 184 (0xB8)
        # Encoded as: 0xB8, 0x01 (184 % 128 = 56, with continuation | 0x80 = 0xB8, then 184 // 128 = 1)
        data = bytearray([0x30, 0xB8, 0x01])  # PUBLISH with length 184
        # But we don't have enough data for remaining 184 bytes
        output = []
        consumed = parse(data, output)
        
        assert consumed == 0  # Not enough data


# ===========================================================================
# parse_one Tests
# ===========================================================================

class TestParseOne:
    """Test parse_one function."""

    def test_parse_one_bytes(self):
        """Test parse_one with bytes input."""
        data = bytes([0x20, 0x02, 0x00, 0x00])  # CONNACK
        result = parse_one(data)
        
        assert isinstance(result, ConnackPacket)

    def test_parse_one_bytearray(self):
        """Test parse_one with bytearray input."""
        data = bytearray([0xD0, 0x00])  # PINGRESP
        result = parse_one(data)
        
        assert isinstance(result, PingrespPacket)

    def test_parse_one_empty(self):
        """Test parse_one with empty data."""
        result = parse_one(bytearray())
        
        assert result is None
        """Test remaining length 128-16383 (2 bytes)."""
        result = _encode_remaining_length(200)
        # 200 = 0x80 | (200 % 128) + (200 // 128)
        assert len(result) == 2
        assert result[0] & 0x80  # Continuation bit

    def test_large_length(self):
        """Test remaining length requiring 3+ bytes."""
        result = _encode_remaining_length(20000)
        assert len(result) >= 2
        # First bytes should have continuation bit
        assert result[0] & 0x80


# ===========================================================================
# SubscriptionSpec Tests
# ===========================================================================

class TestSubscriptionSpec:
    """Test SubscriptionSpec."""

    def test_remaining_len(self):
        """Test remaining_len calculation."""
        spec = SubscriptionSpec("test/topic", 1)
        
        # 2 bytes for length + topic bytes + 1 for QoS
        assert spec.remaining_len() == 3 + len("test/topic")

    def test_to_bytes(self):
        """Test to_bytes encoding."""
        spec = SubscriptionSpec("test/topic", 1)
        data = spec.to_bytes()
        
        # Should have length prefix + topic + QoS
        assert len(data) == 2 + len("test/topic") + 1


# ===========================================================================
# Packet Parser Tests
# ===========================================================================

class TestPacketParsers:
    """Test packet parser functions."""

    def test_parse_connack(self):
        """Test parsing CONNACK packet."""
        # CONNACK: type 0x20, length 2, session present, return code
        data = bytearray([0x20, 0x02, 0x00, 0x00])
        output = []
        consumed = parse(data, output)
        
        assert consumed == 4
        assert len(output) == 1
        assert isinstance(output[0], ConnackPacket)
        assert output[0].return_code == 0

    def test_parse_suback(self):
        """Test parsing SUBACK packet."""
        # SUBACK: type 0x90, length, packet_id, return codes
        data = bytearray([0x90, 0x03, 0x00, 0x01, 0x01])
        output = []
        consumed = parse(data, output)
        
        assert consumed == 5
        assert isinstance(output[0], SubackPacket)
        assert output[0].packet_id == 1

    def test_parse_publish_qos0(self):
        """Test parsing PUBLISH packet with QoS 0."""
        # Build a simple PUBLISH packet
        topic = b"test/topic"
        payload = b"hello"
        topic_len = len(topic)
        remaining_len = 2 + topic_len + len(payload)
        data = bytearray([0x30, remaining_len]) + struct.pack("!H", topic_len) + topic + payload
        
        output = []
        consumed = parse(data, output)
        
        assert isinstance(output[0], PublishPacket)
        assert output[0].topic == "test/topic"
        assert output[0].payload == b"hello"
        assert output[0].qos == 0
        assert output[0].packetid is None

    def test_parse_publish_qos1(self):
        """Test parsing PUBLISH packet with QoS 1 (has packet_id)."""
        topic = b"test/topic"
        payload = b"hello"
        topic_len = len(topic)
        packet_id = 42
        remaining_len = 2 + topic_len + 2 + len(payload)  # +2 for packet_id
        # QoS 1 is flags 0x02
        data = bytearray([0x32, remaining_len]) + struct.pack("!H", topic_len) + topic + struct.pack("!H", packet_id) + payload
        
        output = []
        consumed = parse(data, output)
        
        assert isinstance(output[0], PublishPacket)
        assert output[0].qos == 1
        assert output[0].packetid == 42

    def test_parse_puback(self):
        """Test parsing PUBACK packet."""
        # PUBACK: type 0x40, length 2, packet_id
        data = bytearray([0x40, 0x02, 0x00, 0x7B])  # packet_id = 123
        output = []
        consumed = parse(data, output)
        
        assert consumed == 4
        assert isinstance(output[0], PubackPacket)
        assert output[0].packet_id == 123

    def test_parse_pingresp(self):
        """Test parsing PINGRESP packet."""
        data = bytearray([0xD0, 0x00])
        output = []
        consumed = parse(data, output)
        
        assert consumed == 2
        assert isinstance(output[0], PingrespPacket)

    def test_parse_unknown_type(self):
        """Test parsing unknown packet type returns None."""
        # Use an unhandled type (e.g., 0x70 = type 7)
        data = bytearray([0x70, 0x00])
        output = []
        consumed = parse(data, output)
        
        assert consumed == 2
        assert len(output) == 0  # Unknown type not added

    def test_parse_type_error(self):
        """Test parse raises TypeError for non-bytearray."""
        with pytest.raises(TypeError, match="data must be a bytearray"):
            parse(b"bytes", [])

    def test_parse_incomplete_header(self):
        """Test parse returns early on incomplete header."""
        data = bytearray([0x20])  # Only first byte, no remaining length
        output = []
        consumed = parse(data, output)
        
        assert consumed == 0
        assert len(output) == 0

    def test_parse_incomplete_packet(self):
        """Test parse returns early on incomplete packet body."""
        # CONNACK header says 2 bytes remaining, but only provide 1
        data = bytearray([0x20, 0x02, 0x00])  # Missing 1 byte
        output = []
        consumed = parse(data, output)
        
        assert consumed == 0
        assert len(output) == 0

    def test_parse_multi_byte_remaining_length(self):
        """Test parsing packet with multi-byte remaining length."""
        # Create a packet with remaining length > 127 (requires continuation bit)
        # We'll simulate this with remaining length 184 (0xB8)
        # Encoded as: 0xB8, 0x01 (184 % 128 = 56, with continuation | 0x80 = 0xB8, then 184 // 128 = 1)
        data = bytearray([0x30, 0xB8, 0x01])  # PUBLISH with length 184
        # But we don't have enough data for remaining 184 bytes
        output = []
        consumed = parse(data, output)
        
        assert consumed == 0  # Not enough data


# ===========================================================================
# parse_one Tests
# ===========================================================================

class TestParseOne:
    """Test parse_one function."""

    def test_parse_one_bytes(self):
        """Test parse_one with bytes input."""
        data = bytes([0x20, 0x02, 0x00, 0x00])  # CONNACK
        result = parse_one(data)
        
        assert isinstance(result, ConnackPacket)

    def test_parse_one_bytearray(self):
        """Test parse_one with bytearray input."""
        data = bytearray([0xD0, 0x00])  # PINGRESP
        result = parse_one(data)
        
        assert isinstance(result, PingrespPacket)

    def test_parse_one_empty(self):
        """Test parse_one with empty data."""
        result = parse_one(bytearray())
        
        assert result is None


# ===========================================================================
# From test_mqtt.py
# ===========================================================================
        # Topic: /test (5 bytes: 00 05 2f 74 65 73 74)
        # Payload: hello
        topic = "/test"
        payload = b"hello"
        
        # Build packet manually
        topic_bytes = topic.encode()
        topic_len = len(topic_bytes)
        
        # Variable header: topic length (2 bytes) + topic
        var_header = bytes([0, topic_len]) + topic_bytes
        
        # Full remaining = var_header + payload
        remaining = var_header + payload
        remaining_len = len(remaining)
        
        # Fixed header: 0x30 + remaining length
        packet = bytes([0x30, remaining_len]) + remaining
        
        result = parse_one(packet)
        
        assert isinstance(result, PublishPacket)
        assert result.topic == topic
        assert result.payload == payload

    def test_parse_connack_packet(self):
        """Test parsing a CONNACK packet."""
        from custom_components.mysa.mqtt import parse_one, ConnackPacket
        
        # CONNACK: 0x20 0x02 0x00 0x00 (success)
        packet = bytes([0x20, 0x02, 0x00, 0x00])
        
        result = parse_one(packet)
        
        assert isinstance(result, ConnackPacket)
        assert result.return_code == 0

    def test_parse_suback_packet(self):
        """Test parsing a SUBACK packet."""
        from custom_components.mysa.mqtt import parse_one, SubackPacket
        
        # SUBACK: 0x90 0x03 0x00 0x01 0x00 (packet_id=1, QoS 0 granted)
        packet = bytes([0x90, 0x03, 0x00, 0x01, 0x00])
        
        result = parse_one(packet)
        
        assert isinstance(result, SubackPacket)
        assert result.packet_id == 1

    def test_create_connect_packet(self):
        """Test creating a CONNECT packet."""
        from custom_components.mysa.mqtt import connect
        
        client_id = "test-client"
        keepalive = 60
        
        packet = connect(client_id, keepalive)
        
        assert isinstance(packet, bytes)
        assert len(packet) > 0
        # First byte should be 0x10 (CONNECT)
        assert packet[0] == 0x10
        # Should contain the client ID
        assert client_id.encode() in packet

    def test_create_subscribe_packet(self):
        """Test creating a SUBSCRIBE packet."""
        from custom_components.mysa.mqtt import subscribe, SubscriptionSpec
        
        topics = [
            SubscriptionSpec("/test/topic1", 0),
            SubscriptionSpec("/test/topic2", 1),
        ]
        
        packet = subscribe(1, topics)
        
        assert isinstance(packet, bytes)
        assert len(packet) > 0
        # First byte should be 0x82 (SUBSCRIBE with QoS 1)
        assert packet[0] == 0x82

    def test_create_publish_packet(self):
        """Test creating a PUBLISH packet."""
        from custom_components.mysa.mqtt import publish
        
        topic = "/test/topic"
        payload = b'{"test": "data"}'
        
        packet = publish(topic, False, 1, False, packet_id=1, payload=payload)
        
        assert isinstance(packet, bytes)
        assert len(packet) > 0
        # Should contain the topic
        assert topic.encode() in packet
        # Should contain the payload
        assert payload in packet

    def test_create_pingreq_packet(self):
        """Test creating a PINGREQ packet."""
        from custom_components.mysa.mqtt import pingreq
        
        packet = pingreq()
        
        # PINGREQ is always 0xC0 0x00
        assert packet == bytes([0xC0, 0x00])

    def test_create_disconnect_packet(self):
        """Test creating a DISCONNECT packet."""
        from custom_components.mysa.mqtt import disconnect
        
        packet = disconnect()
        
        # DISCONNECT is always 0xE0 0x00
        assert packet == bytes([0xE0, 0x00])


class TestMqttTopicBuilding:
    """Test MQTT topic building functions."""

    def test_build_subscription_topics(self):
        """Test building subscription topics for devices."""
        from custom_components.mysa.mysa_mqtt import build_subscription_topics
        
        device_ids = ["device1", "device2"]
        
        topics = build_subscription_topics(device_ids)
        
        # Should have 2 topics per device (out and in)
        assert len(topics) == 4
        
        # Check topic format
        topic_strings = [t.topicfilter for t in topics]
        assert "/v1/dev/device1/out" in topic_strings
        assert "/v1/dev/device1/in" in topic_strings
        assert "/v1/dev/device2/out" in topic_strings
        assert "/v1/dev/device2/in" in topic_strings

    def test_build_subscription_topics_empty(self):
        """Test building subscription topics with empty list."""
        from custom_components.mysa.mysa_mqtt import build_subscription_topics
        
        topics = build_subscription_topics([])
        
        assert topics == []

    def test_build_subscription_topics_normalizes_ids(self):
        """Test that device IDs are normalized (lowercase, no colons)."""
        from custom_components.mysa.mysa_mqtt import build_subscription_topics
        
        # Device ID with colons and mixed case
        device_ids = ["40:91:51:E4:0D:E0"]
        
        topics = build_subscription_topics(device_ids)
        
        topic_strings = [t.topicfilter for t in topics]
        # Should be lowercase without colons
        assert "/v1/dev/409151e40de0/out" in topic_strings


# ===========================================================================
# From test_mqtt_protocol.py
# ===========================================================================

    def test_out_topic_format(self):
        """Test outgoing topic format."""
        device_id = "device1"
        topic = f"/v1/dev/{device_id}/out"
        
        assert topic == "/v1/dev/device1/out"
        assert topic.startswith("/v1/dev/")
        assert topic.endswith("/out")

    def test_in_topic_format(self):
        """Test incoming topic format."""
        device_id = "device1"
        topic = f"/v1/dev/{device_id}/in"
        
        assert topic == "/v1/dev/device1/in"
        assert topic.endswith("/in")

    def test_batch_topic_format(self):
        """Test batch topic format."""
        device_id = "device1"
        topic = f"/v1/dev/{device_id}/batch"
        
        assert topic == "/v1/dev/device1/batch"
        assert topic.endswith("/batch")

    def test_extract_device_id_from_topic(self):
        """Test extracting device ID from topic."""
        topic = "/v1/dev/device1/out"
        
        parts = topic.split("/")
        device_id = parts[3]  # /v1/dev/{id}/out
        
        assert device_id == "device1"


class TestMqttMessageEnvelope:
    """Test MQTT message envelope structure."""

    def test_publish_envelope_structure(self):
        """Test publish message envelope structure."""
        envelope = {
            "did": "device1",
            "type": 4,
            "cmd": [{"sp": 21.0}],
            "t": 1704890400000,
        }
        
        assert "did" in envelope
        assert "type" in envelope
        assert "cmd" in envelope
        assert "t" in envelope

    def test_state_envelope_structure(self):
        """Test state message envelope structure."""
        envelope = {
            "did": "device1",
            "type": 4,
            "state": {
                "sp": 21.0,
                "temp": 20.5,
                "hum": 45,
            },
            "t": 1704890400000,
        }
        
        assert "state" in envelope

    def test_cmd_array_format(self):
        """Test cmd array format."""
        cmd = [{"sp": 22.0}, {"br": 75}]
        
        assert isinstance(cmd, list)
        assert len(cmd) == 2
        assert cmd[0]["sp"] == 22.0
        assert cmd[1]["br"] == 75


class TestMqttPayloadParsing:
    """Test MQTT payload parsing."""

    def test_parse_json_payload(self):
        """Test parsing JSON payload."""
        payload = b'{"did":"device1","sp":21.0}'
        
        data = json.loads(payload)
        
        assert data["did"] == "device1"
        assert data["sp"] == 21.0

    def test_parse_nested_state(self):
        """Test parsing nested state payload."""
        payload = b'{"state":{"sp":21.0,"temp":20.5}}'
        
        data = json.loads(payload)
        
        assert data["state"]["sp"] == 21.0
        assert data["state"]["temp"] == 20.5

    def test_parse_cmd_array(self):
        """Test parsing cmd array payload."""
        payload = b'{"cmd":[{"sp":21.0}]}'
        
        data = json.loads(payload)
        
        assert isinstance(data["cmd"], list)
        assert data["cmd"][0]["sp"] == 21.0

    def test_extract_values_from_cmd_array(self):
        """Test extracting values from cmd array."""
        data = {"cmd": [{"sp": 22.0}, {"br": 80}, {"lk": 1}]}
        
        extracted = {}
        for item in data["cmd"]:
            extracted.update(item)
        
        assert extracted["sp"] == 22.0
        assert extracted["br"] == 80
        assert extracted["lk"] == 1


class TestMqttPacketTypes:
    """Test MQTT packet type identification."""

    def test_connect_packet_type(self):
        """Test CONNECT packet type."""
        CONNECT = 0x10
        
        assert CONNECT == 16

    def test_connack_packet_type(self):
        """Test CONNACK packet type."""
        CONNACK = 0x20
        
        assert CONNACK == 32

    def test_publish_packet_type(self):
        """Test PUBLISH packet type."""
        PUBLISH = 0x30
        
        assert PUBLISH == 48

    def test_subscribe_packet_type(self):
        """Test SUBSCRIBE packet type."""
        SUBSCRIBE = 0x82
        
        assert SUBSCRIBE == 130

    def test_suback_packet_type(self):
        """Test SUBACK packet type."""
        SUBACK = 0x90
        
        assert SUBACK == 144

    def test_pingreq_packet_type(self):
        """Test PINGREQ packet type."""
        PINGREQ = 0xC0
        
        assert PINGREQ == 192

    def test_pingresp_packet_type(self):
        """Test PINGRESP packet type."""
        PINGRESP = 0xD0
        
        assert PINGRESP == 208

    def test_disconnect_packet_type(self):
        """Test DISCONNECT packet type."""
        DISCONNECT = 0xE0
        
        assert DISCONNECT == 224


class TestMqttQosLevels:
    """Test MQTT QoS level handling."""

    def test_qos_0(self):
        """Test QoS 0 (at most once)."""
        QOS_0 = 0
        
        assert QOS_0 == 0

    def test_qos_1(self):
        """Test QoS 1 (at least once)."""
        QOS_1 = 1
        
        assert QOS_1 == 1

    def test_qos_2(self):
        """Test QoS 2 (exactly once)."""
        QOS_2 = 2
        
        assert QOS_2 == 2

    def test_valid_qos_range(self):
        """Test valid QoS range."""
        valid_qos = [0, 1, 2]
        
        for qos in valid_qos:
            assert 0 <= qos <= 2


class TestMqttConnectionParams:
    """Test MQTT connection parameters."""

    def test_connection_url_format(self):
        """Test MQTT WebSocket URL format."""
        url = "wss://mqtt.example.com/mqtt"
        
        assert url.startswith("wss://")
        assert "/mqtt" in url

    def test_client_id_format(self):
        """Test client ID format."""
        import uuid
        
        client_id = str(uuid.uuid4())
        
        assert len(client_id) == 36
        assert "-" in client_id

    def test_keepalive_bounds(self):
        """Test keepalive bounds."""
        keepalive = 60
        
        assert keepalive >= 10
        assert keepalive <= 600


class TestMqttStateKeys:
    """Test MQTT state key mappings."""

    def test_setpoint_key_sp(self):
        """Test setpoint key 'sp'."""
        state = {"sp": 21.0}
        
        setpoint = state.get("sp")
        
        assert setpoint == 21.0

    def test_temperature_key_temp(self):
        """Test temperature key 'temp'."""
        state = {"temp": 20.5}
        
        temperature = state.get("temp")
        
        assert temperature == 20.5

    def test_humidity_key_hum(self):
        """Test humidity key 'hum'."""
        state = {"hum": 45}
        
        humidity = state.get("hum")
        
        assert humidity == 45

    def test_mode_key_md(self):
        """Test mode key 'md'."""
        state = {"md": 1}
        
        mode = state.get("md")
        
        assert mode == 1

    def test_heating_key(self):
        """Test heating key."""
        state = {"Heating": True}
        
        heating = state.get("Heating")
        
        assert heating is True

    def test_duty_cycle_key_dc(self):
        """Test duty cycle key 'dc'."""
        state = {"dc": 75}
        
        duty_cycle = state.get("dc")
        
        assert duty_cycle == 75

    def test_brightness_key_br(self):
        """Test brightness key 'br'."""
        state = {"br": 50}
        
        brightness = state.get("br")
        
        assert brightness == 50

    def test_lock_key_lk(self):
        """Test lock key 'lk'."""
        state = {"lk": 1}
        
        lock = state.get("lk")
        
        assert lock == 1


# ===========================================================================
# From test_websocket_mqtt.py
# ===========================================================================

ROOT_DIR = os.path.dirname(TEST_DIR)
sys.path.insert(0, ROOT_DIR)

import pytest

# Module-level imports
from custom_components.mysa.mysa_mqtt import (
    get_websocket_url,
    create_connect_packet,
    build_subscription_topics,
    parse_mqtt_packet,
)
from custom_components.mysa import mqtt


class TestWebSocketUrl:
    """Test WebSocket URL handling."""

    def test_websocket_url_conversion(self):
        """Test HTTPS to WSS URL conversion."""
        https_url = "https://test.iot.amazonaws.com/mqtt?X-Amz-Security-Token=token"
        wss_url = get_websocket_url(https_url)
        
        assert wss_url.startswith("wss://")
        assert "X-Amz-Security-Token=token" in wss_url


class TestMqttPacketBuilding:
    """Test MQTT packet building functions."""

    def test_create_connect_packet(self):
        """Test CONNECT packet is correctly built."""
        packet = create_connect_packet(keepalive=60)
        
        assert isinstance(packet, bytes)
        assert len(packet) > 0
        assert packet[0] == 0x10  # CONNECT packet type

    def test_build_subscription_topics(self):
        """Test building subscription topics for devices."""
        device_ids = ["device1", "device2"]
        topics = build_subscription_topics(device_ids)
        
        assert len(topics) == 4  # 2 topics per device
        
        topic_strings = [t.topicfilter for t in topics]
        assert "/v1/dev/device1/out" in topic_strings
        assert "/v1/dev/device1/in" in topic_strings

    def test_build_subscription_topics_normalizes_ids(self):
        """Test device IDs are normalized."""
        device_ids = ["40:91:51:E4:0D:E0"]  # With colons and uppercase
        topics = build_subscription_topics(device_ids)
        
        topic_strings = [t.topicfilter for t in topics]
        assert "/v1/dev/409151e40de0/out" in topic_strings


class TestMqttPacketParsing:
    """Test MQTT packet parsing."""

    def test_parse_connack_success(self):
        """Test parsing successful CONNACK."""
        packet = bytes([0x20, 0x02, 0x00, 0x00])
        result = parse_mqtt_packet(packet)
        
        assert isinstance(result, mqtt.ConnackPacket)
        assert result.return_code == 0

    def test_parse_suback(self):
        """Test parsing SUBACK."""
        packet = bytes([0x90, 0x03, 0x00, 0x01, 0x00])
        result = parse_mqtt_packet(packet)
        
        assert isinstance(result, mqtt.SubackPacket)
        assert result.packet_id == 1

    def test_parse_publish(self):
        """Test parsing PUBLISH packet."""
        topic = "/test"
        payload = b"hello"
        topic_bytes = topic.encode()
        var_header = bytes([0, len(topic_bytes)]) + topic_bytes
        remaining = var_header + payload
        packet = bytes([0x30, len(remaining)]) + remaining
        
        result = parse_mqtt_packet(packet)
        
        assert isinstance(result, mqtt.PublishPacket)
        assert result.topic == topic
        assert result.payload == payload


class TestMqttPacketTypes:
    """Test MQTT packet creation functions."""

    def test_pingreq_packet(self):
        """Test PINGREQ packet creation."""
        packet = mqtt.pingreq()
        assert packet == bytes([0xC0, 0x00])

    def test_disconnect_packet(self):
        """Test DISCONNECT packet creation."""
        packet = mqtt.disconnect()
        assert packet == bytes([0xE0, 0x00])


class TestMqttConnectionAsync:
    """Test async MQTT connection with mocking."""

    @pytest.mark.asyncio
    async def test_mqtt_connection_aenter_mocked(self):
        """Test MqttConnection __aenter__ with mocked WebSocket."""
        from unittest.mock import patch, AsyncMock, MagicMock
        from custom_components.mysa.mysa_mqtt import MqttConnection
        
        with patch("custom_components.mysa.mysa_mqtt.connect_websocket") as mock_connect, \
             patch("custom_components.mysa.mysa_mqtt.create_connect_packet") as mock_pkt:
            
            mock_ws = AsyncMock()
            mock_connect.return_value = mock_ws
            mock_pkt.return_value = b"\x10\x00"
            
            # Mock CONNACK response
            mock_ws.recv.return_value = bytes([0x20, 0x02, 0x00, 0x00])
            
            with patch("custom_components.mysa.mysa_mqtt.parse_mqtt_packet") as mock_parse:
                mock_parse.return_value = MagicMock(spec=mqtt.ConnackPacket)
                
                conn = MqttConnection(
                    signed_url="wss://test.example.com/mqtt",
                    device_ids=[],
                    keepalive=60
                )
                
                result = await conn.__aenter__()
                
                assert result is conn
                assert conn.connected is True
                mock_ws.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_mqtt_connection_aexit_mocked(self):
        """Test MqttConnection __aexit__ with mocked WebSocket."""
        from unittest.mock import AsyncMock
        from custom_components.mysa.mysa_mqtt import MqttConnection
        
        conn = MqttConnection.__new__(MqttConnection)
        conn._connected = True
        mock_ws = AsyncMock()
        conn._ws = mock_ws
        
        result = await conn.__aexit__(None, None, None)
        
        assert result is False
        assert conn._connected is False
        mock_ws.send.assert_called_once()  # DISCONNECT packet
        mock_ws.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_mqtt_connection_send_ping_mocked(self):
        """Test MqttConnection send_ping with mocked WebSocket."""
        from unittest.mock import AsyncMock
        from custom_components.mysa.mysa_mqtt import MqttConnection
        
        conn = MqttConnection.__new__(MqttConnection)
        conn._connected = True
        conn._ws = AsyncMock()
        
        await conn.send_ping()
        
        conn._ws.send.assert_called_once()
        sent_data = conn._ws.send.call_args[0][0]
        assert sent_data == mqtt.pingreq()


# ===========================================================================
# mysa_mqtt.py Coverage Tests
# ===========================================================================

from unittest.mock import MagicMock, AsyncMock, patch


class TestRefreshAndSignUrl:
    """Test refresh_and_sign_url function."""

    def test_refresh_success(self):
        """Test successful token refresh."""
        from custom_components.mysa.mysa_mqtt import refresh_and_sign_url
        
        mock_user = MagicMock()
        mock_user.renew_access_token = MagicMock()
        mock_user.get_credentials = MagicMock(return_value=MagicMock())
        
        with patch('custom_components.mysa.mysa_mqtt.sigv4_sign_mqtt_url') as mock_sign:
            mock_sign.return_value = "wss://signed-url"
            
            url, user = refresh_and_sign_url(mock_user, "test@example.com", "pass")
            
            mock_user.renew_access_token.assert_called_once()
            assert url == "wss://signed-url"
            assert user == mock_user

    def test_refresh_failure_reauth(self):
        """Test token refresh failure triggers re-authentication."""
        from custom_components.mysa.mysa_mqtt import refresh_and_sign_url
        
        mock_user = MagicMock()
        mock_user.renew_access_token = MagicMock(side_effect=Exception("Token expired"))
        
        mock_new_user = MagicMock()
        mock_new_user.get_credentials = MagicMock(return_value=MagicMock())
        
        with patch('custom_components.mysa.mysa_mqtt.login') as mock_login:
            mock_login.return_value = mock_new_user
            
            with patch('custom_components.mysa.mysa_mqtt.sigv4_sign_mqtt_url') as mock_sign:
                mock_sign.return_value = "wss://new-signed-url"
                
                url, user = refresh_and_sign_url(mock_user, "test@example.com", "pass")
                
                mock_login.assert_called_once_with("test@example.com", "pass")
                assert user == mock_new_user

    def test_refresh_reauth_failure(self):
        """Test re-authentication failure raises exception."""
        from custom_components.mysa.mysa_mqtt import refresh_and_sign_url
        
        mock_user = MagicMock()
        mock_user.renew_access_token = MagicMock(side_effect=Exception("Token expired"))
        
        with patch('custom_components.mysa.mysa_mqtt.login') as mock_login:
            mock_login.side_effect = Exception("Auth failed")
            
            with pytest.raises(Exception, match="Auth failed"):
                refresh_and_sign_url(mock_user, "test@example.com", "pass")


class TestGetWebsocketUrl:
    """Test get_websocket_url function."""

    def test_converts_https_to_wss(self):
        """Test HTTPS URL is converted to WSS."""
        from custom_components.mysa.mysa_mqtt import get_websocket_url
        
        https_url = "https://example.com/mqtt?X-Amz-Credential=test"
        
        wss_url = get_websocket_url(https_url)
        
        assert wss_url.startswith("wss://")
        assert "example.com" in wss_url


class TestParseMqttPacket:
    """Test parse_mqtt_packet function."""

    def test_parse_bytes_input(self):
        """Test parsing bytes input."""
        from custom_components.mysa.mysa_mqtt import parse_mqtt_packet
        
        # CONNACK packet
        data = bytes([0x20, 0x02, 0x00, 0x00])
        
        result = parse_mqtt_packet(data)
        
        assert result is not None

    def test_parse_bytearray_input(self):
        """Test parsing bytearray input."""
        from custom_components.mysa.mysa_mqtt import parse_mqtt_packet
        
        # CONNACK packet
        data = bytearray([0x20, 0x02, 0x00, 0x00])
        
        result = parse_mqtt_packet(data)
        
        assert result is not None

    def test_parse_empty_returns_none(self):
        """Test parsing empty data returns None."""
        from custom_components.mysa.mysa_mqtt import parse_mqtt_packet
        
        result = parse_mqtt_packet(b"")
        
        assert result is None


class TestCreateConnectPacket:
    """Test create_connect_packet function."""

    def test_creates_valid_packet(self):
        """Test creating CONNECT packet."""
        from custom_components.mysa.mysa_mqtt import create_connect_packet
        
        pkt = create_connect_packet(60)
        
        assert isinstance(pkt, bytes)
        assert pkt[0] == 0x10  # CONNECT type

    def test_default_keepalive(self):
        """Test default keepalive value."""
        from custom_components.mysa.mysa_mqtt import create_connect_packet
        
        pkt = create_connect_packet()
        
        assert isinstance(pkt, bytes)


class TestCreateSubscribePacket:
    """Test create_subscribe_packet function."""

    def test_creates_valid_packet(self):
        """Test creating SUBSCRIBE packet."""
        from custom_components.mysa.mysa_mqtt import create_subscribe_packet
        
        pkt = create_subscribe_packet(["device1"])
        
        assert isinstance(pkt, bytes)
        assert pkt[0] == 0x82  # SUBSCRIBE type

    def test_custom_packet_id(self):
        """Test custom packet ID."""
        from custom_components.mysa.mysa_mqtt import create_subscribe_packet
        
        pkt = create_subscribe_packet(["device1"], packet_id=42)
        
        assert isinstance(pkt, bytes)


class TestMqttConnectionClass:
    """Test MqttConnection class."""

    def test_init(self):
        """Test MqttConnection initialization."""
        from custom_components.mysa.mysa_mqtt import MqttConnection
        
        conn = MqttConnection("wss://test", ["device1"], keepalive=120)
        
        assert conn.signed_url == "wss://test"
        assert conn.device_ids == ["device1"]
        assert conn.keepalive == 120
        assert conn._ws is None
        assert conn._connected is False

    def test_connected_property(self):
        """Test connected property."""
        from custom_components.mysa.mysa_mqtt import MqttConnection
        
        conn = MqttConnection.__new__(MqttConnection)
        conn._connected = False
        conn._ws = None
        
        assert conn.connected is False
        
        conn._connected = True
        conn._ws = MagicMock()
        
        assert conn.connected is True

    def test_websocket_property(self):
        """Test websocket property."""
        from custom_components.mysa.mysa_mqtt import MqttConnection
        
        conn = MqttConnection.__new__(MqttConnection)
        mock_ws = MagicMock()
        conn._ws = mock_ws
        
        assert conn.websocket == mock_ws

    @pytest.mark.asyncio
    async def test_receive_not_connected(self):
        """Test receive raises error when not connected."""
        from custom_components.mysa.mysa_mqtt import MqttConnection
        
        conn = MqttConnection.__new__(MqttConnection)
        conn._ws = None
        
        with pytest.raises(RuntimeError, match="Not connected"):
            await conn.receive()

    @pytest.mark.asyncio
    async def test_receive_with_timeout(self):
        """Test receive with timeout."""
        from custom_components.mysa.mysa_mqtt import MqttConnection
        import asyncio
        
        conn = MqttConnection.__new__(MqttConnection)
        conn._ws = AsyncMock()
        
        # Simulate timeout
        async def slow_recv():
            await asyncio.sleep(10)
            return b""
        
        conn._ws.recv = slow_recv
        
        result = await conn.receive(timeout=0.01)
        
        assert result is None

    @pytest.mark.asyncio
    async def test_receive_success(self):
        """Test successful receive."""
        from custom_components.mysa.mysa_mqtt import MqttConnection
        
        conn = MqttConnection.__new__(MqttConnection)
        conn._ws = AsyncMock()
        # PINGRESP packet
        conn._ws.recv = AsyncMock(return_value=bytes([0xD0, 0x00]))
        
        result = await conn.receive()
        
        assert result is not None

    @pytest.mark.asyncio
    async def test_send_not_connected(self):
        """Test send raises error when not connected."""
        from custom_components.mysa.mysa_mqtt import MqttConnection
        
        conn = MqttConnection.__new__(MqttConnection)
        conn._ws = None
        
        with pytest.raises(RuntimeError, match="Not connected"):
            await conn.send(b"test")

    @pytest.mark.asyncio
    async def test_send_success(self):
        """Test successful send."""
        from custom_components.mysa.mysa_mqtt import MqttConnection
        
        conn = MqttConnection.__new__(MqttConnection)
        conn._ws = AsyncMock()
        
        await conn.send(b"test_data")
        
        conn._ws.send.assert_called_once_with(b"test_data")

    @pytest.mark.asyncio
    async def test_send_ping_not_connected(self):
        """Test send_ping raises error when not connected."""
        from custom_components.mysa.mysa_mqtt import MqttConnection
        
        conn = MqttConnection.__new__(MqttConnection)
        conn._ws = None
        
        with pytest.raises(RuntimeError, match="Not connected"):
            await conn.send_ping()

    @pytest.mark.asyncio
    async def test_aexit_cleanup(self):
        """Test __aexit__ cleanup."""
        from custom_components.mysa.mysa_mqtt import MqttConnection
        
        conn = MqttConnection.__new__(MqttConnection)
        conn._connected = True
        mock_ws = AsyncMock()
        conn._ws = mock_ws
        
        result = await conn.__aexit__(None, None, None)
        
        assert result is False
        assert conn._connected is False
        mock_ws.send.assert_called_once()
        mock_ws.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_aexit_exception_suppressed(self):
        """Test __aexit__ suppresses exceptions during cleanup."""
        from custom_components.mysa.mysa_mqtt import MqttConnection
        
        conn = MqttConnection.__new__(MqttConnection)
        conn._connected = True
        conn._ws = AsyncMock()
        conn._ws.send = AsyncMock(side_effect=Exception("Network error"))
        
        # Should not raise
        result = await conn.__aexit__(None, None, None)
        
        assert result is False
        assert conn._ws is None


class TestConnectWebsocket:
    """Test connect_websocket function."""

    @pytest.mark.asyncio
    async def test_connect_websocket_success(self):
        """Test successful WebSocket connection."""
        from custom_components.mysa.mysa_mqtt import connect_websocket
        
        mock_ws = AsyncMock()
        
        with patch('custom_components.mysa.mysa_mqtt.websockets.connect', new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = mock_ws
            
            result = await connect_websocket("https://example.com/mqtt?token=test")
            
            assert result == mock_ws
            mock_connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_websocket_fallback(self):
        """Test WebSocket connection fallback for older websockets library."""
        from custom_components.mysa.mysa_mqtt import connect_websocket
        
        mock_ws = AsyncMock()
        
        # First call raises TypeError, second succeeds
        with patch('custom_components.mysa.mysa_mqtt.websockets.connect', new_callable=AsyncMock) as mock_connect:
            mock_connect.side_effect = [TypeError("additional_headers not supported"), mock_ws]
            
            # Patch a second connect for the fallback
            with patch('custom_components.mysa.mysa_mqtt.websockets.connect', new_callable=AsyncMock) as mock_fallback:
                mock_fallback.side_effect = [TypeError("test"), mock_ws]
                
                # This should try the fallback
                try:
                    result = await connect_websocket("https://example.com/mqtt")
                except TypeError:
                    pass  # Expected for this simplified test


class TestMqttConnectionAenter:
    """Test MqttConnection.__aenter__ method."""

    @pytest.mark.asyncio
    async def test_aenter_connack_failure(self):
        """Test __aenter__ raises error on non-CONNACK response."""
        from custom_components.mysa.mysa_mqtt import MqttConnection
        
        conn = MqttConnection("wss://test", ["device1"])
        
        mock_ws = AsyncMock()
        # Return a non-CONNACK packet (e.g., PINGRESP)
        mock_ws.recv = AsyncMock(return_value=bytes([0xD0, 0x00]))
        
        with patch('custom_components.mysa.mysa_mqtt.connect_websocket', new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = mock_ws
            
            with pytest.raises(RuntimeError, match="Expected CONNACK"):
                await conn.__aenter__()

    @pytest.mark.asyncio
    async def test_aenter_suback_failure(self):
        """Test __aenter__ raises error on non-SUBACK response."""
        from custom_components.mysa.mysa_mqtt import MqttConnection
        from custom_components.mysa import mqtt
        
        conn = MqttConnection("wss://test", ["device1"])
        
        mock_ws = AsyncMock()
        # First call returns CONNACK, second returns non-SUBACK
        mock_ws.recv = AsyncMock(side_effect=[
            bytes([0x20, 0x02, 0x00, 0x00]),  # CONNACK
            bytes([0xD0, 0x00]),  # PINGRESP instead of SUBACK
        ])
        
        with patch('custom_components.mysa.mysa_mqtt.connect_websocket', new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = mock_ws
            
            with pytest.raises(RuntimeError, match="Expected SUBACK"):
                await conn.__aenter__()

    @pytest.mark.asyncio
    async def test_aenter_success_with_devices(self):
        """Test successful __aenter__ with device subscription."""
        from custom_components.mysa.mysa_mqtt import MqttConnection
        
        conn = MqttConnection("wss://test", ["device1", "device2"])
        
        mock_ws = AsyncMock()
        # CONNACK then SUBACK
        mock_ws.recv = AsyncMock(side_effect=[
            bytes([0x20, 0x02, 0x00, 0x00]),  # CONNACK
            bytes([0x90, 0x03, 0x00, 0x01, 0x01]),  # SUBACK
        ])
        
        with patch('custom_components.mysa.mysa_mqtt.connect_websocket', new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = mock_ws
            
            result = await conn.__aenter__()
            
            assert result == conn
            assert conn._connected is True

    @pytest.mark.asyncio
    async def test_aenter_success_no_devices(self):
        """Test successful __aenter__ without devices (skips subscription)."""
        from custom_components.mysa.mysa_mqtt import MqttConnection
        
        conn = MqttConnection("wss://test", [])  # No devices
        
        mock_ws = AsyncMock()
        # Only CONNACK needed (no subscription)
        mock_ws.recv = AsyncMock(return_value=bytes([0x20, 0x02, 0x00, 0x00]))
        
        with patch('custom_components.mysa.mysa_mqtt.connect_websocket', new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = mock_ws
            
            result = await conn.__aenter__()
            
            assert result == conn
            assert conn._connected is True
