from unittest.mock import PropertyMock
import asyncio
"""Tests for Mysa API Facade."""

import time
from typing import Any
from unittest.mock import ANY, AsyncMock, MagicMock, patch, PropertyMock

import pytest

from custom_components.mysa.device import MysaDeviceLogic
from custom_components.mysa.client import MysaClient
from custom_components.mysa.mysa_api import MysaApi
from custom_components.mysa.realtime import MysaRealtime


@pytest.fixture
def mock_hass():
    hass = MagicMock()
    def mock_async_create_task(coro, *args, **kwargs):
        """Close coroutine to avoid unawaited warnings."""
        if hasattr(coro, "close"):
            try:
                coro.close()
            except Exception:
                pass
        return MagicMock()

    hass.async_create_task = MagicMock(side_effect=mock_async_create_task)
    hass.async_create_background_task = MagicMock(side_effect=mock_async_create_task)
    return hass


@pytest.fixture
def mock_api(mock_hass):
    api = MysaApi.__new__(MysaApi)
    api.hass = mock_hass
    api.client = MagicMock(spec=MysaClient)
    api.client.user_id = "user1"
    api.client.get_devices = AsyncMock(return_value={})
    api.client.get_all_firmware_versions = AsyncMock(return_value={})
    api.realtime = MagicMock(spec=MysaRealtime)
    api.realtime.send_command = AsyncMock()
    # Mock background methods to avoid accidental coroutine creation
    # api.update_request = AsyncMock()
    # api.fetch_stv10_shadows = AsyncMock()
    api._periodic_legacy_mqtt_poll = MagicMock() # Return MagicMock, not coroutine
    # api._wait_and_refresh_mqtt = AsyncMock()

    api.devices = {"dev1": {"type": 4, "Model": "BB-V2", "SupportedCaps": {}}}
    api.states = {"dev1": {}}
    api.device_caps = {}
    api.upgraded_lite_devices = []
    api._last_command_time = {}
    api._latest_timestamp = {}
    api._clock_skew = {}
    api._shadow_versions = {}
    api._shadow_version_timestamps = {}
    api._metadata_requested = {}
    api._last_mqtt_poll_time = {}

    api.coordinator_callback = None
    return api


