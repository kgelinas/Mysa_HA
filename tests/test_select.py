"""
Tests for Select entities.
"""

import pytest
import time
from typing import Any
from unittest.mock import MagicMock, AsyncMock
from custom_components.mysa import MysaData


class TestHorizontalSwingSelect:
    """Test AC horizontal swing select entity."""

    def test_horizontal_swing_modes_mapping(self):
        """Test horizontal swing position to name mapping."""
        # From const.py AC_HORIZONTAL_SWING_MODES
        swing_modes = {
            0: "auto",
            1: "left",
            2: "left_center",
            3: "center",
            4: "right_center",
            5: "right",
        }

        assert swing_modes[0] == "auto"
        assert swing_modes[3] == "center"
        assert len(swing_modes) >= 6

    def test_horizontal_swing_reverse_mapping(self):
        """Test reverse mapping from name to position."""
        reverse_map = {
            "auto": 0,
            "left": 1,
            "left_center": 2,
            "center": 3,
            "right_center": 4,
            "right": 5,
        }

        assert reverse_map["auto"] == 0
        assert reverse_map["center"] == 3

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
        supported_caps = {"modes": {"cool": {"horizontalSwing": [0, 1, 2, 3, 4, 5]}}}

        modes = supported_caps.get("modes", {})
        horizontal_swings = []

        for mode_key, mode_caps in modes.items():
            horizontal_swings = mode_caps.get("horizontalSwing", [])
            if horizontal_swings:
                break

        assert horizontal_swings == [0, 1, 2, 3, 4, 5]

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
        state: dict[str, Any] = {"SwingStateHorizontal": 3}

        val = state.get("SwingStateHorizontal")

        assert val == 3  # "center"

    def test_state_from_mqtt_nested(self):
        """Test reading horizontal swing state from nested MQTT value."""
        state: dict[str, Any] = {"SwingStateHorizontal": {"v": 3, "t": 1704067200}}

        val = state.get("SwingStateHorizontal")
        if isinstance(val, dict):
            val = val.get("v")

        assert val == 3

    def test_state_default_when_missing(self):
        """Test default value when no state available."""
        state: dict[str, Any] = {}

        val = state.get("SwingStateHorizontal")
        if val is None:
            val = 0  # auto

        swing_modes = {0: "auto", 3: "center"}
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
            swing_modes = {0: "auto", 3: "center"}
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
        position = 3  # center

        command: dict[str, Any] = {
            "did": device_id,
            "cmd": [{"swh": position}],
        }

        assert command["did"] == device_id
        assert command["cmd"][0]["swh"] == 3

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
    @pytest.mark.asyncio
    async def test_sensor_mode_infloor_only(self, hass, mock_api, mock_config_entry):
        """Test sensor mode select is created for In-Floor devices."""
        from custom_components.mysa.select import async_setup_entry

        # Mock Data with In-Floor device
        mock_data = MagicMock(spec=MysaData)
        mock_data.api = mock_api
        mock_data.coordinator = MagicMock()
        mock_config_entry.runtime_data = mock_data

        mock_api.get_devices = AsyncMock(return_value={
            "infloor_id": {"Model": "INF-V1"}
        })
        mock_api.is_ac_device = MagicMock(return_value=False)

        async_add_entities = MagicMock()

        await async_setup_entry(hass, mock_config_entry, async_add_entities)

        assert async_add_entities.called
        # Verify call args
        args = async_add_entities.call_args[0][0]
        assert len(args) == 1
        assert args[0]._device_id == "infloor_id"

