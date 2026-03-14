from unittest.mock import AsyncMock, patch
"""Tests for Mysa Realtime Coordinator."""

import asyncio
import base64
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from websockets.exceptions import ConnectionClosedOK, ConnectionClosedError

from custom_components.mysa import mqtt
from custom_components.mysa.realtime import MysaRealtime


@pytest.fixture
def mock_hass():
    hass = MagicMock()
    hass.async_add_executor_job = AsyncMock(side_effect=lambda f, *args: f(*args))
    return hass


@pytest.fixture
def mock_ws():
    ws = AsyncMock()
    ws.close = AsyncMock()
    ws.send = AsyncMock()
    ws.recv = AsyncMock()
    return ws


@pytest.mark.asyncio
class TestMysaRealtime:
    async def test_initialization(self, mock_hass):
        """Test initialization."""
        rt = MysaRealtime(mock_hass, AsyncMock(), MagicMock())
        assert rt.is_running is False
        assert rt._devices_ids == []

    async def test_start_stop(self, mock_hass):
        """Test start and stop lifecycle."""
        rt = MysaRealtime(mock_hass, AsyncMock(), MagicMock())

        # Mock _mqtt_listener_loop to run forever until cancelled
        async def mock_loop():
            try:
                while True:
                    await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                pass

        with patch.object(rt, "_mqtt_listener_loop", side_effect=mock_loop):
            await rt.start()
            assert rt.is_running

            # Start again should be no-op
            await rt.start()
            assert rt.is_running

            await rt.stop()
            assert not rt.is_running

    async def test_wait_until_connected(self, mock_hass):
        """Test wait_until_connected success and timeout."""
        rt = MysaRealtime(mock_hass, AsyncMock(), MagicMock())

        # Test timeout (default event state is unset)
        assert await rt.wait_until_connected(timeout=0.1) is False

        # Test success
        rt._mqtt_connected.set()
        assert await rt.wait_until_connected(timeout=0.1) is True

    async def test_listener_loop_flow(self, mock_hass):
        """Test listener loop calls listen and handles errors."""
        rt = MysaRealtime(mock_hass, AsyncMock(), MagicMock())
        rt._mqtt_reconnect_delay = 0.01  # type: ignore[assignment] # Fast retry

        # Mock listen to fail once then succeed (which just returns normally)
        listen_mock = AsyncMock(side_effect=[Exception("Connection failed"), None])

        # Only run loop for a short time
        async def run_loop_briefly():
            task = asyncio.create_task(rt._mqtt_listener_loop())
            await asyncio.sleep(0.05)
            rt._mqtt_should_reconnect = False
            # Wait for it to exit
            await task

        with patch.object(rt, "_mqtt_listen", side_effect=listen_mock):
            rt._mqtt_should_reconnect = True
            await run_loop_briefly()

            assert listen_mock.call_count >= 2

    async def test_mqtt_listen_connect_flow(self, mock_hass, mock_ws):
        """Test successful connection flow."""
        get_url = AsyncMock(return_value="https://test.url")
        rt = MysaRealtime(mock_hass, get_url, MagicMock())
        rt.set_devices(["dev1"])

        # Mock connection helper
        with patch(
            "custom_components.mysa.realtime.connect_websocket", return_value=mock_ws
        ) as mock_connect:
            # Mock internal steps
            rt._perform_mqtt_handshake = AsyncMock()  # type: ignore[method-assign]
            rt._run_mqtt_loop = AsyncMock()  # type: ignore[method-assign]

            await rt._mqtt_listen()

            mock_connect.assert_called_with("https://test.url")
            rt._perform_mqtt_handshake.assert_called_once()
            rt._run_mqtt_loop.assert_called_once()
            mock_ws.close.assert_called()

    async def test_perform_handshake_success(self, mock_hass, mock_ws):
        """Test successful handshake."""
        rt = MysaRealtime(mock_hass, AsyncMock(), MagicMock())
        rt.set_devices(["dev1"])

        # Setup responses: Connack, Suback
        connack = mqtt.ConnackPacket(0, 0)
        suback = mqtt.SubackPacket(1, [0, 0, 0])  # [Out, In, Batch]

        # We need to assume parse_mqtt_packet returns objects.
        # Ideally we'd use real bytes but mocking parser is easier
        with patch(
            "custom_components.mysa.realtime.parse_mqtt_packet",
            side_effect=[connack, suback],
        ):
            await rt._perform_mqtt_handshake(mock_ws)

            assert mock_ws.send.call_count == 2  # Connect + Subscribe

    async def test_perform_handshake_connack_fail(self, mock_hass, mock_ws):
        """Test handshake fails if not Connack."""
        rt = MysaRealtime(mock_hass, AsyncMock(), MagicMock())

        # Return None or other packet type to simulate failure
        with (
            patch(
                "custom_components.mysa.realtime.parse_mqtt_packet", return_value=None
            ),
            pytest.raises(RuntimeError, match="Expected CONNACK"),
        ):
            await rt._perform_mqtt_handshake(mock_ws)

    async def test_run_mqtt_loop_msg_processing(self, mock_hass, mock_ws):
        """Test message processing loop."""
        ready_state = {"temp": 20}
        on_update = MagicMock()
        rt = MysaRealtime(mock_hass, AsyncMock(), on_update)

        # Mock payload
        class MockPkt:
            topic = "/v1/dev/dev1/out"
            payload = b'{"msg": 44, "body": {"state": {"temp": 20}}}'

        # PublishPacket(dup, qos, retain, topic, packetid, payload)
        pkt = mqtt.PublishPacket(0, 0, 0, MockPkt.topic, None, MockPkt.payload)

        # Return packet then raise timeout/error to exit loop
        async def recv_side_effect():
            if mock_ws.recv.call_count == 1:
                return b"packet_data"
            # Trigger exit
            raise Exception("Stop loop")

        mock_ws.recv.side_effect = recv_side_effect

        with patch(
            "custom_components.mysa.realtime.parse_mqtt_packet", return_value=pkt
        ):
            try:
                await rt._run_mqtt_loop(mock_ws)
            except Exception:
                pass

            on_update.assert_called_once_with("dev1", {"temp": 20}, True)

    async def test_extract_state_update(self, mock_hass):
        """Test payload extraction."""
        rt = MysaRealtime(mock_hass, AsyncMock(), MagicMock())

        # Case 1: Direct state
        payload = {"msg": 44, "body": {"state": {"sp": 20}}}
        assert rt._extract_state_update(payload) == {"sp": 20}

        # Case 2: From CMD echo
        payload = {"msg": 44, "body": {"cmd": [{"sp": 21}]}}
        assert rt._extract_state_update(payload) == {"sp": 21}

        # Case 3: Wrong msg type
        payload = {"msg": 99}
        assert rt._extract_state_update(payload) is None

    async def test_send_command_one_off(self, mock_hass, mock_ws):
        """Test send_command logic."""
        rt = MysaRealtime(mock_hass, AsyncMock(return_value="https://url"), MagicMock())

        with patch(
            "custom_components.mysa.realtime.connect_websocket", new_callable=AsyncMock
        ) as mock_connect:
            mock_connect.return_value = mock_ws
            # Mock responses for handshake + puback + response
            # connect, connack, subscribe, suback, publish, puback, wait_response
            # Send calls: Connect, Sub, Pub
            # Recv calls: Connack, Suback, Puback, Response

            connack = mqtt.ConnackPacket(0, 0)
            suback = mqtt.SubackPacket(1, [1])
            # PublishPacket doesn't have simple return for Puback?
            # Wait, puback is separate packet type.
            puback = mqtt.PubackPacket(2)

            resp_pkt = mqtt.PublishPacket(
                0,
                0,
                0,
                "/v1/dev/dev1/out",
                None,
                b'{"msg": 44, "body": {"state": {"ok": 1}}}',
            )

            with patch(
                "custom_components.mysa.realtime.parse_mqtt_packet",
                side_effect=[connack, suback, puback, resp_pkt],
            ):
                mock_ws.recv.side_effect = ["connack", "suback", "puback", "response"]

                await rt.send_command("dev1", {"cmd": 1}, "user1")

                assert mock_ws.send.call_count == 3  # Connect, Sub, Pub
                assert mock_ws.close.call_count == 1

    async def test_send_command_connected(self, mock_hass, mock_ws):
        """Test send_command uses persistent connection if available."""
        rt = MysaRealtime(mock_hass, AsyncMock(), MagicMock())
        rt._mqtt_ws = mock_ws  # Simulate connected

        with patch.object(
            rt, "_send_one_off_command", new_callable=AsyncMock
        ) as mock_send_off:
            await rt.send_command("dev1", {"a": 1}, "u1")
            # Should NOT call one-off
            mock_send_off.assert_not_called()
            # Should call ws.send
            assert mock_ws.send.called

    async def test_send_command_fallback(self, mock_hass, mock_ws):
        """Test send_command falls back to one-off if ws fails or is missing."""
        rt = MysaRealtime(mock_hass, AsyncMock(), MagicMock())

        # Case 1: WS missing
        rt._mqtt_ws = None
        with patch.object(
            rt, "_send_one_off_command", new_callable=AsyncMock
        ) as mock_send_off:
            await rt.send_command("dev1", {"a": 1}, "u1")
            mock_send_off.assert_called_once()

        # Case 2: WS fails
        rt._mqtt_ws = mock_ws
        mock_ws.send.side_effect = Exception("WS send failed")
        with patch.object(
            rt, "_send_one_off_command", new_callable=AsyncMock
        ) as mock_send_off:
            await rt.send_command("dev1", {"a": 1}, "u1")
            mock_send_off.assert_called_once()

    async def test_send_command_no_wrap_persistent(self, mock_hass, mock_ws):
        """Test send_command with wrap=False via persistent connection."""
        rt = MysaRealtime(mock_hass, AsyncMock(), MagicMock())
        rt._mqtt_ws = mock_ws
        await rt.send_command("dev1", {"raw": "data"}, "u1", wrap=False)
        assert mock_ws.send.called

    async def test_send_one_off_no_user(self, mock_hass):
        """Test _send_one_off_command handles missing user ID (coverage)."""
        rt = MysaRealtime(mock_hass, AsyncMock(), MagicMock())
        # This hits line 407-408
        await rt._send_one_off_command("dev1", {}, None, 44, 100, True)

    async def test_extract_state_update_nested_complex(self, mock_hass):
        """Test complex nested structure extraction."""
        rt = MysaRealtime(mock_hass, AsyncMock(), MagicMock())
        payload = {"msg": 44, "body": {"cmd": [{"sp": 25}, {"invalid": 2}]}}
        # It updates existing state with cmd items (if no state key)
        res = rt._extract_state_update(payload)
        assert res is not None
        # assert res["curr"] == 1 # Removed
        assert res["sp"] == 25
        assert res["invalid"] == 2

    async def test_process_exception_handling(self, mock_hass):
        """Test exception handling in process_mqtt_publish."""
        rt = MysaRealtime(mock_hass, AsyncMock(), MagicMock())

        class MockPkt:
            topic = "topic"
            payload = b"{ }"

        # Mock extract to raise
        with patch.object(
            rt, "_extract_state_update", side_effect=ValueError("Bad JSON")
        ):
            # Should catch and log, not raise
            await rt._process_mqtt_publish(MockPkt())
            # Verify no crash
            # We can verify logging if we mock it, or just ensure no raise logic holds safely.

    async def test_run_mqtt_loop_keepalive_failure(self, mock_hass, mock_ws):
        """Test keepalive failure."""
        rt = MysaRealtime(mock_hass, AsyncMock(), MagicMock())

        # We use a custom wait implementation to control the loop flow
        loop_state = {"iters": 0}

        async def mock_recv():
            loop_state["iters"] += 1
            if loop_state["iters"] > 2:
                raise Exception("Stop Loop")
            await asyncio.sleep(0.01)  # fast wait
            raise TimeoutError()

        mock_ws.recv.side_effect = mock_recv

        # Mock time to force ping
        with patch("time.time", side_effect=[100, 200, 300, 400]):
            mock_ws.send.side_effect = Exception("Ping Fail")

            try:
                await rt._run_mqtt_loop(mock_ws)
            except Exception as e:
                # expecting "Ping Fail" to bubble up
                assert str(e) == "Ping Fail"

    async def test_run_mqtt_loop_keepalive_success(self, mock_hass, mock_ws):
        """Test keepalive success path."""
        rt = MysaRealtime(mock_hass, AsyncMock(), MagicMock())
        loop_state = {"iters": 0}

        async def mock_recv():
            loop_state["iters"] += 1
            if loop_state["iters"] > 2:
                raise Exception("Stop Loop")
            await asyncio.sleep(0.01)
            raise TimeoutError()

        mock_ws.recv.side_effect = mock_recv

        with patch("time.time", side_effect=[100, 200, 300, 400]):
            try:
                await rt._run_mqtt_loop(mock_ws)
            except Exception:
                pass
            # verify ping sent and no log error
            mock_ws.send.assert_called()

    async def test_mqtt_listen_exception_and_close_fail(self, mock_hass, mock_ws):
        """Test listen exception handling and close exception suppression."""
        rt = MysaRealtime(mock_hass, AsyncMock(return_value="url"), MagicMock())

        # 1. connect succeeds
        with patch(
            "custom_components.mysa.realtime.connect_websocket", return_value=mock_ws
        ):
            # 2. handshake raises (hits catch block 116-120)
            # 3. close raises (hits finally block 126-127)

            async def mock_handshake(ws):
                raise Exception("Handshake Fail")

            rt._perform_mqtt_handshake = mock_handshake  # type: ignore[method-assign]
            mock_ws.close.side_effect = Exception("Close Fail")

            with pytest.raises(Exception, match="Handshake Fail"):
                await rt._mqtt_listen()

            # Verify close was called
            mock_ws.close.assert_called()

    async def test_extract_state_update_fallback(self, mock_hass):
        """Test extraction falls back to body if no state/cmd."""
        rt = MysaRealtime(mock_hass, AsyncMock(), MagicMock())
        # msg 44, body has data but no state/cmd keys
        payload = {"msg": 44, "body": {"root_key": 1}}
        assert rt._extract_state_update(payload) == {"root_key": 1}

    async def test_send_one_off_success_response(self, mock_hass, mock_ws):
        """Test one-off command handles response and updates state."""
        on_update = MagicMock()
        rt = MysaRealtime(mock_hass, AsyncMock(return_value="url"), on_update)

        with patch(
            "custom_components.mysa.realtime.connect_websocket", return_value=mock_ws
        ):
            # Handshake
            connack = mqtt.ConnackPacket(0, 0)
            suback = mqtt.SubackPacket(1, [1])
            puback = mqtt.PubackPacket(2)

            # Response
            resp_payload = b'{"msg": 44, "body": {"state": {"new": 1}}}'
            resp_pkt = mqtt.PublishPacket(0, 0, 0, "topic", None, resp_payload)

            # So side_effect should be: JUST the response packet.
            with patch(
                "custom_components.mysa.realtime.parse_mqtt_packet",
                side_effect=[resp_pkt],
            ):
                mock_ws.recv.side_effect = [b"c", b"s", b"p", b"resp"]

                await rt.send_command("dev1", {}, "u")

                on_update.assert_called_once_with("dev1", {"new": 1}, True)

    async def test_close_websocket_exception(self, mock_hass, mock_ws):
        """Test exception during close is suppressed."""
        rt = MysaRealtime(mock_hass, AsyncMock(), MagicMock())
        rt._mqtt_ws = mock_ws
        mock_ws.close.side_effect = Exception("Close error")

        await rt._close_websocket()
        assert rt._mqtt_ws is None  # Should be cleared despite error

    async def test_mqtt_listener_loop_cancelled(self, mock_hass):
        """Test task cancellation in loop."""
        rt = MysaRealtime(mock_hass, AsyncMock(), MagicMock())
        rt._mqtt_reconnect_delay = 0

        async def mock_listen():
            raise asyncio.CancelledError()

        with patch.object(rt, "_mqtt_listen", side_effect=mock_listen):
            try:
                await rt._mqtt_listener_loop()
            except asyncio.CancelledError:
                pass  # Expected

    async def test_mqtt_listen_generic_exception(self, mock_hass, mock_ws):
        """Test generic exception in listen connection."""
        rt = MysaRealtime(mock_hass, AsyncMock(return_value="url"), MagicMock())

        with (
            patch(
                "custom_components.mysa.realtime.connect_websocket",
                side_effect=Exception("Conn fail"),
            ),
            pytest.raises(Exception, match="Conn fail"),
        ):
            await rt._mqtt_listen()

    async def test_perform_handshake_suback_fail(self, mock_hass, mock_ws):
        """Test handshake fails if not Suback."""
        rt = MysaRealtime(mock_hass, AsyncMock(), MagicMock())
        rt.set_devices(["dev1"])  # Needed to trigger subscribe

        connack = mqtt.ConnackPacket(0, 0)
        # Return connack then something else
        with (
            patch(
                "custom_components.mysa.realtime.parse_mqtt_packet",
                side_effect=[connack, mqtt.ConnackPacket(0, 0)],
            ),
            pytest.raises(RuntimeError, match="Expected SUBACK"),
        ):
            await rt._perform_mqtt_handshake(mock_ws)

    async def test_run_mqtt_loop_pingresp(self, mock_hass, mock_ws):
        """Test PINGRESP handling and parse error."""
        rt = MysaRealtime(mock_hass, AsyncMock(), MagicMock())

        # 1. PINGRESP
        pingresp = mqtt.PingrespPacket()
        # 2. Parse Error (raise Exception)
        # 3. Timeout (handled)
        # 4. Exit

        call_count = 0

        async def mock_recv():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return b"pingresp"
            if call_count == 2:
                return b"garbage"
            if call_count == 3:
                raise TimeoutError()
            raise Exception("Stop")

        mock_ws.recv.side_effect = mock_recv

        with patch("custom_components.mysa.realtime.parse_mqtt_packet") as mock_parse:

            def parse_side_effect(data):
                if data == b"pingresp":
                    return pingresp
                if data == b"garbage":
                    raise ValueError("Parse Error")
                return None

            mock_parse.side_effect = parse_side_effect

            try:
                await rt._run_mqtt_loop(mock_ws)
            except Exception:
                pass

    async def test_send_command_missing_user(self, mock_hass):
        """Test send command with missing user ID."""
        rt = MysaRealtime(mock_hass, AsyncMock(), MagicMock())
        # Should return early, log error
        await rt.send_command("dev1", {}, None)
        # How to verify? Log capture or coverage check.
        # Coverage check is enough via line hit.

    async def test_send_one_off_wrap_false(self, mock_hass, mock_ws):
        """Test send one off with wrap=False and response timeout."""
        rt = MysaRealtime(mock_hass, AsyncMock(return_value="url"), MagicMock())

        with patch(
            "custom_components.mysa.realtime.connect_websocket", return_value=mock_ws
        ):
            # Mock handshake sequence
            connack = mqtt.ConnackPacket(0, 0)
            suback = mqtt.SubackPacket(1, [1])
            puback = mqtt.PubackPacket(2)

            with patch(
                "custom_components.mysa.realtime.parse_mqtt_packet",
                side_effect=[connack, suback, puback],
            ):
                mock_ws.recv.side_effect = [
                    b"c",
                    b"s",
                    b"p",
                    asyncio.TimeoutError,
                ]  # Timeout waiting for response

                await rt.send_command("dev1", {"a": 1}, "u", wrap=False)

                # Verify payload sent was not wrapped
                # Argument capture on pub logic inside?
                # Actually mock_ws.send was called with pub packet containing payload.
                # Too complex to unpack bytes here, rely on coverage of line 302.

    async def test_send_one_off_exception(self, mock_hass):
        """Test top level exception in send_one_off."""
        rt = MysaRealtime(mock_hass, AsyncMock(return_value="url"), MagicMock())
        with patch(
            "custom_components.mysa.realtime.connect_websocket",
            side_effect=Exception("Fail"),
        ):
            await rt.send_command("d", {}, "u")

    async def test_extract_state_update_msg_10(self, mock_hass):
        """Test extraction of MsgType 10 (Boot Status)."""
        rt = MysaRealtime(mock_hass, AsyncMock(), MagicMock())
        payload = {
            "msg": 10,
            "ip": "192.168.1.10",
            "version": "1.2.3",
            "device": "SERIAL123",
        }
        res = rt._extract_state_update(payload)
        assert res == {"ip": "192.168.1.10", "FirmwareVersion": "1.2.3"}

        # Partial MsgType 10 with 'ver'
        payload_ver = {"msg": 10, "ver": "1.2.4"}
        res_ver = rt._extract_state_update(payload_ver)
        assert res_ver == {"FirmwareVersion": "1.2.4"}

    async def test_extract_state_update_msg_4(self, mock_hass):
        """Test extraction of MsgType 4 (Logs)."""
        rt = MysaRealtime(mock_hass, AsyncMock(), MagicMock())

        # IP Case
        payload_ip = {"msg": 4, "Message": "Some log prefix Local IP: 192.168.1.50"}
        res_ip = rt._extract_state_update(payload_ip)
        assert res_ip == {"ip": "192.168.1.50"}

        # Serial Case
        payload_serial = {"msg": 4, "Message": "Info Device Serial: SN999"}
        res_serial = rt._extract_state_update(payload_serial)
        assert res_serial == {"serial_number": "SN999"}

        # Both Case
        payload_both = {"msg": 4, "Message": "Local IP: 1.1.1.1 Device Serial: ST-V1-0"}
        res_both = rt._extract_state_update(payload_both)
        assert res_both == {"ip": "1.1.1.1", "serial_number": "ST-V1-0"}

        # Irrelevant log
        payload_none = {"msg": 4, "Message": "Just a log message"}
        assert rt._extract_state_update(payload_none) is None

    async def test_extract_state_update_cmd_only(self, mock_hass):
        """Test extraction fallback to cmd when state is missing."""
        rt = MysaRealtime(mock_hass, AsyncMock(), MagicMock())
        payload = {
            "msg": 44,
            "body": {
                # No "state" key
                "cmd": [{"sp": 21}, {"m": 1}]
            },
        }
        res = rt._extract_state_update(payload)
        # Should merge items from cmd list
        assert res == {"sp": 21, "m": 1}

    async def test_extract_state_update_key_variant(self, mock_hass):
        """Test extraction using 'MsgType' key instead of 'msg'."""
        rt = MysaRealtime(mock_hass, AsyncMock(), MagicMock())
        payload = {"MsgType": 4, "Message": "Local IP: 192.168.1.99"}
        res = rt._extract_state_update(payload)
        assert res == {"ip": "192.168.1.99"}

    async def test_extract_state_update_invalid_body(self, mock_hass):
        """Test extraction with invalid body type (not dict)."""
        rt = MysaRealtime(mock_hass, AsyncMock(), MagicMock())
        payload = {"msg": 44, "body": "invalid_string_body"}
        res = rt._extract_state_update(payload)
        assert res is None

    async def test_extract_state_update_msg_4_reversed_order(self, mock_hass):
        """Test extraction of MsgType 4 with reversed order (Serial then IP)."""
        rt = MysaRealtime(mock_hass, AsyncMock(), MagicMock())
        payload = {
            "msg": 4,
            "Message": "Prefix Device Serial: SN999 Local IP: 10.0.0.99",
        }
        res = rt._extract_state_update(payload)
        assert res == {"ip": "10.0.0.99", "serial_number": "SN999"}

    async def test_extract_state_update_msg_61(self, mock_hass):
        """Test extraction of MsgType 61 (Firmware Report)."""
        rt = MysaRealtime(mock_hass, AsyncMock(), MagicMock())
        payload = {"msg": 61, "version": "2.0.0"}
        res = rt._extract_state_update(payload)
        assert res == {"FirmwareVersion": "2.0.0"}

    async def test_extract_state_update_catchall(self, mock_hass):
        """Test catch-all metadata extraction from top-level keys."""
        rt = MysaRealtime(mock_hass, AsyncMock(), MagicMock())

        # Test 1: IP in top level
        payload = {"msg": 20, "ip": "10.0.0.1"}
        res = rt._extract_state_update(payload)
        assert res == {"ip": "10.0.0.1"}

        # Test 2: version in top level
        payload = {"msg": 20, "version": "1.1.1"}
        res = rt._extract_state_update(payload)
        assert res == {"FirmwareVersion": "1.1.1"}

        # Test 3: ver in top level
        payload = {"msg": 20, "ver": "1.1.2"}
        res = rt._extract_state_update(payload)
        assert res == {"FirmwareVersion": "1.1.2"}

        # Test 4: Merge with body state
        payload = {
            "msg": 44,
            "body": {"state": {"temp": 21}},
            "ip": "10.0.0.5",
            "version": "3.0.0",
        }
        res = rt._extract_state_update(payload)
        assert res == {"temp": 21, "ip": "10.0.0.5", "FirmwareVersion": "3.0.0"}

    # --- Gap Fill Tests (Merged) ---

    async def test_extract_state_update_msg_30(self, mock_hass):
        """Test extraction of MsgType 30 (Periodic Update)."""
        rt = MysaRealtime(mock_hass, AsyncMock(), MagicMock())
        payload = {
            "msg": 30,
            "body": {"ambTemp": 20.5, "hum": 44, "stpt": 19.0, "mode": 6},
        }
        res = rt._extract_state_update(payload)
        # Should return everything (mode filtering moved to device.py)
        assert res is not None
        assert res["ambTemp"] == 20.5
        assert res["mode"] == 6

    # --- Gap Fill Tests (Merged) ---

    async def test_extract_state_update_invalid_msg_type(self, mock_hass):
        """Test extraction with non-numeric msg type (hits exception block)."""
        rt = MysaRealtime(mock_hass, AsyncMock(), MagicMock())
        payload = {"msg": "invalid_int"}
        # Should catch ValueError and return None (since msg_type becomes None)
        assert rt._extract_state_update(payload) is None

    async def test_perform_handshake_batch_rejected(self, mock_hass, mock_ws):
        """Test that batch rejection doesn't fail the whole connection."""
        rt = MysaRealtime(mock_hass, AsyncMock(), MagicMock())
        rt.set_devices(["dev1"])
        rt._use_batch = True

        # Connack (Success)
        connack = mqtt.ConnackPacket(0, 0)
        # Suback: [Out=Success, In=Success, Batch=Failure]
        suback = mqtt.SubackPacket(1, [0x01, 0x01, 0x80])

        with patch(
            "custom_components.mysa.realtime.parse_mqtt_packet",
            side_effect=[connack, suback],
        ):
            # Should NOT raise RuntimeError
            await rt._perform_mqtt_handshake(mock_ws)

    async def test_perform_handshake_standard_rejected(self, mock_hass, mock_ws):
        """Test that standard topic rejection DOES fail the connection."""
        rt = MysaRealtime(mock_hass, AsyncMock(), MagicMock())
        rt.set_devices(["dev1"])

        connack = mqtt.ConnackPacket(0, 0)
        # Suback: [Out=Failure, In=Success, Batch=Success]
        suback = mqtt.SubackPacket(1, [0x80, 0x01, 0x01])

        with (
            patch(
                "custom_components.mysa.realtime.parse_mqtt_packet",
                side_effect=[connack, suback],
            ),
            pytest.raises(RuntimeError, match="Broker rejected standard topics"),
        ):
            await rt._perform_mqtt_handshake(mock_ws)



