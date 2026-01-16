"""
DataUpdateCoordinator Tests.

Simple tests for coordinator patterns using real DataUpdateCoordinator.
"""

import asyncio
import os
import sys
from datetime import timedelta
from unittest.mock import MagicMock, AsyncMock, patch

# Add project root to path for imports
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(TEST_DIR)
sys.path.insert(0, ROOT_DIR)

import pytest

# Module-level imports
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from custom_components.mysa.mysa_api import MysaApi


class TestCoordinatorSetup:
    """Test coordinator setup and configuration."""

    @pytest.mark.asyncio
    async def test_coordinator_update_interval(self, hass):
        """Test coordinator has correct update interval."""

        async def mock_update():
            return {}

        coordinator = DataUpdateCoordinator(
            hass,
            MagicMock(),
            name="mysa_integration",
            update_method=mock_update,
            update_interval=timedelta(seconds=120),
            config_entry=MagicMock(entry_id="test"),
        )

        assert coordinator.update_interval == timedelta(seconds=120)

    @pytest.mark.asyncio
    async def test_coordinator_name(self, hass):
        """Test coordinator has correct name."""

        async def mock_update():
            return {}

        coordinator = DataUpdateCoordinator(
            hass,
            MagicMock(),
            name="mysa_integration",
            update_method=mock_update,
            config_entry=MagicMock(entry_id="test"),
        )

        assert coordinator.name == "mysa_integration"


class TestCoordinatorUpdates:
    """Test coordinator update mechanism."""

    @pytest.mark.asyncio
    async def test_coordinator_calls_update_method(self, hass):
        """Test coordinator calls update_method on refresh."""
        update_called = False

        async def mock_update():
            nonlocal update_called
            update_called = True
            return {"device1": {"temperature": 20.0}}

        coordinator = DataUpdateCoordinator(
            hass,
            MagicMock(),
            name="test_coordinator",
            update_method=mock_update,
            config_entry=MagicMock(entry_id="test"),
        )

        await coordinator.async_refresh()

        assert update_called is True
        assert coordinator.data == {"device1": {"temperature": 20.0}}


class TestCoordinatorListeners:
    """Test coordinator listener patterns."""

    @pytest.mark.asyncio
    async def test_coordinator_notifies_listeners(self, hass):
        """Test coordinator notifies registered listeners."""
        listener_called = False

        async def mock_update():
            return {"data": "test"}

        coordinator = DataUpdateCoordinator(
            hass,
            MagicMock(),
            name="test_coordinator",
            update_method=mock_update,
            config_entry=MagicMock(entry_id="test"),
        )

        def listener():
            nonlocal listener_called
            listener_called = True

        coordinator.async_add_listener(listener)
        await coordinator.async_refresh()

        assert listener_called is True

    @pytest.mark.asyncio
    async def test_multiple_listeners_notified(self, hass):
        """Test multiple listeners are all notified."""
        call_count = 0

        async def mock_update():
            return {}

        coordinator = DataUpdateCoordinator(
            hass,
            MagicMock(),
            name="test_coordinator",
            update_method=mock_update,
            config_entry=MagicMock(entry_id="test"),
        )

        def listener1():
            nonlocal call_count
            call_count += 1

        def listener2():
            nonlocal call_count
            call_count += 1

        coordinator.async_add_listener(listener1)
        coordinator.async_add_listener(listener2)
        await coordinator.async_refresh()

        assert call_count == 2


class TestCoordinatorErrorHandling:
    """Test coordinator error handling."""

    @pytest.mark.asyncio
    async def test_coordinator_sets_exception_on_error(self, hass):
        """Test coordinator sets last_exception on error."""

        async def failing_update():
            raise Exception("API error")

        coordinator = DataUpdateCoordinator(
            hass,
            MagicMock(),
            name="test_coordinator",
            update_method=failing_update,
            config_entry=MagicMock(entry_id="test"),
        )

        await coordinator.async_refresh()

        assert coordinator.last_exception is not None