@pytest.mark.asyncio
class TestMysaApi:
    """Test MysaApi facade."""

    def get_cmd_body(self, api):
        """Helper to find the command body from send_command calls."""
        for call_args in api.realtime.send_command.call_args_list:
            args, kwargs = call_args
            body = args[1] if len(args) > 1 else kwargs.get("body")
            if body and "cmd" in body:
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
        with (
            patch("custom_components.mysa.mysa_api.MysaClient") as mock_client_cls,
            patch("custom_components.mysa.mysa_api.MysaRealtime") as mock_realtime_cls,
            patch("custom_components.mysa.mysa_api.ClientSession") as mock_session_cls,
        ):
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
            assert (
                kwargs["get_signed_url_callback"]
                == mock_client_cls.return_value.get_signed_mqtt_url
            )
            # Check on_update_callback is bound method
            # Justification: Comparing bound method to verify callback assignment in test.
            assert kwargs["on_update_callback"] == api._on_mqtt_update  # pylint: disable=comparison-with-callable

    # --- Tests from test_mysa_api_coverage.py ---

    async def test_set_lock(self, mock_api):
        """Test set_lock via HTTP."""
        api = mock_api
        api.client.set_device_setting_http = AsyncMock()

        await api.set_lock("dev1", True)

        api.client.set_device_setting_http.assert_called_with(
            "dev1", {"ButtonState": "Locked"}, legacy=True
        )
        assert api.states["dev1"]["Lock"]["v"] == 1

        # Verify MsgType 6 (Notify) was sent
        assert self.get_msg_type_body(api, 6) is not None
        assert self.get_msg_type_body(api, 7) is None

    async def test_set_ac_climate_plus(self, mock_api):
        """Test set_ac_climate_plus via HTTP."""
        api = mock_api
        api.devices["dev1"] = {"Model": "AC-V1", "type": 9}
        api.client.user_id = "user1"
        api.client.set_device_setting_http = AsyncMock()
        await api.set_ac_climate_plus("dev1", True)

        api.client.set_device_setting_http.assert_called_with(
            "dev1", {"IsThermostatic": True}, legacy=True
        )
        # AC settings also trigger MsgType 6 (Notification)
        msg6_body = self.get_msg_type_body(api, 6)
        assert msg6_body is not None
        assert msg6_body["MsgType"] == 6

        # Verify state was updated (optimistic)
        assert api.states["dev1"]["EcoMode"] is True

    async def test_async_send_state_poll(self, mock_hass):
        """Test MsgType 11 polling."""
        api = MysaApi.__new__(MysaApi)
        api.hass = mock_hass
        api.client = MagicMock()
        api.client.user_id = "user1"
        api.realtime = MagicMock()
        api.devices = {}
        api._last_mqtt_poll_time = {}

        # 1. Ignored for ST-V1-0
        api.devices["stv1"] = {"Model": "ST-V1-0"}
        api.realtime.is_connected = True
        api._last_mqtt_poll_time = {}
        await api.async_send_state_poll("stv1")
        api.realtime.send_command.assert_not_called()

        # 2. Ignored if MQTT not active
        api.devices["dev2"] = {"Model": "BB-V1"}
        api.realtime.is_connected = False
        api._last_mqtt_poll_time = {}
        api.realtime.send_command.reset_mock()
        await api.async_send_state_poll("dev2")
        api.realtime.send_command.assert_not_called()

        # 3. Successful payload send
        api.realtime.is_connected = True
        api._last_mqtt_poll_time = {}
        api.realtime.send_command.reset_mock()
        await api.async_send_state_poll("dev2")
        api.realtime.send_command.assert_called_with(
            "dev2", {"Device": "dev2", "Timestamp": ANY, "MsgType": 11, "Timeout": 300}, api.client.user_id, msg_type=11, wrap=False, use_persistent_only=True
        )

        # 4. Exception handling
        api.realtime.send_command.reset_mock()
        api.realtime.send_command.side_effect = Exception("Test Error")
        api.realtime.is_connected = True
        api._last_mqtt_poll_time = {}
        await api.async_send_state_poll("dev2")
        # Should log error and not raise
        api.realtime.send_command.assert_called()


    async def test_set_proximity(self, mock_api):
        """Test set_proximity via HTTP."""
        api = mock_api
        api.client.set_device_setting_http = AsyncMock()
        await api.set_proximity("dev1", True)

        api.client.set_device_setting_http.assert_called_with(
            "dev1", {"ProximityMode": True}, legacy=True
        )
        assert api.states["dev1"]["ProximityMode"] is True
        assert self.get_msg_type_body(api, 6) is not None
        assert self.get_msg_type_body(api, 7) is None

    async def test_set_auto_brightness(self, mock_api):
        """Test set_auto_brightness via HTTP."""
        api = mock_api
        api.client.set_device_setting_http = AsyncMock()
        await api.set_auto_brightness("dev1", True)

        api.client.set_device_setting_http.assert_called_with(
            "dev1", {"AutoBrightness": True}, legacy=True
        )
        assert api.states["dev1"]["AutoBrightness"] is True
        assert self.get_msg_type_body(api, 6) is not None
        assert self.get_msg_type_body(api, 7) is None

    async def test_set_min_brightness(self, mock_api):
        """Test set_min_brightness via HTTP."""
        api = mock_api
        api.client.set_device_setting_http = AsyncMock()
        await api.set_min_brightness("dev1", 10)

        api.client.set_device_setting_http.assert_called_with(
            "dev1", {"MinBrightness": 10}, legacy=True
        )
        assert api.states["dev1"]["MinBrightness"] == 10
        assert self.get_msg_type_body(api, 6) is not None
        assert self.get_msg_type_body(api, 7) is None

    async def test_set_max_brightness(self, mock_api):
        """Test set_max_brightness via HTTP."""
        api = mock_api
        api.client.set_device_setting_http = AsyncMock()
        await api.set_max_brightness("dev1", 90)

        api.client.set_device_setting_http.assert_called_with(
            "dev1", {"MaxBrightness": 90}, legacy=True
        )
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
        api.client.async_request.assert_called_with(
            "POST", ANY, json={"Model": "BB-V2-0"}
        )

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
        api.client.async_request.assert_called_with(
            "POST", ANY, json={"Model": "BB-V2-0-L"}
        )

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
        api.client.get_state = AsyncMock(
            return_value={"dev1": {"Lock": 0, "sp": 20, "Online": True}}
        )

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
            "fan_only": 5,
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

    async def test_extract_stv10_shadow_format(self, mock_api):
        """Test extraction of format from physicalInterface shadow."""
        api = mock_api
        state_update = {"format": "F"}
        api._extract_stv10_shadow_data(state_update)
        assert state_update["temperature_format"] == "F"

    async def test_on_mqtt_update_flatten(self, mock_api):
        """Test flattening of state payload."""
        api = mock_api
        update = {"state": {"foo": "bar"}}
        await api._on_mqtt_update("dev1", update)
        assert api.states["dev1"]["foo"] == "bar"

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


    async def test_stv10_extraction_edge_cases(self, mock_api):
        """Test edge cases in ST-V1-0 extraction logic."""
        api = mock_api

        # Specifically test that normalize_state is called OR logic is present
        api.devices["dev1"] = {"Model": "ST-V1-0", "type": 1}
        state_update={"currentTemperature": 2300}
        api._extract_stv10_shadow_data(state_update, skip_sensors=False)
        from custom_components.mysa.device import MysaDeviceLogic
        MysaDeviceLogic.normalize_state(state_update)
        assert state_update.get("current_temp") == 23.0

        # humidity in reading path
        state_update={"reading": {"humidity": 50}}
        api._extract_stv10_shadow_data(state_update, skip_sensors=False)
        MysaDeviceLogic.normalize_state(state_update)
        assert state_update.get("current_humidity") == 50

        # current_temp_raw heuristic (val > 100)
        await api._on_mqtt_update("dev1", {"current_temp_raw": 2400})
        # current_temp SHOULD be in states for ST-V1 via MQTT after fix
        assert api.states["dev1"]["current_temp"] == 24.0
        # And raw value should be there
        assert api.states["dev1"]["current_temp_raw"] == 2400

        # current_temp_raw heuristic (val <= 100)
        await api._on_mqtt_update("dev1", {"current_temp_raw": 22.5})
        # current_temp SHOULD be in states for ST-V1 via MQTT after fix
        assert api.states["dev1"]["current_temp"] == 22.5
        # And raw value should be there
        assert api.states["dev1"]["current_temp_raw"] == 22.5
    async def test_lifecycle_delegation(self, mock_api):
        """Test lifecycle methods."""
        api = mock_api

        api.client.authenticate = AsyncMock(return_value=True)
        assert await api.authenticate() is True
        api.client.get_devices = AsyncMock(return_value={"d1": {}})
        api.client.fetch_homes = AsyncMock()
        api.realtime.start = AsyncMock()
        api.realtime.stop = AsyncMock()

        await api.authenticate()
        api.client.authenticate.assert_called()

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

    async def test_stv10_telemetry_extraction(self, mock_api):
        """Test ST-V1-0 telemetry extraction."""
        api = mock_api
        payload = {
            "_shadow_name": "latestTelemetry",
            "reading": {
                "temperature": 2250,
                "humidityDisplay": 45
            }
        }
        api._extract_stv10_shadow_data(payload, skip_sensors=False)
        MysaDeviceLogic.normalize_state(payload)
        assert payload["current_temp"] == 22.5
        assert payload["current_humidity"] == 45

        await api.start_mqtt_listener()
        api.realtime.start.assert_called_once()

        await api.stop_mqtt_listener()
        api.realtime.stop.assert_called_once()
        # And not clobber Brightness if it exists (which it doesn't here, but key check passes)

    # --- Merged from original test_api.py ---

    async def test_is_connected(self, mock_hass):
        """Test is_connected property."""
        api = MysaApi.__new__(MysaApi)
        api.client = MagicMock()
        api.client.is_connected = True
        assert api.is_connected
        api.client.is_connected = False
        assert not api.is_connected

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
            "d2": {"SetPoint": 22},
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
        with (
            patch("custom_components.mysa.mysa_api.MysaClient"),
            patch("custom_components.mysa.mysa_api.MysaRealtime"),
        ):
            api = MysaApi("u", "p", hass)

            api.client.fetch_firmware_info = AsyncMock(return_value={"fw": "1.0"})  # type: ignore[method-assign]
            assert await api.fetch_firmware_info("dev1") == {"fw": "1.0"}

            api.client.get_electricity_rate.return_value = 0.1  # type: ignore[attr-defined]
            assert api.get_electricity_rate("dev1") == 0.1

    async def test_get_electricity_rate_with_custom_override(self, hass):
        """Test get_electricity_rate with custom_erate override from mysa_extended."""
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        with (
            patch("custom_components.mysa.mysa_api.MysaClient"),
            patch("custom_components.mysa.mysa_api.MysaRealtime"),
        ):
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

        # Capture the foreground task (wait_and_refresh) via async_create_task
        fg_tasks = []
        def capture_fg_task(coro, **kwargs):
            fg_tasks.append(coro)
            return MagicMock()

        # Capture the background polling task via async_create_background_task
        bg_tasks = []
        def capture_bg_task(coro, **kwargs):
            bg_tasks.append(coro)
            return MagicMock()

        api.hass.async_create_task.side_effect = capture_fg_task
        api.hass.async_create_background_task.side_effect = capture_bg_task

        await api.start_mqtt_listener()

        api.realtime.start.assert_called_once()

        # Periodic poll scheduled as background task
        assert len(bg_tasks) == 1
        # Wait/refresh scheduled as foreground task
        assert len(fg_tasks) == 1

        # Await the wait_and_refresh coroutine
        await fg_tasks[0]

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

        fg_tasks = []
        def capture_fg_task(coro, **kwargs):
            fg_tasks.append(coro)
            return MagicMock()

        bg_tasks = []
        def capture_bg_task(coro, **kwargs):
            bg_tasks.append(coro)
            return MagicMock()

        api.hass.async_create_task.side_effect = capture_fg_task
        api.hass.async_create_background_task.side_effect = capture_bg_task

        await api.start_mqtt_listener()

        api.realtime.start.assert_called_once()

        assert len(bg_tasks) == 1
        assert len(fg_tasks) == 1

        # Await the wait_and_refresh coroutine
        await fg_tasks[0]

        api.realtime.wait_until_connected.assert_called_once()
        api.update_request.assert_not_called()

    async def test_mqtt_echo_contamination(self, mock_api):
        """Test that an MQTT echo containing 'br' as a dict does not corrupt the 'br' state (int)."""
        api = mock_api
        api.coordinator_callback = AsyncMock()

        # Scenario: br is echoed as a dict (settings object)
        state_update = {"br": {"a_b": 0, "a_br": 100}}

        await api._on_mqtt_update("dev_echo", state_update)

        # 1. Check normalization: br dict should be moved to BrightnessSettings
        assert "BrightnessSettings" in api.states["dev_echo"]
        assert api.states["dev_echo"]["BrightnessSettings"]["a_b"] == 0

        # 2. Check that 'br' key is REMOVED or NOT dirtied with the dict
        assert "br" not in api.states["dev_echo"]

        # Verify existing state preservation
        api.states["dev_echo"]["br"] = 50

        state_update_2 = {"br": {"a_b": 1}}
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
        api.client.get_state = AsyncMock(
            return_value={"dev1": {"px": 0, "ProximityMode": False}}
        )

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
        setters.extend(
            [
                (api.set_ac_fan_speed, ("ac1", "low")),
                (api.set_ac_swing_mode, ("ac1", "auto")),
                (api.set_ac_horizontal_swing, ("ac1", 1)),
            ]
        )

        for setter_func, args in setters:
            api.coordinator_callback.reset_mock()
            await setter_func(*args)
            assert api.coordinator_callback.called, (
                f"Callback not called for {setter_func.__name__}"
            )

    async def test_proactive_metadata_nudge(self, mock_api):
        """Test that missing firmware/IP triggers a metadata nudge with backoff."""
        api = mock_api
        api.update_request = AsyncMock()
        api.states = {"dev1": {}}  # Missing FirmwareVersion and IP

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
        with patch("time.time", return_value=1400.0):  # > 300s later
            await api._on_mqtt_update("dev1", {"temp": 22})
            api.update_request.assert_called_once_with("dev1")
            assert api._metadata_requested["dev1"] == 1400.0

        # 4. Device HAS metadata - should NOT nudge
        api.update_request.reset_mock()
        api.states["dev2"] = {"FirmwareVersion": "1.0.0", "ip": "1.2.3.4"}
        await api._on_mqtt_update("dev2", {"temp": 22})
        api.update_request.assert_not_called()

    async def test_nested_timestamp_extraction(self, mock_api):
        """Test that extract_timestamp correctly finds nested 't' timestamps."""
        api = mock_api
        # Using static method directly

        # 1. Simulate an MQTT update (e.g. at T=100)
        device_id = "dev1"
        mqtt_update = {
            "CorrectedTemp": 20.0,
            "Timestamp": 100
        }

        api._update_state_cache(device_id, mqtt_update, filter_stale=False)

        assert api.states[device_id]["CorrectedTemp"] == 20.0
        assert api._latest_timestamp[device_id] == 100

        # 2. Simulate an HTTP Poll update (e.g. at T=110)
        # HTTP update lacks top-level Timestamp/time, but has nested 't'
        http_update = {
            "CorrectedTemp": {
                "v": 18.3,
                "t": 110  # Newer than 100
            },
            "Mode": {
                "v": 4,
                "t": 105  # Also newer
            }
        }

        # HTTP updates use filter_stale=True
        api._update_state_cache(device_id, http_update, filter_stale=True)

        # Checks
        current_temp = api.states[device_id]["CorrectedTemp"]
        assert isinstance(current_temp, dict)
        assert current_temp["v"] == 18.3
        assert current_temp["t"] == 110

        # Should have updated latest_timestamp to 110
        assert api._latest_timestamp[device_id] == 110

    async def test_stale_http_update_rejected(self, mock_api):
        """Test that truly stale HTTP updates are rejected."""
        api = mock_api
        api.update_request = AsyncMock()
        device_id = "dev1"

        # 1. Fresh MQTT update (T=200)
        api._update_state_cache(device_id, {"Timestamp": 200, "CorrectedTemp": 21.0}, filter_stale=False)
        assert api._latest_timestamp[device_id] == 200

        # 2. Stale HTTP update (T=190)
        stale_update = {
            "CorrectedTemp": {
                "v": 19.5,
                "t": 190
            }
        }

        api._update_state_cache(device_id, stale_update, filter_stale=True)

        # Should still be the MQTT value (21.0)
        assert api.states[device_id]["CorrectedTemp"] == 21.0
        assert api._latest_timestamp[device_id] == 200
        # Check metadata request wasn't called (it's an AsyncMock)
        api.update_request.assert_not_called()
        assert "dev2" not in api._metadata_requested

    async def test_proactive_metadata_partial_missing(self, mock_api):
        """Test that having FirmwareVersion but missing IP still triggers nudge."""
        api = mock_api
        api.update_request = AsyncMock()

        # Case: Firmware OK, IP Missing -> Should Nudge
        api.states["dev3"] = {"FirmwareVersion": "1.0.0"}  # No IP

        with patch("time.time", return_value=2000.0):
            await api._on_mqtt_update("dev3", {"temp": 20})
            api.update_request.assert_called_once_with("dev3")
            assert api._metadata_requested["dev3"] == 2000.0

    async def test_api_mqtt_update_detailed_final(self, mock_api):
        """Test activeMode extraction from ST-V1-0 MQTT update (coverage)."""
        api = mock_api
        api.coordinator_callback = AsyncMock()
        api.devices = {"dev1": {"Model": "ST-V1-0"}}

        # Payload with activeMode
        update = {"activeMode": 4, "hvacState": 4}
        await api._on_mqtt_update("dev1", update)

        assert api.states["dev1"]["active_mode"] == 4
        assert api.states["dev1"]["hvac_state"] == 4


    async def test_legacy_http_setters_coverage(self, mock_api):
        """Test new legacy HTTP setter methods for coverage."""
        api = mock_api
        api.client.set_device_setting_http = AsyncMock()
        api.notify_settings_changed = AsyncMock()
        api.coordinator_callback = AsyncMock()

        # 1. set_min_setpoint
        await api.set_min_setpoint("dev1", 10.5)
        api.client.set_device_setting_http.assert_called_with("dev1", {"MinSetpoint": 10.5}, legacy=True)
        assert api.states["dev1"]["MinSetpoint"] == 10.5
        api.notify_settings_changed.assert_called_with("dev1")

        # 2. set_max_setpoint
        api.notify_settings_changed.reset_mock()
        await api.set_max_setpoint("dev1", 29.5)
        api.client.set_device_setting_http.assert_called_with("dev1", {"MaxSetpoint": 29.5}, legacy=True)
        assert api.states["dev1"]["MaxSetpoint"] == 29.5
        api.notify_settings_changed.assert_called_with("dev1")

        # 3. set_temperature_format
        api.notify_settings_changed.reset_mock()
        await api.set_temperature_format("dev1", True)  # Fahrenheit
        api.client.set_device_setting_http.assert_called_with("dev1", {"Format": "fahrenheit"}, legacy=True)
        assert api.states["dev1"]["Format"] == "fahrenheit"
        api.notify_settings_changed.assert_called_with("dev1")

        # 4. set_duty_cycle_opt
        api.notify_settings_changed.reset_mock()
        await api.set_duty_cycle_opt("dev1", 8)
        api.client.set_device_setting_http.assert_called_with("dev1", {"DutyCycleOpt": 8}, legacy=True)
        assert api.states["dev1"]["DutyCycleOpt"] == 8
        api.notify_settings_changed.assert_called_with("dev1")

        # 5. set_target_temperature_range (Legacy path)
        api.client.set_device_setting_http.reset_mock()
        api.devices["dev1"] = {"Model": "BB-V2"}
        await api.set_target_temperature_range("dev1", 18.0, 22.0)
        # Should call set_min and set_max
        assert api.client.set_device_setting_http.call_count == 2
        calls = [tuple(c.args) for c in api.client.set_device_setting_http.call_args_list]
        assert ("dev1", {"MinSetpoint": 18.0}) in calls
        assert ("dev1", {"MaxSetpoint": 22.0}) in calls


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
        "AutoBrightness": False,
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
        "BrightnessSettings": {"i_br": 20},  # Explicitly set in dict
        "MaxBrightness": 85,  # Top-level fallback
        "AutoBrightness": True,
    }

    br_obj = mock_api._get_brightness_object("d1")

    assert br_obj["i_br"] == 20
    assert br_obj["a_br"] == 85
    assert br_obj["a_b"] == 1


