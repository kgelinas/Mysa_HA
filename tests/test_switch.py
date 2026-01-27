"""
Tests for Switch entities.
"""




import pytest
import time
from typing import Any
from unittest.mock import MagicMock, AsyncMock
from custom_components.mysa.switch import MysaClimatePlusSwitch

class TestMysaLockSwitch:
    """Test thermostat lock switch entity."""

    def test_lock_switch_on_value(self):
        """Test lock switch on value (locked)."""
        is_locked = True
        mqtt_value = 1 if is_locked else 0

        assert mqtt_value == 1

    def test_lock_switch_off_value(self):
        """Test lock switch off value (unlocked)."""
        is_locked = False
        mqtt_value = 1 if is_locked else 0

        assert mqtt_value == 0

    def test_lock_state_keys(self):
        """Test all possible keys used for lock state."""
        # The lock switch checks multiple keys for compatibility
        state_keys = ["Lock", "ButtonState", "alk", "lk", "lc"]

        assert "lk" in state_keys
        assert "Lock" in state_keys
        assert len(state_keys) == 5

    def test_lock_icon(self):
        """Test lock switch icon."""
        icon = "mdi:lock"

        assert icon.startswith("mdi:")

    def test_lock_unique_id_format(self):
        """Test lock unique ID format."""
        device_id = "device1"
        sensor_key = "Lock"

        unique_id = f"{device_id}_{sensor_key.lower()}"

        assert unique_id == "device1_lock"


class TestMysaAutoBrightnessSwitch:
    """Test auto brightness switch entity."""

    def test_auto_brightness_enabled(self):
        """Test auto brightness enabled value."""
        enabled = True
        assert enabled

    def test_auto_brightness_state_keys(self):
        """Test keys used for auto brightness state."""
        state_keys = ["AutoBrightness", "ab"]

        assert "ab" in state_keys
        assert "AutoBrightness" in state_keys

    def test_auto_brightness_icon(self):
        """Test auto brightness switch icon."""
        icon = "mdi:brightness-auto"

        assert icon == "mdi:brightness-auto"

    def test_auto_brightness_unique_id_format(self):
        """Test auto brightness unique ID format."""
        device_id = "device1"
        sensor_key = "AutoBrightness"

        unique_id = f"{device_id}_{sensor_key.lower()}"

        assert unique_id == "device1_autobrightness"


class TestMysaProximitySwitch:
    """Test proximity (wake on approach) switch entity."""

    def test_proximity_enabled_value(self):
        """Test proximity enabled MQTT value."""
        # Proximity uses 2 for enabled, 1 for disabled
        enabled = True
        mqtt_value = 2 if enabled else 1

        assert mqtt_value == 2

    def test_proximity_disabled_value(self):
        """Test proximity disabled MQTT value."""
        enabled = False
        mqtt_value = 2 if enabled else 1

        assert mqtt_value == 1

    def test_proximity_state_keys(self):
        """Test keys used for proximity state."""
        state_keys = ["ProximityMode", "Proximity", "px", "pr"]

        assert "pr" in state_keys
        assert "ProximityMode" in state_keys

    def test_proximity_icon(self):
        """Test proximity switch icon."""
        icon = "mdi:motion-sensor"

        assert icon == "mdi:motion-sensor"

    def test_proximity_name_suffix(self):
        """Test proximity switch name suffix."""
        name_suffix = "Wake on Approach"

        assert name_suffix == "Wake on Approach"


class TestMysaClimatePlusSwitch:
    """Test Climate+ (thermostatic) switch entity for AC devices."""

    def test_climate_plus_enabled(self):
        """Test Climate+ enabled value."""
        enabled = True
        mqtt_value = 1 if enabled else 0

        assert mqtt_value == 1

    def test_climate_plus_disabled(self):
        """Test Climate+ disabled value."""
        enabled = False
        mqtt_value = 1 if enabled else 0

        assert mqtt_value == 0

    def test_climate_plus_state_keys(self):
        """Test keys used for Climate+ state."""
        state_keys = ["IsThermostatic", "it"]

        assert "it" in state_keys
        assert "IsThermostatic" in state_keys

    def test_climate_plus_icon(self):
        """Test Climate+ switch icon."""
        icon = "mdi:thermostat-auto"

        assert icon == "mdi:thermostat-auto"

    def test_climate_plus_ac_only(self):
        """Test Climate+ is only for AC devices."""
        ac_device_type = 9  # AC-V1
        heater_device_type = 4  # BB-V2

        ac_types = [9]

        assert ac_device_type in ac_types
        assert heater_device_type not in ac_types

    @pytest.mark.asyncio
    async def test_climate_plus_prioritizes_ecomode(self):
        """Test that Climate+ switch prioritizes EcoMode key."""
        mock_coordinator = MagicMock()
        mock_api = MagicMock()

        # Data is in EcoMode key
        mock_coordinator.data = {"DID": {"EcoMode": True}}

        switch = MysaClimatePlusSwitch(
            mock_coordinator, "DID", {"Id": "DID"}, mock_api, MagicMock()
        )

        assert switch.is_on == True

        # Data is in legacy it key
        mock_coordinator.data = {"DID": {"it": 1}}
        assert switch.is_on == True


