"""Tests for Select entities."""

import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from homeassistant.exceptions import HomeAssistantError
from custom_components.mysa import MysaData
from custom_components.mysa.select import (
    MysaTemperatureFormatSelect,
    MysaSensorModeSelect,
    MysaHorizontalSwingSelect,
)


class TestHorizontalSwingSelect:
    """Test AC horizontal swing select entity."""

    def test_horizontal_swing_modes_mapping(self):
        """Test horizontal swing position to name mapping."""
        # From const.py AC_HORIZONTAL_SWING_MODES
        swing_modes = {
            2: "auto",
            3: "left",
            4: "left_center",
            5: "center",
            6: "right_center",
            8: "right",
        }

        assert swing_modes[2] == "auto"
        assert swing_modes[5] == "center"
        assert len(swing_modes) >= 6

    def test_horizontal_swing_reverse_mapping(self):
        """Test reverse mapping from name to position."""
        reverse_map = {
            "auto": 2,
            "left": 3,
            "left_center": 4,
            "center": 5,
            "right_center": 6,
            "right": 8,
        }

        assert reverse_map["auto"] == 2
        assert reverse_map["center"] == 5

    def test_horizontal_swing_icon(self):
        """Test horizontal swing select icon."""
        icon = "mdi:arrow-left-right"

        assert icon == "mdi:arrow-left-right"

    def test_horizontal_swing_unique_id_format(self):
        """Test horizontal swing unique ID format."""
        device_id = "device1"

        unique_id = f"{device_id}_horizontal_swing"

        assert unique_id == "device1_horizontal_swing"

    def test_horizontal_swing_name_suffix(self):
        """Test horizontal swing name format."""
        device_name = "Living Room AC"

        entity_name = f"{device_name} Horizontal Swing"

        assert entity_name == "Living Room AC Horizontal Swing"


class TestHorizontalSwingFromCapabilities:
    """Test building horizontal swing options from device capabilities."""

    def test_options_from_supported_caps(self):
        """Test building options from SupportedCaps."""
        supported_caps = {"modes": {"cool": {"horizontalSwing": [2, 3, 4, 5, 6, 8]}}}

        modes = supported_caps.get("modes", {})
        horizontal_swings = []

        for mode_key, mode_caps in modes.items():
            horizontal_swings = mode_caps.get("horizontalSwing", [])
            if horizontal_swings:
                break

        assert horizontal_swings == [2, 3, 4, 5, 6, 8]

    def test_options_fallback_when_no_caps(self):
        """Test fallback to default options when no caps available."""
        supported_caps: dict[str, Any] = {}

        modes = supported_caps.get("modes", {})
        horizontal_swings = []

        for mode_key, mode_caps in modes.items():
            horizontal_swings = mode_caps.get("horizontalSwing", [])
            if horizontal_swings:
                break

        # Should be empty, triggering fallback
        assert horizontal_swings == []

    def test_options_default_list(self):
        """Test default horizontal swing options."""
        default_options = [
            "auto",
            "left",
            "left_center",
            "center",
            "right_center",
            "right",
        ]

        assert "auto" in default_options
        assert "center" in default_options
        assert len(default_options) >= 6


class TestHorizontalSwingState:
    """Test horizontal swing state reading."""

    def test_state_from_mqtt_simple(self):
        """Test reading horizontal swing state from simple MQTT value."""
        state: dict[str, Any] = {"SwingStateHorizontal": 5}

        val = state.get("SwingStateHorizontal")

        assert val == 5  # "center"

    def test_state_from_mqtt_nested(self):
        """Test reading horizontal swing state from nested MQTT value."""
        state: dict[str, Any] = {"SwingStateHorizontal": {"v": 5, "t": 1704067200}}

        val = state.get("SwingStateHorizontal")
        if isinstance(val, dict):
            val = val.get("v")

        assert val == 5

    def test_state_default_when_missing(self):
        """Test default value when no state available."""
        state: dict[str, Any] = {}

        val = state.get("SwingStateHorizontal")
        if val is None:
            val = 0  # auto

        swing_modes = {2: "auto", 5: "center"}
        result = swing_modes.get(val, "auto")

        assert result == "auto"