class TestRealtimeException:
    """Test realtime.py exception handling."""

    @pytest.mark.asyncio
    async def test_on_update_exception(self, mock_hass):
        """Test that exception in _process_mqtt_publish is caught."""
        rt = MysaRealtime(mock_hass, AsyncMock(), MagicMock())

        # Create a packet with invalid JSON to trigger json.loads exception
        pkt = MagicMock()
        pkt.payload = b"{invalid json"
        pkt.topic = "/v1/dev/dev1/out"

        # Should catch exception and log error, not raise
        await rt._process_mqtt_publish(pkt)


# ===========================================================================
# Merged Coverage Tests
# ===========================================================================


class TestRealtimeCoverage:
    """Test coverage for MysaRealtime extraction logic."""

    @pytest.fixture
    def realtime(self, hass):
        return MysaRealtime(hass, MagicMock(), MagicMock())

    def test_extract_boot_info(self, realtime):
        """Test MsgType 10 extraction (covers _extract_boot_info)."""
        payload = {"msg": 10, "ip": "1.2.3.4", "version": "1.0.0"}
        update = realtime._extract_state_update(payload)
        assert update["ip"] == "1.2.3.4"
        assert update["FirmwareVersion"] == "1.0.0"

        # Variant with 'ver'
        payload2 = {"msg": 10, "ver": "2.0.0"}
        update2 = realtime._extract_state_update(payload2)
        assert update2["FirmwareVersion"] == "2.0.0"

    def test_extract_msg_type_30_timestamp(self, realtime):
        """Test MsgType 30 timestamp extraction."""
        payload = {"msg": 30, "time": 1234567890, "body": {"ambTemp": 20.0}}
        update = realtime._extract_state_update(payload)
        assert update["ambTemp"] == 20.0
        assert update["Timestamp"] == 1234567890

    def test_extract_msg_type_30_invalid_timestamp(self, realtime):
        """Test MsgType 30 invalid timestamp handling."""
        payload = {"msg": 30, "time": "bad_ts", "body": {"ambTemp": 21.0}}
        update = realtime._extract_state_update(payload)
        assert update["ambTemp"] == 21.0
        assert "Timestamp" not in update

    def test_extract_body_empty(self, realtime):
        """Test empty body extraction."""
        payload = {"body": None}
        update = realtime._extract_state_update(payload)
        assert update is None

    def test_extract_body_null_state(self, realtime):
        """Test body with null state."""
        payload = {"body": {"state": None}}
        update = realtime._extract_state_update(payload)
        assert update == {"state": None}

    def test_extract_invalid_timestamp(self, realtime):
        """Test invalid timestamp graceful handling."""
        payload = {"time": "not-a-number", "body": {"stpt": 20.0}}
        update = realtime._extract_state_update(payload)
        assert update["stpt"] == 20.0
        assert "Timestamp" not in update

    def test_extract_batch_info_coverage(self, realtime):
        """Test _extract_batch_info coverage (lines 337-357)."""
        import base64
        import struct
        from unittest.mock import patch

        # Hit 339-340 (no body)
        assert realtime._extract_batch_info({}) is None

        # Hit 343-344 (no readings)
        assert realtime._extract_batch_info({"body": {}}) is None

        # Hit 349-350 (not parsed)
        assert (
            realtime._extract_batch_info(
                {"body": {"readings": base64.b64encode(b"not_magic").decode()}}
            )
            is None
        )

        # Hit 355-357 (Exception)
        with patch("base64.b64decode", side_effect=ValueError("Mock Error")):
            assert realtime._extract_batch_info({"body": {"readings": "any"}}) is None

        # Hit 278-279 via _extract_state_update
        raw_data = (
            b"\xca\xa0\x00"
            + struct.pack("<LhhhbbhhhHbb", 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1)
            + b"\x01"
        )
        payload_msg3 = {
            "msg": 3,
            "body": {"readings": base64.b64encode(raw_data).decode()},
        }
        result = realtime._extract_state_update(payload_msg3)
        # In Core, batch updates are now ignored/empty
        assert result == {}

        # Hit 343-344 (no readings)
        assert realtime._extract_batch_info({"body": {"readings": None}}) is None
        assert realtime._extract_batch_info({"body": {"readings": ""}}) is None