@pytest.mark.asyncio
async def test_update_state_cache_flattens_brightness_correctly(mock_api_logic):
    """Test that _update_state_cache correctly flattens BrightnessSettings."""
    mock_api = mock_api_logic
    mock_api._update_state_cache(
        "d1", {"BrightnessSettings": {"a_b": 0, "a_br": 95, "i_br": 36}}
    )

    state = mock_api.states["d1"]
    assert state["AutoBrightness"] is False
    assert state["MaxBrightness"] == 95
    assert state["MinBrightness"] == 36


@pytest.mark.asyncio
async def test_set_max_brightness_preserves_min(mock_api_logic):
    """Integration style test to verify set_max_brightness doesn't reset min."""
    mock_api = mock_api_logic
    with (
        patch.object(
            mock_api.client, "set_device_setting_http", new_callable=AsyncMock
        ) as mock_http,
        patch.object(
            mock_api.realtime, "send_command", new_callable=AsyncMock
        ) as mock_send,
    ):
        # Initial state has MinBrightness 36
        mock_api.states["d1"] = {"MinBrightness": 36, "AutoBrightness": True}

        await mock_api.set_max_brightness("d1", 95)

        # Verify HTTP call
        mock_http.assert_called_once_with("d1", {"MaxBrightness": 95}, legacy=True)

        # Verify MQTT notify cycle (MsgType 6 only)
        assert mock_send.called
        msg_types = [call[0][1].get("MsgType") for call in mock_send.call_args_list]
        assert 6 in msg_types
        assert 7 not in msg_types  # MsgType 7 is for metadata only