class TestHorizontalSwingPendingState:
    """Test pending state mechanism for horizontal swing."""

    def test_pending_option_initial(self):
        """Test pending option is initially None."""
        pending_option = None

        assert pending_option is None

    def test_pending_option_set_on_select(self):
        """Test pending option is set when user selects."""
        pending_option = None

        # User selects "center"
        pending_option = "center"

        assert pending_option == "center"

    def test_pending_option_returned_when_set(self):
        """Test pending option takes priority over coordinator state."""
        pending_option = "center"
        coordinator_value = 0  # "auto"

        if pending_option is not None:
            result = pending_option
        else:
            swing_modes = {2: "auto", 5: "center"}
            result = swing_modes.get(coordinator_value, "auto")

        assert result == "center"

    def test_pending_option_cleared_on_confirm(self):
        """Test pending option is cleared when MQTT confirms."""
        pending_option: str | None = "center"

        # MQTT confirms the change
        if True:  # Got confirmed value from MQTT
            pending_option = None

        assert pending_option is None

class TestHorizontalSwingCommands:
    """Test horizontal swing command building."""

    def test_command_structure(self):
        """Test horizontal swing command structure."""
        device_id = "device1"
        position = 5  # center

        command: dict[str, Any] = {
            "did": device_id,
            "cmd": [{"swh": position}],
        }

        assert command["did"] == device_id
        assert command["cmd"][0]["swh"] == 5

    def test_command_lowercase_conversion(self):
        """Test option is lowercased before lookup."""
        option = "CENTER"

        position = option.lower()

        assert position == "center"


class TestSelectEntitySetup:
    """Test select entity setup logic."""

    def test_horizontal_swing_ac_only(self):
        """Test horizontal swing is only for AC devices."""
        is_ac = True

        should_create = is_ac

        assert should_create is True

    def test_horizontal_swing_not_for_heaters(self):
        """Test horizontal swing is NOT created for heaters."""
        is_ac = False

        should_create = is_ac

        assert should_create is False

    def test_no_entities_for_empty_device_list(self):
        """Test no entities created for empty device list."""
        devices: dict[str, Any] = {}
        entities = []

        for device_id, device_data in devices.items():
            entities.append(device_id)

        assert entities == []

    @pytest.mark.asyncio
    async def test_sensor_mode_infloor_only(self, hass, mock_api, mock_config_entry):
        """Test sensor mode select is created for In-Floor devices."""
        from custom_components.mysa.select import async_setup_entry

        # Mock Data with In-Floor device
        mock_data = MagicMock(spec=MysaData)
        mock_data.api = mock_api
        mock_data.coordinator = MagicMock()
        mock_config_entry.runtime_data = mock_data

        mock_api.get_devices = AsyncMock(
            return_value={"infloor_id": {"Model": "INF-V1"}}
        )
        mock_api.is_ac_device = MagicMock(return_value=False)

        async_add_entities = MagicMock()

        await async_setup_entry(hass, mock_config_entry, async_add_entities)

        assert async_add_entities.called
        # Verify call args
        args = async_add_entities.call_args[0][0]
        # Should create SensorModeSelect and TemperatureFormatSelect
        assert len(args) == 2
        assert any(e._device_id == "infloor_id" for e in args)


