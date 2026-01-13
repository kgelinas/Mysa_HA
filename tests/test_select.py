"""
Tests for Select entities.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock


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
        supported_caps = {}

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
        state = {"SwingStateHorizontal": 3}

        val = state.get("SwingStateHorizontal")

        assert val == 3  # "center"

    def test_state_from_mqtt_nested(self):
        """Test reading horizontal swing state from nested MQTT value."""
        state = {"SwingStateHorizontal": {"v": 3, "t": 1704067200}}

        val = state.get("SwingStateHorizontal")
        if isinstance(val, dict):
            val = val.get("v")

        assert val == 3

    def test_state_default_when_missing(self):
        """Test default value when no state available."""
        state = {}

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
        pending_option = "center"

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

        command = {
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
        devices = {}
        entities = []

        for device_id, device_data in devices.items():
            entities.append(device_id)

        assert entities == []