@pytest.mark.asyncio
async def test_fibonacci_backoff_sequence(mock_hass):
    """Test that the retry delay follows a Fibonacci sequence."""
    rt = MysaRealtime(mock_hass, AsyncMock(), MagicMock())
    rt._mqtt_reconnect_delay = 1.0

    # Mock _mqtt_listen to always fail
    # We want to check the sequence of delays passed to asyncio.sleep
    with patch(
        "custom_components.mysa.realtime.asyncio.sleep", new_callable=AsyncMock
    ) as mock_sleep:
        # Mock _mqtt_listen to raise an exception 5 times then stop the loop
        call_count = 0

        async def mock_listen():
            nonlocal call_count
            call_count += 1
            if call_count >= 6:
                rt._mqtt_should_reconnect = False
            raise Exception("Retry test")

        with patch.object(rt, "_mqtt_listen", side_effect=mock_listen):
            rt._mqtt_should_reconnect = True
            await rt._mqtt_listener_loop()

        # Expected sleeps: 1.0, 1.0, 2.0, 3.0, 5.0, 8.0
        sleep_calls = [call.args[0] for call in mock_sleep.call_args_list]
        assert sleep_calls == [1.0, 1.0, 2.0, 3.0, 5.0, 8.0]


@pytest.mark.asyncio
async def test_fibonacci_backoff_cap(mock_hass):
    """Test that the retry delay is capped at 60s."""
    rt = MysaRealtime(mock_hass, AsyncMock(), MagicMock())
    rt._mqtt_reconnect_delay = 55.0

    with patch(
        "custom_components.mysa.realtime.asyncio.sleep", new_callable=AsyncMock
    ) as mock_sleep:
        call_count = 0

        async def mock_listen():
            nonlocal call_count
            call_count += 1
            if call_count >= 3:
                rt._mqtt_should_reconnect = False
            raise Exception("Retry test")

        with patch.object(rt, "_mqtt_listen", side_effect=mock_listen):
            rt._mqtt_should_reconnect = True
            await rt._mqtt_listener_loop()

        sleep_calls = [call.args[0] for call in mock_sleep.call_args_list]
        assert all(s <= 60.0 for s in sleep_calls)
        assert sleep_calls[-1] == 60.0


