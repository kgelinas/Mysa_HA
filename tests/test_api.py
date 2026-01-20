"""Tests for Mysa API Facade."""
import time
from unittest.mock import MagicMock, AsyncMock, patch, ANY
from typing import Any

import pytest
from custom_components.mysa.mysa_api import MysaApi
from custom_components.mysa.client import MysaClient
from custom_components.mysa.realtime import MysaRealtime

@pytest.fixture
def mock_hass():
    return MagicMock()

@pytest.fixture
def mock_api(mock_hass):
    api = MysaApi.__new__(MysaApi)
    api.hass = mock_hass
    api.client = MagicMock(spec=MysaClient)
    api.client.user_id = "user1"
    api.realtime = MagicMock(spec=MysaRealtime)
    api.realtime.send_command = AsyncMock()
    api.devices = {"dev1": {"type": 4, "Model": "BB-V2", "SupportedCaps": {}}}
    api.states = {"dev1": {}}
    api._last_command_time = {}
    def mock_async_create_task(coro):
        """Close coroutine to avoid unawaited warnings."""
        if hasattr(coro, "close"):
            coro.close()
        return MagicMock()

    api.hass.async_create_task = MagicMock(side_effect=mock_async_create_task)
    api.coordinator_callback = None
    api.upgraded_lite_devices = []

    api._metadata_requested = {}

    # Mock helpers
    # setattr(api, "_update_state_cache", MagicMock(wraps=api._update_state_cache))

    return api

