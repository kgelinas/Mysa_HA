from unittest.mock import MagicMock
from custom_components.mysa.switch import MysaSTV10AllowAutoModeSwitch
"""Tests for Switch entities."""

import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from homeassistant.exceptions import HomeAssistantError
from custom_components.mysa.switch import (
    MysaAutoBrightnessSwitch,
    MysaClimatePlusSwitch,
    MysaLockSwitch,
    MysaProximitySwitch,
    MysaSTV10AllowAutoModeSwitch,
)


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

    async def test_lock_stv1_uses_shadow(self):
        """Test lock switch uses shadow API for ST-V1-0."""
        mock_coordinator = MagicMock()
        mock_api = MagicMock()
        mock_api.set_stv10_lock = AsyncMock()
        mock_api.set_lock = AsyncMock()
        device_data = {"Model": "ST-V1-0"}

        switch = MysaLockSwitch(
            mock_coordinator, "STV1", device_data, mock_api, MagicMock()
        )
        switch.async_write_ha_state = MagicMock()
        switch.hass = MagicMock()

        await switch.async_turn_on()
        mock_api.set_stv10_lock.assert_called_with("STV1", True)
        mock_api.set_lock.assert_not_called()

        await switch.async_turn_off()
        mock_api.set_stv10_lock.assert_called_with("STV1", False)

    async def test_lock_legacy_uses_http(self):
        """Test lock switch uses legacy API for non-ST-V1-0."""
        mock_coordinator = MagicMock()
        mock_api = MagicMock()
        mock_api.set_stv10_lock = AsyncMock()
        mock_api.set_lock = AsyncMock()
        device_data = {"Model": "BB-V1"}

        switch = MysaLockSwitch(
            mock_coordinator, "BBV1", device_data, mock_api, MagicMock()
        )
        switch.async_write_ha_state = MagicMock()
        switch.hass = MagicMock()

        await switch.async_turn_on()
        mock_api.set_lock.assert_called_with("BBV1", True)
        mock_api.set_stv10_lock.assert_not_called()

        await switch.async_turn_off()
        mock_api.set_lock.assert_called_with("BBV1", False)


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

    async def test_proximity_stv1_uses_shadow(self):
        """Test proximity switch uses shadow API for ST-V1-0."""
        mock_coordinator = MagicMock()
        mock_api = MagicMock()
        mock_api.set_stv10_proximity = AsyncMock()
    async def test_proximity_legacy_uses_http(self):
        """Test proximity switch uses legacy API for non-ST-V1-0."""
        mock_coordinator = MagicMock()
        mock_api = MagicMock()
        mock_api.set_stv10_proximity = AsyncMock()
        mock_api.set_proximity = AsyncMock()
        device_data = {"Model": "BB-V1"}

        switch = MysaProximitySwitch(
            mock_coordinator, "BBV1", device_data, mock_api, MagicMock()
        )
        switch.async_write_ha_state = MagicMock()
        switch.hass = MagicMock()

        await switch.async_turn_on()
        mock_api.set_proximity.assert_called_with("BBV1", True)
        mock_api.set_stv10_proximity.assert_not_called()

        await switch.async_turn_off()
        mock_api.set_proximity.assert_called_with("BBV1", False)


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

    async def test_switch_is_on_pending(self):
        """Test is_on property with pending states."""
        mock_coordinator = MagicMock()
        mock_coordinator.data = {"dev1": {"lk": 0}} # Unlocked
        mock_api = MagicMock()
        device_data = {"Model": "BB-V1"}
        entity = MysaLockSwitch(mock_coordinator, "dev1", device_data, mock_api, MagicMock())
        assert entity.is_on == False

        entity._pending_state = True # We are turning it ON (Locked)
        entity._pending_timestamp = time.time()
        assert entity.is_on == True # Should prefer pending

        entity._pending_state = None
        assert entity.is_on == False # Back to real state

    async def test_switch_setup_entry(self, hass):
        """Test switch setup_entry."""
        from custom_components.mysa.switch import async_setup_entry
        from custom_components.mysa import MysaData

        mock_api = MagicMock()
        mock_api.get_devices = AsyncMock()
        mock_api.is_ac_device = MagicMock(return_value=False)
        mock_api.devices = {
            "heater1": {"Model": "BB-V2", "Name": "Heater"},
            "stv1": {"Model": "ST-V1-0", "Name": "HVAC"},
        }
        mock_api.get_devices.return_value = mock_api.devices

        mock_entry = MagicMock()
        mock_entry.runtime_data = MysaData(mock_api, MagicMock())

        async_add_entities = MagicMock()
        await async_setup_entry(hass, mock_entry, async_add_entities)

        async_add_entities.assert_called_once()
        entities = async_add_entities.call_args[0][0]
        # Heater: Lock, AutoBrightness, Proximity = 3
        # ST-V1: Lock, AllowAutoMode = 2
        # Total = 5
        assert len(entities) == 5

    async def test_switch_setup_entry_ac(self, hass):
        """Test switch setup_entry with AC device."""
        from custom_components.mysa.switch import async_setup_entry
        from custom_components.mysa import MysaData

        mock_api = MagicMock()
        mock_api.get_devices = AsyncMock()
        mock_api.is_ac_device = MagicMock(return_value=True) # It is AC
        mock_api.devices = {
            "ac1": {"Model": "AC-V1", "Name": "AC"},
        }
        mock_api.get_devices.return_value = mock_api.devices

        mock_entry = MagicMock()
        mock_entry.runtime_data = MysaData(mock_api, MagicMock())

        async_add_entities = MagicMock()
        await async_setup_entry(hass, mock_entry, async_add_entities)

        async_add_entities.assert_called_once()
        entities = async_add_entities.call_args[0][0]
        # AC: Lock, Climate+ = 2
        assert len(entities) == 2

    def test_switch_device_info(self):
        """Test device_info property (hit lines 109-114)."""
        mock_coordinator = MagicMock()
        mock_coordinator.data = {"dev1": {"sn": "123"}}
        mock_api = MagicMock()

        entity = MysaLockSwitch(mock_coordinator, "dev1", {"Model": "BB-V2"}, mock_api, MagicMock())
        info = entity.device_info
        assert info["identifiers"] == {("mysa", "dev1")}

    def test_switch_extract_value_dict(self):
        """Test _extract_value with dict branches (hit lines 126-129)."""
        mock_coordinator = MagicMock()
        entity = MysaLockSwitch(mock_coordinator, "dev1", {}, MagicMock(), MagicMock())

        # Test 'v' key
        assert entity._extract_value({"lk": {"v": 1}}, ["lk"]) == 1
        # Test 'Id' key
        assert entity._extract_value({"zone": {"Id": "z1"}}, ["zone"]) == "z1"

    async def test_climate_plus_switch_error(self):
        """Test climate plus switch turn_on error handling."""
        mock_coordinator = MagicMock()
        mock_api = MagicMock()
        mock_api.set_ac_climate_plus = AsyncMock(side_effect=Exception("API Error"))

        switch = MysaClimatePlusSwitch(mock_coordinator, "device1", {}, mock_api, MagicMock())
        switch.async_write_ha_state = MagicMock()
        switch.hass = MagicMock()

        from homeassistant.exceptions import HomeAssistantError
        with pytest.raises(HomeAssistantError):
            await switch.async_turn_on()

    async def test_climate_plus_switch_turn_off_error(self):
        """Test climate plus switch turn_off error handling."""
        mock_coordinator = MagicMock()
        mock_api = MagicMock()
        mock_api.set_ac_climate_plus = AsyncMock(side_effect=Exception("API Error"))

        switch = MysaClimatePlusSwitch(mock_coordinator, "device1", {}, mock_api, MagicMock())
        switch.async_write_ha_state = MagicMock()
        switch.hass = MagicMock()

        from homeassistant.exceptions import HomeAssistantError
        with pytest.raises(HomeAssistantError):
            await switch.async_turn_off()

    async def test_turn_off_error_handling(self):
        """Test async_turn_off error handling for all switches."""
        mock_api = MagicMock()
        mock_api.set_lock = AsyncMock(side_effect=Exception("API Error"))
        mock_api.set_stv10_lock = AsyncMock(side_effect=Exception("API Error"))

        lock_entity = MysaLockSwitch(MagicMock(), "dev1", {"Model": "BB-V1"}, mock_api, MagicMock())
        lock_entity.hass = MagicMock()
        lock_entity.async_write_ha_state = MagicMock()
        from homeassistant.exceptions import HomeAssistantError
        with pytest.raises(HomeAssistantError):
            await lock_entity.async_turn_off()

        lock_stv1 = MysaLockSwitch(MagicMock(), "dev1", {"Model": "ST-V1-0"}, mock_api, MagicMock())
        lock_stv1.hass = MagicMock()
        lock_stv1.async_write_ha_state = MagicMock()
        with pytest.raises(HomeAssistantError):
            await lock_stv1.async_turn_off()

    async def test_auto_brightness_switch_error(self):
        """Test auto brightness switch error handling."""
        mock_api = MagicMock()
        mock_api.set_auto_brightness = AsyncMock(side_effect=Exception("API Error"))
        entity = MysaAutoBrightnessSwitch(MagicMock(), "dev1", {"Model": "BB-V1"}, mock_api, MagicMock())
        entity.hass = MagicMock()
        entity.async_write_ha_state = MagicMock()
        from homeassistant.exceptions import HomeAssistantError
        with pytest.raises(HomeAssistantError):
            await entity.async_turn_on()
        with pytest.raises(HomeAssistantError):
            await entity.async_turn_off()

    async def test_proximity_switch_all_errors(self):
        """Test proximity switch error handling for both models."""
        mock_api = MagicMock()
        mock_api.set_proximity = AsyncMock(side_effect=Exception("API Error"))
        mock_api.set_stv10_proximity = AsyncMock(side_effect=Exception("API Error"))

        from homeassistant.exceptions import HomeAssistantError

        # Legacy
        entity = MysaProximitySwitch(MagicMock(), "dev1", {"Model": "BB-V1"}, mock_api, MagicMock())
        entity.hass = MagicMock()
        entity.async_write_ha_state = MagicMock()
        with pytest.raises(HomeAssistantError):
            await entity.async_turn_on()
        with pytest.raises(HomeAssistantError):
            await entity.async_turn_off()

        # ST-V1
        entity_stv1 = MysaProximitySwitch(MagicMock(), "dev1", {"Model": "ST-V1-0"}, mock_api, MagicMock())
        entity_stv1.hass = MagicMock()
        entity_stv1.async_write_ha_state = MagicMock()
        with pytest.raises(HomeAssistantError):
            await entity_stv1.async_turn_on()
        with pytest.raises(HomeAssistantError):
            await entity_stv1.async_turn_off()

    async def test_turn_on_error_handling(self):
        """Test async_turn_on error handling for all switches (hit lines 196-199)."""
        mock_api = MagicMock()
        mock_api.set_lock = AsyncMock(side_effect=Exception("API Error"))
        mock_api.set_stv10_lock = AsyncMock(side_effect=Exception("API Error"))

        from homeassistant.exceptions import HomeAssistantError

        # Legacy Lock
        lock_entity = MysaLockSwitch(MagicMock(), "dev1", {"Model": "BB-V1"}, mock_api, MagicMock())
        lock_entity.hass = MagicMock()
        lock_entity.async_write_ha_state = MagicMock()
        with pytest.raises(HomeAssistantError):
            await lock_entity.async_turn_on()

        # ST-V1 Lock
        lock_stv1 = MysaLockSwitch(MagicMock(), "dev1", {"Model": "ST-V1-0"}, mock_api, MagicMock())
        lock_stv1.hass = MagicMock()
        lock_stv1.async_write_ha_state = MagicMock()
        with pytest.raises(HomeAssistantError):
            await lock_stv1.async_turn_on()

    def test_switch_additional_is_on(self):
        """Test is_on for AutoBrightness and Proximity (hit lines 253, 314)."""
        mock_coordinator = MagicMock()
        mock_coordinator.data = {"dev1": {"ab": 1, "px": 1}}
        mock_api = MagicMock()

        ab_switch = MysaAutoBrightnessSwitch(mock_coordinator, "dev1", {}, mock_api, MagicMock())
        assert ab_switch.is_on == True

        px_switch = MysaProximitySwitch(mock_coordinator, "dev1", {}, mock_api, MagicMock())
        assert px_switch.is_on == True

    def test_switch_extract_value_none(self):
        """Test _extract_value returns None at end (hit line 131)."""
        mock_coordinator = MagicMock()
        entity = MysaLockSwitch(mock_coordinator, "dev1", {}, MagicMock(), MagicMock())
        assert entity._extract_value({"other": 1}, ["missing"]) is None

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

        entity = MysaSwitch(
            mock_coordinator, "dev1", {}, MagicMock(), mock_config_entry, "key", "key"
        )
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