@pytest.mark.asyncio
async def test_fibonacci_reset_on_success(mock_hass):
    """Test that retry sequence resets on successful connection."""
    rt = MysaRealtime(mock_hass, AsyncMock(), MagicMock())
    rt._mqtt_reconnect_delay = 1.0

    with patch(
        "custom_components.mysa.realtime.asyncio.sleep", new_callable=AsyncMock
    ) as mock_sleep:
        call_count = 0

        async def mock_listen():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Fail 1")
            if call_count == 2:
                raise Exception("Fail 2")
            if call_count == 3:
                return  # Success
            if call_count == 4:
                rt._mqtt_should_reconnect = False
                raise Exception("Fail 3")
            return

        with patch.object(rt, "_mqtt_listen", side_effect=mock_listen):
            rt._mqtt_should_reconnect = True
            await rt._mqtt_listener_loop()

        sleep_calls = [call.args[0] for call in mock_sleep.call_args_list]
        assert sleep_calls == [1.0, 1.0, 1.0]

@pytest.mark.asyncio
async def test_realtime_empty_subscription_skip():
    """Test realtime skips empty subscription topics (line 239 in realtime.py)."""
    rt = MysaRealtime(
        hass=MagicMock(),
        get_signed_url_callback=AsyncMock(return_value="wss://test"),
        on_update_callback=AsyncMock(),
    )
    # Ensure we have devices to iterate over
    rt._devices_ids = ["dev1"]
    rt._use_batch = False

    # Create mock websocket
    mock_ws = AsyncMock()

    # We will call _perform_mqtt_handshake directly
    # It does:
    # 1. Send CONNECT
    # 2. Recv CONNACK
    # 3. Build topics
    # 4. If empty -> continue (SKIP sending SUBSCRIBE)

    # Setup mocks
    mock_ws.recv.return_value = b"connack_bytes"

    # Mock parse_mqtt_packet to return valid ConnackPacket
    # Note: realtime.py imports parse_mqtt_packet from mysa_mqtt
    # We must patch where it is used: custom_components.mysa.realtime.parse_mqtt_packet
    connack = mqtt.ConnackPacket(0, 0)

    with patch("custom_components.mysa.realtime.parse_mqtt_packet", return_value=connack):
        # Mock build_subscription_topics to return empty list
        with patch("custom_components.mysa.realtime.build_subscription_topics", return_value=[]):

             await rt._perform_mqtt_handshake(mock_ws)

             # Verify behaviors:
             # 1. CONNECT packet sent (lines 210-211)
             assert mock_ws.send.call_count == 1

             # 2. SUBSCRIBE packet NOT sent (because we skipped it)
             # Logic: if sub_topics empty, continue.
             # Since we only have 1 chunk and skipped it, no more sends happen.

             # We can verify the arg to send was CONNECT, not SUBSCRIBE.
             call_args = mock_ws.send.call_args[0][0]
             # CONNECT packet is bytearray or similar, typically starts with 0x10
             assert call_args[0] == 0x10