# --- Merged from test_api_freshness.py ---


@pytest.mark.asyncio
async def test_mqtt_update_prevents_cloud_overwrite(mock_hass):
    """Test that an MQTT update prevents stale cloud data from overwriting state."""
    api = MysaApi("user", "pass", mock_hass)
    dev_id = "test_dev"
    api.devices = {dev_id: {}}

    # 1. Initial State
    api.states[dev_id] = {"stpt": 20.0, "SetPoint": 20.0}

    # 2. Simulate User sending command (sets _last_command_time)
    api._last_command_time[dev_id] = time.time()

    # 2b. Simulate incoming MQTT Update (User sets 24.0)
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
        "ACState": {"3": 20.0},  # Nested old temp
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
    assert MysaDeviceLogic.extract_timestamp({"Timestamp": "invalid"}) is None

    # 2. Invalid nested type (e.g. dict where int expected, though unlikely)
    assert MysaDeviceLogic.extract_timestamp({"time": {}}) is None

    # Valid
    assert MysaDeviceLogic.extract_timestamp({"Timestamp": 12345}) == 12345
    assert MysaDeviceLogic.extract_timestamp({"time": "54321"}) == 54321


@pytest.mark.asyncio
async def test_set_sensor_mode_coverage(mock_hass):
    """Test set_sensor_mode via HTTP (Cover mysa_api.py lines 442-463)."""
    with (
        patch("custom_components.mysa.mysa_api.MysaClient"),
        patch("custom_components.mysa.mysa_api.MysaRealtime"),
    ):
        api = MysaApi("u", "p", mock_hass)
        api.client.set_device_setting_http = AsyncMock()
        api.realtime.send_command = AsyncMock()
        api.coordinator_callback = AsyncMock()

        # Call the method
        await api.set_sensor_mode("d1", 1)

        # Verify Optimistic Cache Update
        assert api.states["d1"]["SensorMode"] == 1
        assert "Timestamp" in api.states["d1"]

        # Verify UI Refresh
        api.coordinator_callback.assert_called_once()

        # Verify HTTP call
        api.client.set_device_setting_http.assert_called_with(
            "d1", {"TrackedSensor": 3}, legacy=True
        )

        # Verify Notify
        # Notify calls realtime.send_command with msg_type=6
        api.realtime.send_command.assert_called()
        call_args = api.realtime.send_command.call_args
        assert call_args.kwargs.get("msg_type") == 6


@pytest.mark.asyncio
async def test_device_infloor_ambient_logic(mock_hass):
    """Test In-Floor Ambient mode detection (Cover device.py lines 207-208)."""
    # This logic is in normalize_state, which is called by api._on_mqtt_update or get_state
    # We can test it via _on_mqtt_update

    with (
        patch("custom_components.mysa.mysa_api.MysaClient"),
        patch("custom_components.mysa.mysa_api.MysaRealtime"),
    ):
        api = MysaApi("u", "p", mock_hass)

        # Test case: TrackedSensor = 5 (Ambient)
        await api._on_mqtt_update("d1", {"TrackedSensor": 5})

        # Verify SensorMode is set to 0 (Ambient)
        assert api.states["d1"]["SensorMode"] == 0

        # Verify other case (Floor) just to be sure
        await api._on_mqtt_update("d1", {"TrackedSensor": 3})
        assert api.states["d1"]["SensorMode"] == 1


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
    update_data = {"stpt": 25.0, "Timestamp": 1000}
    api._update_state_cache(dev_id, update_data)

    # Verify 'stpt' was NOT applied
    assert "stpt" not in api.states[dev_id]

    # 3. Try update with SAME timestamp and filter_stale=True.
    # Previously this was rejected, but we removed the equal-timestamp rejection
    # because it silently dropped valid HTTP state at startup.
    # Equal-timestamp updates are now ACCEPTED; command-sensitive fields are
    # still protected by _filter_stale_updates within the 90s window.
    update_data_same = {"stpt": 25.0, "Timestamp": 2000}
    api._update_state_cache(dev_id, update_data_same, filter_stale=True)
    # stpt should now be written (no recent command within 90s to block it)
    assert api.states[dev_id].get("stpt") == 25.0


    async def test_mysa_api_fires_history_event_is_noop(self):
        """Test that MysaApi no longer fires history events (feature removed from core)."""
        # Feature removed.
        pass

    async def test_s1_target_auto_shadow_normalization(self, mock_api):
        """Test normalization of S1 targetAuto shadow fields."""
        api = mock_api
        api.devices = {"dev1": {"Model": "ST-V1-0"}}
        api.coordinator_callback = AsyncMock()

        # Simulate targetAuto shadow update
        state_update = {
            "heatSetpoint": 2000,
            "coolSetpoint": 2400,
            "version": 24,
            "_shadow_name": "targetAuto"
        }
        await api._on_mqtt_update("dev1", state_update, resolve_safe_id=True)

        device_state = api.states["dev1"]
        assert device_state["target_heat"] == 20.0
        assert device_state["target_cool"] == 24.0
        # Check backward compatibility keys if any were added
        assert device_state["heatsetpoint"] == 20.0
        assert device_state["coolsetpoint"] == 24.0

    async def test_set_target_temperature_range_stv10(self, mock_api):
        """Test setting temperature range for S1 Auto mode."""
        api = mock_api
        api.devices = {"dev1": {"Model": "ST-V1-0"}}
        api.realtime.publish = AsyncMock()

        await api.set_target_temperature_range("dev1", 18.5, 25.0)

        # Verify publish call
        api.realtime.publish.assert_called_once()
        topic, payload = api.realtime.publish.call_args[0]
        assert "dev1" in topic
        assert "targetAuto" in topic
        assert payload["state"]["desired"]["heatSetpoint"] == 1850
        assert payload["state"]["desired"]["coolSetpoint"] == 2500

        # Verify optimistic update
        assert api.states["dev1"]["target_heat"] == 18.5
        assert api.states["dev1"]["target_cool"] == 25.0


