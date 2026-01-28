from unittest.mock import AsyncMock, patch

import pytest

from custom_components.mysa import mqtt, mysa_mqtt


@pytest.fixture
def mock_ws():
    ws = AsyncMock()
    ws.send = AsyncMock()
    ws.recv = AsyncMock()
    ws.close = AsyncMock()
    return ws


def test_parse_mqtt_packet_bytes():
    """Test parsing bytes converts to bytearray."""
    # Create valid CONNACK (type 2, length 2, flags 0, code 0)
    data = b"\x20\x02\x00\x00"
    pkt = mysa_mqtt.parse_mqtt_packet(data)
    assert isinstance(pkt, mqtt.ConnackPacket)


@patch("custom_components.mysa.mysa_mqtt.websockets.connect", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_connect_websocket_fallback(mock_connect):
    """Test websocket connect fallback for older versions."""
    # First call raises TypeError, second succeeds
    mock_connect.side_effect = [
        TypeError("unexpected keyword argument 'additional_headers'"),
        AsyncMock(),
    ]

    await mysa_mqtt.connect_websocket("wss://example.com")

    assert mock_connect.call_count == 2
    # Verify second call used extra_headers
    kwargs = mock_connect.call_args_list[1][1]
    assert "extra_headers" in kwargs


def test_create_subscribe_packet():
    """Test create_subscribe_packet."""
    pkt = mysa_mqtt.create_subscribe_packet(["device1"])
    assert isinstance(pkt, (bytes, bytearray))
    # Basic check - type 8 (SUBSCRIBE)
    assert pkt[0] >> 4 == 8


@pytest.mark.asyncio
async def test_mqtt_connection_enter_bad_connack(mock_ws):
    """Test connection checks for valid CONNACK."""
    with (
        patch(
            "custom_components.mysa.mysa_mqtt.connect_websocket", return_value=mock_ws
        ),
        patch(
            "custom_components.mysa.mysa_mqtt.parse_mqtt_packet",
            return_value="NotConnack",
        ),
    ):
        conn = mysa_mqtt.MqttConnection("url", [])

        with pytest.raises(RuntimeError, match="Expected CONNACK"):
            await conn.__aenter__()

        mock_ws.close.assert_called()


@pytest.mark.asyncio
async def test_mqtt_connection_enter_bad_suback(mock_ws):
    """Test connection checks for valid SUBACK."""
    # First valid CONNACK, then Invalid SUBACK
    mock_ws.recv.side_effect = ["connack_bytes", "bad_suback_bytes"]

    with (
        patch(
            "custom_components.mysa.mysa_mqtt.connect_websocket", return_value=mock_ws
        ),
        patch("custom_components.mysa.mysa_mqtt.parse_mqtt_packet") as mock_parse,
    ):
        mock_parse.side_effect = [mqtt.ConnackPacket(0, 0), "NotSuback"]

        conn = mysa_mqtt.MqttConnection("url", ["dev1"])

        with pytest.raises(RuntimeError, match="Expected SUBACK"):
            await conn.__aenter__()

        mock_ws.close.assert_called()


@pytest.mark.asyncio
async def test_mqtt_connection_exit_exception(mock_ws):
    """Test exit suppresses disconnect exception."""
    mock_ws.send.side_effect = Exception("Send failed")

    conn = mysa_mqtt.MqttConnection("url", [])
    conn._ws = mock_ws
    conn._connected = True

    # Should not raise
    await conn.__aexit__(None, None, None)

    mock_ws.close.assert_called()  # Should still try to close (now fixed in impl)
    assert conn._ws is None


@pytest.mark.asyncio
async def test_mqtt_connection_receive_timeout(mock_ws):
    """Test receive timeout returns None."""
    conn = mysa_mqtt.MqttConnection("url", [])
    conn._ws = mock_ws

    # Mock wait_for to timeout
    # Mock wait_for to timeout and cleanup the coroutine
    async def mock_wait_for_side_effect(coro, timeout):
        coro.close()
        raise TimeoutError()

    with patch("asyncio.wait_for", side_effect=mock_wait_for_side_effect):
        pkt = await conn.receive(timeout=1.0)
        assert pkt is None


@pytest.mark.asyncio
async def test_mqtt_connection_send_not_connected():
    """Test send raises if not connected."""
    conn = mysa_mqtt.MqttConnection("url", [])
    conn._ws = None

    with pytest.raises(RuntimeError, match="Not connected"):
        await conn.send(b"data")


@pytest.mark.asyncio
async def test_mqtt_connection_ping_not_connected():
    """Test ping raises if not connected."""
    conn = mysa_mqtt.MqttConnection("url", [])
    conn._ws = None

    with pytest.raises(RuntimeError, match="Not connected"):
        await conn.send_ping()


@pytest.mark.asyncio
async def test_mqtt_connection_success_flow(mock_ws):
    """Test full success flow for MqttConnection coverage."""
    mock_ws.recv.side_effect = ["connack", "suback", "message"]

    with (
        patch(
            "custom_components.mysa.mysa_mqtt.connect_websocket", return_value=mock_ws
        ),
        patch("custom_components.mysa.mysa_mqtt.parse_mqtt_packet") as mock_parse,
    ):
        mock_parse.side_effect = [
            mqtt.ConnackPacket(0, 0),
            mqtt.SubackPacket(1, [0]),
            mqtt.PublishPacket(0, 0, 0, "topic", 0, b"payload"),
        ]

        conn = mysa_mqtt.MqttConnection("url", ["dev1"])

        # Enter
        await conn.__aenter__()
        assert conn.connected
        assert conn.websocket == mock_ws

        # Receive
        pkt = await conn.receive()
        assert isinstance(pkt, mqtt.PublishPacket)

        # Send
        await conn.send(b"data")
        mock_ws.send.assert_called()

        # Ping
        await conn.send_ping()

        # Exit
        await conn.__aexit__(None, None, None)
        assert conn._ws is None


@pytest.mark.asyncio
async def test_mqtt_connection_receive_not_connected():
    """Test receive raises if not connected."""
    conn = mysa_mqtt.MqttConnection("url", [])
    conn._ws = None

    with pytest.raises(RuntimeError, match="Not connected"):
        await conn.receive()


def test_legacy_parse_alias():
    """Test legacy parse_mqtt_packet alias."""
    from custom_components.mysa.mqtt import parse_mqtt_packet

    # MysaPacketType is not exported, we check type instance or just not None
    data = b"\x20\x02\x00\x00"  # CONNACK
    pkt = parse_mqtt_packet(data)
    assert pkt is not None
    # Check it is ConnackPacket
    from custom_components.mysa.mqtt import ConnackPacket

    assert isinstance(pkt, ConnackPacket)