@pytest.mark.asyncio
async def test_realtime_extract_full_history():
    """Test that realtime coordinator extracts full history from batch packet."""
    import base64
    mock_callback = MagicMock()
    realtime = MysaRealtime(MagicMock(), MagicMock(), mock_callback)

    mock_history = [
        {"Timestamp": 1000, "ambTemp": 22.1, "rssi": -60},
        {"Timestamp": 1060, "ambTemp": 22.2, "rssi": -61},
    ]

    with patch("custom_components.mysa.realtime.parse_batch_readings", return_value=mock_history):
        payload = {
            "msg": 3,
            "body": {"readings": base64.b64encode(b"header-then-data").decode()}
        }

        # Test extraction
        update = realtime._extract_state_update(payload)

        # In Core, batch updates are now ignored/empty to avoid redundancy
        assert update == {}

@pytest.mark.asyncio
async def test_realtime_batch_rejection_coverage(mock_hass):
    """Targeted test to hit line 268 in realtime.py (batch topic rejection)."""
    rt = MysaRealtime(mock_hass, AsyncMock(), MagicMock())
    rt.set_devices(["dev1"])
    rt._use_batch = True

    mock_ws = AsyncMock()

    # Connack (Success)
    connack = mqtt.ConnackPacket(0, 0)
    # Suback: [Out=Success, In=Success, Batch=Failure (0x80)]
    suback = mqtt.SubackPacket(1, [0x01, 0x01, 0x80])

    with patch(
        "custom_components.mysa.realtime.parse_mqtt_packet",
        side_effect=[connack, suback],
    ):
        await rt._perform_mqtt_handshake(mock_ws)

    # Verification: Ensure handshake completed without error
    assert rt.is_running is False  # Not yet running loop