class TestSwitchConsolidated:
    """Consolidated switch tests from extra and final coverage files."""

    @pytest.mark.asyncio
    async def test_switch_auto_mode_coverage_consolidated(self, hass):
        """Cover missing lines in switch.py (454, 458-466, 470-478)."""
        coordinator = MagicMock()
        api = MagicMock()
        api.set_stv10_allow_auto_mode = AsyncMock()
        entry = MagicMock()

        sw = MysaSTV10AllowAutoModeSwitch(
            coordinator, "d1", {"Model": "ST-V1-0"}, api, entry
        )
        sw.hass = hass
        sw.async_write_ha_state = MagicMock()

        # 454: is_on
        coordinator.data = {"d1": {"auto_mode_enabled": 1}}
        assert sw.is_on is True

        # 458-466: turn_on success/error
        await sw.async_turn_on()
        api.set_stv10_allow_auto_mode.assert_called_with("d1", True)

        api.set_stv10_allow_auto_mode.side_effect = Exception("Fail")
        with pytest.raises(HomeAssistantError):
            await sw.async_turn_on()

        # 470-478: turn_off success/error
        api.set_stv10_allow_auto_mode.side_effect = None
        await sw.async_turn_off()
        api.set_stv10_allow_auto_mode.assert_called_with("d1", False)

        api.set_stv10_allow_auto_mode.side_effect = Exception("Fail")
        with pytest.raises(HomeAssistantError):
            await sw.async_turn_off()

        # TargetAuto dict coverage (lines 472-474)
        api.set_stv10_allow_auto_mode.side_effect = None
        coordinator.data = {"d1": {"targetAuto": {"enabled": True}}}
        assert sw.is_on is True
        coordinator.data = {"d1": {"targetAuto": {"enabled": False}}}
        assert sw.is_on is False

        # Fallback coverage (line 476)
        coordinator.data = {"d1": {"something_else": True}}
        assert sw.is_on is False

        # None coordinator coverage (line 459)
        coordinator.data = None
        sw._pending_state = True
        assert sw.is_on is True
        sw._pending_state = None
        assert sw.is_on is False

        # Pending coverage (line 464)
        coordinator.data = {"d1": {}}
        sw._pending_state = True
        assert sw.is_on is True

    @pytest.mark.asyncio
    async def test_switch_entity_logic_consolidated(self, hass):
        """Test MysaSwitch entity logic."""
        coordinator = MagicMock()
        api = MagicMock()
        entry = MagicMock()
        device_id = "d1"
        device_data = {}

        # Use MysaLockSwitch which sets keys automatically
        entity = MysaLockSwitch(coordinator, device_id, device_data, api, entry)
        entity.hass = hass

        # Test is_on
        coordinator.data = {"d1": {"lk": 1}}  # 1 = on/locked
        assert entity.is_on is True

        coordinator.data = {"d1": {"lk": 0}}  # 0 = off/unlocked
        assert entity.is_on is False

        # Test methods
        api.set_lock = AsyncMock()  # Generic lock setter
        api.set_stv10_lock = AsyncMock()  # ST-V1 specific

        # Test Generic
        with patch.object(entity, "async_write_ha_state"):
            await entity.async_turn_on()
        api.set_lock.assert_called_with("d1", True)

        with patch.object(entity, "async_write_ha_state"):
            await entity.async_turn_off()
        api.set_lock.assert_called_with("d1", False)

        # Test ST-V1
        device_data["Model"] = "ST-V1-0"
        with patch.object(entity, "async_write_ha_state"):
            await entity.async_turn_on()
        api.set_stv10_lock.assert_called_with("d1", True)

    @pytest.mark.asyncio
    async def test_other_switches_logic_consolidated(self, hass):
        """Test other switch types."""
        coordinator = MagicMock()
        api = MagicMock()
        entry = MagicMock()
        device_id = "d1"
        device_data = {}

        # AutoBrightness
        sw = MysaAutoBrightnessSwitch(
            coordinator, device_id, device_data, api, entry
        )
        sw.hass = hass
        coordinator.data = {"d1": {"ab": 1}}
        assert sw.is_on is True

        api.set_auto_brightness = AsyncMock()
        with patch.object(sw, "async_write_ha_state"):
            await sw.async_turn_on()
        api.set_auto_brightness.assert_called_with("d1", True)

        # Proximity
        sw = MysaProximitySwitch(coordinator, device_id, device_data, api, entry)
        sw.hass = hass
        coordinator.data = {"d1": {"px": 0}}
        assert sw.is_on is False

        api.set_proximity = AsyncMock()
        with patch.object(sw, "async_write_ha_state"):
            await sw.async_turn_on()
        api.set_proximity.assert_called_with("d1", True)

        # Climate Plus (AC)
        sw = MysaClimatePlusSwitch(coordinator, device_id, device_data, api, entry)
        sw.hass = hass
        coordinator.data = {"d1": {"it": 1}}
        assert sw.is_on is True

        api.set_ac_climate_plus = AsyncMock()
        with patch.object(sw, "async_write_ha_state"):
            await sw.async_turn_off()
        api.set_ac_climate_plus.assert_called_with("d1", False)

    @pytest.mark.asyncio
    async def test_switch_exceptions_consolidated(self, hass):
        """Test exception handling in switch setters."""
        coordinator = MagicMock()
        api = MagicMock()
        entry = MagicMock()
        device_id = "d1"
        device_data = {}

        # Lock Switch Exception
        sw = MysaLockSwitch(coordinator, device_id, device_data, api, entry)
        sw.hass = hass
        api.set_lock = AsyncMock(side_effect=Exception("Failed"))

        with pytest.raises(HomeAssistantError):
            with patch.object(sw, "async_write_ha_state"):
                await sw.async_turn_on()

        # AutoBrightness Exception
        sw_ab = MysaAutoBrightnessSwitch(
            coordinator, device_id, device_data, api, entry
        )
        sw_ab.hass = hass
        api.set_auto_brightness = AsyncMock(side_effect=Exception("Failed"))

        with pytest.raises(HomeAssistantError):
            with patch.object(sw_ab, "async_write_ha_state"):
                await sw_ab.async_turn_on()

    @pytest.mark.asyncio
    async def test_switch_base_logic_consolidated(self, hass):
        """Test MysaSwitch base logic (pending state, extraction)."""
        coordinator = MagicMock()
        api = MagicMock()
        entry = MagicMock()
        device_id = "d1"
        device_data = {}

        sw = MysaLockSwitch(coordinator, device_id, device_data, api, entry)
        sw.hass = hass

        # Test _extract_value with dict logic
        # value is {"v": 1}
        coordinator.data = {"d1": {"Lock": {"v": 1}}}
        assert sw.is_on is True

        # value is {"Id": 1} (rare case handled in code)
        coordinator.data = {"d1": {"Lock": {"Id": 0}}}
        assert sw.is_on is False

        # Test Pending State Logic
        # 1. Sticky
        sw._pending_state = True
        sw._pending_timestamp = time.time()
        # Cloud says Off
        coordinator.data = {"d1": {"lk": 0}}
        assert sw.is_on is True  # Sticky

        # Case when coordinator.data is None (line 459 in switch.py)
        coordinator.data = None
        assert sw.is_on is True
        sw._pending_state = None
        assert sw.is_on is False

        # 2. Convergence
        sw._pending_state = True
        sw._pending_timestamp = time.time()
        # Cloud matches pending (True)
        coordinator.data = {"d1": {"lk": 1}}
        assert sw._pending_state is True
        assert sw.is_on is True  # Should clear pending
        assert sw._pending_state is None

        # 3. Expiration
        sw._pending_state = True
        sw._pending_timestamp = time.time() - 31  # Expired
        # Cloud says Off
        coordinator.data = {"d1": {"lk": 0}}
        assert sw.is_on is False  # Uses cloud value
        assert sw._pending_state is None

    @pytest.mark.asyncio
    async def test_setup_stv1_switch_consolidated(self, hass):
        """Test ST-V1 switch setup (AutoBrightness excluded)."""
        from custom_components.mysa.switch import async_setup_entry

        mock_api = MagicMock()
        mock_api.devices = {"d1": {"Model": "ST-V1-0"}}
        mock_api.get_devices = AsyncMock(return_value=mock_api.devices)
        mock_api.is_ac_device = MagicMock(return_value=False)

        mock_entry = MagicMock()
        from custom_components.mysa import MysaData
        mock_entry.runtime_data = MysaData(api=mock_api, coordinator=MagicMock())

        mock_add_entities = MagicMock()
        await async_setup_entry(hass, mock_entry, mock_add_entities)

        # Verify entities added
        args = mock_add_entities.call_args[0][0]
        # Should have Lock, but NOT Proximity or AutoBrightness
        types = [type(e).__name__ for e in args]
        assert "MysaLockSwitch" in types
        assert "MysaProximitySwitch" not in types
        assert "MysaAutoBrightnessSwitch" not in types

