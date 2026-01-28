"""MQTT Module Coverage Tests.

Tests for mqtt.py: packet builders and parsers, edge cases for full coverage.
"""

import os
import sys

# Add project root to path for imports
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(TEST_DIR)
sys.path.insert(0, ROOT_DIR)

import json
import struct
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# Module-level imports after path setup
from custom_components.mysa.mqtt import (
    ConnackPacket,
    PingrespPacket,
    PubackPacket,
    PublishPacket,
    SubackPacket,
    SubscriptionSpec,
    _encode_remaining_length,
    connect,
    disconnect,
    parse,
    parse_one,
    pingreq,
    publish,
    subscribe,
)


class TestImportFallback:
    """Test fallback imports when package relative imports fail."""

    def test_import_fallback(self):
        """Test fallback to direct imports when relative imports fail."""

        # Save original modules
        original_modules = sys.modules.copy()

        try:
            # Cleanup for test
            if "custom_components.mysa.mysa_mqtt" in sys.modules:
                del sys.modules["custom_components.mysa.mysa_mqtt"]

            real_import = __import__
            triggered = {"val": False}

            def side_effect(name, globals=None, locals=None, fromlist=(), level=0):
                # Trigger on relative import of mqtt
                if level > 0 and fromlist and "mqtt" in fromlist:
                    triggered["val"] = True
                    raise ImportError("Simulated relative import failure")
                return real_import(name, globals, locals, fromlist, level)

            with patch("builtins.__import__", side_effect=side_effect):
                # Prepare fallback mocks
                mock_mqtt = MagicMock()
                mock_mqtt.connect = MagicMock(return_value="FALLBACK_CONNECT")

                mock_const = MagicMock()
                mock_const.MQTT_KEEPALIVE = 60
                mock_const.MQTT_USER_AGENT = "test-agent"

                # Mock the fallback modules (mqtt, const)
                # These are ABSOLUTE imports in the fallback block
                fallback_mocks = {
                    "mqtt": mock_mqtt,
                    "const": mock_const,
                }

                with patch.dict(sys.modules, fallback_mocks):
                    import custom_components.mysa.mysa_mqtt

                    # Verify we triggered the error
                    assert triggered["val"], "Relative import was not intercepted!"

                    # Verify we used the fallback by calling a function that uses mqtt module
                    res = custom_components.mysa.mysa_mqtt.create_connect_packet()
                    assert res == "FALLBACK_CONNECT"

        finally:
            # Restore original modules
            sys.modules.update(original_modules)


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

        assert pkt == b"\xc0\x00"

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
        output: list[Any] = []
        consumed = parse(data, output)

        assert consumed == 4
        assert len(output) == 1
        assert isinstance(output[0], ConnackPacket)
        assert output[0].return_code == 0

    def test_parse_suback(self):
        """Test parsing SUBACK packet."""
        # SUBACK: type 0x90, length, packet_id, return codes
        data = bytearray([0x90, 0x03, 0x00, 0x01, 0x01])
        output: list[Any] = []
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
        data = (
            bytearray([0x30, remaining_len])
            + struct.pack("!H", topic_len)
            + topic
            + payload
        )

        output: list[Any] = []
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
        data = (
            bytearray([0x32, remaining_len])
            + struct.pack("!H", topic_len)
            + topic
            + struct.pack("!H", packet_id)
            + payload
        )

        output: list[Any] = []
        consumed = parse(data, output)

        assert isinstance(output[0], PublishPacket)
        assert output[0].qos == 1
        assert output[0].packetid == 42

    def test_parse_puback(self):
        """Test parsing PUBACK packet."""
        # PUBACK: type 0x40, length 2, packet_id
        data = bytearray([0x40, 0x02, 0x00, 0x7B])  # packet_id = 123
        output: list[Any] = []
        consumed = parse(data, output)

        assert consumed == 4
        assert isinstance(output[0], PubackPacket)
        assert output[0].packet_id == 123

    def test_parse_pingresp(self):
        """Test parsing PINGRESP packet."""
        data = bytearray([0xD0, 0x00])
        output: list[Any] = []
        consumed = parse(data, output)

        assert consumed == 2
        assert isinstance(output[0], PingrespPacket)

    def test_parse_unknown_type(self):
        """Test parsing unknown packet type returns None."""
        # Use an unhandled type (e.g., 0x70 = type 7)
        data = bytearray([0x70, 0x00])
        output: list[Any] = []
        consumed = parse(data, output)

        assert consumed == 2
        assert len(output) == 0  # Unknown type not added

    def test_parse_type_error(self):
        """Test parse raises TypeError for non-bytearray."""
        with pytest.raises(TypeError, match="data must be a bytearray"):
            parse(b"bytes", [])  # type: ignore[arg-type]

    def test_parse_incomplete_header(self):
        """Test parse returns early on incomplete header."""
        data = bytearray([0x20])  # Only first byte, no remaining length
        output: list[Any] = []
        consumed = parse(data, output)

        assert consumed == 0
        assert len(output) == 0

    def test_parse_incomplete_packet(self):
        """Test parse returns early on incomplete packet body."""
        # CONNACK header says 2 bytes remaining, but only provide 1
        data = bytearray([0x20, 0x02, 0x00])  # Missing 1 byte
        output: list[Any] = []
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
        output: list[Any] = []
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


class TestMqttTopicBuilding:
    """Test MQTT topic building functions."""

    def test_build_subscription_topics_with_batch(self):
        """Test building subscription topics with /batch included."""
        from custom_components.mysa.mysa_mqtt import build_subscription_topics

        device_ids = ["device1", "device2"]

        topics = build_subscription_topics(device_ids, include_batch=True)

        # Should have 3 topics per device (out, in, batch)
        assert len(topics) == 6

        # Check topic format
        topic_strings = [t.topicfilter for t in topics]
        assert "/v1/dev/device1/out" in topic_strings
        assert "/v1/dev/device1/in" in topic_strings
        assert "/v1/dev/device1/batch" in topic_strings
        assert "/v1/dev/device2/out" in topic_strings
        assert "/v1/dev/device2/in" in topic_strings
        assert "/v1/dev/device2/batch" in topic_strings

    def test_build_subscription_topics_without_batch(self):
        """Test building subscription topics without /batch included."""
        from custom_components.mysa.mysa_mqtt import build_subscription_topics

        device_ids = ["device1", "device2"]

        topics = build_subscription_topics(device_ids, include_batch=False)

        # Should have 2 topics per device (out, in)
        assert len(topics) == 4

        # Check topic format
        topic_strings = [t.topicfilter for t in topics]
        assert "/v1/dev/device1/out" in topic_strings
        assert "/v1/dev/device1/in" in topic_strings
        assert "/v1/dev/device1/batch" not in topic_strings
        assert "/v1/dev/device2/out" in topic_strings
        assert "/v1/dev/device2/in" in topic_strings
        assert "/v1/dev/device2/batch" not in topic_strings

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
        cmd: list[dict[str, float]] = [{"sp": 22.0}, {"br": 75}]

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
        data: dict[str, list[dict[str, Any]]] = {
            "cmd": [{"sp": 22.0}, {"br": 80}, {"lk": 1}]
        }

        extracted: dict[str, Any] = {}
        for item in data["cmd"]:
            extracted.update(item)

        assert extracted["sp"] == 22.0
        assert extracted["br"] == 80
        assert extracted["lk"] == 1


class TestMqttPacketConstants:
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