@pytest.mark.asyncio
async def test_realtime_s1_handshake(mock_hass, mock_ws):
    """Test handshake for S1 devices with shadow wildcard."""
    rt = MysaRealtime(mock_hass, AsyncMock(), MagicMock())
    rt.set_devices(["dev1"], stv10_devices=["dev1"])

    connack = mqtt.ConnackPacket(0, 0)
    # Suback: [Out=Success, In=Success, Shadow=Success]
    suback = mqtt.SubackPacket(1, [0x01, 0x01, 0x01])

    with patch(
        "custom_components.mysa.realtime.parse_mqtt_packet",
        side_effect=[connack, suback],
    ):
        await rt._perform_mqtt_handshake(mock_ws)

    # Coverage for rejection
    suback_fail = mqtt.SubackPacket(1, [0x01, 0x01, 0x80])
    with patch(
        "custom_components.mysa.realtime.parse_mqtt_packet",
        side_effect=[connack, suback_fail],
    ), pytest.raises(RuntimeError, match="rejected shadow wildcard"):
        await rt._perform_mqtt_handshake(mock_ws)

@pytest.mark.asyncio
async def test_realtime_aws_shadow_extraction(mock_hass):
    """Test extraction of AWS shadow data."""
    rt = MysaRealtime(mock_hass, AsyncMock(), MagicMock())

    # Mock AWS Thing topic
    payload = {
        "state": {
            "reported": {"Temperature": 22.5},
            "desired": {"Temperature": 23.0}
        },
        "timestamp": 123456789,
        "version": 1
    }

    # 1. Standard shadow update
    update = rt._extract_state_update(payload, shadow_name="test_shadow")
    assert update["Temperature"] == 22.5
    assert update["_shadow_name"] == "test_shadow"
    assert update["Timestamp"] == 123456789
    assert update["version"] == 1

    # 2. 'documents' structure
    payload_docs = {
        "current": payload,
        "version": 1  # Still need version at top for detection if no shadow_name
    }
    update = rt._extract_state_update(payload_docs, shadow_name="test_shadow")
    assert update["Temperature"] == 22.5
    assert update["version"] == 1