@pytest.mark.asyncio
class TestMysaApi:
    """Test MysaApi facade."""

    def get_cmd_body(self, api):
        """Helper to find the command body from send_command calls."""
        for call in api.realtime.send_command.call_args_list:
            args = call[0]  # (device_id, body, user_id, ...)
            body = args[1]
            if "cmd" in body:
                return body
        return None

    def get_msg_type_body(self, api, msg_type):
        """Helper to find a specific MsgType in send_command calls."""
        for call in api.realtime.send_command.call_args_list:
            args = call[0]
            body = args[1]
            if body.get("MsgType") == msg_type:
                return body
        return None

    async def test_init(self, mock_hass):
        """Test initialization."""
        # Mock dependencies since __init__ instantiates them
        with patch("custom_components.mysa.mysa_api.MysaClient") as mock_client_cls, \
             patch("custom_components.mysa.mysa_api.MysaRealtime") as mock_realtime_cls, \
             patch("custom_components.mysa.mysa_api.ClientSession") as mock_session_cls:

            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session

            api = MysaApi("u", "p", mock_hass)

            assert api.hass == mock_hass
            assert api.username == mock_client_cls.return_value.username
            assert api.password == mock_client_cls.return_value.password

            # Verify sub-components initialized
            mock_client_cls.assert_called_with(mock_hass, "u", "p", mock_session)
            mock_realtime_cls.assert_called_once()

            # Verify callbacks passed to Realtime
            _, kwargs = mock_realtime_cls.call_args
            assert kwargs["get_signed_url_callback"] == mock_client_cls.return_value.get_signed_mqtt_url
            # Check on_update_callback is bound method
            assert kwargs["on_update_callback"] == api._on_mqtt_update  # pylint: disable=comparison-with-callable

    # --- Tests from test_mysa_api_coverage.py ---

    async def test_set_lock(self, mock_api):
        """Test set_lock via HTTP."""
        api = mock_api
        api.client.set_device_setting_http = AsyncMock()

        await api.set_lock("dev1", True)

        api.client.set_device_setting_http.assert_called_with("dev1", {"Lock": 1})
        assert api.states["dev1"]["Lock"]["v"] == 1

        # Verify MsgType 6 (Notify) was sent
        assert self.get_msg_type_body(api, 6) is not None
        assert self.get_msg_type_body(api, 7) is None

    async def test_set_ac_climate_plus(self, mock_api):
        """Test set_ac_climate_plus via HTTP."""
        api = mock_api
        api.client.set_device_setting_http = AsyncMock()
        await api.set_ac_climate_plus("dev1", True)

        api.client.set_device_setting_http.assert_called_with("dev1", {"IsThermostatic": True})
        assert api.states["dev1"]["EcoMode"] is True
        assert self.get_msg_type_body(api, 6) is not None
        assert self.get_msg_type_body(api, 7) is None

    async def test_set_proximity(self, mock_api):
        """Test set_proximity via HTTP."""
        api = mock_api
        api.client.set_device_setting_http = AsyncMock()
        await api.set_proximity("dev1", True)

        api.client.set_device_setting_http.assert_called_with("dev1", {"ProximityMode": True})
        assert api.states["dev1"]["ProximityMode"] is True
        assert self.get_msg_type_body(api, 6) is not None
        assert self.get_msg_type_body(api, 7) is None

    async def test_set_auto_brightness(self, mock_api):
        """Test set_auto_brightness via HTTP."""
        api = mock_api
        api.client.set_device_setting_http = AsyncMock()
        await api.set_auto_brightness("dev1", True)

        api.client.set_device_setting_http.assert_called_with("dev1", {"AutoBrightness": True})
        assert api.states["dev1"]["AutoBrightness"] is True
        assert self.get_msg_type_body(api, 6) is not None
        assert self.get_msg_type_body(api, 7) is None

    async def test_set_min_brightness(self, mock_api):
        """Test set_min_brightness via HTTP."""
        api = mock_api
        api.client.set_device_setting_http = AsyncMock()
        await api.set_min_brightness("dev1", 10)

        api.client.set_device_setting_http.assert_called_with("dev1", {"MinBrightness": 10})
        assert api.states["dev1"]["MinBrightness"] == 10
        assert self.get_msg_type_body(api, 6) is not None
        assert self.get_msg_type_body(api, 7) is None

    async def test_set_max_brightness(self, mock_api):
        """Test set_max_brightness via HTTP."""
        api = mock_api
        api.client.set_device_setting_http = AsyncMock()
        await api.set_max_brightness("dev1", 90)

        api.client.set_device_setting_http.assert_called_with("dev1", {"MaxBrightness": 90})
        assert api.states["dev1"]["MaxBrightness"] == 90
        assert self.get_msg_type_body(api, 6) is not None
        assert self.get_msg_type_body(api, 7) is None

    async def test_ac_helpers(self, mock_api):
        """Test AC helpers."""
        api = mock_api
        api.devices["ac1"] = {"Model": "AC-V1", "SupportedCaps": {"swing": True}}
        assert api.is_ac_device("ac1") is True
        assert api.is_ac_device("dev1") is False
        caps = api.get_ac_supported_caps("ac1")
        assert caps["swing"] is True

    async def test_set_ac_fan_speed(self, mock_api):
        """Test set_ac_fan_speed."""
        api = mock_api
        await api.set_ac_fan_speed("dev1", "low")
        body = self.get_cmd_body(api)
        assert body is not None
        assert body["cmd"][0]["fn"] == 3

        api.realtime.send_command.reset_mock()
        await api.set_ac_fan_speed("dev1", "invalid")
        assert self.get_cmd_body(api) is None

    async def test_set_ac_swing_mode(self, mock_api):
        """Test set_ac_swing_mode."""
        api = mock_api
        await api.set_ac_swing_mode("dev1", "middle")
        body = self.get_cmd_body(api)
        assert body is not None
        assert body["cmd"][0]["ss"] == 6

        api.realtime.send_command.reset_mock()
        await api.set_ac_swing_mode("dev1", "invalid")
        assert self.get_cmd_body(api) is None

    async def test_set_ac_horizontal_swing(self, mock_api):
        """Test set_ac_horizontal_swing."""
        api = mock_api
        await api.set_ac_horizontal_swing("dev1", 2)
        body = self.get_cmd_body(api)
        assert body is not None
        assert body["cmd"][0]["ssh"] == 2

    async def test_magic_upgrade(self, mock_api):
        """Test magic upgrade."""
        api = mock_api
        api.client.async_request = AsyncMock()

        # Success
        assert await api.async_upgrade_lite_device("dev1") is True
        api.client.async_request.assert_called_with("POST", ANY, json={'Model': 'BB-V2-0'})

        # Fail
        api.client.async_request.side_effect = Exception("Fail")
        assert await api.async_upgrade_lite_device("dev1") is False

        # Invalid device
        assert await api.async_upgrade_lite_device("unknown") is False

    async def test_magic_downgrade(self, mock_api):
        """Test magic downgrade."""
        api = mock_api
        api.client.async_request = AsyncMock()

        # Success
        assert await api.async_downgrade_lite_device("dev1") is True
        api.client.async_request.assert_called_with("POST", ANY, json={'Model': 'BB-V2-0-L'})

        # Fail
        api.client.async_request.side_effect = Exception("Fail")
        assert await api.async_downgrade_lite_device("dev1") is False

        # Invalid device
        assert await api.async_downgrade_lite_device("unknown") is False

    async def test_properties_delegation(self, mock_api):
        """Test property delegation."""
        api = mock_api
        api.client.username = "user1"
        api.client.password = "pass1"
        api.client.homes = ["home1"]
        api.client.is_connected = True
        api.realtime.is_running = True

        assert api.username == "user1"
        assert api.password == "pass1"
        assert api.homes == ["home1"]
        assert api.is_connected is True
        assert api.is_mqtt_running is True

        new_devices: dict[str, Any] = {"dev2": {}}
        api.devices = new_devices
        assert api.client.devices == new_devices

    async def test_get_state_stale_filtering(self, mock_api):
        """Test get_state filters stale keys."""
        api = mock_api
        api.client.get_state = AsyncMock(return_value={
            "dev1": {"Lock": 0, "sp": 20, "Online": True}
        })

        # Case 1: No recent command
        api.states = {}
        api._last_command_time = {}
        state = await api.get_state()
        assert state["dev1"]["Lock"] == 0
        assert state["dev1"]["sp"] == 20

        # Case 2: Recent command (< 90s)
        api.states = {"dev1": {"Lock": 1, "sp": 25}}
        api._last_command_time = {"dev1": time.time()}

        state = await api.get_state()
        assert state["dev1"]["Lock"] == 1
        assert state["dev1"]["sp"] == 25
        assert state["dev1"]["Online"] is True

    async def test_mqtt_update_resolution(self, mock_api):
        """Test MQTT update ID resolution."""
        api = mock_api
        api.coordinator_callback = AsyncMock()

        api.devices = {"dev:1": {}}
        state_update = {"v": 1}
        await api._on_mqtt_update("dev1", state_update, resolve_safe_id=True)
        assert api.states["dev:1"]["v"] == 1
        api.coordinator_callback.assert_called()

        api.coordinator_callback.reset_mock()
        await api._on_mqtt_update("unknown", state_update, resolve_safe_id=True)
        api.coordinator_callback.assert_not_called()

    async def test_set_hvac_mode_fallback(self, mock_api):
        """Test set_hvac_mode fallbacks."""
        api = mock_api
        api.devices["ac1"] = {"Model": "AC-V1"}

        # Unknown mode AC -> Defaults to Off (1)
        await api.set_hvac_mode("ac1", "unknown_mode")
        body = self.get_cmd_body(api)
        assert body is not None
        assert body["cmd"][0]["md"] == 1

        # ELV Off -> Defaults to Off (1) for non-AC too?
        # Non-AC logic: mode_val = 1 if "off" in mode_str else 3
        api.realtime.send_command.reset_mock()
        await api.set_hvac_mode("dev1", "off")
        body = self.get_cmd_body(api)
        assert body is not None
        assert body["cmd"][0]["md"] == 1

        # ELV Heat
        api.realtime.send_command.reset_mock()
        await api.set_hvac_mode("dev1", "heat")
        body = self.get_cmd_body(api)
        assert body is not None
        assert body["cmd"][0]["md"] == 3

    # ... (skipping intervening tests) ...

    async def test_set_hvac_mode_ac_all_modes(self, mock_api):
        """Test all HVAC modes for AC device."""
        api = mock_api
        api.devices["ac1"] = {"Model": "AC-V1"}

        # Mapping: cool=4, heat=3, auto=2, dry=6, fan=5, off=1
        modes = {
            "heat_cool": 2,  # Should map to Auto (2)
            "cool": 4,
            "heat": 3,
            "auto": 2,
            "dry": 6,
            "fan_only": 5
        }

        for mode_str, expected_val in modes.items():
            api.realtime.send_command.reset_mock()
            await api.set_hvac_mode("ac1", mode_str)
            body = self.get_cmd_body(api)
            assert body is not None
            assert body["cmd"][0]["md"] == expected_val, f"Failed for {mode_str}"

    async def test_set_ac_off(self, mock_api):
        """Test setting AC mode to off."""
        api = mock_api
        api.devices["ac1"] = {"Model": "AC-V1"}
        await api.set_hvac_mode("ac1", "off")
        body = self.get_cmd_body(api)
        assert body is not None
        assert body["cmd"][0]["md"] == 1

    async def test_update_state_cache_new(self, mock_api):
        """Test update cache for new device."""
        api = mock_api
        api.states = {}
        api._update_state_cache("new_dev", {"v": 1})
        assert api.states["new_dev"]["v"] == 1

    async def test_brightness_helpers_invalid(self, mock_api):
        """Test brightness helper with invalid state data."""
        api = mock_api
        api.states = {"dev1": {"Brightness": "invalid"}}
        br = api._get_brightness_object("dev1")
        assert br["a_br"] == 100

    async def test_update_brightness_cache_new_device(self, mock_api):
        """Test update brightness cache for new device misses self.states."""
        api = mock_api
        api.states = {}
        # This triggers line 436: if device_id not in self.states
        api._update_brightness_cache("device_1", "a_br", 85)

    async def test_lifecycle_delegation(self, mock_api):
        """Test lifecycle methods."""
        api = mock_api

        api.client.authenticate = AsyncMock()
        api.client.get_devices = AsyncMock(return_value={"d1": {}})
        api.client.fetch_homes = AsyncMock()
        api.realtime.start = AsyncMock()
        api.realtime.stop = AsyncMock()

        await api.authenticate()
        api.client.authenticate.assert_called_once()

        await api.get_devices()
        api.client.get_devices.assert_called_once()
        api.realtime.set_devices.assert_called()

        await api.fetch_homes()
        api.client.fetch_homes.assert_called_once()

        api.client.fetch_firmware_info = AsyncMock()
        await api.fetch_firmware_info("dev1")
        api.client.fetch_firmware_info.assert_called_with("dev1")

        api.client.get_electricity_rate = MagicMock()
        api.get_electricity_rate("dev1")
        api.client.get_electricity_rate.assert_called_with("dev1")

        await api.start_mqtt_listener()
        api.realtime.start.assert_called_once()

        await api.stop_mqtt_listener()
        api.realtime.stop.assert_called_once()
        # And not clobber Brightness if it exists (which it doesn't here, but key check passes)

    # --- Merged from original test_api.py ---

    async def test_set_target_temperature(self, mock_api):
        """Test setting target temperature."""
        api = mock_api
        await api.set_target_temperature("dev1", 22.0)

        api.realtime.send_command.assert_called()
        first_call = api.realtime.send_command.call_args_list[0]
        assert first_call.args[0] == "dev1"
        assert first_call.args[1]["cmd"][0]["sp"] == 22.0

    async def test_notify_settings_changed(self, mock_api):
        """Test notify delegation."""
        api = mock_api
        await api.notify_settings_changed("dev1")

        api.realtime.send_command.assert_called()
        kwargs = api.realtime.send_command.call_args.kwargs
        if "msg_type" in kwargs:
            assert kwargs["msg_type"] == 6

    async def test_get_state_merge_explicit(self, mock_api):
        """Test implicit state merge with specific values."""
        api = mock_api
        api.client.get_state.return_value = {
            "d1": {"SetPoint": 20, "Current": 10},
            "d2": {"SetPoint": 22}
        }
        api.states = {"d1": {"SetPoint": 15, "Mode": 1}}
        api._last_command_time = {}

        await api.get_state()

        # d1 merged
        assert api.states["d1"]["SetPoint"] == 20
        assert api.states["d1"]["Current"] == 10
        assert api.states["d1"]["Mode"] == 1
        # d2 added
        assert "d2" in api.states


    async def test_api_delegation_coverage(self, hass):
        """Test missing delegation methods coverage."""
        with patch("custom_components.mysa.mysa_api.MysaClient"), \
             patch("custom_components.mysa.mysa_api.MysaRealtime"):

            api = MysaApi("u", "p", hass)

            api.client.fetch_firmware_info = AsyncMock(return_value={"fw": "1.0"})  # type: ignore[method-assign]
            assert await api.fetch_firmware_info("dev1") == {"fw": "1.0"}

            api.client.get_electricity_rate.return_value = 0.1  # type: ignore[attr-defined]
            assert api.get_electricity_rate("dev1") == 0.1

    async def test_get_electricity_rate_with_custom_override(self, hass):
        """Test get_electricity_rate with custom_erate override from mysa_extended."""
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        with patch("custom_components.mysa.mysa_api.MysaClient"), \
             patch("custom_components.mysa.mysa_api.MysaRealtime"):

            api = MysaApi("u", "p", hass)
            api.client.get_electricity_rate.return_value = 0.15  # type: ignore[attr-defined]

            # No mysa_extended entry → fallback to cloud rate
            assert api.get_electricity_rate("dev1") == 0.15

            # Add mysa_extended entry with custom rate
            extended_entry = MockConfigEntry(
                domain="mysa_extended",
                data={},
                options={"custom_erate": 0.25},
            )
            extended_entry.add_to_hass(hass)

            # Should now return custom rate
            assert api.get_electricity_rate("dev1") == 0.25

            # Empty override → fallback
            hass.config_entries.async_update_entry(extended_entry, options={})
            assert api.get_electricity_rate("dev1") == 0.15

    async def test_async_send_killer_ping_success(self, mock_api):
        """Test async_send_killer_ping success."""
        api = mock_api
        api.realtime.send_command = AsyncMock()
        api.devices = {"dev1": {"Name": "Test"}}
        api.client.user_id = "user1"

        result = await api.async_send_killer_ping("dev1")

        assert result is True
        api.realtime.send_command.assert_called_once()
        call_args = api.realtime.send_command.call_args
        assert call_args.kwargs.get("msg_type") == 5
        assert call_args.kwargs.get("wrap") is False

    async def test_async_send_killer_ping_device_not_found(self, mock_api):
        """Test async_send_killer_ping with unknown device."""
        api = mock_api
        api.devices = {}

        result = await api.async_send_killer_ping("unknown")

        assert result is False

    async def test_async_send_killer_ping_failure(self, mock_api):
        """Test async_send_killer_ping handles exceptions."""
        api = mock_api
        api.realtime.send_command = AsyncMock(side_effect=Exception("MQTT error"))
        api.devices = {"dev1": {"Name": "Test"}}
        api.client.user_id = "user1"

        result = await api.async_send_killer_ping("dev1")

        assert result is False

    async def test_get_electricity_rate_custom_invalid(self, mock_api):
        """Test fetching electricity rate with invalid custom overlap."""
        api = mock_api
        api.client.get_electricity_rate.return_value = 0.15

        # Mock config entry with invalid custom rate
        mock_entry = MagicMock()
        mock_entry.domain = "mysa_extended"
        mock_entry.options = {"custom_erate": "invalid"}
        api.hass.config_entries.async_entries.return_value = [mock_entry]

        rate = api.get_electricity_rate("device1")
        assert rate == 0.15

    async def test_update_request(self, mock_api):
        """Test update_request sends MsgType 7."""
        api = mock_api
        api.realtime.send_command = AsyncMock()
        api.client.user_id = "user1"

        await api.update_request("dev1")

        api.realtime.send_command.assert_called_once()
        args = api.realtime.send_command.call_args
        assert args[0][0] == "dev1"
        payload = args[0][1]
        assert payload["MsgType"] == 7
        assert payload["Device"] == "dev1"
        kwargs = args[1]
        assert kwargs["msg_type"] == 7
        assert kwargs["wrap"] is False

    async def test_start_mqtt_listener_force_refresh(self, mock_api):
        """Test start_mqtt_listener waits for connection and refreshes."""
        api = mock_api
        api.realtime.start = AsyncMock()
        api.realtime.wait_until_connected = AsyncMock(return_value=True)
        api.update_request = AsyncMock()
        api.devices = {"dev1": {}, "dev2": {}}

        await api.start_mqtt_listener()

        api.realtime.start.assert_called_once()
        api.realtime.wait_until_connected.assert_called_once_with(timeout=35.0)
        assert api.update_request.call_count == 2
        api.update_request.assert_any_call("dev1")
        api.update_request.assert_any_call("dev2")

    async def test_start_mqtt_listener_timeout(self, mock_api):
        """Test start_mqtt_listener handles connection timeout."""
        api = mock_api
        api.realtime.start = AsyncMock()
        api.realtime.wait_until_connected = AsyncMock(return_value=False)
        api.update_request = AsyncMock()

        await api.start_mqtt_listener()

        api.realtime.start.assert_called_once()
        api.realtime.wait_until_connected.assert_called_once()
        api.update_request.assert_not_called()

    async def test_mqtt_echo_contamination(self, mock_api):
        """Test that an MQTT echo containing 'br' as a dict does not corrupt the 'br' state (int)."""
        api = mock_api
        api.coordinator_callback = AsyncMock()

        # Scenario: br is echoed as a dict (settings object)
        state_update = {
            "br": {
                "a_b": 0,
                "a_br": 100
            }
        }

        await api._on_mqtt_update("dev_echo", state_update)

        # 1. Check normalization: br dict should be moved to BrightnessSettings
        assert "BrightnessSettings" in api.states["dev_echo"]
        assert api.states["dev_echo"]["BrightnessSettings"]["a_b"] == 0

        # 2. Check that 'br' key is REMOVED or NOT dirtied with the dict
        assert "br" not in api.states["dev_echo"]

        # Verify existing state preservation
        api.states["dev_echo"]["br"] = 50

        state_update_2 = {
            "br": { "a_b": 1 }
        }
        await api._on_mqtt_update("dev_echo", state_update_2)

        # The update dict effectively becomes {"BrightnessSettings": ...}
        # So "br" key is NOT in the update dict, so it doesn't overwrite existing "br": 50
        assert api.states["dev_echo"]["br"] == 50
        assert api.states["dev_echo"]["BrightnessSettings"]["a_b"] == 1

    async def test_brightness_invalid_value(self, mock_api):
        """Test that invalid brightness values are ignored (coverage for ValueError)."""
        api = mock_api
        api.coordinator_callback = AsyncMock()

        # Scenario: br is a string that cannot be cast to int
        state_update = {"br": "invalid"}

        await api._on_mqtt_update("dev_invalid", state_update)

        # (Assuming no prior state)
        assert "Brightness" not in api.states["dev_invalid"]

    async def test_proximity_race_condition(self, mock_api):
        """Test that stale 'px' from cloud is filtered if command was recent."""
        api = mock_api
        api.client.set_device_setting_silent = AsyncMock()

        # Cloud returns stale OFF state using 'px' key
        api.client.get_state = AsyncMock(return_value={
            "dev1": {"px": 0, "ProximityMode": False}
        })

        # Local state is optimistically ON
        api.states = {"dev1": {"ProximityMode": True}}

        # Simulate recent command (0 seconds ago)
        api._last_command_time = {"dev1": time.time()}

        # Trigger get_state which merges cloud data
        await api.get_state()

        # Should remain True if 'px' (and ProximityMode) are filtered
        assert api.states["dev1"]["ProximityMode"] is True

    async def test_mqtt_accepts_all_updates(self, mock_api):
        """Test that MQTT updates are always accepted (trusted real-time source)."""
        api = mock_api
        device_id = "dev1"

        # Simulate recent command
        api._last_command_time = {device_id: time.time()}

        # Incoming MQTT update with keys that would be filtered for HTTP polls
        update = {"br": 123, "ProximityMode": True, "SetPoint": 20}

        # Call _on_mqtt_update
        await api._on_mqtt_update(device_id, update)

        # All keys should be accepted because MQTT is trusted
        assert api.states[device_id].get("Brightness") == 123
        assert api.states[device_id].get("ProximityMode") is True
        assert api.states[device_id].get("SetPoint") == 20

    async def test_all_setters_trigger_coordinator_callback(self, mock_api):
        """Verify that every setter triggers the coordinator callback."""
        api = mock_api
        api.coordinator_callback = AsyncMock()
        api.client.set_device_setting_silent = AsyncMock()

        # Test targets
        setters = [
            (api.set_target_temperature, ("d1", 22.0)),
            (api.set_hvac_mode, ("d1", "heat")),
            (api.set_lock, ("d1", True)),
            (api.set_ac_climate_plus, ("d1", True)),
            (api.set_proximity, ("d1", True)),
            (api.set_auto_brightness, ("d1", True)),
            (api.set_min_brightness, ("d1", 10)),
            (api.set_max_brightness, ("d1", 90)),
        ]

        # AC Specific targets
        api.devices["ac1"] = {"Model": "AC-V1", "SupportedCaps": {}}
        api.states["ac1"] = {}
        setters.extend([
            (api.set_ac_fan_speed, ("ac1", "low")),
            (api.set_ac_swing_mode, ("ac1", "auto")),
            (api.set_ac_horizontal_swing, ("ac1", 1)),
        ])

        for setter_func, args in setters:
            api.coordinator_callback.reset_mock()
            await setter_func(*args)
            assert api.coordinator_callback.called, f"Callback not called for {setter_func.__name__}"
    async def test_proactive_metadata_nudge(self, mock_api):
        """Test that missing firmware/IP triggers a metadata nudge with backoff."""
        api = mock_api
        api.update_request = AsyncMock()
        api.states = {"dev1": {}} # Missing FirmwareVersion and IP

        # 1. First trigger - should nudge
        with patch("time.time", return_value=1000.0):
            await api._on_mqtt_update("dev1", {"temp": 20})
            api.update_request.assert_called_once_with("dev1")
            assert api._metadata_requested["dev1"] == 1000.0

        # 2. Second trigger immediately - should NOT nudge (backoff)
        api.update_request.reset_mock()
        with patch("time.time", return_value=1010.0):
            await api._on_mqtt_update("dev1", {"temp": 21})
            api.update_request.assert_not_called()

        # 3. Third trigger after timeout - should nudge again
        with patch("time.time", return_value=1400.0): # > 300s later
            await api._on_mqtt_update("dev1", {"temp": 22})
            api.update_request.assert_called_once_with("dev1")
            assert api._metadata_requested["dev1"] == 1400.0

        # 4. Device HAS metadata - should NOT nudge
        api.update_request.reset_mock()
        api.states["dev2"] = {"FirmwareVersion": "1.0.0", "ip": "1.2.3.4"}
        await api._on_mqtt_update("dev2", {"temp": 22})
        api.update_request.assert_not_called()
        assert "dev2" not in api._metadata_requested