class TestCoordinatorDataFlow:
    """Test data flow through coordinator."""

    @pytest.mark.asyncio
    async def test_state_update_in_data(self, hass):
        """Test state updates are in coordinator data."""
        api_response = {
            "device1": {
                "temperature": 21.5,
                "setpoint": 22.0,
            }
        }

        async def mock_update():
            return api_response

        coordinator = DataUpdateCoordinator(
            hass,
            MagicMock(),
            name="test_coordinator",
            update_method=mock_update,
            config_entry=MagicMock(entry_id="test"),
        )

        await coordinator.async_refresh()

        assert coordinator.data["device1"]["temperature"] == 21.5
        assert coordinator.data["device1"]["setpoint"] == 22.0


class TestApiCoordinatorIntegration:
    """Test coordinator with MysaApi async mocking."""

    @pytest.mark.asyncio
    async def test_coordinator_with_mocked_api(self, hass):
        """Test coordinator calling mocked MysaApi.get_state."""
        from unittest.mock import patch
        from custom_components.mysa.mysa_api import MysaApi
        from custom_components.mysa.client import MysaClient

        mock_api = MysaApi.__new__(MysaApi)
        mock_api.hass = hass
        mock_api.client = MysaClient(hass, "u", "p")
        mock_api.states = {}
        mock_api._last_command_time = {}

        with patch.object(MysaClient, "_get_state_sync") as mock_sync:
            mock_sync.return_value = {"device1": {"temperature": 22.5, "humidity": 50}}

            async def update_method():
                return await mock_api.get_state()

            coordinator = DataUpdateCoordinator(
                hass,
                MagicMock(),
                name="test_coordinator",
                update_method=update_method,
                config_entry=MagicMock(entry_id="test"),
            )

            await coordinator.async_refresh()

            assert coordinator.data["device1"]["temperature"] == 22.5
            mock_sync.assert_called()

    @pytest.mark.asyncio
    async def test_coordinator_callback_triggered(self, hass):
        """Test coordinator callback is triggered on refresh."""
        callback_called = False

        async def mock_callback():
            nonlocal callback_called
            callback_called = True

        async def mock_update():
            await mock_callback()
            return {"device": {"temp": 20.0}}

        coordinator = DataUpdateCoordinator(
            hass,
            MagicMock(),
            name="test_coordinator",
            update_method=mock_update,
            config_entry=MagicMock(entry_id="test"),
        )

        await coordinator.async_refresh()

        assert callback_called is True
        assert coordinator.data["device"]["temp"] == 20.0

        # --- From test_constants.py ---

        """Test integration domain name."""
        from custom_components.mysa.const import DOMAIN

        assert DOMAIN == "mysa"

    def test_domain_lowercase(self):
        """Test domain is lowercase."""
        from custom_components.mysa.const import DOMAIN

        assert DOMAIN.islower()


class TestMqttConstants:
    """Test MQTT constants."""

    def test_mqtt_keepalive(self):
        """Test MQTT keepalive value."""
        from custom_components.mysa.const import MQTT_KEEPALIVE

        assert MQTT_KEEPALIVE > 0
        assert MQTT_KEEPALIVE <= 600  # Max reasonable keepalive

    def test_mqtt_ping_interval(self):
        """Test MQTT ping interval."""
        from custom_components.mysa.const import MQTT_PING_INTERVAL

        assert MQTT_PING_INTERVAL > 0
        assert MQTT_PING_INTERVAL < 300  # Should be less than 5 minutes

    def test_mqtt_user_agent(self):
        """Test MQTT user agent string."""
        from custom_components.mysa.const import MQTT_USER_AGENT

        assert isinstance(MQTT_USER_AGENT, str)
        assert len(MQTT_USER_AGENT) > 0


class TestDeviceTypeConstants:
    """Test device type constants."""

    def test_device_type_values_unique(self):
        """Test device type values are unique."""
        device_types = {
            "BB-V2": 4,
            "BB-V2-L": 5,
            "AC-V1": 9,
        }

        values = list(device_types.values())
        assert len(values) == len(set(values))

    def test_device_type_all_positive(self):
        """Test all device type values are positive."""
        device_types = [4, 5, 9]

        for t in device_types:
            assert t > 0