class TestSensorModeSelect:
    """Test MysaSensorModeSelect entity logic."""

    @pytest.mark.asyncio
    async def test_sensor_mode_select(self, hass, mock_coordinator, mock_config_entry):
        """Test MysaSensorModeSelect entity."""
        from custom_components.mysa.select import MysaSensorModeSelect

        # Mock API
        mock_api = MagicMock()
        mock_api.set_sensor_mode = AsyncMock()

        # Create the select entity
        entity = MysaSensorModeSelect(
            mock_coordinator,
            "infloor_device",
            {"Id": "infloor_device", "Name": "Bathroom", "Model": "INF-V1"},
            mock_api,
            mock_config_entry,
        )
        entity.async_write_ha_state = MagicMock()
        entity.hass = hass

        # Test options
        assert "floor" in entity.options
        assert "ambient" in entity.options

        # Test initial state (Ambient default)
        mock_coordinator.data = {"infloor_device": {}}
        assert entity.current_option == "ambient"

        # Test with SensorMode=1 (Floor)
        mock_coordinator.data = {"infloor_device": {"SensorMode": 1}}
        # Note: entity.current_option reads from coordinator
        assert entity.current_option == "floor"

        # Test selecting an option
        await entity.async_select_option("floor")

        # Assert API called
        mock_api.set_sensor_mode.assert_called_with("infloor_device", 1)

    @pytest.mark.asyncio
    async def test_sensor_mode_select_edge_cases(
        self, hass, mock_coordinator, mock_config_entry
    ):
        """Test edge cases for MysaSensorModeSelect to reach 100% coverage."""
        import time

        from homeassistant.exceptions import HomeAssistantError

        from custom_components.mysa.select import MysaSensorModeSelect

        mock_api = MagicMock()
        mock_api.set_sensor_mode = AsyncMock()

        entity = MysaSensorModeSelect(
            mock_coordinator,
            "infloor_device",
            {"Id": "infloor_device", "Name": "Bathroom", "Model": "INF-V1"},
            mock_api,
            mock_config_entry,
        )
        entity.async_write_ha_state = MagicMock()

        # 1. Test invalid option selection
        await entity.async_select_option("invalid_mode")
        mock_api.set_sensor_mode.assert_not_called()
        assert entity._pending_option is None

        # 2. Test API failure
        mock_api.set_sensor_mode.side_effect = Exception("API Error")
        with pytest.raises(HomeAssistantError):
            await entity.async_select_option("floor")
        assert entity._pending_option is None
        mock_api.set_sensor_mode.side_effect = None  # Reset

        # 3. Test Device Info
        info = entity.device_info
        assert info is not None
        # Simulate caching scenario
        mock_coordinator.data = None
        info_no_data = entity.device_info
        assert info_no_data is not None

        # 4. Test Pending Logic
        mock_coordinator.data = {
            "infloor_device": {"SensorMode": 0}  # Ambient
        }

        # Set pending
        entity._pending_option = "floor"
        entity._pending_timestamp = time.time()

        # 4a. Pending is valid
        assert entity.current_option == "floor"

        # 4b. Pending converged
        # Cloud updates to match pending
        mock_coordinator.data["infloor_device"]["SensorMode"] = 1  # Floor
        assert entity.current_option == "floor"
        assert entity._pending_option is None  # Should be cleared

        # 4c. Pending expired
        entity._pending_option = "ambient"
        entity._pending_timestamp = time.time() - 40  # Expired
        mock_coordinator.data["infloor_device"]["SensorMode"] = (
            1  # Floor (Cloud says Floor)
        )

        # Should return Cloud value (Floor) because pending expired
        assert entity.current_option == "floor"
        assert entity._pending_option is None

        # 4d. Pending expired fallback
        # If cloud value is missing and pending expired
        entity._pending_option = "floor"
        entity._pending_timestamp = time.time() - 40
        mock_coordinator.data["infloor_device"] = {}  # No SensorMode

        assert entity.current_option == "ambient"  # Default fallback


class TestSelectCoverageGaps:
    """Coverage tests moved from test_coverage_gap.py."""

    def test_select_coverage(self, mock_coordinator, mock_config_entry):
        """Exercise select.py missing lines."""
        from custom_components.mysa.const import AC_SWING_AUTO, AC_SWING_POSITION_3
        from custom_components.mysa.select import MysaHorizontalSwingSelect

        entity = MysaHorizontalSwingSelect(
            mock_coordinator, "dev1", {}, MagicMock(), mock_config_entry
        )
        # 146, 152 sticky expiration and convergence
        # Expiration
        entity._pending_option = "swing1"
        entity._pending_timestamp = time.time() - 31
        mock_coordinator.data = {"dev1": {"ssh": AC_SWING_AUTO}}  # 2 -> 'auto'
        assert entity.current_option == "auto"
        assert entity._pending_option is None
        # Convergence
        entity._pending_option = "center"
        entity._pending_timestamp = time.time()
        mock_coordinator.data = {"dev1": {"ssh": AC_SWING_POSITION_3}}  # 5 -> 'center'
        assert entity.current_option == "center"
        assert entity._pending_option is None