# --- Merged from test_brightness_logic.py ---

@pytest.fixture
def mock_api_logic(mock_hass):
    """Mock MysaApi instance for logic tests."""
    with patch("custom_components.mysa.mysa_api.ClientSession"):
        api = MysaApi("user", "pass", mock_hass)
        api.devices = {"d1": {"Id": "d1", "Model": "BB-V2"}}
        return api

@pytest.mark.asyncio
async def test_brightness_object_preserves_state(mock_api_logic):
    """Test that _get_brightness_object uses top-level state if dict is missing."""
    mock_api = mock_api_logic
    # Setup state with top-level keys but NO BrightnessSettings dict
    mock_api.states["d1"] = {
        "MaxBrightness": 90,
        "MinBrightness": 36,
        "AutoBrightness": False
    }

    br_obj = mock_api._get_brightness_object("d1")

    # Defaults in old code were a_b:1, a_br:100, i_br:50
    # New code should pick up values from state
    assert br_obj["a_b"] == 0
    assert br_obj["a_br"] == 90
    assert br_obj["i_br"] == 36

@pytest.mark.asyncio
async def test_brightness_object_merges_dict_with_state(mock_api_logic):
    """Test that _get_brightness_object merges existing dict with state fallbacks."""
    mock_api = mock_api_logic
    # Setup state with partial BrightnessSettings dict and some top-level keys
    mock_api.states["d1"] = {
        "BrightnessSettings": {"i_br": 20}, # Explicitly set in dict
        "MaxBrightness": 85,                 # Top-level fallback
        "AutoBrightness": True
    }

    br_obj = mock_api._get_brightness_object("d1")

    assert br_obj["i_br"] == 20
    assert br_obj["a_br"] == 85
    assert br_obj["a_b"] == 1