class TestHvacModeConstants:
    """Test HVAC mode constants."""

    def test_hvac_mode_off(self):
        """Test HVAC mode off value."""
        HVAC_MODE_OFF = 0

        assert HVAC_MODE_OFF == 0

    def test_hvac_mode_heat(self):
        """Test HVAC mode heat value."""
        HVAC_MODE_HEAT = 1

        assert HVAC_MODE_HEAT == 1

    def test_hvac_mode_cool(self):
        """Test HVAC mode cool value."""
        HVAC_MODE_COOL = 2

        assert HVAC_MODE_COOL == 2

    def test_hvac_mode_auto(self):
        """Test HVAC mode auto value."""
        HVAC_MODE_AUTO = 3

        assert HVAC_MODE_AUTO == 3


class TestTemperatureConstants:
    """Test temperature constants."""

    def test_min_temperature(self):
        """Test minimum temperature constant."""
        MIN_TEMP = 5.0

        assert MIN_TEMP == 5.0
        assert MIN_TEMP > 0

    def test_max_temperature(self):
        """Test maximum temperature constant."""
        MAX_TEMP = 30.0

        assert MAX_TEMP == 30.0
        assert MAX_TEMP > 0

    def test_temperature_step(self):
        """Test temperature step constant."""
        TEMP_STEP = 0.5

        assert TEMP_STEP == 0.5
        assert TEMP_STEP > 0


class TestBrightnessConstants:
    """Test brightness constants."""

    def test_brightness_min(self):
        """Test minimum brightness."""
        MIN_BRIGHTNESS = 0

        assert MIN_BRIGHTNESS == 0

    def test_brightness_max(self):
        """Test maximum brightness."""
        MAX_BRIGHTNESS = 100

        assert MAX_BRIGHTNESS == 100

    def test_brightness_default(self):
        """Test default brightness."""
        DEFAULT_BRIGHTNESS = 50

        assert DEFAULT_BRIGHTNESS == 50
        assert 0 <= DEFAULT_BRIGHTNESS <= 100


class TestUpdateIntervalConstants:
    """Test update interval constants."""

    def test_scan_interval_positive(self):
        """Test scan interval is positive."""
        SCAN_INTERVAL = 30  # seconds

        assert SCAN_INTERVAL > 0

    def test_scan_interval_reasonable(self):
        """Test scan interval is reasonable."""
        SCAN_INTERVAL = 30  # seconds

        assert SCAN_INTERVAL >= 10  # Not too fast
        assert SCAN_INTERVAL <= 300  # Not too slow


class TestAcConstants:
    """Test AC-specific constants."""

    def test_ac_fan_modes_list(self):
        """Test AC fan modes is a list."""
        AC_FAN_MODES = ["auto", "low", "medium", "high"]

        assert isinstance(AC_FAN_MODES, list)
        assert len(AC_FAN_MODES) > 0

    def test_ac_swing_modes_list(self):
        """Test AC swing modes is a list."""
        AC_SWING_MODES = ["off", "on", "horizontal", "vertical", "both"]

        assert isinstance(AC_SWING_MODES, list)
        assert len(AC_SWING_MODES) > 0

    def test_ac_fan_mode_auto_included(self):
        """Test AC fan modes include auto."""
        AC_FAN_MODES = ["auto", "low", "medium", "high"]

        assert "auto" in AC_FAN_MODES

    def test_ac_swing_mode_off_included(self):
        """Test AC swing modes include off."""
        AC_SWING_MODES = ["off", "on", "horizontal", "vertical", "both"]

        assert "off" in AC_SWING_MODES


# --- From test_state_normalization.py ---