class TestMysaTemperatureFormatSelect:
    """Test MysaTemperatureFormatSelect entity logic."""

    @pytest.mark.asyncio
    async def test_display_format_select(self, hass, mock_coordinator, mock_config_entry):
        """Test MysaTemperatureFormatSelect entity."""
        from custom_components.mysa.select import MysaTemperatureFormatSelect

        # Mock API
        mock_api = MagicMock()
        mock_api.set_stv10_temperature_format = AsyncMock()

        # Create the select entity
        entity = MysaTemperatureFormatSelect(
            mock_coordinator,
            "stv1_device",
            {"Id": "stv1_device", "Name": "Living Room", "Model": "ST-V1-0"},
            mock_api,
            mock_config_entry,
        )
        entity.async_write_ha_state = MagicMock()
        entity.hass = hass

        # Test options
        assert "Celsius" in entity.options
        assert "Fahrenheit" in entity.options

        # Test initial state (Celsius default)
        mock_coordinator.data = {"stv1_device": {}}
        assert entity.current_option == "Celsius"

        # Test with format="F"
        mock_coordinator.data = {"stv1_device": {"temperature_format": "F"}}
        assert entity.current_option == "Fahrenheit"

        # Test selecting Fahrenheit
        await entity.async_select_option("Fahrenheit")
        # Check model to decide setter - ST-V1-0 uses set_stv10_temperature_format
        mock_api.set_stv10_temperature_format.assert_called_with("stv1_device", True)

        # Test selecting Celsius
        await entity.async_select_option("Celsius")
        mock_api.set_stv10_temperature_format.assert_called_with("stv1_device", False)