@pytest.mark.asyncio
async def test_update_state_cache_flattens_brightness_correctly(mock_api_logic):
    """Test that _update_state_cache correctly flattens BrightnessSettings."""
    mock_api = mock_api_logic
    mock_api._update_state_cache("d1", {
        "BrightnessSettings": {"a_b": 0, "a_br": 95, "i_br": 36}
    })

    state = mock_api.states["d1"]
    assert state["AutoBrightness"] is False
    assert state["MaxBrightness"] == 95
    assert state["MinBrightness"] == 36

@pytest.mark.asyncio
async def test_set_max_brightness_preserves_min(mock_api_logic):
    """Integration style test to verify set_max_brightness doesn't reset min."""
    mock_api = mock_api_logic
    with patch.object(mock_api.client, "set_device_setting_http", new_callable=AsyncMock) as mock_http, \
         patch.object(mock_api.realtime, "send_command", new_callable=AsyncMock) as mock_send:
        # Initial state has MinBrightness 36
        mock_api.states["d1"] = {
            "MinBrightness": 36,
            "AutoBrightness": True
        }

        await mock_api.set_max_brightness("d1", 95)

        # Verify HTTP call
        mock_http.assert_called_once_with("d1", {"MaxBrightness": 95})

        # Verify MQTT notify cycle (MsgType 6 only)
        assert mock_send.called
        msg_types = [call[0][1].get("MsgType") for call in mock_send.call_args_list]
        assert 6 in msg_types
        assert 7 not in msg_types # MsgType 7 is for metadata only