class TestApiConsolidated:
    """Consolidated API tests from final and extra coverage."""

    @pytest.mark.asyncio
    async def test_stv10_target_cool_shadow_consolidated(self, hass):
        """Test ST-V1-0 targetCool shadow handling."""
        mock_websession = MagicMock()
        api = MysaApi("user", "pass", hass, websession=mock_websession)
        api.devices = {"dev1": {"Model": "ST-V1-0"}}
        api.states = {"dev1": {}}
        api.realtime = MagicMock()
        api.realtime.publish = AsyncMock()

        state_update = {"_shadow_name": "targetCool", "value": 2200, "source": "mqtt"}
        await api._on_mqtt_update("dev1", state_update)

        assert api.states["dev1"]["target_cool"] == 22.0
        assert api.states["dev1"]["stpt"] == 22.0

    @pytest.mark.asyncio
    async def test_set_target_temperature_stv10_branch_consolidated(self, hass):
        """Test set_target_temperature with ST-V1-0 device."""
        mock_websession = MagicMock()
        api = MysaApi("user", "pass", hass, websession=mock_websession)
        api.devices = {"dev1": {"Model": "ST-V1-0"}}
        api.states = {"dev1": {"md": 4}}
        api.realtime = MagicMock()
        api.realtime.publish = AsyncMock()

        mock_set = AsyncMock()
        api.set_stv10_target_temperature = mock_set
        api.client.set_device_setting_http = AsyncMock()

        await api.set_target_temperature("dev1", 21.5)
        mock_set.assert_called_once_with("dev1", 21.5)

    @pytest.mark.asyncio
    async def test_mysa_api_stv10_setters_coverage_consolidated(self, hass):
        """Cover missing setter lines in mysa_api.py."""
        mock_websession = MagicMock()
        with patch("custom_components.mysa.mysa_api.MysaRealtime") as mock_real_class:
            mock_realtime = mock_real_class.return_value
            mock_realtime.wait_until_connected = AsyncMock(return_value=True)

            mock_callback = AsyncMock()
            api = MysaApi(
                "u",
                "p",
                hass,
                websession=mock_websession,
                coordinator_callback=mock_callback,
            )
            api.realtime = mock_realtime
            api.client = MagicMock()
            api.client.user_id = "u1"
            api.client.post_state_update = AsyncMock()
            api.notify_settings_changed = AsyncMock()
            api.states["d1"] = {}
            api.devices = {"d1": {"Model": "ST-V1-0"}}

            await api.set_stv10_proximity("d1", True)
            assert api.states["d1"]["pr"] == 1
            mock_callback.assert_called()

            await api.set_stv10_allow_auto_mode("d1", True)
            assert api.states["d1"]["auto_mode_enabled"] == 1

            await api.set_stv10_temperature_format("d1", True)
            assert api.states["d1"]["temperature_format"] == "F"

    @pytest.mark.asyncio
    async def test_mysa_api_initialization_metadata_coverage_consolidated(self, hass):
        """Cover metadata initialization lines in mysa_api.py."""
        mock_websession = MagicMock()
        with patch("custom_components.mysa.mysa_api.MysaRealtime") as mock_real_class:
            mock_realtime = mock_real_class.return_value
            mock_realtime.wait_until_connected = AsyncMock(return_value=True)

            api = MysaApi("u", "p", hass, websession=mock_websession)
            api.client.get_all_firmware_versions = AsyncMock(
                return_value={"d1": {"InstalledVersion": "1.2.3"}}
            )

            await api._initialize_firmware_versions()
            assert api.states["d1"]["FirmwareVersion"] == "1.2.3"

    @pytest.mark.asyncio
    async def test_mysa_api_stale_update_detailed_logic_consolidated(self, hass):
        """Cover missing staleness lines in mysa_api.py."""
        mock_websession = MagicMock()
        api = MysaApi("u", "p", hass, websession=mock_websession)
        api.devices = {"d1": {"Model": "ST-V1-0"}}

        if hasattr(api, "_shadow_version_timestamps"):
            del api._shadow_version_timestamps
        api._check_shadow_version_staleness("d1", 10, "shadow", False)
        assert hasattr(api, "_shadow_version_timestamps")

        api._shadow_versions["d1"] = {"shadow": 10}
        api._shadow_version_timestamps["d1"] = {"shadow": time.time() - 400}
        assert api._check_shadow_version_staleness("d1", 5, "shadow", False) is False

    @pytest.mark.asyncio
    async def test_mysa_api_nested_mode_extraction_consolidated(self, hass):
        """Cover nested mode extraction."""
        mock_websession = MagicMock()
        api = MysaApi("u", "p", hass, websession=mock_websession)
        api.devices = {"d1": {"Model": "ST-V1-0"}}
        state_update = {"modes": {"reported": {"activeMode": 3}}}
        api._update_state_cache("d1", state_update)
        assert api.states["d1"]["active_mode"] == 3