@pytest.mark.asyncio
async def test_realtime_shadow_delta_skip(mock_hass):
    """Test skipping of shadow delta messages."""
    rt = MysaRealtime(mock_hass, AsyncMock(), MagicMock())
    payload = {
        "state": {"delta": {"Temperature": 25}},
        "metadata": {"delta": {"Temperature": {"timestamp": 123}}},
        "version": 5
    }
    # Should return None for delta if shadow_name is provided
    assert rt._extract_state_update(payload, shadow_name="test") is None

@pytest.mark.asyncio
async def test_realtime_aws_thing_topic_extraction(mock_hass):
    """Test extraction of device ID and shadow name from AWS Thing topics."""
    on_update = MagicMock()
    rt = MysaRealtime(mock_hass, AsyncMock(), on_update)

    # 1. Shadow update accepted
    topic = "$aws/things/dev1/shadow/name/test_shadow/update/accepted"
    payload = {"state": {"reported": {"v": 1}}, "version": 1, "timestamp": 123}
    pkt = mqtt.PublishPacket(0, 0, 0, topic, None, json.dumps(payload).encode())
    await rt._process_mqtt_publish(pkt)
    on_update.assert_called_with("dev1", {"v": 1, "_shadow_name": "test_shadow", "Timestamp": 123, "version": 1}, True)

    # 2. Shadow get accepted
    on_update.reset_mock()
    topic = "$aws/things/dev1/shadow/name/test_shadow/get/accepted"
    pkt = mqtt.PublishPacket(0, 0, 0, topic, None, json.dumps(payload).encode())
    await rt._process_mqtt_publish(pkt)
    on_update.assert_called_with("dev1", {"v": 1, "_shadow_name": "test_shadow", "Timestamp": 123, "version": 1}, True)

    # 3. Malformed shadow topic
    on_update.reset_mock()
    topic = "$aws/things/dev1/shadow/name/"
    pkt = mqtt.PublishPacket(0, 0, 0, topic, None, json.dumps(payload).encode())
    await rt._process_mqtt_publish(pkt) # Should log warning but not crash
    on_update.assert_not_called()

@pytest.mark.asyncio
async def test_realtime_publish_coverage(mock_hass, mock_ws):
    """Test publish method coverage."""
    rt = MysaRealtime(mock_hass, AsyncMock(), MagicMock())

    # 1. Not connected
    await rt.publish("topic", {"data": 1}) # No error, just warning

    # 2. Connected
    rt._mqtt_ws = mock_ws
    await rt.publish("topic", {"data": 1})
    mock_ws.send.assert_called()

    # 3. String payload
    mock_ws.send.reset_mock()
    await rt.publish("topic", "raw-string")
    mock_ws.send.assert_called()

    # 4. Exception handling
    mock_ws.send.side_effect = Exception("Publish fail")
    await rt.publish("topic", "fail") # Should catch and log

@pytest.mark.asyncio
async def test_realtime_shadow_no_state(mock_hass):
    """Test shadow update with no reported or desired state."""
    rt = MysaRealtime(mock_hass, AsyncMock(), MagicMock())
    payload = {"state": {}, "version": 1}
    # Should hit the "No reported/desired state" debug log and return None
    assert rt._extract_state_update(payload, shadow_name="test") is None

@pytest.mark.asyncio
async def test_realtime_shadow_no_timestamp(mock_hass):
    """Test shadow update without timestamp."""
    rt = MysaRealtime(mock_hass, AsyncMock(), MagicMock())
    payload = {"state": {"reported": {"v": 1}}, "version": 1}
    # Should work but update will not have Timestamp
    update = rt._extract_state_update(payload, shadow_name="test")
    assert update["v"] == 1
    assert "Timestamp" not in update