# --- Merged from test_api_freshness.py ---

@pytest.mark.asyncio
async def test_mqtt_update_prevents_cloud_overwrite(mock_hass):
    """Test that an MQTT update prevents stale cloud data from overwriting state."""
    api = MysaApi("user", "pass", mock_hass)
    dev_id = "test_dev"
    api.devices = {dev_id: {}}

    # 1. Initial State
    api.states[dev_id] = {"stpt": 20.0, "SetPoint": 20.0}

    # 2. MQTT Update (User sets 24.0)
    # This should update _last_command_time
    await api._on_mqtt_update(dev_id, {"stpt": 24.0, "3": 24.0})

    # Verify State is 24.0
    assert api.states[dev_id]["stpt"] == 24.0
    last_cmd = api._last_command_time.get(dev_id, 0)
    assert last_cmd > 0

    # 3. Simulate Stale Cloud Poll (Cloud still says 20.0)
    # This calls _update_state_cache with filter_stale=True
    # loophole check: ACState
    stale_cloud_data = {
        "stpt": 20.0,
        "SetPoint": 20.0,
        "Mode": 2,
        "ACState": {"3": 20.0} # Nested old temp
    }

    # Using the public update_state_cache via a mock or directly if accessible would be best,
    # but we can verify the logic by calling the method used by get_state:
    api._update_state_cache(dev_id, stale_cloud_data, filter_stale=True)

    # 4. Filter should have BLOCKED the 20.0 overwrite b/c it was stale
    # So state should STILL be 24.0
    assert api.states[dev_id]["stpt"] == 24.0