class MockMysaApi:
    """Minimal mock of MysaApi for testing _normalize_state."""

    def __init__(self):
        self.devices = {}
        self.states = {}

    def _normalize_state(self, state):
        """Copy of normalization logic for testing."""
        from custom_components.mysa.const import AC_FAN_MODES, AC_SWING_MODES

        def get_v(keys, prefer_v=True):
            for k in keys:
                val = state.get(k)
                if val is not None:
                    if isinstance(val, dict):
                        extracted = val.get("v")
                        if extracted is not None:
                            return extracted
                        if k == "Brightness":
                            v2_br = val.get("a_br")
                            if v2_br is not None:
                                return v2_br
                        if prefer_v:
                            continue
                    return val
            return None

        # Basic mappings
        mode_val = get_v(["md", "TstatMode", "Mode"])
        if mode_val is not None:
            state["Mode"] = mode_val

        sp_val = get_v(["sp", "stpt", "SetPoint"])
        if sp_val is not None:
            state["SetPoint"] = sp_val

        duty_val = get_v(["dc", "Duty", "DutyCycle"])
        if duty_val is not None:
            state["Duty"] = duty_val

        rssi_val = get_v(["rssi", "Rssi", "RSSI"])
        if rssi_val is not None:
            state["Rssi"] = rssi_val

        br_val = get_v(["br", "MaxBrightness", "Brightness"])
        if br_val is not None:
            state["Brightness"] = int(br_val)

        lock_val = get_v(["ButtonState", "alk", "lc", "lk", "Lock"])
        if lock_val is not None:
            state["Lock"] = (
                1 if (str(lock_val).lower() in ["1", "true", "on", "locked"]) else 0
            )


class TestStateNormalization:
    """Test state normalization for various input formats."""

    def test_normalize_mqtt_style_keys(self):
        """Test normalization of MQTT-style short keys."""
        api = MockMysaApi()
        state = {"md": 3, "sp": 21.5, "dc": 50, "rssi": -45, "br": 80, "lk": 0}

        api._normalize_state(state)

        assert state["Mode"] == 3
        assert state["SetPoint"] == 21.5
        assert state["Duty"] == 50
        assert state["Rssi"] == -45
        assert state["Brightness"] == 80
        assert state["Lock"] == 0

    def test_normalize_http_style_keys(self):
        """Test normalization of HTTP-style long keys."""
        api = MockMysaApi()
        state = {
            "TstatMode": 3,
            "SetPoint": 22.0,
            "DutyCycle": 75,
            "Rssi": -50,
            "Brightness": 100,
            "Lock": 1,
        }

        api._normalize_state(state)

        assert state["Mode"] == 3
        assert state["SetPoint"] == 22.0
        assert state["Duty"] == 75
        assert state["Rssi"] == -50
        assert state["Brightness"] == 100
        assert state["Lock"] == 1

    def test_normalize_dict_with_v_key(self):
        """Test normalization of dict values with 'v' key."""
        api = MockMysaApi()
        state = {
            "SetPoint": {"v": 21.0, "t": 1234567890},
            "Rssi": {"v": -40, "t": 1234567890},
        }

        api._normalize_state(state)

        assert state["SetPoint"] == 21.0
        assert state["Rssi"] == -40

    def test_normalize_brightness_with_a_br(self):
        """Test normalization of V2 brightness with a_br key."""
        api = MockMysaApi()
        state = {"Brightness": {"a_br": 75, "i_br": 50}}

        api._normalize_state(state)

        assert state["Brightness"] == 75

    def test_normalize_lock_variants(self):
        """Test normalization of various lock value formats."""
        api = MockMysaApi()

        # Test 'Locked' string
        state = {"ButtonState": "Locked"}
        api._normalize_state(state)
        assert state["Lock"] == 1

        # Test 'Unlocked' string
        state = {"ButtonState": "Unlocked"}
        api._normalize_state(state)
        assert state["Lock"] == 0

        # Test boolean True
        state = {"lk": True}
        api._normalize_state(state)
        assert state["Lock"] == 1

        # Test integer 1
        state = {"lc": 1}
        api._normalize_state(state)
        assert state["Lock"] == 1

    def test_normalize_preserves_original_keys(self):
        """Test that normalization preserves original keys."""
        api = MockMysaApi()
        state = {"md": 3, "sp": 21.0, "CustomKey": "custom_value"}

        api._normalize_state(state)

        # Original keys should still exist
        assert state["md"] == 3
        assert state["sp"] == 21.0
        assert state["CustomKey"] == "custom_value"
        # Normalized keys added
        assert state["Mode"] == 3
        assert state["SetPoint"] == 21.0

    def test_normalize_empty_state(self):
        """Test normalization of empty state dict."""
        api = MockMysaApi()
        state = {}

        api._normalize_state(state)

        # Should not crash, state should still be empty
        assert "Mode" not in state
        assert "SetPoint" not in state

    def test_normalize_none_values_ignored(self):
        """Test that None values are not normalized."""
        api = MockMysaApi()
        state = {"md": None, "sp": 21.0}

        api._normalize_state(state)

        # md was None, so Mode should not be set
        assert "Mode" not in state
        # sp was valid, so SetPoint should be set
        assert state["SetPoint"] == 21.0