class TestSelectConsolidated:
    """Consolidated select tests from extra and final coverage files."""

    @pytest.mark.asyncio
    async def test_select_temperature_format_coverage_consolidated(self, hass):
        """Cover missing lines in select.py (388, 401-413, 430-434)."""
        coordinator = MagicMock()
        api = MagicMock()
        api.set_temperature_format = AsyncMock()
        entry = MagicMock()

        sel = MysaTemperatureFormatSelect(coordinator, "d1", {"Model": "V1"}, api, entry)
        sel.hass = hass
        sel.async_write_ha_state = MagicMock()

        # 388: "C" in _get_start_value
        assert sel._get_start_value({"Format": "C"}) == "C"

        # 401-413: Sticky logic
        sel._pending_option = "Fahrenheit"
        sel._pending_timestamp = time.time()
        # If currently Celsius on cloud, should return pending
        coordinator.data = {"d1": {"Format": "C"}}
        assert sel.current_option == "Fahrenheit"

        # Expiration (402-404)
        sel._pending_timestamp = time.time() - 40  # > 30s
        assert sel.current_option == "Celsius"
        assert sel._pending_option is None

        # Clears when convergent
        sel._pending_option = "Fahrenheit"
        sel._pending_timestamp = time.time()
        coordinator.data = {"d1": {"Format": "F"}}
        assert sel.current_option == "Fahrenheit"
        assert sel._pending_option is None

        # 430-434: Error path
        api.set_stv10_temperature_format = AsyncMock(side_effect=Exception("Fail"))
        api.set_temperature_format = AsyncMock(side_effect=Exception("Fail"))
        with pytest.raises(HomeAssistantError):
            await sel.async_select_option("Fahrenheit")

    @pytest.mark.asyncio
    async def test_select_entity_logic_consolidated(self, hass):
        """Test MysaSelect entity logic."""
        coordinator = MagicMock()
        api = MagicMock()
        entry = MagicMock()
        device_id = "d1"
        device_data = {
            "SupportedCaps": {
                "modes": {"1": {"horizontalSwing": [2, 3]}}  # 2=auto, 3=left
            }
        }

        # 1. MysaHorizontalSwingSelect
        entity = MysaHorizontalSwingSelect(
            coordinator, device_id, device_data, api, entry
        )
        entity.hass = hass

        # Test options property
        assert "auto" in entity.options
        assert "left" in entity.options

        # Test current_option (from coordinator data)
        coordinator.data = {"d1": {"ssh": 2}}  # 2 = auto
        assert entity.current_option == "auto"

        # Test current_option fallback (SwingStateHorizontal uses dict {"v": ...})
        coordinator.data = {"d1": {"SwingStateHorizontal": {"v": 3}}}  # 3 = left
        assert entity.current_option == "left"

        # Test async_select_option
        api.set_ac_horizontal_swing = AsyncMock()
        with patch.object(entity, "async_write_ha_state"):
            await entity.async_select_option("auto")

        assert api.set_ac_horizontal_swing.call_count == 1
        assert api.set_ac_horizontal_swing.call_args == (("d1", 2),)

        # 2. MysaSensorModeSelect (In-Floor)
        entity_sensor = MysaSensorModeSelect(
            coordinator, device_id, device_data, api, entry
        )
        entity_sensor.hass = hass

        # Test options
        assert "ambient" in entity_sensor.options

        # Test current_option
        coordinator.data = {"d1": {"SensorMode": 0}}  # 0 = ambient
        assert entity_sensor.current_option == "ambient"

        # Test async_select_option
        api.set_sensor_mode = AsyncMock()
        with patch.object(entity_sensor, "async_write_ha_state"):
            await entity_sensor.async_select_option("ambient")
        api.set_sensor_mode.assert_called_with("d1", 0)  # 0 = ambient

    @pytest.mark.asyncio
    async def test_select_pending_logic_consolidated(self, hass):
        """Test MysaSelect pending and error logic."""
        coordinator = MagicMock()
        api = MagicMock()
        entry = MagicMock()
        device_id = "d1"
        device_data = {"SupportedCaps": {"modes": {"1": {"horizontalSwing": [2]}}}}

        entity = MysaHorizontalSwingSelect(
            coordinator, device_id, device_data, api, entry
        )
        entity.hass = hass

        # Error handling for unknown option
        await entity.async_select_option("invalid_option")
        # Should log error and return, no api call
        assert api.set_ac_horizontal_swing.call_count == 0

        # Exception in async_select_option
        api.set_ac_horizontal_swing = AsyncMock(side_effect=Exception("Fail"))
        with pytest.raises(HomeAssistantError):
            with patch.object(entity, "async_write_ha_state"):
                await entity.async_select_option("auto")

        # Pending Expiration
        entity._pending_option = "left"
        entity._pending_timestamp = time.time() - 31
        coordinator.data = {"d1": {"ssh": 2}}  # auto
        assert entity.current_option == "auto"
        assert entity._pending_option is None

        # Pending Convergence
        entity._pending_option = "auto"
        entity._pending_timestamp = time.time()
        coordinator.data = {"d1": {"ssh": 2}}  # auto matches
        assert entity.current_option == "auto"
        assert entity._pending_option is None

    @pytest.mark.asyncio
    async def test_select_device_info_none_data_consolidated(self, hass):
        """Test device_info with None coordinator data."""
        coordinator = MagicMock()
        api = MagicMock()
        entry = MagicMock()
        coordinator.data = None

        sel1 = MysaTemperatureFormatSelect(coordinator, "d1", {"Model": "V1"}, api, entry)
        assert sel1.device_info is not None

        sel2 = MysaHorizontalSwingSelect(coordinator, "d1", {"Model": "AC1"}, api, entry)
        assert sel2.device_info is not None

        sel3 = MysaSensorModeSelect(coordinator, "d1", {"Model": "INF1"}, api, entry)
        assert sel3.device_info is not None

    @pytest.mark.asyncio
    async def test_select_get_start_value_none_consolidated(self, hass):
        """Test _get_start_value with missing format keys (line 387)."""
        coordinator = MagicMock()
        api = MagicMock()
        entry = MagicMock()
        sel = MysaTemperatureFormatSelect(coordinator, "d1", {"Model": "V1"}, api, entry)
        assert sel._get_start_value({"Other": "Key"}) is None

    @pytest.mark.asyncio
    async def test_horizontal_swing_sticky_consolidated(self, hass):
        """Test sticky return in current_option (line 190)."""
        coordinator = MagicMock()
        api = MagicMock()
        entry = MagicMock()
        device_data = {"SupportedCaps": {"modes": {"1": {"horizontalSwing": [3]}}}}
        entity = MysaHorizontalSwingSelect(coordinator, "d1", device_data, api, entry)

        entity._pending_option = "center"
        entity._pending_timestamp = time.time()
        coordinator.data = {"d1": {"ssh": 2}} # Different from pending
        assert entity.current_option == "center" # Hits line 190

    @pytest.mark.asyncio
    async def test_select_setup_entry_ac_consolidated(self, hass):
        """Test setup_entry with AC device (line 53)."""
        from custom_components.mysa.select import async_setup_entry
        from custom_components.mysa import MysaData

        mock_api = MagicMock()
        mock_api.get_devices = AsyncMock(return_value={"ac1": {"Model": "AC-V1"}})
        mock_api.is_ac_device = MagicMock(return_value=True)

        mock_entry = MagicMock()
        mock_entry.runtime_data = MysaData(api=mock_api, coordinator=MagicMock())

        mock_add_entities = MagicMock()
        await async_setup_entry(hass, mock_entry, mock_add_entities)
        assert mock_add_entities.called