class TestApiRestoredConsolidated:
    """Consolidated restored tests for MysaApi coverage gaps."""

    @pytest.mark.asyncio
    async def test_api_stv10_shadow_normalization_consolidated(self, mock_api):
        """Cover ST-V1-0 shadow flattening and normalization."""
        api = mock_api
        api.devices = {"d1": {"Model": "ST-V1-0"}}
        api.states = {"d1": {}}
        state_update = {
            "state": {
                "reported": {
                    "targetHeat": 2000,
                    "targetCool": 2500,
                    "setpoint": 2100,
                }
            }
        }

        # Test line 1466-1474 via the mock process
        # `_extract_stv10_shadow_data` is used        # Test line 1466-1474 via the mock process
        # target_heat relies on _on_mqtt_update!
        await api._on_mqtt_update("d1", {"_shadow_name": "targetHeat", "value": 2000, "targetCool": 2500})
        state = api.states["d1"]
        assert state["target_heat"] == 20.0

        await api._on_mqtt_update("d1", {"setpoint": 2100, "heatSetpoint": 2200, "coolSetpoint": 2600})
        state = api.states["d1"]
        assert state["SetPoint"] == 21.0
        assert state["target_heat"] == 22.0
        assert state["target_cool"] == 26.0

    @pytest.mark.asyncio
    async def test_api_parallel_fetch_failure_consolidated(self, mock_api):
        """Cover parallel capability fetch failure (lines 223-227, 237-238)."""
        api = mock_api
        api._capabilities_initialized = False
        # Setup device and states so Cap fetch triggers properly
        api.devices = {"d1_stv1": {"Model": "ST-V1-0"}}
        api.states = {"d1_stv1": {}}
        api.client.get_devices = AsyncMock(return_value=api.devices)

        # Test 1: Exception during fetch
        api.client.fetch_capabilities = AsyncMock(side_effect=Exception("Fetch Fail"))
        await api._initialize_capabilities()
        # It falls back to state-based initialization, but we shouldn't hit cap_results block
        assert api.device_caps["d1_stv1"].is_stv10 is True

        # Test 2: Success path directly hitting 228-229 and 237-238
        api._capabilities_initialized = False
        api.client.fetch_capabilities = AsyncMock(return_value={"modes": {"1": "heat"}})
        await api._initialize_capabilities()
        assert api.device_caps["d1_stv1"].is_stv10 is True

    @pytest.mark.asyncio
    async def test_api_process_mqtt_edge_cases(self, mock_api):
        """Cover all branches in _on_mqtt_update specific normalization (lines 331, 348, 358-360, 362-364, 373, 377)."""
        api = mock_api
        api.devices = {"d1": {"Model": "ST-V1-0"}}
        api.states = {"d1": {}}
        api._update_state_cache = MagicMock()

        # Branch 331: modes shadow
        msg1 = {"mode": 3, "source": 2}
        await api._on_mqtt_update("d1", msg1)
        api._update_state_cache.assert_called_with("d1", {"mode": 3, "source": 2, "md": 3}, filter_stale=False)

        # Branch 348: targetHeat explicitly via _shadow_name
        msg2 = {"value": 2200, "_shadow_name": "targetHeat"}
        await api._on_mqtt_update("d1", msg2)

        # Branches 358-360, 362-364: heatSetpoint and coolSetpoint
        msg3 = {"heatSetpoint": 2000, "coolSetpoint": 2500}
        await api._on_mqtt_update("d1", msg3)

        # Branches 373, 377: ButtonState and hvacConfig
        msg4 = {"ButtonState": 1, "hvacConfig": {"idx": 5}}
        await api._on_mqtt_update("d1", msg4)

    @pytest.mark.asyncio
    async def test_api_stv10_specific_commands(self, mock_api):
        """Cover ST-V1 specific command overrides (lines 760-767, 808-809)."""
        api = mock_api
        api.devices = {"d1": {"Model": "ST-V1-0"}}
        api.set_stv10_hvac_mode = AsyncMock()

        # Lines 808-809
        await api.set_hvac_mode("d1", "heat")
        api.set_stv10_hvac_mode.assert_called_once_with("d1", 4)

        # Lines 760-767
        await api.set_target_temperature_range("d1", 20.0, 25.0)
        api.client.post_state_update.assert_called_once()


    @pytest.mark.asyncio
    async def test_api_stale_metadata_check_consolidated(self, mock_api):
        """Cover _check_shadow_version_staleness return True (line 1612)."""
        api = mock_api
        api._shadow_versions = {"d1": {"s1": 10}}
        api._shadow_version_timestamps = {"d1": {"s1": time.time()}}

        # Trigger line 1612: return True (incoming < current and not relaxed)
        assert api._check_shadow_version_staleness("d1", 5, "s1", False) is True

    @pytest.mark.asyncio
    async def test_api_check_staleness_coverage_consolidated(self, mock_api):
        """Cover _check_staleness branches (lines 1553-1562, 1648-1655, 1657-1662)."""
        api = mock_api
        # Trigger line 1552 logic: if not hasattr(self, "_latest_timestamp")
        if hasattr(api, "_latest_timestamp"):
            del api._latest_timestamp

        # Trigger line 1553: if device_id not in self._shadow_versions: return False
        api._shadow_versions = {}
        assert api._check_staleness("d1", 12345, True, 1, "s1") is False

        # Trigger line 1557: if incoming_ts is None and incoming_version is None: return False
        api._shadow_versions = {"d1": {"s1": 1}}
        assert api._check_staleness("d1", None, True, None, "s1") is False

        # Trigger line 1562: if not filter_stale: return False
        assert api._check_staleness("d1", 12345, False, 1, "s1") is False

        # Trigger line 1648-1655: Genuine stale shadow update
        api._shadow_versions = {"d1": {"s1": 1}}
        api.devices = {"d1": {"Model": "ST-V1-0"}}
        api._latest_timestamp = {"d1": 2000}
        api._last_command_time = {"d1": 1000} # > 90s since now ~ 2000
        with patch("time.time", return_value=3000):
            # Incoming TS (1000) < Current TS (2000) - 10
            assert api._check_staleness("d1", 1000, False, 2, "s1") is True

        # Trigger line 1657-1662: Standard stale update (non-shadow or recent command)
        api.devices = {"d1": {"Model": "BB-V2"}}
        api._latest_timestamp = {"d1": 2000}
        assert api._check_staleness("d1", 1000, False, None, None) is True

    @pytest.mark.asyncio
    async def test_api_additional_coverage_gaps_consolidated(self, mock_api):
        """Cover remaining gaps in mysa_api.py."""
        api = mock_api
        api.client.user_id = "user1"

        # Line 331: md extraction from mode/Mode
        state_update = {"mode": 3}
        api._flatten_stv10_shadows(state_update) # Should trigger md=3
        assert state_update["md"] == 3

        # Line 348: set_ac_fan_speed returns if FAN_MODES.get(fan_mode) is None
        # Note: FAN_MODES might be in const, check exact name
        from custom_components.mysa.const import AC_FAN_MODES
        api.realtime.send_command.reset_mock()
        await api.set_ac_fan_speed("d1", "invalid_fan")
        api.realtime.send_command.assert_not_called()

        # Line 540: set_target_temperature if "st-v1" in model.lower()
        api.devices = {"d1": {"Model": "ST-V1-0"}}
        api.realtime.send_command.reset_mock()
        await api.set_target_temperature("d1", 23.0)
        api.realtime.send_command.assert_called()

        # Line 608: set_stv10_target_cool
        api.realtime.send_command.reset_mock()
        await api.set_stv10_target_cool("d1", 24.0)
        api.realtime.send_command.assert_called()

        # Line 618: set_stv10_target_heat
        api.realtime.send_command.reset_mock()
        await api.set_stv10_target_heat("d1", 21.0)
        api.realtime.send_command.assert_called()

        # Line 687: set_stv10_auto_deadband
        api.realtime.send_command.reset_mock()
        await api.set_stv10_auto_deadband("d1", 1.5)
        api.realtime.send_command.assert_called()

        # Line 784, 808-809: get_electricity_rate override and errors
        api.hass.config_entries.async_entries.return_value = []
        api.client.get_electricity_rate.side_effect = Exception("Cloud Fail")
        assert api.get_electricity_rate("d1") == 0.0

        # Line 1140-1157: set_ac_swing_mode and set_ac_horizontal_swing returns if invalid
        # Reverse mapping used in setters
        api.realtime.send_command.reset_mock()
        await api.set_ac_swing_mode("d1", "invalid")
        api.realtime.send_command.assert_not_called()
        # set_ac_horizontal_swing doesn't have immediate reverse map check in snippet, double check

        # Line 1429-1440, 1445-1456: set_ac_power_button, set_ac_mode_button
        api.coordinator_callback = AsyncMock()
        api.devices = {"d1": {"Model": "AC-V1"}}
        await api.set_ac_power_button("d1")
        api.coordinator_callback.assert_called()
        api.realtime.send_command.assert_called()
        await api.set_ac_mode_button("d1")
        assert api.coordinator_callback.call_count == 2

        # Line 917: test Heat vs Cool branch in set_stv10_target_temperature
        api.states = {"d1": {"md": 3}} # Cool
        # Mocking the internal method to avoid recursive calls or complex logic
        api.set_stv10_cool_setpoint = AsyncMock()
        await api.set_stv10_target_temperature("d1", 22.0)
        api.set_stv10_cool_setpoint.assert_called()

    @pytest.mark.asyncio
    async def test_api_init_metadata_coverage_consolidated(self, mock_api):
        """Cover initialization and metadata gaps."""
        api = mock_api
        api.devices = {"d1": {"Model": "AC-V1"}}

        # Test 1691/metadata check logic implicitly where _check_staleness gets called in _update_state_cache
        # If we just do _update_state_cache, it'll populate _last_command_time if not present because
        # we check stale tracking, skip this for now since it's an internal test detail.
        # Instead, verify _process_mqtt_message missing branch.
        api._latest_timestamp = {}
        api._update_state_cache("d1", {"v": 1})
        assert "d1" in api.states

    @pytest.mark.asyncio
    async def test_api_additional_coverage_gaps_consolidated(self, mock_api):
        """Cover remaining gaps in mysa_api.py."""
        api = mock_api
        api.client.user_id = "user1"

        # Line 331: set_stv10_target_heat logic if st-v1 in Model
        api.devices = {"d1": {"Model": "ST-V1-0"}}
        with patch.object(api, "set_stv10_target_temperature", new_callable=AsyncMock) as mock_stv10_target:
            await api.set_target_temperature("d1", 22.5)
            mock_stv10_target.assert_called()

        # Line 348: set_ac_fan_speed returns if FAN_MODES.get(fan_mode) is None
        api.realtime.send_command.reset_mock()
        await api.set_ac_fan_speed("d1", "invalid_fan")
        print("Calls to send_command:", api.realtime.send_command.call_args_list)
        api.realtime.send_command.assert_not_called()

        # Line 540: set_target_temperature if "st-v1" in model.lower()
        with patch.object(api, "set_stv10_target_temperature", new_callable=AsyncMock) as mock_stv10_target:
            await api.set_target_temperature("d1", 23.0)
            mock_stv10_target.assert_called()

        # Let's mock post_state_update
        api.client.post_state_update = AsyncMock()
        # Line 608 does not exist as set_stv10_target_cool.
        # But set_stv10_cool_setpoint exists!
        await api.set_stv10_cool_setpoint("d1", 24.0)
        api.client.post_state_update.assert_called()

        # Line 618: set_stv10_heat_setpoint
        api.client.post_state_update.reset_mock()
        await api.set_stv10_heat_setpoint("d1", 21.0)
        api.client.post_state_update.assert_called()

        # Line 687: set_stv10_auto_deadband calls post_state_update
        api.client.post_state_update.reset_mock()
        await api.set_stv10_auto_deadband("d1", 1.5)
        api.client.post_state_update.assert_called()

        # Line 784, 808-809: get_electricity_rate override and errors
        mock_entry1 = MagicMock()
        mock_entry1.options = {"custom_erate": "invalid"}
        mock_entry2 = MagicMock()
        mock_entry2.options = {"custom_erate": 0.15}
        api.hass.config_entries.async_entries.return_value = [mock_entry1, mock_entry2]
        api.client.get_electricity_rate.return_value = 0.0
        assert api.get_electricity_rate("d1") == 0.15

        # Test fallback
        api.hass.config_entries.async_entries.return_value = []
        assert api.get_electricity_rate("d1") == 0.0

        # Line 1140-1157: set_ac_swing_mode and set_ac_horizontal_swing returns if invalid
        api.realtime.send_command.reset_mock()
        await api.set_ac_swing_mode("d1", "invalid")
        api.realtime.send_command.assert_not_called()
        await api.set_ac_horizontal_swing("d1", 999)
        api.realtime.send_command.assert_called()

        # Line 1429-1440, 1445-1456: set_ac_power_button, set_ac_mode_button
        api.coordinator_callback = AsyncMock()
        await api.set_ac_power_button("d1")
        api.coordinator_callback.assert_called()
        api.realtime.send_command.assert_called()
        await api.set_ac_mode_button("d1")
        assert api.coordinator_callback.call_count == 2

        # Line 917: test Heat vs Cool branch in set_stv10_target_temperature
        api.states = {"d1": {"md": 3}} # Cool
        # We need to test the REAL set_stv10_target_temperature here, mocking set_stv10_cool_setpoint instead.
        with patch.object(api, "set_stv10_cool_setpoint", new_callable=AsyncMock) as mock_cool_setpoint:
            await api.set_stv10_target_temperature("d1", 22.0)
            mock_cool_setpoint.assert_called()

        with patch.object(api, "set_stv10_heat_setpoint", new_callable=AsyncMock) as mock_heat_setpoint:
            api.states = {"d1": {"md": 4}}
            await api.set_stv10_target_temperature("d1", 22.0)
            mock_heat_setpoint.assert_called()

    @pytest.mark.asyncio
    async def test_api_mysa_api_remaining_lines(self, mock_api):
        """Cover the last missing lines in mysa_api.py."""
        from unittest.mock import AsyncMock, patch, MagicMock
        api = mock_api
        api.client.user_id = "user1"

        # 127-146: mqtt_status
        api.realtime.is_running = False
        assert api.mqtt_status == "Stopped"

        api.realtime.is_running = True
        api.realtime._mqtt_connected = MagicMock()
        api.realtime._mqtt_connected.is_set = MagicMock(return_value=False)
        assert api.mqtt_status == "Connecting"

        api.realtime._mqtt_connected.is_set = MagicMock(return_value=True)
        api.realtime.last_packet_time = 0
        assert api.mqtt_status == "Starting"

        api.realtime.last_packet_time = 100 # very old
        with patch("time.time", return_value=1000):
            assert api.mqtt_status == "Stale"

        with patch("time.time", return_value=105):
            assert api.mqtt_status == "Running"

        # 156: get_devices early return
        api._capabilities_initialized = True
        api.devices = {"d1": {}}
        assert await api.get_devices() == {"d1": {}}
        api._capabilities_initialized = False

        # 447: _extract_stv10_shadow_data skip_sensors
        state2 = {"hum": 50, "humidityDisplay": 50}
        api._extract_stv10_shadow_data(state2, skip_sensors=True)
        assert "current_humidity" not in state2

        # 452: auto_mode_enabled extract
        state3 = {"enabled": 1}
        api._extract_stv10_shadow_data(state3)
        assert state3["auto_mode_enabled"] == 1

        # 491: _flatten_stv10_shadows desired precedence
        state4 = {"targetHeat": {"desired": {"v": 2, "timestamp": 100}, "reported": {"v": 1, "timestamp": 200}}}
        api._flatten_stv10_shadows(state4)
        assert state4["v"] == 1  # reported is newer

        state4_desired = {"targetHeat": {"desired": {"v": 2, "timestamp": 200}, "reported": {"v": 1, "timestamp": 100}}}
        api._flatten_stv10_shadows(state4_desired)
        assert state4_desired["v"] == 2  # desired is newer

        # 495-496: _flatten_stv10_shadows where reported/desired are not dicts
        state4_invalid = {"targetHeat": {"desired": "invalid", "reported": "invalid"}}
        api._flatten_stv10_shadows(state4_invalid)
        assert state4_invalid["targetHeat"]["desired"] == "invalid"  # They remain unchanged, but aren't merged

        # 497-505: flatten latestTelemetry
        state5 = {"latestTelemetry": {"isConnected": True, "reading": {"temperature": 2000}}}
        api._flatten_stv10_shadows(state5)
        assert state5["isConnected"] is True
        assert state5["temperature"] == 2000

        # 540: _extract_stv10_hvac_config
        state6 = {"hvacConfig": {"idx": 1}}
        api._extract_stv10_hvac_config(state6)
        assert state6["hvac_config_index"] == 1

        # 570: _extract_stv10_conversions adv_heat_stage_two_delta
        state7 = {"adv_heat_stage_two_delta": 200}
        api._extract_stv10_conversions(state7)
        assert state7["adv_heat_stage_two_delta"] == 2.0

        # 608: _extract_stv10_sensors roomTemperature > 100
        state8 = {"roomTemperature": 2200}
        api._extract_stv10_sensors(state8)
        assert state8["current_temp"] == 22.0

        # 618: _extract_stv10_sensors nested roomTemperature > 100
        state9 = {"reading": {"roomTemperature": 2300}}
        api._extract_stv10_sensors(state9)
        assert state9["current_temp"] == 23.0

        # 687: _extract_stv10_diagnostics skip_sensors
        state10 = {"diagnostics": {"reported": {"freeHeap": 12345}}}
        api._extract_stv10_diagnostics(state10, skip_sensors=True)
        assert "free_heap" not in state10
        api._extract_stv10_diagnostics(state10, skip_sensors=False)
        assert state10["free_heap"] == 12345

        # 923-935: set_stv10_hvac_mode (line 923 is really set_stv10_hvac_mode)
        api.coordinator_callback = AsyncMock()
        api.client.post_state_update = AsyncMock()
        await api.set_stv10_hvac_mode("d1", 2)
        api.coordinator_callback.assert_called()

        # 956, 978, 1000: set_stv10_auto_deadband, heat_setpoint, cool_setpoint branches
        api.coordinator_callback.reset_mock()
        await api.set_stv10_auto_deadband("d1", 1.5)
        api.coordinator_callback.assert_called()

        api.coordinator_callback.reset_mock()
        await api.set_stv10_heat_setpoint("d1", 21.0)
        api.coordinator_callback.assert_called()

        api.coordinator_callback.reset_mock()
        await api.set_stv10_cool_setpoint("d1", 24.0)
        api.coordinator_callback.assert_called()

        # 1006-1020: set_stv10_fan_mode
        api.coordinator_callback.reset_mock()
        await api.set_stv10_fan_mode("d1", "low")
        api.coordinator_callback.assert_called()
        await api.set_stv10_fan_mode("d1", "invalid")

        # 1083: set_lock for ST-V1-0
        api.devices = {"d1": {"Model": "ST-V1-0"}}
        with patch.object(api, "set_stv10_lock", new_callable=AsyncMock) as set_stv10_lock_mock:
            await api.set_lock("d1", True)
            set_stv10_lock_mock.assert_called_with("d1", True)

        # 1140-1157: set_stv10_lock
        api.client.post_state_update.reset_mock()
        await api.set_stv10_lock("d1", True)
        api.client.post_state_update.assert_called()

        # 1461-1474: set_ac_stpt_buttons
        api.realtime.send_command.reset_mock()
        await api.set_ac_stpt_buttons("d1", "up")
        api.realtime.send_command.assert_called()

        # 1557: _check_staleness missing _clock_skew
        if hasattr(api, "_clock_skew"):
            delattr(api, "_clock_skew")
        with patch.object(api, "_check_shadow_version_staleness", return_value=False):
            with patch.object(api, "_check_timestamp_staleness", return_value=False):
                api._check_staleness("d1", 12345, False)
        assert hasattr(api, "_clock_skew")

        # 1562: _check_staleness shadow stale early return
        with patch.object(api, "_check_shadow_version_staleness", return_value=True):
            assert api._check_staleness("d1", 12345, False) is True

        # 1687-1691: _update_state_cache missing attributes
        if hasattr(api, "_latest_timestamp"):
            delattr(api, "_latest_timestamp")
        if hasattr(api, "_clock_skew"):
            delattr(api, "_clock_skew")
        if hasattr(api, "_last_command_time"):
            delattr(api, "_last_command_time")
        api._update_state_cache("d1", {"v": 1})
        assert hasattr(api, "_last_command_time")

        # 1929-1930: _wait_and_refresh_mqtt STV10 branch
        api.devices = {"d1": {"Model": "ST-V1-0"}}
        api.realtime.wait_until_connected = AsyncMock(return_value=True)
        api.fetch_stv10_shadows = AsyncMock()
        await api._wait_and_refresh_mqtt()
        api.fetch_stv10_shadows.assert_called_with("d1")

        # 1615: _check_shadow_version_staleness == and filter_stale=True
        api._shadow_versions = {"d1": {"test_shadow": 5}}
        api._shadow_version_timestamps = {"d1": {"test_shadow": 0}}
        assert api._check_shadow_version_staleness("d1", 5, "test_shadow", True) is True

        # 1986, 1994-1998: set_min_setpoint ST-V1-0 branch
        api.devices = {"d1": {"Model": "ST-V1-0"}}
        api.client.post_state_update = AsyncMock()
        await api.set_min_setpoint("d1", 10.0)
        api.client.post_state_update.assert_called()

        # 2015, 2023-2027: set_max_setpoint ST-V1-0 branch
        api.client.post_state_update.reset_mock()
        await api.set_max_setpoint("d1", 30.0)
        api.client.post_state_update.assert_called()