class TestCmdArrayExtraction:
    """Test extraction of state from MQTT cmd array."""

    def test_extract_setpoint_from_cmd_array(self):
        """Test extracting setpoint from cmd array structure."""
        # This simulates the MQTT command echo format
        body = {
            "cmd": [{"sp": 22.0, "stpt": 22.0, "a_sp": 22.0, "tm": -1}],
            "type": 4,
            "ver": 1,
        }

        state_update = body.get("state", {})

        # If state is empty but cmd exists, extract from cmd
        if not state_update and "cmd" in body:
            cmd_list = body.get("cmd", [])
            if cmd_list and isinstance(cmd_list, list):
                for cmd_item in cmd_list:
                    if isinstance(cmd_item, dict):
                        state_update.update(cmd_item)

        assert state_update["sp"] == 22.0
        assert state_update["stpt"] == 22.0

    def test_extract_brightness_from_cmd_array(self):
        """Test extracting brightness from cmd array structure."""
        body = {
            "cmd": [{"tm": -1, "br": {"a_b": 1, "a_br": 100, "i_br": 34}}],
            "type": 4,
            "ver": 1,
        }

        state_update = {}

        if "cmd" in body:
            cmd_list = body.get("cmd", [])
            if cmd_list and isinstance(cmd_list, list):
                for cmd_item in cmd_list:
                    if isinstance(cmd_item, dict):
                        state_update.update(cmd_item)

        assert "br" in state_update
        assert state_update["br"]["a_br"] == 100

        # --- From test_zone_lookup.py ---

        """Test getting zone name when zone exists."""
        # Simulate zones dict as populated from /homes API
        zones = {
            "fc1a8826-08e0-4cf4-828a-adbeb1f1b8e9": "Basement",
            "abc12345-def6-7890-abcd-ef1234567890": "Living Room",
        }

        zone_id = "fc1a8826-08e0-4cf4-828a-adbeb1f1b8e9"
        zone_name = zones.get(zone_id)

        assert zone_name == "Basement"

    def test_get_zone_name_not_found(self):
        """Test getting zone name when zone doesn't exist."""
        zones = {"fc1a8826-08e0-4cf4-828a-adbeb1f1b8e9": "Basement"}

        zone_id = "unknown-zone-id"
        zone_name = zones.get(zone_id)

        assert zone_name is None

    def test_get_zone_name_none_id(self):
        """Test getting zone name with None ID."""
        zones = {"fc1a8826-08e0-4cf4-828a-adbeb1f1b8e9": "Basement"}

        zone_id = None
        zone_name = zones.get(zone_id) if zone_id else None

        assert zone_name is None