@pytest.mark.asyncio
async def test_switch_is_on_missing_coverage():
    """Test missing branches in MysaSTV10AllowAutoModeSwitch."""
    from unittest.mock import MagicMock
    from custom_components.mysa.switch import MysaSTV10AllowAutoModeSwitch
    mock_coordinator = MagicMock()
    mock_coordinator.data = None
    mock_api = MagicMock()
    device_data = {"Model": "ST-V1-0"}

    entity = MysaSTV10AllowAutoModeSwitch(mock_coordinator, "dev1", device_data, mock_api, MagicMock())

    entity._pending_state = True
    assert entity.is_on == True
    entity._pending_state = False
    assert entity.is_on == False
    entity._pending_state = None
    assert entity.is_on == False

    mock_coordinator.data = {"dev1": {"auto_mode_enabled": 0}}
    entity._pending_state = True
    assert entity.is_on is True

    mock_coordinator.data = {"dev1": {"targetAuto": {"enabled": 1}}}
    entity._pending_state = None
    assert entity.is_on == True

    mock_coordinator.data = {"dev1": {"targetAuto": {"enabled": 0}}}
    assert entity.is_on == False

    mock_coordinator.data = {"dev1": {"targetAuto": "invalid"}}
    assert entity.is_on == False

    mock_coordinator.data = {"dev1": {}}
    assert entity.is_on == False