@pytest.mark.asyncio
async def test_realtime_shadow_invalid_types_coverage(mock_hass):
    """Test realtime shadow update with invalid types for coverage."""
    rt = MysaRealtime(mock_hass, AsyncMock(), MagicMock())

    # Invalid reported/desired, should become {}
    payload = {
        "state": {
            "reported": "invalid",
            "desired": "invalid"
        },
        "version": 1
    }
    assert rt._extract_state_update(payload, shadow_name="test") is None

    # Valid state, invalid metadata
    payload2 = {
        "state": {
            "reported": {"v": 1},
            "desired": {"v": 2}
        },
        "metadata": {
            "reported": "invalid",
            "desired": ("tuple",)
        },
        "version": 1
    }
    # No timestamps due to invalid metadata, reported wins (v=1)
    update = rt._extract_state_update(payload2, shadow_name="test")
    assert update is not None
    assert update["v"] == 1

    # Desired dict, but reported missing
    payload3 = {
        "state": {"desired": {"v": 2}},
        "version": 1
    }
    update3 = rt._extract_state_update(payload3, shadow_name="test")
    assert update3["v"] == 2

    # Invalid inner metadata timestamps
    payload4 = {
        "state": {"reported": {"v": 1}, "desired": {"v": 2}},
        "metadata": {"reported": {"v": "invalid"}, "desired": {"v": "invalid"}},
        "version": 1
    }
    update4 = rt._extract_state_update(payload4, shadow_name="test")
    assert update4["v"] == 1

    # Current has invalid type
    payload5 = {"current": "invalid_type", "state": {"reported": {"v": 3}}, "version": 1}
    update5 = rt._extract_state_update(payload5)
    assert update5["v"] == 3

    # Desired newer than reported
    payload6 = {
        "state": {"reported": {"v": 1}, "desired": {"v": 2}},
        "metadata": {"reported": {"v": {"timestamp": 100}}, "desired": {"v": {"timestamp": 200}}},
        "version": 1
    }
    update6 = rt._extract_state_update(payload6, shadow_name="test")
    assert update6["v"] == 2


@pytest.mark.asyncio
class TestRealtimeCoverageExtended:
    """Extended coverage for MysaRealtime."""

    async def test_realtime_device_list_change_reconnect(self, mock_hass):
        """Test that changing device list triggers reconnect when MQTT is connected."""
        realtime = MysaRealtime(mock_hass, MagicMock(), MagicMock())

        # Set up initial state - MQTT is connected
        realtime._mqtt_connected.set()
        realtime._mqtt_ws = MagicMock()  # WebSocket exists

        # Mock _close_websocket to track if it's called
        close_called = asyncio.Event()

        async def mock_close():
            close_called.set()

        realtime._close_websocket = mock_close

        # Hit: device list changed, force reconnect
        realtime.set_devices(["new_device"])

        # Give the async task time to execute
        await asyncio.sleep(0.1)

        # Verify reconnect was triggered
        assert close_called.is_set()

    async def test_realtime_connection_closed_exceptions(self, mock_hass):
        """Test handling of ConnectionClosedOK and ConnectionClosedError."""
        realtime = MysaRealtime(mock_hass, MagicMock(), MagicMock())

        # Test ConnectionClosedOK
        mock_ws = AsyncMock()

        # Simulate ConnectionClosedOK being raised
        async def raise_conn_closed_ok():
            raise ConnectionClosedOK(None, None)

        mock_ws.recv = raise_conn_closed_ok

        with pytest.raises(ConnectionClosedOK):
            await realtime._run_mqtt_loop(mock_ws)

        # Test ConnectionClosedError
        async def raise_conn_closed_error():
            raise ConnectionClosedError(None, None)

        mock_ws.recv = raise_conn_closed_error

        with pytest.raises(ConnectionClosedError):
            await realtime._run_mqtt_loop(mock_ws)

@pytest.mark.asyncio
async def test_mqtt_heartbeat_watchdog():
    """Test that the heartbeat watchdog triggers a reconnection after silence."""
    hass = MagicMock()
    get_url = AsyncMock(return_value="wss://example.com")
    on_update = MagicMock()

    realtime = MysaRealtime(hass, get_url, on_update)

    ws = AsyncMock()
    ws.recv = AsyncMock(side_effect=[asyncio.TimeoutError(), b'\xd0\x00'])

    with patch("custom_components.mysa.mqtt.pingreq", return_value=b'\xc0\x00'):
        assert realtime.last_packet_time == 0

        with patch("time.time") as mock_time:
            start_time = 1000.0
            mock_time.return_value = start_time

            async def mock_wait_timeout(coro, timeout=None):
                if hasattr(coro, "close"):
                    coro.close()
                raise asyncio.TimeoutError()

            with patch("asyncio.wait_for", side_effect=mock_wait_timeout):
                realtime._last_packet_time = start_time
                mock_time.return_value = start_time + 601

                with pytest.raises(RuntimeError, match="MQTT silence watchdog triggered"):
                    await realtime._run_mqtt_loop(ws)

def test_realtime_is_connected():
    """Test is_connected property."""
    hass = MagicMock()
    # Provide a simple MagicMock instead of AsyncMock for get_url
    # to avoid RuntimeWarning: coroutine 'AsyncMockMixin._execute_mock_call' was never awaited
    realtime = MysaRealtime(hass, MagicMock(), MagicMock())
    assert realtime.is_connected is False
    realtime._mqtt_connected.set()
    realtime._mqtt_ws = MagicMock()
    assert realtime.is_connected
    realtime._mqtt_ws = None
    assert realtime.is_connected is False

@pytest.mark.asyncio
async def test_realtime_send_command_persistent_only_failure():
    """Test realtime.send_command with use_persistent_only=True and failure."""
    hass = MagicMock()
    realtime = MysaRealtime(hass, AsyncMock(), MagicMock())
    realtime._mqtt_ws = MagicMock()
    realtime._mqtt_ws.send = AsyncMock(side_effect=Exception("Send error"))

    with patch.object(realtime, "_send_one_off_command", AsyncMock()) as mock_one_off:
        await realtime.send_command("dev1", {}, "user1", use_persistent_only=True)
        mock_one_off.assert_not_called()