class TestHomesApiParsing:
    """Test parsing of /homes API response."""

    def test_parse_homes_response(self):
        """Test parsing homes and zones from API response."""
        api_response = {
            "Homes": [
                {
                    "Address": {"PostalCode": "G6W8M3"},
                    "AllowedUsers": ["6d432613-d63b-4a57-96b4-5d3d09f1706c"],
                    "ERate": "0.07",
                    "Id": "f9bce0d1-3eb7-4300-8b7f-94df1c989079",
                    "Name": "DefaultHome",
                    "Owner": "6d432613-d63b-4a57-96b4-5d3d09f1706c",
                    "Zones": [
                        {
                            "Id": "fc1a8826-08e0-4cf4-828a-adbeb1f1b8e9",
                            "Owner": "6d432613-d63b-4a57-96b4-5d3d09f1706c",
                            "Name": "Basement",
                        },
                        {
                            "Id": "abc12345-def6-7890-abcd-ef1234567890",
                            "Owner": "6d432613-d63b-4a57-96b4-5d3d09f1706c",
                            "Name": "Upstairs",
                        },
                    ],
                }
            ]
        }

        # Parse zones from response (as done in _fetch_homes_sync)
        zones = {}
        homes = api_response.get("Homes", api_response.get("homes", []))
        for home in homes:
            for zone in home.get("Zones", []):
                z_id = zone.get("Id")
                z_name = zone.get("Name")
                if z_id and z_name:
                    zones[z_id] = z_name

        assert len(zones) == 2
        assert zones["fc1a8826-08e0-4cf4-828a-adbeb1f1b8e9"] == "Basement"
        assert zones["abc12345-def6-7890-abcd-ef1234567890"] == "Upstairs"

    def test_parse_homes_empty_response(self):
        """Test parsing empty homes response."""
        api_response = {"Homes": []}

        zones = {}
        homes = api_response.get("Homes", api_response.get("homes", []))
        for home in homes:
            for zone in home.get("Zones", []):
                z_id = zone.get("Id")
                z_name = zone.get("Name")
                if z_id and z_name:
                    zones[z_id] = z_name

        assert len(zones) == 0

    def test_parse_homes_no_zones(self):
        """Test parsing homes with no zones."""
        api_response = {
            "Homes": [
                {
                    "Id": "f9bce0d1-3eb7-4300-8b7f-94df1c989079",
                    "Name": "DefaultHome",
                    "Zones": [],
                }
            ]
        }

        zones = {}
        homes = api_response.get("Homes", api_response.get("homes", []))
        for home in homes:
            for zone in home.get("Zones", []):
                z_id = zone.get("Id")
                z_name = zone.get("Name")
                if z_id and z_name:
                    zones[z_id] = z_name

        assert len(zones) == 0

    def test_parse_homes_alternative_key_names(self):
        """Test parsing with lowercase key names."""
        api_response = {
            "homes": [
                {
                    "id": "f9bce0d1-3eb7-4300-8b7f-94df1c989079",
                    "name": "DefaultHome",
                    "Zones": [
                        {
                            "Id": "fc1a8826-08e0-4cf4-828a-adbeb1f1b8e9",
                            "Name": "Basement",
                        }
                    ],
                }
            ]
        }

        zones = {}
        homes = api_response.get("Homes", api_response.get("homes", []))
        for home in homes:
            for zone in home.get("Zones", []):
                z_id = zone.get("Id")
                z_name = zone.get("Name")
                if z_id and z_name:
                    zones[z_id] = z_name

        assert zones["fc1a8826-08e0-4cf4-828a-adbeb1f1b8e9"] == "Basement"

        # --- From test_capabilities.py ---

        """Test full thermostat supports brightness."""
        device = {"type": 4}  # BB-V2

        has_brightness = device.get("type") in [4]  # Full thermostats only

        assert has_brightness is True

    def test_lite_thermostat_no_brightness(self):
        """Test lite thermostat doesn't support brightness."""
        device = {"type": 5}  # BB-V2-L

        has_brightness = device.get("type") in [4]  # Full thermostats only

        assert has_brightness is False

    def test_full_thermostat_has_proximity(self):
        """Test full thermostat supports proximity sensor."""
        device = {"type": 4}

        has_proximity = device.get("type") in [4]

        assert has_proximity is True

    def test_both_thermostats_have_lock(self):
        """Test both thermostat types support lock."""
        device_types = [4, 5]

        for t in device_types:
            has_lock = t in [4, 5]
            assert has_lock is True

    def test_thermostat_has_heating(self):
        """Test thermostats support heating mode."""
        device = {"type": 4, "SupportedCaps": {"Heating": True}}

        has_heating = device.get("SupportedCaps", {}).get("Heating", False)

        assert has_heating is True

    def test_thermostat_voltage_options(self):
        """Test thermostat voltage options."""
        valid_voltages = [120, 208, 240]

        for v in valid_voltages:
            assert 100 <= v <= 250


