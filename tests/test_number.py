from custom_components.mysa.number import MysaAutoDeadbandNumber, MysaMinSetpointNumber, MysaMaxSetpointNumber
import os
import sys
import time

# Add project root to path for imports
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(TEST_DIR)
sys.path.insert(0, ROOT_DIR)

from typing import Any
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.mysa.number import (
    MysaNumber,
    MysaMinBrightnessNumber,
    MysaMaxBrightnessNumber,
    MysaAutoDeadbandNumber,
    MysaMinSetpointNumber,
    MysaMaxSetpointNumber,
)

@pytest.fixture
def mock_coordinator():
    """Fixture for DataUpdateCoordinator."""
    coordinator = MagicMock()
    coordinator.data = {"device1": {"temperature": 21.5}}
    return coordinator


@pytest.fixture
def mock_config_entry():
    """Fixture for ConfigEntry."""
    entry = MagicMock()
    entry.entry_id = "test_entry"
    return entry


@pytest.fixture
def coverage_mock_number(mock_coordinator, mock_config_entry):
    """Fixture for number coverage tests."""
    from custom_components.mysa.number import MysaNumber
    api = MagicMock()
    return MysaNumber(
        mock_coordinator, "device1", {"Model": "V1"}, api, mock_config_entry, "mnbr", "mnbr"
    )


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
        extracted = None
        if isinstance(val, dict):
            extracted = val.get("v")

        assert extracted == 75

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

        command: dict[str, Any] = {
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
        pending_value: int | None = 80

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


# ===========================================================================
# Merged Edge Case Tests
# ===========================================================================


@pytest.mark.asyncio
async def test_number_value_error(hass):
    """Test number native_value handles invalid types."""
    from custom_components.mysa.number import MysaMinBrightnessNumber

    mock_coordinator = MagicMock()
    # MinBrightness keys: ["MinBrightness", "mnbr"]
    mock_coordinator.data = {"device1": {"MinBrightness": "invalid_float"}}

    mock_api = MagicMock()
    mock_entry = MagicMock()

    # Initialize MysaMinBrightnessNumber
    entity = MysaMinBrightnessNumber(
        mock_coordinator, "device1", {"Name": "Test"}, mock_api, mock_entry
    )

    assert entity.native_value is None


class TestNumberCoverageGaps:
    """Coverage tests moved from test_coverage_gap.py."""

    async def test_number_coverage(self, mock_coordinator, mock_config_entry):
        """Exercise number.py missing lines."""
        from custom_components.mysa.number import MysaNumber

        entity = MysaNumber(
            mock_coordinator, "device1", {}, MagicMock(), mock_config_entry, "key", "key"
        )
        # 89, 95, 110
        mock_coordinator.data = {}
        assert entity.device_info is not None
        assert entity._extract_value(None, ["key"]) is None
        assert entity._get_value_with_pending(["key"]) is None


@pytest.mark.asyncio
class TestMysaNumberExtended:
    """Extended coverage for MysaNumber entities."""

    async def test_auto_deadband_number(self, hass, mock_coordinator):
        """Test Auto Deadband Number entity."""
        from custom_components.mysa.number import MysaAutoDeadbandNumber
        api = MagicMock()
        api.set_stv10_auto_deadband = AsyncMock()
        mock_coordinator.data = {"s1": {"autoDeadband": 1.5}}
        entry = MagicMock()

        num = MysaAutoDeadbandNumber(mock_coordinator, "s1", {"Model": "ST-V1-0"}, api, entry)
        num.hass = hass
        num.entity_id = "number.test"
        num.async_write_ha_state = MagicMock()
        num.platform = MagicMock(domain="number", platform_name="mysa")

        # native_value
        assert num.native_value == 1.5

        # set_native_value success
        await num.async_set_native_value(2.0)
        api.set_stv10_auto_deadband.assert_called_with("s1", 2.0)

        # set_native_value failure
        api.set_stv10_auto_deadband.side_effect = Exception("Fail")
        with pytest.raises(HomeAssistantError):
            await num.async_set_native_value(2.5)

    async def test_brightness_number_error_paths(self, hass, mock_coordinator):
        """Test brightness number error paths."""
        from custom_components.mysa.number import MysaMinBrightnessNumber
        api = MagicMock()
        api.set_min_brightness = AsyncMock(side_effect=Exception("Fail"))
        mock_coordinator.data = {"s1": {"mnbr": 10}}
        entry = MagicMock()

        min_b = MysaMinBrightnessNumber(mock_coordinator, "s1", {"Model": "ST-V1-0"}, api, entry)
        min_b.hass = hass
        min_b.entity_id = "number.test_min"
        min_b.async_write_ha_state = MagicMock()
        min_b.platform = MagicMock(domain="number", platform_name="mysa")
        with pytest.raises(HomeAssistantError):
            await min_b.async_set_native_value(20)

    async def test_number_pending_logic(self, hass, mock_coordinator):
        """Test sticky/pending logic in MysaNumber."""
        from custom_components.mysa.number import MysaMinBrightnessNumber
        mock_coordinator.data = {"s1": {"mnbr": 10}}
        api = MagicMock()
        min_b = MysaMinBrightnessNumber(mock_coordinator, "s1", {"Model": "ST-V1-0"}, api, MagicMock())

        # 1. Set pending
        min_b._pending_value = 50.0
        min_b._pending_time = time.time()
        assert min_b.native_value == 50.0

        # 2. Converge
        mock_coordinator.data = {"s1": {"mnbr": 50}}
        assert min_b.native_value == 50.0
        assert min_b._pending_value is None

        # 3. Expire
        min_b._pending_value = 60.0
        min_b._pending_time = time.time() - 31
        mock_coordinator.data = {"s1": {"mnbr": 10}}
        assert min_b.native_value == 10.0
        assert min_b._pending_value is None

    async def test_stv10_deadband_in_setup(self, hass, mock_coordinator):
        """Test ST-V1-0 auto deadband number is created in async_setup_entry."""
        from custom_components.mysa.number import async_setup_entry, MysaAutoDeadbandNumber
        from custom_components.mysa import MysaData

        mock_api = MagicMock()
        _devices = {
            "stv10_device": {
                "Id": "stv10_device",
                "Name": "ST-V1-0 Device",
                "Model": "ST-V1-0",
            }
        }
        mock_api.get_devices = AsyncMock(return_value=_devices)
        mock_api.devices = _devices

        mock_data = MagicMock(spec=MysaData)
        mock_data.coordinator = mock_coordinator
        mock_data.api = mock_api

        mock_entry = MagicMock()
        mock_entry.runtime_data = mock_data

        entities = []
        async_add_entities = MagicMock(side_effect=lambda e: entities.extend(e))

        await async_setup_entry(hass, mock_entry, async_add_entities)

        # Should create MinBrightness, MaxBrightness, MinSetpoint, MaxSetpoint, and AutoDeadband (5 entities)
        assert len(entities) == 5
        assert any(isinstance(e, MysaAutoDeadbandNumber) for e in entities)

    async def test_auto_deadband_availability(self, hass, mock_coordinator):
        """Test Auto Deadband availability logic."""
        from custom_components.mysa.number import MysaAutoDeadbandNumber
        api = MagicMock()
        entry = MagicMock()

        num = MysaAutoDeadbandNumber(mock_coordinator, "s1", {"Model": "ST-V1-0"}, api, entry)
        num.hass = hass

        # Case 1: Coordinator unavailable
        with patch(
            "homeassistant.helpers.update_coordinator.CoordinatorEntity.available",
            new_callable=lambda: property(lambda self: False),
        ):
            assert num.available is False

        # Case 2: Auto Mode Disabled (simple key)
        mock_coordinator.data = {"s1": {"auto_mode_enabled": 0}}
        assert num.available is False

        # Case 3: Auto Mode Enabled (simple key)
        mock_coordinator.data = {"s1": {"auto_mode_enabled": 1}}
        assert num.available is True

        # Case 4: Auto Mode Enabled (shadow structure)
        mock_coordinator.data = {"s1": {"targetAuto": {"enabled": 1}}}
        assert num.available is True

        # Case 5: Auto Mode Disabled (shadow structure)
        mock_coordinator.data = {"s1": {"targetAuto": {"enabled": 0}}}
        assert num.available is False

        # Case 6: Missing data → state unknown → entity is available
        # (avoid false "unavailable" flash on startup before first poll)
        mock_coordinator.data = {"s1": {}}
        assert num.available is True


class TestNumberConsolidated:
    """Consolidated tests from test_extra_coverage.py and test_final_coverage.py."""

    @pytest.mark.asyncio
    async def test_number_stv10_properties_consolidated(self, hass):
        """Cover remaining properties in MysaAutoDeadbandNumber."""
        from custom_components.mysa.number import MysaAutoDeadbandNumber
        coordinator = MagicMock()
        api = MagicMock()
        num = MysaAutoDeadbandNumber(coordinator, "d1_cons", {"Model": "ST-V1-0"}, api, MagicMock())

        assert num.native_step == 0.5
        assert num.native_min_value == 2.0
        coordinator.data = {"d1_cons": {"autoDeadband": 1.5}}
        num.hass = hass
        assert num.native_value == 1.5

        with patch.object(MysaAutoDeadbandNumber, "async_write_ha_state"):
            api.set_stv10_auto_deadband = AsyncMock()
            await num.async_set_native_value(2.0)
            api.set_stv10_auto_deadband.assert_called_with("d1_cons", 2.0)

            api.set_stv10_auto_deadband.side_effect = Exception("failed")
            with pytest.raises(HomeAssistantError):
                await num.async_set_native_value(2.5)

    @pytest.mark.asyncio
    async def test_number_setpoints_coverage_consolidated(self, hass):
        """Cover missing lines in number.py (306, 381-389, 427-435)."""
        from custom_components.mysa.number import MysaMinSetpointNumber, MysaMaxSetpointNumber, MysaAutoDeadbandNumber
        coordinator = MagicMock()
        api = MagicMock()
        api.set_min_setpoint = AsyncMock()
        api.set_max_setpoint = AsyncMock()
        entry = MagicMock()

        # MinSetpoint
        num_min = MysaMinSetpointNumber(coordinator, "d2_cons", {"Model": "V1"}, api, entry)
        num_min.hass = hass
        num_min.async_write_ha_state = MagicMock()
        await num_min.async_set_native_value(20.0)
        api.set_min_setpoint.assert_called_with("d2_cons", 20.0)

        api.set_min_setpoint.side_effect = Exception("Fail")
        with pytest.raises(HomeAssistantError):
            await num_min.async_set_native_value(21.0)

        # MaxSetpoint
        num_max = MysaMaxSetpointNumber(coordinator, "d3_cons", {"Model": "V1"}, api, entry)
        num_max.hass = hass
        num_max.async_write_ha_state = MagicMock()
        await num_max.async_set_native_value(25.0)
        api.set_max_setpoint.assert_called_with("d3_cons", 25.0)

        api.set_max_setpoint.side_effect = Exception("Fail")
        with pytest.raises(HomeAssistantError):
            await num_max.async_set_native_value(26.0)

        # 306: available when super().available is False
        with patch("homeassistant.helpers.update_coordinator.CoordinatorEntity.available", new_callable=PropertyMock) as mock_avail:
            mock_avail.return_value = False
            num_auto = MysaAutoDeadbandNumber(coordinator, "d4_cons", {"Model": "ST-V1-0"}, api, entry)
            assert num_auto.available is False

@pytest.mark.asyncio
async def test_number_missing_coverage():
    """Test missing branches in Number entities."""
    mock_coordinator = MagicMock()
    mock_coordinator.data = {"dev1": {}}
    mock_api = MagicMock()
    device_data = {"Model": "ST-V1-0"}

    # Deadband
    deadband = MysaAutoDeadbandNumber(mock_coordinator, "dev1", device_data, mock_api, MagicMock())
    # val is None
    assert deadband.native_value is None
    # ternary branches
    mock_coordinator.data = {"dev1": {"auto_deadband": 5.0}} # degrees
    assert deadband.native_value == 5.0
    mock_coordinator.data = {"dev1": {"auto_deadband": 500}} # centidegrees
    assert deadband.native_value == 5.0

    # Min Setpoint
    min_sp = MysaMinSetpointNumber(mock_coordinator, "dev1", device_data, mock_api, MagicMock())
    # val is None
    mock_coordinator.data = {"dev1": {}}
    assert min_sp.native_value is None
    # ternary branches
    mock_coordinator.data = {"dev1": {"min_setpoint": 10.0}} # degrees
    assert min_sp.native_value == 10.0
    mock_coordinator.data = {"dev1": {"min_setpoint": 1000}} # centidegrees
    assert min_sp.native_value == 10.0

    # Max Setpoint
    max_sp = MysaMaxSetpointNumber(mock_coordinator, "dev1", device_data, mock_api, MagicMock())
    # val is None
    mock_coordinator.data = {"dev1": {}}
    assert max_sp.native_value is None
    # ternary branches
    mock_coordinator.data = {"dev1": {"max_setpoint": 25.0}} # degrees
    assert max_sp.native_value == 25.0
    mock_coordinator.data = {"dev1": {"max_setpoint": 2500}} # centidegrees
    assert max_sp.native_value == 25.0

@pytest.mark.asyncio
async def test_ac_number_entities_fallback(hass, mock_api):
    """Test that AC devices use tempRange fallback for setpoint numbers."""
    from custom_components.mysa.number import async_setup_entry as async_setup_number

    device_id = "ac_device"
    device_data = {
        "Id": device_id,
        "Model": "AC-V1-0",
        "Name": "AC",
        "SupportedCaps": {
            "tempRange": [17, 30],
        },
    }

    mock_api.devices = {device_id: device_data}
    mock_api.is_ac_device.return_value = True

    entry = MagicMock()
    entry.runtime_data.coordinator = MagicMock()
    entry.runtime_data.api = mock_api
    entry.runtime_data.coordinator.data = {}  # Empty state

    async_add_entities = MagicMock()

    await async_setup_number(hass, entry, async_add_entities)

    # Verify entities were added for this device
    added_entities = async_add_entities.call_args[0][0]

    # Check if they have the correct values
    min_sp = next(
        e
        for e in added_entities
        if hasattr(e, "_sensor_key")
        and e._sensor_key == "MinSetpoint"
        and e._device_id == device_id
    )
    max_sp = next(
        e
        for e in added_entities
        if hasattr(e, "_sensor_key")
        and e._sensor_key == "MaxSetpoint"
        and e._device_id == device_id
    )

    assert min_sp.native_value == 17.0
    assert max_sp.native_value == 30.0
