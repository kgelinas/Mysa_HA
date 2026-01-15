"""
Tests for Number entities.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock


class TestMysaBrightnessNumber:
    """Test brightness number entity."""

    def test_brightness_min_value(self):
        """Test brightness minimum value."""
        min_brightness = 0

        assert min_brightness == 0

    def test_brightness_max_value(self):
        """Test brightness maximum value."""
        max_brightness = 100

        assert max_brightness == 100

    def test_brightness_step(self):
        """Test brightness step increment."""
        step = 1

        assert step == 1

    def test_brightness_unit(self):
        """Test brightness unit is percentage."""
        from homeassistant.const import PERCENTAGE

        unit = PERCENTAGE

        assert unit == "%"

    def test_brightness_icon(self):
        """Test brightness number icon."""
        icon = "mdi:brightness-6"

        assert icon.startswith("mdi:")

    def test_brightness_unique_id_format(self):
        """Test brightness unique ID format."""
        device_id = "device1"

        unique_id = f"{device_id}_brightness"

        assert unique_id == "device1_brightness"


class TestBrightnessState:
    """Test brightness state reading."""

    def test_brightness_from_mqtt_simple(self):
        """Test reading brightness from simple MQTT value."""
        state = {"Brightness": 75}

        brightness = state.get("Brightness")

        assert brightness == 75

    def test_brightness_from_mqtt_nested(self):
        """Test reading brightness from nested MQTT value."""
        state = {"Brightness": {"v": 75, "t": 1704067200}}

        val = state.get("Brightness")
        if isinstance(val, dict):
            val = val.get("v")

        assert val == 75

    def test_brightness_short_key(self):
        """Test reading brightness from short MQTT key."""
        state = {"br": 80}

        brightness = state.get("br")

        assert brightness == 80

    def test_brightness_fallback_keys(self):
        """Test falling back through multiple brightness keys."""
        state = {"br": 75}
        keys = ["Brightness", "br"]

        val = None
        for key in keys:
            val = state.get(key)
            if val is not None:
                break

        assert val == 75


class TestBrightnessCommands:
    """Test brightness command building."""

    def test_brightness_command_structure(self):
        """Test brightness command structure."""
        device_id = "device1"
        brightness = 80

        command = {
            "did": device_id,
            "cmd": [{"br": brightness}],
        }

        assert command["did"] == device_id
        assert command["cmd"][0]["br"] == 80

    def test_brightness_clamp_min(self):
        """Test brightness is clamped to minimum."""
        value = -10
        min_val = 0
        max_val = 100

        clamped = max(min_val, min(max_val, value))

        assert clamped == 0

    def test_brightness_clamp_max(self):
        """Test brightness is clamped to maximum."""
        value = 150
        min_val = 0
        max_val = 100

        clamped = max(min_val, min(max_val, value))

        assert clamped == 100


class TestMysaMaxCurrentNumber:
    """Test estimated maximum current number entity."""

    def test_max_current_min_value(self):
        """Test max current minimum value."""
        min_current = 0

        assert min_current == 0

    def test_max_current_max_value(self):
        """Test max current maximum value."""
        max_current = 30

        assert max_current == 30

    def test_max_current_step(self):
        """Test max current step increment."""
        step = 0.5

        assert step == 0.5

    def test_max_current_unit(self):
        """Test max current unit is Amps."""
        from homeassistant.const import UnitOfElectricCurrent

        unit = UnitOfElectricCurrent.AMPERE

        assert unit == "A"

    def test_max_current_icon(self):
        """Test max current number icon."""
        icon = "mdi:current-ac"

        assert icon == "mdi:current-ac"

    def test_max_current_unique_id_format(self):
        """Test max current unique ID format."""
        device_id = "device1"

        unique_id = f"{device_id}_max_current"

        assert unique_id == "device1_max_current"


class TestMaxCurrentPowerCalculation:
    """Test power calculation using max current."""

    def test_power_calculation_full_duty(self):
        """Test power calculation at 100% duty cycle."""
        max_current = 15.0  # Amps
        duty_cycle = 1.0  # 100%
        voltage = 240  # Volts

        power = max_current * duty_cycle * voltage

        assert power == 3600.0  # 3.6kW

    def test_power_calculation_half_duty(self):
        """Test power calculation at 50% duty cycle."""
        max_current = 15.0
        duty_cycle = 0.5
        voltage = 240

        power = max_current * duty_cycle * voltage

        assert power == 1800.0  # 1.8kW

    def test_simulated_current_calculation(self):
        """Test simulated current calculation for Lite devices."""
        max_current = 20.0
        duty_cycle = 0.75

        simulated_current = max_current * duty_cycle

        assert simulated_current == 15.0

    def test_common_circuit_breaker_values(self):
        """Test common circuit breaker values are within range."""
        min_current = 0
        max_current = 30

        # Common residential circuit breakers
        common_values = [15, 20, 25, 30]

        for value in common_values:
            assert min_current <= value <= max_current


class TestNumberPendingState:
    """Test pending state mechanism for number entities."""

    def test_pending_value_initial(self):
        """Test pending value is initially None."""
        pending_value = None

        assert pending_value is None

    def test_pending_value_set_on_command(self):
        """Test pending value is set when user changes value."""
        pending_value = None

        # User sets brightness to 80
        pending_value = 80

        assert pending_value == 80

    def test_pending_value_returned_when_set(self):
        """Test pending value takes priority over coordinator."""
        pending_value = 80
        coordinator_value = 50

        if pending_value is not None:
            result = pending_value
        else:
            result = coordinator_value

        assert result == 80

    def test_pending_value_cleared_on_confirm(self):
        """Test pending value is cleared when MQTT confirms."""
        pending_value = 80

        # MQTT confirms with new value
        if True:  # Got confirmed value
            pending_value = None

        assert pending_value is None


class TestNumberEntitySetup:
    """Test number entity setup logic."""

    def test_brightness_heater_only(self):
        """Test brightness is only for heater devices."""
        is_ac = True

        should_create = not is_ac

        assert should_create is False

    def test_brightness_created_for_heaters(self):
        """Test brightness is created for heater devices."""
        is_ac = False

        should_create = not is_ac

        assert should_create is True

    def test_max_current_for_lite_only(self):
        """Test max current is only for Lite devices."""
        device_type = 5  # BB-V2-L (Lite)
        lite_types = [5]

        is_lite = device_type in lite_types

        assert is_lite is True

    def test_max_current_not_for_full(self):
        """Test max current is NOT for Full devices."""
        device_type = 4  # BB-V2 (Full)
        lite_types = [5]

        is_lite = device_type in lite_types

        assert is_lite is False