@pytest.mark.asyncio
async def test_extract_timestamp_invalid(mock_hass):
    """Test timestamp extraction handles invalid values (Cover lines 660-661)."""
    api = MysaApi("user", "pass", mock_hass)

    # 1. Invalid string
    assert api._extract_timestamp({"Timestamp": "invalid"}) is None

    # 2. Invalid nested type (e.g. dict where int expected, though unlikely)
    assert api._extract_timestamp({"time": {}}) is None

    # 3. Valid
    assert api._extract_timestamp({"Timestamp": 12345}) == 12345
    assert api._extract_timestamp({"time": "54321"}) == 54321

@pytest.mark.asyncio
async def test_timestamp_prevents_stale_update_explicit(mock_hass):
    """Test that a newer cached timestamp blocks older incoming updates (Cover line 682)."""
    api = MysaApi("user", "pass", mock_hass)
    dev_id = "test_dev"
    api.devices = {dev_id: {}}

    # 1. Set current state with NEW timestamp (e.g. 2000)
    api.states[dev_id] = {}
    api._latest_timestamp[dev_id] = 2000

    # 2. Try to update with OLD timestamp (e.g. 1000)
    # Should perform early return at line 682
    update_data = {
        "stpt": 25.0,
        "Timestamp": 1000
    }
    api._update_state_cache(dev_id, update_data)

    # Verify 'stpt' was NOT applied
    assert "stpt" not in api.states[dev_id]

    # 3. Try update with SAME timestamp but filter_stale=True
    # Should also return early
    update_data_same = {
        "stpt": 25.0,
        "Timestamp": 2000
    }
    api._update_state_cache(dev_id, update_data_same, filter_stale=True)
    assert "stpt" not in api.states[dev_id]