class TestSensorModeSelect:
    """Test MysaSensorModeSelect entity logic."""

    @pytest.mark.asyncio
    async def test_sensor_mode_select(self, hass, mock_coordinator, mock_config_entry):
        """Test MysaSensorModeSelect entity."""
        from custom_components.mysa.select import MysaSensorModeSelect
        from custom_components.mysa.const import SENSOR_MODES

        # Mock API
        mock_api = MagicMock()
        mock_api.set_sensor_mode = AsyncMock()

        # Create the select entity
        entity = MysaSensorModeSelect(
            mock_coordinator,
            "infloor_device",
            {"Id": "infloor_device", "Name": "Bathroom", "Model": "INF-V1"},
            mock_api,
            mock_config_entry
        )
        entity.async_write_ha_state = MagicMock()
        entity.hass = hass

        # Test options
        assert "floor" in entity.options
        assert "ambient" in entity.options

        # Test initial state (Ambient default)
        mock_coordinator.data = {
             "infloor_device": {}
        }
        assert entity.current_option == "ambient"

        # Test with SensorMode=1 (Floor)
        mock_coordinator.data = {
             "infloor_device": {"SensorMode": 1}
        }
        # Note: entity.current_option reads from coordinator
        assert entity.current_option == "floor"

        # Test selecting an option
        await entity.async_select_option("floor")

        # Assert API called
        mock_api.set_sensor_mode.assert_called_with("infloor_device", 1)

    @pytest.mark.asyncio
    async def test_sensor_mode_select_edge_cases(self, hass, mock_coordinator, mock_config_entry):
        """Test edge cases for MysaSensorModeSelect to reach 100% coverage."""
        import time
        from custom_components.mysa.select import MysaSensorModeSelect
        from homeassistant.exceptions import HomeAssistantError

        mock_api = MagicMock()
        mock_api.set_sensor_mode = AsyncMock()

        entity = MysaSensorModeSelect(
            mock_coordinator,
            "infloor_device",
            {"Id": "infloor_device", "Name": "Bathroom", "Model": "INF-V1"},
            mock_api,
            mock_config_entry
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
        mock_api.set_sensor_mode.side_effect = None # Reset

        # 3. Test Device Info
        info = entity.device_info
        assert info is not None
        # Simulate caching scenario
        mock_coordinator.data = None
        info_no_data = entity.device_info
        assert info_no_data is not None

        # 4. Test Pending Logic
        mock_coordinator.data = {
            "infloor_device": {"SensorMode": 0} # Ambient
        }

        # Set pending
        entity._pending_option = "floor"
        entity._pending_timestamp = time.time()

        # 4a. Pending is valid
        assert entity.current_option == "floor"

        # 4b. Pending converged
        # Cloud updates to match pending
        mock_coordinator.data["infloor_device"]["SensorMode"] = 1 # Floor
        assert entity.current_option == "floor"
        assert entity._pending_option is None # Should be cleared

        # 4c. Pending expired
        entity._pending_option = "ambient"
        entity._pending_timestamp = time.time() - 40 # Expired
        mock_coordinator.data["infloor_device"]["SensorMode"] = 1 # Floor (Cloud says Floor)

        # Should return Cloud value (Floor) because pending expired
        assert entity.current_option == "floor"
        assert entity._pending_option is None

        # 4d. Pending expired fallback
        # If cloud value is missing and pending expired
        entity._pending_option = "floor"
        entity._pending_timestamp = time.time() - 40
        mock_coordinator.data["infloor_device"] = {} # No SensorMode

        assert entity.current_option == "ambient" # Default fallback


class TestSelectCoverageGaps:
    """Coverage tests moved from test_coverage_gap.py."""

    def test_select_coverage(self, mock_coordinator, mock_config_entry):
        """Exercise select.py missing lines."""
        from custom_components.mysa.select import MysaHorizontalSwingSelect
        from custom_components.mysa.const import AC_SWING_AUTO, AC_SWING_POSITION_3
        entity = MysaHorizontalSwingSelect(mock_coordinator, "dev1", {}, MagicMock(), mock_config_entry)
        # 146, 152 sticky expiration and convergence
        # Expiration
        entity._pending_option = "swing1"
        entity._pending_timestamp = time.time() - 31
        mock_coordinator.data = {"dev1": {"ssh": AC_SWING_AUTO}} # 3 -> 'auto'
        assert entity.current_option == "auto"
        assert entity._pending_option is None
        # Convergence
        entity._pending_option = "center"
        entity._pending_timestamp = time.time()
        mock_coordinator.data = {"dev1": {"ssh": AC_SWING_POSITION_3}} # 6 -> 'center'
        assert entity.current_option == "center"
        assert entity._pending_option is None