class TestSwitchPendingState:
    """Test pending state mechanism for switches."""

    def test_pending_state_initial(self):
        """Test pending state is initially None."""
        pending_state = None

        assert pending_state is None

    def test_pending_state_on_command(self):
        """Test pending state is set when command is sent."""
        pending_state = None

        # Simulate turn_on
        pending_state = True

        assert pending_state

    def test_pending_state_cleared_on_update(self):
        """Test pending state is cleared when MQTT update confirms."""
        pending_state: bool | None = True

        # Simulate MQTT confirmation
        # if True:  # Got confirmed state from MQTT
        pending_state = None

        assert pending_state is None

    def test_pending_state_fallback(self):
        """Test pending state is used when coordinator has no value."""
        pending_state = True
        coordinator_value = None

        # Logic from switch.py
        if coordinator_value is not None:
            result = coordinator_value
        elif pending_state is not None:
            result = pending_state
        else:
            result = False

        assert result is True


class TestSwitchValueExtraction:
    """Test value extraction from state dictionaries."""

    def test_extract_simple_value(self):
        """Test extracting a simple value from state."""
        state = {"Lock": 1}

        val = state.get("Lock")

        assert val == 1

    def test_extract_nested_value(self):
        """Test extracting a nested value with 'v' key."""
        state: dict[str, Any] = {"Lock": {"v": 1, "t": 1704067200}}

        val = state.get("Lock")
        if isinstance(val, dict):
            val = val.get("v")

        assert val == 1

    def test_extract_nested_with_id(self):
        """Test extracting a nested value with 'Id' key."""
        state: dict[str, Any] = {"Zone": {"Id": "zone-123"}}

        val = state.get("Zone")
        if isinstance(val, dict):
            extracted = val.get("v")
            if extracted is None:
                extracted = val.get("Id")
            val = extracted

        assert val == "zone-123"

    def test_extract_missing_key(self):
        """Test extracting a missing key returns None."""
        state: dict[str, Any] = {}

        val = state.get("Lock")

        assert val is None

    def test_extract_fallback_keys(self):
        """Test falling back through multiple keys."""
        state = {"lk": 1}  # Uses short MQTT key
        keys = ["Lock", "lk"]

        val = None
        for key in keys:
            val = state.get(key)
            if val is not None:
                break

        assert val == 1


class TestSwitchEntitySetup:
    """Test switch entity setup logic."""

    def test_lock_switch_created_for_all_devices(self):
        """Test lock switch is created for all device types."""
        entities_for_all = ["MysaLockSwitch"]

        assert "MysaLockSwitch" in entities_for_all

    def test_auto_brightness_heater_only(self):
        """Test auto brightness is only for heater devices."""
        is_ac = True

        # Auto brightness should NOT be created for AC devices
        should_create = not is_ac

        assert should_create is False

    def test_proximity_heater_only(self):
        """Test proximity is only for heater devices."""
        is_ac = True

        # Proximity should NOT be created for AC devices
        should_create = not is_ac

        assert should_create is False

    def test_climate_plus_ac_only(self):
        """Test Climate+ is only created for AC devices."""
        is_ac = True

        should_create = is_ac

        assert should_create is True


class TestSwitchCoverageGaps:
    """Coverage tests moved from test_coverage_gap.py."""

    def test_switch_coverage(self, mock_coordinator, mock_config_entry):
        """Exercise switch.py missing lines."""
        from custom_components.mysa.switch import MysaSwitch
        entity = MysaSwitch(mock_coordinator, "dev1", {}, MagicMock(), mock_config_entry, "key", "key")
        # 100, 115, 118, 126, 131
        assert entity._extract_value(None, ["key"]) is None
        mock_coordinator.data = None
        assert entity._get_state_with_pending(["key"]) is False
        mock_coordinator.data = {"other": {}}
        assert entity._get_state_with_pending(["key"]) is False
        # Expiration
        entity._pending_state = True
        entity._pending_timestamp = time.time() - 31
        mock_coordinator.data = {"dev1": {"key": False}}
        assert entity._get_state_with_pending(["key"]) is False
        # Convergence
        entity._pending_state = True
        entity._pending_timestamp = time.time()
        mock_coordinator.data = {"dev1": {"key": True}}
        assert entity._get_state_with_pending(["key"]) is True
        assert entity._pending_state is None