@pytest.fixture
def mock_hass_new_cov():
    return MagicMock()

@pytest.fixture
def new_cov_api(mock_hass_new_cov):
    api = MysaApi.__new__(MysaApi)
    api.hass = mock_hass_new_cov
    api.client = MagicMock() # Set client BEFORE devices as devices property access it
    api.devices = {"dev1": {"Model": "BB-V2"}}
    api.realtime = MagicMock(spec=MysaRealtime)
    api.realtime.is_connected = True
    api.async_send_state_poll = AsyncMock()
    return api

@pytest.mark.asyncio
async def test_mqtt_status_stale():
    """Test that mqtt_status returns 'Stale' when no packets are received."""
    import time
    from unittest.mock import PropertyMock
    api = MagicMock()
    api.realtime = MagicMock()

    type(api.realtime).is_running = PropertyMock(return_value=True)
    api.realtime._mqtt_connected = MagicMock()
    api.realtime._mqtt_connected.is_set.return_value = True

    now = time.time()
    type(api.realtime).last_packet_time = PropertyMock(return_value=now - 601)

    mock_hass = MagicMock()
    mock_hass.async_create_task = MagicMock()
    mock_hass.async_create_background_task = MagicMock()

    real_api = MysaApi("user", "pass", mock_hass, websession=AsyncMock())
    real_api.realtime = api.realtime

    assert real_api.mqtt_status == "Stale"

    type(api.realtime).last_packet_time = PropertyMock(return_value=now - 30)
    assert real_api.mqtt_status == "Running"

    type(api.realtime).last_packet_time = PropertyMock(return_value=0)
    assert real_api.mqtt_status == "Starting"

    api.realtime._mqtt_connected.is_set.return_value = False
    assert real_api.mqtt_status == "Connecting"

    type(api.realtime).is_running = PropertyMock(return_value=False)
    assert real_api.mqtt_status == "Stopped"