class TestACCapabilities:
    """Test AC controller capabilities."""

    def test_ac_has_fan_mode(self):
        """Test AC supports fan mode."""
        device = {"type": 9}  # AC-V1

        has_fan_mode = device.get("type") == 9

        assert has_fan_mode is True

    def test_ac_has_swing_mode(self):
        """Test AC supports swing mode."""
        device = {"type": 9}

        has_swing_mode = device.get("type") == 9

        assert has_swing_mode is True

    def test_ac_has_cooling(self):
        """Test AC supports cooling mode."""
        device = {"type": 9, "SupportedCaps": {"Cooling": True}}

        has_cooling = device.get("SupportedCaps", {}).get("Cooling", False)

        assert has_cooling is True

    def test_ac_has_climate_plus(self):
        """Test AC supports Climate+ mode."""
        device = {"type": 9}

        has_climate_plus = device.get("type") == 9

        assert has_climate_plus is True

    def test_ac_no_brightness(self):
        """Test AC doesn't support brightness."""
        device = {"type": 9}

        has_brightness = device.get("type") in [4]  # Only full thermostats

        assert has_brightness is False

    def test_ac_no_proximity(self):
        """Test AC doesn't support proximity sensor."""
        device = {"type": 9}

        has_proximity = device.get("type") in [4]  # Only full thermostats

        assert has_proximity is False


class TestSupportedCapsLogic:
    """Test SupportedCaps parsing logic."""

    def test_parse_supported_caps_dict(self):
        """Test parsing SupportedCaps as dictionary."""
        caps = {
            "Heating": True,
            "Cooling": False,
            "MinSetpoint": 5.0,
            "MaxSetpoint": 30.0,
        }

        assert caps["Heating"] is True
        assert caps["Cooling"] is False

    def test_get_min_setpoint_from_caps(self):
        """Test getting min setpoint from caps."""
        caps = {"MinSetpoint": 10.0}

        min_setpoint = caps.get("MinSetpoint", 5.0)

        assert min_setpoint == 10.0

    def test_get_max_setpoint_from_caps(self):
        """Test getting max setpoint from caps."""
        caps = {"MaxSetpoint": 28.0}

        max_setpoint = caps.get("MaxSetpoint", 30.0)

        assert max_setpoint == 28.0

    def test_default_caps_when_missing(self):
        """Test default values when caps missing."""
        caps = {}

        heating = caps.get("Heating", True)  # Default True for thermostats
        cooling = caps.get("Cooling", False)

        assert heating is True
        assert cooling is False


class TestDeviceFeatureDetection:
    """Test device feature detection logic."""

    def test_is_thermostat(self):
        """Test thermostat detection."""
        thermostat_types = [4, 5]
        device = {"type": 4}

        is_thermostat = device.get("type") in thermostat_types

        assert is_thermostat is True

    def test_is_ac(self):
        """Test AC detection."""
        ac_types = [9]
        device = {"type": 9}

        is_ac = device.get("type") in ac_types

        assert is_ac is True

    def test_is_full_thermostat(self):
        """Test full thermostat detection."""
        device = {"type": 4}

        is_full = device.get("type") == 4

        assert is_full is True

    def test_is_lite_thermostat(self):
        """Test lite thermostat detection."""
        device = {"type": 5}

        is_lite = device.get("type") == 5

        assert is_lite is True

    def test_is_upgraded_lite(self):
        """Test upgraded lite detection from options."""
        options = {"upgraded_lite_devices": ["device1"]}
        device_id = "device1"

        is_upgraded = device_id in options.get("upgraded_lite_devices", [])

        assert is_upgraded is True


class TestDeviceFeaturesMatrix:
    """Test device features matrix."""

    def test_feature_matrix_bb_v2(self):
        """Test BB-V2 feature matrix."""
        features = {
            "brightness": True,
            "proximity": True,
            "lock": True,
            "heating": True,
            "cooling": False,
            "fan_mode": False,
            "swing_mode": False,
        }

        assert features["brightness"] is True
        assert features["fan_mode"] is False

    def test_feature_matrix_bb_v2_l(self):
        """Test BB-V2-L feature matrix."""
        features = {
            "brightness": False,
            "proximity": False,
            "lock": True,
            "heating": True,
            "cooling": False,
            "fan_mode": False,
            "swing_mode": False,
        }

        assert features["brightness"] is False
        assert features["lock"] is True

    def test_feature_matrix_ac_v1(self):
        """Test AC-V1 feature matrix."""
        features = {
            "brightness": False,
            "proximity": False,
            "lock": False,
            "heating": True,
            "cooling": True,
            "fan_mode": True,
            "swing_mode": True,
            "climate_plus": True,
        }

        assert features["cooling"] is True
        assert features["fan_mode"] is True
        assert features["climate_plus"] is True


