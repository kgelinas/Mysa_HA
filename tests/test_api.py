"""Tests for Mysa API Facade."""
import time
from unittest.mock import MagicMock, AsyncMock, patch, ANY

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
    api.upgraded_lite_devices = []
    api.zone_overrides = {}

    # Mock helpers
    api._update_state_cache = MagicMock(wraps=api._update_state_cache)

    return api

@pytest.mark.asyncio
class TestMysaApi:  # pylint: disable=too-many-public-methods
    """Test MysaApi facade."""

    def get_cmd_body(self, api):
        """Helper to find the command body from send_command calls."""
        for call in api.realtime.send_command.call_args_list:
            args = call[0]  # (device_id, body, user_id, ...)
            body = args[1]
            if "cmd" in body:
                return body
        return None

    async def test_init(self, mock_hass):
        """Test initialization."""
        # Mock dependencies since __init__ instantiates them
        with patch("custom_components.mysa.mysa_api.MysaClient") as mock_client_cls, \
             patch("custom_components.mysa.mysa_api.MysaRealtime") as mock_realtime_cls:

            api = MysaApi("u", "p", mock_hass)

            assert api.hass == mock_hass
            assert api.username == mock_client_cls.return_value.username
            assert api.password == mock_client_cls.return_value.password

            # Verify sub-components initialized
            mock_client_cls.assert_called_with(mock_hass, "u", "p")
            mock_realtime_cls.assert_called_once()

            # Verify callbacks passed to Realtime
            _, kwargs = mock_realtime_cls.call_args
            assert kwargs["get_signed_url_callback"] == mock_client_cls.return_value.get_signed_mqtt_url
            # Check on_update_callback is bound method
            assert kwargs["on_update_callback"] == api._on_mqtt_update

    # --- Tests from test_mysa_api_coverage.py ---

    async def test_set_lock(self, mock_api):
        """Test set_lock."""
        api = mock_api
        api.client.set_device_setting_silent = AsyncMock()

        await api.set_lock("dev1", True)

        body = self.get_cmd_body(api)
        assert body is not None
        assert body["cmd"][0]["lk"] == 1

        api.client.set_device_setting_silent.assert_called_with("dev1", {"Lock": 1})
        assert api.states["dev1"]["Lock"]["v"] == 1

    async def test_set_ac_climate_plus(self, mock_api):
        """Test set_ac_climate_plus."""
        api = mock_api
        await api.set_ac_climate_plus("dev1", True)
        body = self.get_cmd_body(api)
        assert body is not None
        assert body["cmd"][0]["it"] == 1
        assert api.states["dev1"]["IsThermostatic"]["v"] == 1

    async def test_set_proximity(self, mock_api):
        """Test set_proximity."""
        api = mock_api
        api.client.set_device_setting_silent = AsyncMock()
        await api.set_proximity("dev1", True)
        body = self.get_cmd_body(api)
        assert body is not None
        assert body["cmd"][0]["pr"] == 1
        api.client.set_device_setting_silent.assert_called_with("dev1", {"ProximityMode": True})

    async def test_set_auto_brightness(self, mock_api):
        """Test set_auto_brightness."""
        api = mock_api
        api.client.set_device_setting_silent = AsyncMock()
        await api.set_auto_brightness("dev1", True)
        body = self.get_cmd_body(api)
        assert body is not None
        assert body["cmd"][0]["br"]["a_b"] == 1
        api.client.set_device_setting_silent.assert_called_with("dev1", {"AutoBrightness": True})

    async def test_set_min_brightness(self, mock_api):
        """Test set_min_brightness."""
        api = mock_api
        api.client.set_device_setting_silent = AsyncMock()
        await api.set_min_brightness("dev1", 10)
        body = self.get_cmd_body(api)
        assert body is not None
        assert body["cmd"][0]["br"]["i_br"] == 10
        api.client.set_device_setting_silent.assert_called_with("dev1", {"MinBrightness": 10})

    async def test_set_max_brightness(self, mock_api):
        """Test set_max_brightness."""
        api = mock_api
        api.client.set_device_setting_silent = AsyncMock()
        await api.set_max_brightness("dev1", 90)
        body = self.get_cmd_body(api)
        assert body is not None
        assert body["cmd"][0]["br"]["a_br"] == 90
        api.client.set_device_setting_silent.assert_called_with("dev1", {"MaxBrightness": 90})

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
        api.client.zones = ["zone1"]
        api.client.is_connected = True
        api.realtime.is_running = True

        assert api.username == "user1"
        assert api.password == "pass1"
        assert api.homes == ["home1"]
        assert api.zones == ["zone1"]
        assert api.is_connected is True
        assert api.is_mqtt_running is True

        new_devices = {"dev2": {}}
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

        # Unknown mode AC
        await api.set_hvac_mode("ac1", "unknown_mode")
        body = self.get_cmd_body(api)
        assert body is not None
        assert body["cmd"][0]["md"] == 0

        # ELV Off
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

    async def test_set_hvac_mode_ac_all_modes(self, mock_api):
        """Test all HVAC modes for AC device."""
        api = mock_api
        api.devices["ac1"] = {"Model": "AC-V1"}

        # Mapping: cool=2, heat=1, auto=3, dry=4, fan=5
        modes = {
            "cool": 2,
            "heat": 1,
            "auto": 3,
            "dry": 4,
            "fan_only": 5
        }

        for mode_str, expected_val in modes.items():
            api.realtime.send_command.reset_mock()
            await api.set_hvac_mode("ac1", mode_str)
            body = self.get_cmd_body(api)
            assert body is not None
            assert body["cmd"][0]["md"] == expected_val, f"Failed for {mode_str}"

    async def test_brightness_helpers_defaults(self, mock_api):
        """Test brightness defaults."""
        api = mock_api
        api.states = {}
        br = api._get_brightness_object("dev1")
        assert br["a_br"] == 100
        assert br["i_br"] == 50

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

        api.client.get_zone_name = MagicMock()
        api.get_zone_name("z1")
        api.client.get_zone_name.assert_called_with("z1")

        api.client.fetch_firmware_info = MagicMock()
        api.fetch_firmware_info("dev1")
        api.client.fetch_firmware_info.assert_called_with("dev1")

        api.client.get_electricity_rate = MagicMock()
        api.get_electricity_rate("dev1")
        api.client.get_electricity_rate.assert_called_with("dev1")

        await api.start_mqtt_listener()
        api.realtime.start.assert_called_once()

        await api.stop_mqtt_listener()
        api.realtime.stop.assert_called_once()

    async def test_mqtt_update_existing(self, mock_api):
        """Test MQTT update for existing state."""
        api = mock_api
        api.states = {"dev1": {"v": 0}}
        api.coordinator_callback = AsyncMock()
        await api._on_mqtt_update("dev1", {"v": 1})
        assert api.states["dev1"]["v"] == 1

    async def test_set_ac_off(self, mock_api):
        """Test setting AC mode to off."""
        api = mock_api
        api.devices["ac1"] = {"Model": "AC-V1"}
        await api.set_hvac_mode("ac1", "off")
        body = self.get_cmd_body(api)
        assert body is not None
        assert body["cmd"][0]["md"] == 0

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
        api._update_brightness_cache("new_dev", "a_br", 80)
        assert api.states["new_dev"]["Brightness"]["a_br"] == 80

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

    async def test_api_zone_overrides_coverage(self, hass):
        """Test zone override get_zone_name coverage."""
        from custom_components.mysa.mysa_api import MysaApi

        with patch("custom_components.mysa.mysa_api.MysaClient") as mock_client_cls, \
             patch("custom_components.mysa.mysa_api.MysaRealtime"):

            api = MysaApi("u", "p", hass, zone_overrides={"123": "Renamed Zone"})

            # Override case
            assert api.get_zone_name("123") == "Renamed Zone"
            # Integer conversion covered
            assert api.get_zone_name(123) == "Renamed Zone"

            # Passthrough case
            api.client.get_zone_name.return_value = "Original"
            assert api.get_zone_name("456") == "Original"

    async def test_api_delegation_coverage(self, hass):
        """Test missing delegation methods coverage."""
        with patch("custom_components.mysa.mysa_api.MysaClient"), \
             patch("custom_components.mysa.mysa_api.MysaRealtime"):

            api = MysaApi("u", "p", hass)

            api.client.fetch_firmware_info.return_value = {"fw": "1.0"}
            assert api.fetch_firmware_info("dev1") == {"fw": "1.0"}

            api.client.get_electricity_rate.return_value = 0.1
            assert api.get_electricity_rate("dev1") == 0.1