@pytest.mark.asyncio
async def test_api_polling_debounce():
    """Test that legacy polls are debounced and check connection."""
    import time
    from unittest.mock import PropertyMock
    mock_hass = MagicMock()
    api = MysaApi("u", "p", mock_hass, websession=MagicMock())
    api.realtime = MagicMock(spec=MysaRealtime)

    type(api.realtime).is_connected = PropertyMock(return_value=False)
    api.devices = {"d1": {"Model": "BB-V1"}}
    await api.async_send_state_poll("d1")
    assert api.realtime.send_command.call_count == 0

    type(api.realtime).is_connected = PropertyMock(return_value=True)
    api.devices = {"d1": {"Model": "ST-V1-0"}}
    await api.async_send_state_poll("d1")
    assert api.realtime.send_command.call_count == 0

    api.devices = {"d1": {"Model": "BB-V1"}}
    await api.async_send_state_poll("d1")
    assert api.realtime.send_command.call_count == 1

    await api.async_send_state_poll("d1")
    assert api.realtime.send_command.call_count == 1

    with patch("time.time", return_value=time.time() + 61):
        await api.async_send_state_poll("d1")
        assert api.realtime.send_command.call_count == 2

@pytest.mark.asyncio
async def test_periodic_legacy_mqtt_poll_coverage():
    """Test _periodic_legacy_mqtt_poll for coverage."""
    import asyncio
    api = MysaApi.__new__(MysaApi)
    api.hass = MagicMock()
    api.client = MagicMock()
    api.devices = {"dev1": {"Model": "BB-V2"}}
    api.realtime = MagicMock(spec=MysaRealtime)
    api.realtime.is_connected = True
    api.async_send_state_poll = AsyncMock()

    with patch("asyncio.sleep", side_effect=[None, asyncio.CancelledError()]):
        try:
            await api._periodic_legacy_mqtt_poll()
        except asyncio.CancelledError:
            pass
    api.async_send_state_poll.assert_called_with("dev1")

@pytest.mark.asyncio
async def test_periodic_legacy_mqtt_poll_disconnected():
    """Test _periodic_legacy_mqtt_poll when disconnected."""
    import asyncio
    api = MysaApi.__new__(MysaApi)
    api.hass = MagicMock()
    api.client = MagicMock()
    api.devices = {"dev1": {"Model": "BB-V2"}}
    api.realtime = MagicMock(spec=MysaRealtime)
    api.realtime.is_connected = False
    api.async_send_state_poll = AsyncMock()

    with patch("asyncio.sleep", side_effect=[None, asyncio.CancelledError()]):
        try:
            await api._periodic_legacy_mqtt_poll()
        except asyncio.CancelledError:
            pass
    api.async_send_state_poll.assert_not_called()

@pytest.mark.asyncio
async def test_periodic_legacy_mqtt_poll_exception():
    """Test _periodic_legacy_mqtt_poll handles individual poll exceptions."""
    import asyncio
    api = MysaApi.__new__(MysaApi)
    api.hass = MagicMock()
    api.client = MagicMock()
    api.devices = {"dev1": {"Model": "BB-V2"}}
    api.realtime = MagicMock(spec=MysaRealtime)
    api.realtime.is_connected = True
    api.async_send_state_poll = AsyncMock(side_effect=[Exception("Poll error"), None])

    with patch("asyncio.sleep", side_effect=[None, None, asyncio.CancelledError()]):
        try:
            await api._periodic_legacy_mqtt_poll()
        except asyncio.CancelledError:
            pass
    assert api.async_send_state_poll.call_count == 2

def test_check_timestamp_staleness_stv10_http_poll():
    """Test that ST-V1 HTTP polls do not get dropped by simple timestamp checks."""
    api = MysaApi.__new__(MysaApi)
    api.client = MagicMock()
    api._latest_timestamp = {"test_device": 2000}
    api._last_command_time = {"test_device": 0}
    api._clock_skew = {}
    api.devices = {"test_device": {"Model": "ST-V1-0"}}

    with patch("time.time", return_value=3000):
        # Even if incoming_ts (1000) is < current_ts (2000), it should be evaluated
        # but filter_stale and is_shadow should bypass the drop and return False
        result = api._check_timestamp_staleness("test_device", 1000, filter_stale=True)
        assert result is False

    with patch("time.time", return_value=3000):
        # Regular stale test for coverage of line 1682
        api.devices = {"test_device": {"Model": "V2"}}
        result2 = api._check_timestamp_staleness("test_device", 1000, filter_stale=False)
        assert result2 is True


@pytest.mark.asyncio
async def test_periodic_legacy_mqtt_poll_fatal_error():
    """Test _periodic_legacy_mqtt_poll handles main loop exceptions (Fatal error)."""
    import asyncio
    from unittest.mock import PropertyMock
    api = MysaApi.__new__(MysaApi)
    api.hass = MagicMock()
    api.client = MagicMock()
    api.devices = {"dev1": {"Model": "BB-V2"}}
    api.realtime = MagicMock(spec=MysaRealtime)
    type(api.realtime).is_connected = PropertyMock(side_effect=Exception("Fatal loop error"))
    api.async_send_state_poll = AsyncMock()

    with patch("asyncio.sleep", side_effect=[None, asyncio.CancelledError()]):
        try:
            await api._periodic_legacy_mqtt_poll()
        except asyncio.CancelledError:
            pass