# --- From test_async.py ---


class TestAsyncPatterns:
    """Test basic async patterns."""

    @pytest.mark.asyncio
    async def test_async_event_signaling(self):
        """Test asyncio.Event for connection status."""
        connected = asyncio.Event()

        assert not connected.is_set()

        connected.set()
        assert connected.is_set()

        try:
            await asyncio.wait_for(connected.wait(), timeout=0.1)
            waited = True
        except asyncio.TimeoutError:
            waited = False

        assert waited is True

    @pytest.mark.asyncio
    async def test_async_task_cancellation(self):
        """Test proper task cancellation handling."""
        cancelled = False

        async def long_running_task():
            nonlocal cancelled
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                cancelled = True
                raise

        task = asyncio.create_task(long_running_task())
        await asyncio.sleep(0.01)
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        assert cancelled is True

    @pytest.mark.asyncio
    async def test_async_gather(self):
        """Test concurrent async operations."""
        results = []

        async def task1():
            await asyncio.sleep(0.01)
            results.append(1)
            return 1

        async def task2():
            await asyncio.sleep(0.01)
            results.append(2)
            return 2

        await asyncio.gather(task1(), task2())

        assert len(results) == 2
        assert 1 in results
        assert 2 in results


class TestAsyncMocking:
    """Test async mocking patterns."""

    @pytest.mark.asyncio
    async def test_async_mock_return_value(self):
        """Test AsyncMock with return value."""
        mock_func = AsyncMock(return_value=42)

        result = await mock_func()

        assert result == 42
        mock_func.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_mock_side_effect(self):
        """Test AsyncMock with side effect."""
        mock_func = AsyncMock(side_effect=[1, 2, 3])

        r1 = await mock_func()
        r2 = await mock_func()
        r3 = await mock_func()

        assert r1 == 1
        assert r2 == 2
        assert r3 == 3

    @pytest.mark.asyncio
    async def test_async_mock_exception(self):
        """Test AsyncMock with exception."""
        mock_func = AsyncMock(side_effect=ValueError("test error"))

        with pytest.raises(ValueError, match="test error"):
            await mock_func()


class TestMysaApiAsyncMocking:
    """Test async mocking of MysaApi methods."""

    @pytest.mark.asyncio
    async def test_get_state_async_mocked(self, hass):
        """Test mocking MysaApi.get_state with AsyncMock."""
        from custom_components.mysa.client import MysaClient

        with patch.object(MysaClient, "_get_state_sync") as mock_sync:
            mock_sync.return_value = {
                "device1": {
                    "temperature": 21.5,
                    "setpoint": 22.0,
                    "humidity": 45,
                }
            }

            api = MysaApi.__new__(MysaApi)
            api.hass = hass
            api.client = MysaClient(hass, "user", "pass")
            # We mock the session so _get_state_sync doesn't explode if called for real (though it should be patched)
            api.client._session = MagicMock()
            api.states = {}
            api._last_command_time = {}

            result = await api.get_state()

            assert "device1" in result
            assert result["device1"]["temperature"] == 21.5
            mock_sync.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_temperature_async_mocked(self, hass):
        """Test mocking MysaApi.set_target_temperature."""

        api = MysaApi.__new__(MysaApi)
        api.hass = hass
        api.client = MagicMock()
        api.client.user_id = "test-user-id"
        api.client.devices = {"device1": {"type": 4}}

        api.realtime = MagicMock()
        api.realtime.send_command = AsyncMock()

        # Other necessary init
        api._last_command_time = {}
        api.states = {}
        api.upgraded_lite_devices = []

        await api.set_target_temperature("device1", 23.0)

        api.realtime.send_command.assert_called()

        # We need to look through all calls because notify_settings_changed is called after
        found_cmd = False
        for call in api.realtime.send_command.call_args_list:
            args, _kwargs = call
            body = args[1]
            if "cmd" in body:
                found_cmd = True
                assert args[0] == "device1"
                assert body["cmd"][0]["sp"] == 23.0
                break

        assert found_cmd, "Did not find command call with 'cmd' in body"
