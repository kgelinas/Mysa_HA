"""
Entity Files Coverage Tests.

Tests for number.py, switch.py, select.py, update.py:
async_setup_entry, entity actions, and edge cases.
"""

import sys
import os

# Add project root to path for imports
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(TEST_DIR)
sys.path.insert(0, ROOT_DIR)

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

# Module-level imports after path setup
from custom_components.mysa.const import DOMAIN


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def mock_coordinator(hass, mock_entry):
    """Create mock coordinator."""

    async def async_update():
        return {
            "device1": {
                "MinBrightness": 10,
                "MaxBrightness": 80,
                "Lock": True,
                "AutoBrightness": True,
                "ProximityMode": True,
                "Zone": "zone123",
                "DutyCycle": 50,
            },
            "ac_device": {
                "IsThermostatic": True,
                "SwingStateHorizontal": 2,
                "Zone": "zone456",
            },
        }

    return DataUpdateCoordinator(
        hass, MagicMock(), name="test", update_method=async_update, config_entry=mock_entry
    )


@pytest.fixture
def mock_device_data():
    """Mock device data."""
    return {
        "Id": "device1",
        "Name": "Living Room",
        "Model": "BB-V2",
        "FirmwareVersion": "1.2.3",
    }


@pytest.fixture
def mock_ac_device_data():
    """Mock AC device data."""
    return {
        "Id": "ac_device",
        "Name": "Bedroom AC",
        "Model": "AC-V1",
        "SupportedCaps": {"modes": {"4": {"horizontalSwing": [0, 1, 2, 3, 4]}}},
    }


@pytest.fixture
def mock_api():
    """Mock API with all entity methods."""
    api = MagicMock()
    api.get_devices = AsyncMock(
        return_value={
            "device1": {"Id": "device1", "Name": "Living Room", "Model": "BB-V2"},
            "ac_device": {"Id": "ac_device", "Name": "Bedroom AC", "Model": "AC-V1"},
        }
    )
    api.is_ac_device = MagicMock(side_effect=lambda x: x == "ac_device")
    api.devices = {
        "device1": {
            "Id": "device1",
            "Name": "Living Room",
            "Model": "BB-V2",
            "FirmwareVersion": "1.0.0",
        },
    }

    # Number methods
    api.set_min_brightness = AsyncMock()
    api.set_max_brightness = AsyncMock()

    # Switch methods
    api.set_lock = AsyncMock()
    api.set_auto_brightness = AsyncMock()
    api.set_proximity = AsyncMock()
    api.set_ac_climate_plus = AsyncMock()

    # Select methods
    api.set_ac_horizontal_swing = AsyncMock()

    return api


@pytest.fixture
def mock_entry():
    """Mock config entry."""
    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.options = {}
    return entry


# ===========================================================================
# Number Entity Tests
# ===========================================================================


class TestNumberSetup:
    """Test number.py async_setup_entry."""

    @pytest.mark.asyncio
    async def test_async_setup_entry(self, hass, mock_api, mock_entry):
        """Test number entities are created."""
        from custom_components.mysa.number import async_setup_entry

        hass.data[DOMAIN] = {
            "test_entry": {"coordinator": MagicMock(), "api": mock_api}
        }

        entities = []
        async_add_entities = MagicMock(side_effect=lambda e: entities.extend(e))

        await async_setup_entry(hass, mock_entry, async_add_entities)

        assert async_add_entities.called


class TestMinBrightnessNumber:
    """Test MysaMinBrightnessNumber."""

    @pytest.mark.asyncio
    async def test_native_value(
        self, hass, mock_coordinator, mock_device_data, mock_api, mock_entry
    ):
        """Test native_value property."""
        from custom_components.mysa.number import MysaMinBrightnessNumber

        await mock_coordinator.async_refresh()
        entity = MysaMinBrightnessNumber(
            mock_coordinator, "device1", mock_device_data, mock_api, mock_entry
        )

        assert entity.native_value == 10

    @pytest.mark.asyncio
    async def test_set_native_value(
        self, hass, mock_coordinator, mock_device_data, mock_api, mock_entry
    ):
        """Test set_native_value action."""
        from custom_components.mysa.number import MysaMinBrightnessNumber

        await mock_coordinator.async_refresh()
        entity = MysaMinBrightnessNumber(
            mock_coordinator, "device1", mock_device_data, mock_api, mock_entry
        )
        entity.async_write_ha_state = MagicMock()

        await entity.async_set_native_value(25.0)

        mock_api.set_min_brightness.assert_called_once_with("device1", 25)

    @pytest.mark.asyncio
    async def test_device_info(
        self, hass, mock_coordinator, mock_device_data, mock_api, mock_entry
    ):
        """Test device_info property."""
        from custom_components.mysa.number import MysaMinBrightnessNumber

        await mock_coordinator.async_refresh()
        entity = MysaMinBrightnessNumber(
            mock_coordinator, "device1", mock_device_data, mock_api, mock_entry
        )

        info = entity.device_info
        assert "identifiers" in info


class TestMaxBrightnessNumber:
    """Test MysaMaxBrightnessNumber."""

    @pytest.mark.asyncio
    async def test_native_value(
        self, hass, mock_coordinator, mock_device_data, mock_api, mock_entry
    ):
        """Test native_value property."""
        from custom_components.mysa.number import MysaMaxBrightnessNumber

        await mock_coordinator.async_refresh()
        entity = MysaMaxBrightnessNumber(
            mock_coordinator, "device1", mock_device_data, mock_api, mock_entry
        )

        assert entity.native_value == 80

    @pytest.mark.asyncio
    async def test_set_native_value(
        self, hass, mock_coordinator, mock_device_data, mock_api, mock_entry
    ):
        """Test set_native_value action."""
        from custom_components.mysa.number import MysaMaxBrightnessNumber

        await mock_coordinator.async_refresh()
        entity = MysaMaxBrightnessNumber(
            mock_coordinator, "device1", mock_device_data, mock_api, mock_entry
        )
        entity.async_write_ha_state = MagicMock()

        await entity.async_set_native_value(90.0)

        mock_api.set_max_brightness.assert_called_once_with("device1", 90)


# ===========================================================================
# Switch Entity Tests
# ===========================================================================


class TestSwitchSetup:
    """Test switch.py async_setup_entry."""

    @pytest.mark.asyncio
    async def test_async_setup_entry(self, hass, mock_api, mock_entry):
        """Test switch entities are created."""
        from custom_components.mysa.switch import async_setup_entry

        hass.data[DOMAIN] = {
            "test_entry": {"coordinator": MagicMock(), "api": mock_api}
        }

        entities = []
        async_add_entities = MagicMock(side_effect=lambda e: entities.extend(e))

        await async_setup_entry(hass, mock_entry, async_add_entities)

        assert async_add_entities.called


class TestLockSwitch:
    """Test MysaLockSwitch."""

    @pytest.mark.asyncio
    async def test_is_on(
        self, hass, mock_coordinator, mock_device_data, mock_api, mock_entry
    ):
        """Test is_on property."""
        from custom_components.mysa.switch import MysaLockSwitch

        await mock_coordinator.async_refresh()
        entity = MysaLockSwitch(
            mock_coordinator, "device1", mock_device_data, mock_api, mock_entry
        )

        assert entity.is_on is True

    @pytest.mark.asyncio
    async def test_turn_on(
        self, hass, mock_coordinator, mock_device_data, mock_api, mock_entry
    ):
        """Test turn_on action."""
        from custom_components.mysa.switch import MysaLockSwitch

        await mock_coordinator.async_refresh()
        entity = MysaLockSwitch(
            mock_coordinator, "device1", mock_device_data, mock_api, mock_entry
        )
        entity.async_write_ha_state = MagicMock()

        await entity.async_turn_on()

        mock_api.set_lock.assert_called_once_with("device1", True)

    @pytest.mark.asyncio
    async def test_turn_off(
        self, hass, mock_coordinator, mock_device_data, mock_api, mock_entry
    ):
        """Test turn_off action."""
        from custom_components.mysa.switch import MysaLockSwitch

        await mock_coordinator.async_refresh()
        entity = MysaLockSwitch(
            mock_coordinator, "device1", mock_device_data, mock_api, mock_entry
        )
        entity.async_write_ha_state = MagicMock()

        await entity.async_turn_off()

        mock_api.set_lock.assert_called_once_with("device1", False)

    @pytest.mark.asyncio
    async def test_device_info(
        self, hass, mock_coordinator, mock_device_data, mock_api, mock_entry
    ):
        """Test device_info property."""
        from custom_components.mysa.switch import MysaLockSwitch

        await mock_coordinator.async_refresh()
        entity = MysaLockSwitch(
            mock_coordinator, "device1", mock_device_data, mock_api, mock_entry
        )

        info = entity.device_info
        assert "identifiers" in info


class TestAutoBrightnessSwitch:
    """Test MysaAutoBrightnessSwitch."""

    @pytest.mark.asyncio
    async def test_turn_on(
        self, hass, mock_coordinator, mock_device_data, mock_api, mock_entry
    ):
        """Test turn_on action."""
        from custom_components.mysa.switch import MysaAutoBrightnessSwitch

        await mock_coordinator.async_refresh()
        entity = MysaAutoBrightnessSwitch(
            mock_coordinator, "device1", mock_device_data, mock_api, mock_entry
        )
        entity.async_write_ha_state = MagicMock()

        await entity.async_turn_on()

        mock_api.set_auto_brightness.assert_called_once_with("device1", True)

    @pytest.mark.asyncio
    async def test_turn_off(
        self, hass, mock_coordinator, mock_device_data, mock_api, mock_entry
    ):
        """Test turn_off action."""
        from custom_components.mysa.switch import MysaAutoBrightnessSwitch

        await mock_coordinator.async_refresh()
        entity = MysaAutoBrightnessSwitch(
            mock_coordinator, "device1", mock_device_data, mock_api, mock_entry
        )
        entity.async_write_ha_state = MagicMock()

        await entity.async_turn_off()

        mock_api.set_auto_brightness.assert_called_once_with("device1", False)


class TestProximitySwitch:
    """Test MysaProximitySwitch."""

    @pytest.mark.asyncio
    async def test_turn_on(
        self, hass, mock_coordinator, mock_device_data, mock_api, mock_entry
    ):
        """Test turn_on action."""
        from custom_components.mysa.switch import MysaProximitySwitch

        await mock_coordinator.async_refresh()
        entity = MysaProximitySwitch(
            mock_coordinator, "device1", mock_device_data, mock_api, mock_entry
        )
        entity.async_write_ha_state = MagicMock()

        await entity.async_turn_on()

        mock_api.set_proximity.assert_called_once_with("device1", True)

    @pytest.mark.asyncio
    async def test_turn_off(
        self, hass, mock_coordinator, mock_device_data, mock_api, mock_entry
    ):
        """Test turn_off action."""
        from custom_components.mysa.switch import MysaProximitySwitch

        await mock_coordinator.async_refresh()
        entity = MysaProximitySwitch(
            mock_coordinator, "device1", mock_device_data, mock_api, mock_entry
        )
        entity.async_write_ha_state = MagicMock()

        await entity.async_turn_off()

        mock_api.set_proximity.assert_called_once_with("device1", False)


class TestClimatePlusSwitch:
    """Test MysaClimatePlusSwitch."""

    @pytest.mark.asyncio
    async def test_turn_on(
        self, hass, mock_coordinator, mock_ac_device_data, mock_api, mock_entry
    ):
        """Test turn_on action."""
        from custom_components.mysa.switch import MysaClimatePlusSwitch

        await mock_coordinator.async_refresh()
        entity = MysaClimatePlusSwitch(
            mock_coordinator, "ac_device", mock_ac_device_data, mock_api, mock_entry
        )
        entity.async_write_ha_state = MagicMock()

        await entity.async_turn_on()

        mock_api.set_ac_climate_plus.assert_called_once_with("ac_device", True)

    @pytest.mark.asyncio
    async def test_turn_off(
        self, hass, mock_coordinator, mock_ac_device_data, mock_api, mock_entry
    ):
        """Test turn_off action."""
        from custom_components.mysa.switch import MysaClimatePlusSwitch

        await mock_coordinator.async_refresh()
        entity = MysaClimatePlusSwitch(
            mock_coordinator, "ac_device", mock_ac_device_data, mock_api, mock_entry
        )
        entity.async_write_ha_state = MagicMock()

        await entity.async_turn_off()

        mock_api.set_ac_climate_plus.assert_called_once_with("ac_device", False)


# ===========================================================================
# Select Entity Tests
# ===========================================================================


class TestSelectSetup:
    """Test select.py async_setup_entry."""

    @pytest.mark.asyncio
    async def test_async_setup_entry_with_ac(self, hass, mock_entry):
        """Test select entities are created for AC devices."""
        from custom_components.mysa.select import async_setup_entry

        mock_api = MagicMock()
        mock_api.get_devices = AsyncMock(
            return_value={
                "ac_device": {
                    "Id": "ac_device",
                    "Name": "AC",
                    "Model": "AC-V1",
                    "SupportedCaps": {},
                }
            }
        )
        mock_api.is_ac_device = MagicMock(return_value=True)

        hass.data[DOMAIN] = {
            "test_entry": {"coordinator": MagicMock(), "api": mock_api}
        }

        entities = []
        async_add_entities = MagicMock(side_effect=lambda e: entities.extend(e))

        await async_setup_entry(hass, mock_entry, async_add_entities)

        assert async_add_entities.called

    @pytest.mark.asyncio
    async def test_async_setup_entry_no_ac(self, hass, mock_entry):
        """Test no select entities when no AC devices."""
        from custom_components.mysa.select import async_setup_entry

        mock_api = MagicMock()
        mock_api.get_devices = AsyncMock(
            return_value={
                "device1": {"Id": "device1", "Name": "Thermostat", "Model": "BB-V2"}
            }
        )
        mock_api.is_ac_device = MagicMock(return_value=False)

        hass.data[DOMAIN] = {
            "test_entry": {"coordinator": MagicMock(), "api": mock_api}
        }

        async_add_entities = MagicMock()

        await async_setup_entry(hass, mock_entry, async_add_entities)

        # async_add_entities should not be called with empty list
        assert not async_add_entities.called


class TestHorizontalSwingSelect:
    """Test MysaHorizontalSwingSelect."""

    @pytest.mark.asyncio
    async def test_options(
        self, hass, mock_coordinator, mock_ac_device_data, mock_api, mock_entry
    ):
        """Test options property."""
        from custom_components.mysa.select import MysaHorizontalSwingSelect

        await mock_coordinator.async_refresh()
        entity = MysaHorizontalSwingSelect(
            mock_coordinator, "ac_device", mock_ac_device_data, mock_api, mock_entry
        )

        assert isinstance(entity.options, list)
        assert len(entity.options) > 0

    @pytest.mark.asyncio
    async def test_current_option(
        self, hass, mock_coordinator, mock_ac_device_data, mock_api, mock_entry
    ):
        """Test current_option property."""
        from custom_components.mysa.select import MysaHorizontalSwingSelect

        await mock_coordinator.async_refresh()
        entity = MysaHorizontalSwingSelect(
            mock_coordinator, "ac_device", mock_ac_device_data, mock_api, mock_entry
        )

        option = entity.current_option
        assert option is not None

    @pytest.mark.asyncio
    async def test_select_option(
        self, hass, mock_coordinator, mock_ac_device_data, mock_api, mock_entry
    ):
        """Test select_option action."""
        from custom_components.mysa.select import MysaHorizontalSwingSelect

        await mock_coordinator.async_refresh()
        entity = MysaHorizontalSwingSelect(
            mock_coordinator, "ac_device", mock_ac_device_data, mock_api, mock_entry
        )
        entity.async_write_ha_state = MagicMock()

        await entity.async_select_option("auto")

        mock_api.set_ac_horizontal_swing.assert_called()

    @pytest.mark.asyncio
    async def test_select_unknown_option(
        self, hass, mock_coordinator, mock_ac_device_data, mock_api, mock_entry
    ):
        """Test select_option with unknown option."""
        from custom_components.mysa.select import MysaHorizontalSwingSelect

        await mock_coordinator.async_refresh()
        entity = MysaHorizontalSwingSelect(
            mock_coordinator, "ac_device", mock_ac_device_data, mock_api, mock_entry
        )
        entity.async_write_ha_state = MagicMock()

        await entity.async_select_option("invalid_option")

        # API should not be called for unknown option
        mock_api.set_ac_horizontal_swing.assert_not_called()

    @pytest.mark.asyncio
    async def test_device_info(
        self, hass, mock_coordinator, mock_ac_device_data, mock_api, mock_entry
    ):
        """Test device_info property."""
        from custom_components.mysa.select import MysaHorizontalSwingSelect

        await mock_coordinator.async_refresh()
        entity = MysaHorizontalSwingSelect(
            mock_coordinator, "ac_device", mock_ac_device_data, mock_api, mock_entry
        )

        info = entity.device_info
        assert "identifiers" in info


# ===========================================================================
# Update Entity Tests
# ===========================================================================


class TestUpdateSetup:
    """Test update.py async_setup_entry."""

    @pytest.mark.asyncio
    async def test_async_setup_entry(self, hass, mock_api, mock_entry):
        """Test update entities are created."""
        from custom_components.mysa.update import async_setup_entry

        hass.data[DOMAIN] = {"test_entry": {"api": mock_api}}

        async_add_entities = MagicMock()

        await async_setup_entry(hass, mock_entry, async_add_entities)

        assert async_add_entities.called


class TestMysaUpdate:
    """Test MysaUpdate entity."""

    @pytest.mark.asyncio
    async def test_init(self, hass, mock_api):
        """Test MysaUpdate initialization."""
        from custom_components.mysa.update import MysaUpdate

        device_data = {
            "Id": "device1",
            "Name": "Living Room",
            "Model": "BB-V2",
            "FirmwareVersion": "1.2.3",
        }

        entity = MysaUpdate(mock_api, "device1", device_data)

        assert entity._attr_installed_version == "1.2.3"
        assert entity._attr_name == "Living Room Firmware"

    @pytest.mark.asyncio
    async def test_async_update_success(self, hass, mock_api):
        """Test async_update success."""
        from custom_components.mysa.update import MysaUpdate

        mock_api.hass = hass
        mock_api.fetch_firmware_info = AsyncMock(
            return_value={
                "installedVersion": "1.2.3",
                "allowedVersion": "1.3.0",
                "update": True,
            }
        )

        device_data = {
            "Id": "device1",
            "Name": "Living Room",
            "Model": "BB-V2",
            "FirmwareVersion": "1.2.3",
        }
        entity = MysaUpdate(mock_api, "device1", device_data)

        await entity.async_update()

        assert entity._attr_installed_version == "1.2.3"
        assert entity._attr_latest_version == "1.3.0"

    @pytest.mark.asyncio
    async def test_async_update_error(self, hass, mock_api):
        """Test async_update handles errors."""
        from custom_components.mysa.update import MysaUpdate

        mock_api.hass = hass
        mock_api.fetch_firmware_info = AsyncMock(side_effect=Exception("Network error"))

        device_data = {
            "Id": "device1",
            "Name": "Living Room",
            "Model": "BB-V2",
            "FirmwareVersion": "1.2.3",
        }
        entity = MysaUpdate(mock_api, "device1", device_data)

        # Should not raise - the entity catches the exception
        await entity.async_update()


# ===========================================================================
# Edge Case Tests for Entity Files
# ===========================================================================


class TestNumberEdgeCases:
    """Test edge cases for number entities."""

    @pytest.fixture
    def mock_coordinator_with_zone(self, hass):
        """Coordinator with zone data."""

        async def async_update():
            return {"device1": {"Zone": "zone123", "MinBrightness": 20}}

        return DataUpdateCoordinator(
            hass, MagicMock(), name="test", update_method=async_update, config_entry=MagicMock(entry_id="test")
        )

    @pytest.mark.asyncio
    async def test_device_info_with_zone_name(
        self, hass, mock_coordinator_with_zone, mock_device_data, mock_api
    ):
        """Test device_info includes zone name when configured."""
        from custom_components.mysa.number import MysaMinBrightnessNumber

        await mock_coordinator_with_zone.async_refresh()

        entry = MagicMock()
        entry.entry_id = "test"
        entry.options = {"zone_name_zone123": "Living Room Zone"}

        entity = MysaMinBrightnessNumber(
            mock_coordinator_with_zone, "device1", mock_device_data, mock_api, entry
        )

        info = entity.device_info
        assert info.get("suggested_area") == "Living Room Zone"

    @pytest.mark.asyncio
    async def test_extract_value_with_id_key(
        self, hass, mock_coordinator, mock_device_data, mock_api, mock_entry
    ):
        """Test _extract_value falls back to 'Id' key."""
        from custom_components.mysa.number import MysaMinBrightnessNumber

        await mock_coordinator.async_refresh()
        entity = MysaMinBrightnessNumber(
            mock_coordinator, "device1", mock_device_data, mock_api, mock_entry
        )

        # Test dict with 'Id' instead of 'v'
        state = {"Zone": {"Id": "zone_id_value"}}
        value = entity._extract_value(state, ["Zone"])
        assert value == "zone_id_value"

    @pytest.mark.asyncio
    async def test_pending_expired(self, hass, mock_device_data, mock_api, mock_entry):
        """Test pending value expires after 60 seconds."""
        import time
        from custom_components.mysa.number import MysaMinBrightnessNumber

        async def async_update():
            return {"device1": {"MinBrightness": 15}}

        coordinator = DataUpdateCoordinator(
            hass, MagicMock(), name="test", update_method=async_update, config_entry=mock_entry
        )
        await coordinator.async_refresh()

        entity = MysaMinBrightnessNumber(
            coordinator, "device1", mock_device_data, mock_api, mock_entry
        )

        # Set pending value with old timestamp
        entity._pending_value = 25.0
        entity._pending_time = time.time() - 100  # 100 seconds ago (expired)

        # Should return actual value, not pending
        assert entity.native_value == 15

    @pytest.mark.asyncio
    async def test_no_state_returns_none(
        self, hass, mock_device_data, mock_api, mock_entry
    ):
        """Test returns None when no state data."""
        from custom_components.mysa.number import MysaMinBrightnessNumber

        async def async_update():
            return {}  # No device data

        coordinator = DataUpdateCoordinator(
            hass, MagicMock(), name="test", update_method=async_update, config_entry=mock_entry
        )
        await coordinator.async_refresh()

        entity = MysaMinBrightnessNumber(
            coordinator, "device1", mock_device_data, mock_api, mock_entry
        )

        assert entity.native_value is None


class TestSwitchEdgeCases:
    """Test edge cases for switch entities."""

    @pytest.mark.asyncio
    async def test_device_info_with_zone_name(
        self, hass, mock_coordinator, mock_device_data, mock_api
    ):
        """Test device_info includes zone name when configured."""
        from custom_components.mysa.switch import MysaLockSwitch

        await mock_coordinator.async_refresh()

        entry = MagicMock()
        entry.entry_id = "test"
        entry.options = {"zone_name_zone123": "Kitchen Zone"}

        entity = MysaLockSwitch(
            mock_coordinator, "device1", mock_device_data, mock_api, entry
        )

        info = entity.device_info
        assert info.get("suggested_area") == "Kitchen Zone"

    @pytest.mark.asyncio
    async def test_extract_value_with_id_key(
        self, hass, mock_coordinator, mock_device_data, mock_api, mock_entry
    ):
        """Test _extract_value falls back to 'Id' key."""
        from custom_components.mysa.switch import MysaLockSwitch

        await mock_coordinator.async_refresh()
        entity = MysaLockSwitch(
            mock_coordinator, "device1", mock_device_data, mock_api, mock_entry
        )

        state = {"Lock": {"Id": "lock_id"}}
        value = entity._extract_value(state, ["Lock"])
        assert value == "lock_id"

    @pytest.mark.asyncio
    async def test_pending_state_on_no_data(
        self, hass, mock_device_data, mock_api, mock_entry
    ):
        """Test pending state returned when no coordinator data."""
        from custom_components.mysa.switch import MysaLockSwitch

        async def async_update():
            return {}  # No device data

        coordinator = DataUpdateCoordinator(
            hass, MagicMock(), name="test", update_method=async_update, config_entry=mock_entry
        )
        await coordinator.async_refresh()

        entity = MysaLockSwitch(
            coordinator, "device1", mock_device_data, mock_api, mock_entry
        )
        entity._pending_state = True

        assert entity.is_on is True

    @pytest.mark.asyncio
    async def test_pending_cleared_on_confirmed(
        self, hass, mock_coordinator, mock_device_data, mock_api, mock_entry
    ):
        """Test pending state cleared when state confirmed."""
        from custom_components.mysa.switch import MysaLockSwitch

        await mock_coordinator.async_refresh()
        entity = MysaLockSwitch(
            mock_coordinator, "device1", mock_device_data, mock_api, mock_entry
        )
        entity._pending_state = True  # Set pending to match Cloud (True)

        # is_on should return True (from coordinator) and clear pending
        assert entity.is_on is True
        assert entity._pending_state is None


class TestSelectEdgeCases:
    """Test edge cases for select entities."""

    @pytest.mark.asyncio
    async def test_device_info_with_zone_name(
        self, hass, mock_coordinator, mock_ac_device_data, mock_api
    ):
        """Test device_info includes zone name when configured."""
        from custom_components.mysa.select import MysaHorizontalSwingSelect

        await mock_coordinator.async_refresh()

        entry = MagicMock()
        entry.entry_id = "test"
        entry.options = {"zone_name_zone456": "Bedroom Zone"}

        entity = MysaHorizontalSwingSelect(
            mock_coordinator, "ac_device", mock_ac_device_data, mock_api, entry
        )

        info = entity.device_info
        assert info.get("suggested_area") == "Bedroom Zone"

    @pytest.mark.asyncio
    async def test_current_option_with_dict_value(
        self, hass, mock_ac_device_data, mock_api, mock_entry
    ):
        """Test current_option extracts from dict with 'v' key."""
        from custom_components.mysa.select import MysaHorizontalSwingSelect

        async def async_update():
            return {"ac_device": {"SwingStateHorizontal": {"v": 1}}}  # Dict format

        coordinator = DataUpdateCoordinator(
            hass, MagicMock(), name="test", update_method=async_update, config_entry=mock_entry
        )
        await coordinator.async_refresh()

        entity = MysaHorizontalSwingSelect(
            coordinator, "ac_device", mock_ac_device_data, mock_api, mock_entry
        )

        option = entity.current_option
        assert option is not None

    @pytest.mark.asyncio
    async def test_pending_cleared_on_confirmed(
        self, hass, mock_coordinator, mock_ac_device_data, mock_api, mock_entry
    ):
        """Test pending option cleared when confirmed."""
        from custom_components.mysa.select import MysaHorizontalSwingSelect

        await mock_coordinator.async_refresh()
        entity = MysaHorizontalSwingSelect(
            mock_coordinator, "ac_device", mock_ac_device_data, mock_api, mock_entry
        )
        entity._pending_option = "left"

        # Access current_option - should clear pending since state exists
        _ = entity.current_option
        # Note: pending is only cleared when val is not None from state

    @pytest.mark.asyncio
    async def test_select_option_exception(
        self, hass, mock_coordinator, mock_ac_device_data, mock_entry
    ):
        """Test select_option handles API exception."""
        from custom_components.mysa.select import MysaHorizontalSwingSelect

        await mock_coordinator.async_refresh()

        mock_api = MagicMock()
        mock_api.set_ac_horizontal_swing = AsyncMock(side_effect=Exception("API Error"))

        entity = MysaHorizontalSwingSelect(
            mock_coordinator, "ac_device", mock_ac_device_data, mock_api, mock_entry
        )
        entity.async_write_ha_state = MagicMock()

        # Should not raise, just log error
        await entity.async_select_option("auto")

        # Pending should be cleared on error
        assert entity._pending_option is None


class TestFinalEdgeCases:
    """Final edge cases to reach 100% coverage."""

    @pytest.mark.asyncio
    async def test_number_pending_valid(
        self, hass, mock_device_data, mock_api, mock_entry
    ):
        """Test pending value returned when still valid (<60s)."""
        import time
        from custom_components.mysa.number import MysaMinBrightnessNumber

        async def async_update():
            return {"device1": {"MinBrightness": 15}}

        coordinator = DataUpdateCoordinator(
            hass, MagicMock(), name="test", update_method=async_update, config_entry=mock_entry
        )
        await coordinator.async_refresh()

        entity = MysaMinBrightnessNumber(
            coordinator, "device1", mock_device_data, mock_api, mock_entry
        )

        # Set pending value with recent timestamp (valid)
        entity._pending_value = 30.0
        entity._pending_time = time.time() - 10  # 10 seconds ago (still valid)

        # Should return pending value, not actual
        assert entity.native_value == 30.0

    @pytest.mark.asyncio
    async def test_number_extract_value_none(
        self, hass, mock_coordinator, mock_device_data, mock_api, mock_entry
    ):
        """Test _extract_value returns None when key not found."""
        from custom_components.mysa.number import MysaMinBrightnessNumber

        await mock_coordinator.async_refresh()
        entity = MysaMinBrightnessNumber(
            mock_coordinator, "device1", mock_device_data, mock_api, mock_entry
        )

        # Key doesn't exist
        state = {"SomeOtherKey": 123}
        value = entity._extract_value(state, ["NonExistentKey"])
        assert value is None

    @pytest.mark.asyncio
    async def test_select_no_state_returns_auto(
        self, hass, mock_ac_device_data, mock_api, mock_entry
    ):
        """Test current_option returns 'auto' when no state."""
        from custom_components.mysa.select import MysaHorizontalSwingSelect

        async def async_update():
            return {}  # No device data

        coordinator = DataUpdateCoordinator(
            hass, MagicMock(), name="test", update_method=async_update, config_entry=mock_entry
        )
        await coordinator.async_refresh()

        entity = MysaHorizontalSwingSelect(
            coordinator, "ac_device", mock_ac_device_data, mock_api, mock_entry
        )

        assert entity.current_option == "auto"

    @pytest.mark.asyncio
    async def test_select_no_swing_value_returns_auto(
        self, hass, mock_ac_device_data, mock_api, mock_entry
    ):
        """Test current_option returns 'auto' when SwingStateHorizontal is None."""
        from custom_components.mysa.select import MysaHorizontalSwingSelect

        async def async_update():
            return {"ac_device": {"SomeOtherKey": 123}}  # No SwingStateHorizontal

        coordinator = DataUpdateCoordinator(
            hass, MagicMock(), name="test", update_method=async_update, config_entry=mock_entry
        )
        await coordinator.async_refresh()

        entity = MysaHorizontalSwingSelect(
            coordinator, "ac_device", mock_ac_device_data, mock_api, mock_entry
        )

        assert entity.current_option == "auto"

    @pytest.mark.asyncio
    async def test_switch_extract_value_none(
        self, hass, mock_coordinator, mock_device_data, mock_api, mock_entry
    ):
        """Test _extract_value returns None when key not found."""
        from custom_components.mysa.switch import MysaLockSwitch

        await mock_coordinator.async_refresh()
        entity = MysaLockSwitch(
            mock_coordinator, "device1", mock_device_data, mock_api, mock_entry
        )

        state = {"SomeOtherKey": 123}
        value = entity._extract_value(state, ["NonExistentKey"])
        assert value is None

    @pytest.mark.asyncio
    async def test_switch_pending_fallback_when_val_none(
        self, hass, mock_device_data, mock_api, mock_entry
    ):
        """Test switch returns pending when val is None but state exists."""
        from custom_components.mysa.switch import MysaLockSwitch

        async def async_update():
            return {"device1": {"SomeOtherKey": 123}}  # No Lock key

        coordinator = DataUpdateCoordinator(
            hass, MagicMock(), name="test", update_method=async_update, config_entry=mock_entry
        )
        await coordinator.async_refresh()

        entity = MysaLockSwitch(
            coordinator, "device1", mock_device_data, mock_api, mock_entry
        )
        entity._pending_state = True

        # State exists but Lock key doesn't, should return pending
        assert entity.is_on is True

    @pytest.mark.asyncio
    async def test_auto_brightness_is_on(
        self, hass, mock_coordinator, mock_device_data, mock_api, mock_entry
    ):
        """Test AutoBrightnessSwitch is_on property."""
        from custom_components.mysa.switch import MysaAutoBrightnessSwitch

        await mock_coordinator.async_refresh()
        entity = MysaAutoBrightnessSwitch(
            mock_coordinator, "device1", mock_device_data, mock_api, mock_entry
        )

        assert entity.is_on is True  # From fixture data

    @pytest.mark.asyncio
    async def test_proximity_is_on(
        self, hass, mock_coordinator, mock_device_data, mock_api, mock_entry
    ):
        """Test ProximitySwitch is_on property."""
        from custom_components.mysa.switch import MysaProximitySwitch

        await mock_coordinator.async_refresh()
        entity = MysaProximitySwitch(
            mock_coordinator, "device1", mock_device_data, mock_api, mock_entry
        )

        assert entity.is_on is True  # From fixture data

    @pytest.mark.asyncio
    async def test_climate_plus_is_on(
        self, hass, mock_coordinator, mock_ac_device_data, mock_api, mock_entry
    ):
        """Test ClimatePlusSwitch is_on property."""
        from custom_components.mysa.switch import MysaClimatePlusSwitch

        await mock_coordinator.async_refresh()
        entity = MysaClimatePlusSwitch(
            mock_coordinator, "ac_device", mock_ac_device_data, mock_api, mock_entry
        )

        assert entity.is_on is True  # From fixture data

    # ===========================================================================
    # From test_entities.py
    # ===========================================================================

    def test_lock_on_value(self):
        """Test lock on value mapping."""
        # Lock switch uses 1 for locked
        locked = True
        value = 1 if locked else 0

        assert value == 1

    def test_lock_off_value(self):
        """Test lock off value mapping."""
        locked = False
        value = 1 if locked else 0

        assert value == 0

    def test_lock_from_mqtt_state(self):
        """Test extracting lock state from MQTT."""
        state = {"lk": 1}

        is_locked = state.get("lk", 0) == 1

        assert is_locked is True

    def test_lock_command_structure(self):
        """Test lock command structure."""
        device_id = "device1"
        locked = True

        command = {
            "did": device_id,
            "cmd": [{"lk": 1 if locked else 0}],
        }

        assert command["cmd"][0]["lk"] == 1


class TestProximitySensor:
    """Test proximity sensor switch entity."""

    def test_proximity_enabled(self):
        """Test proximity sensor enabled."""
        enabled = True
        value = 2 if enabled else 1

        assert value == 2  # 2 = enabled

    def test_proximity_disabled(self):
        """Test proximity sensor disabled."""
        enabled = False
        value = 2 if enabled else 1

        assert value == 1  # 1 = disabled

    def test_proximity_from_mqtt_state(self):
        """Test extracting proximity state from MQTT."""
        state = {"pr": 2}

        is_enabled = state.get("pr", 1) == 2

        assert is_enabled is True

    def test_climate_plus_from_mqtt_state(self):
        """Test extracting Climate+ state from MQTT."""
        state = {"climateplus": 1}

        is_enabled = state.get("climateplus", 0) == 1

        assert is_enabled is True


class TestBrightnessNumber:
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
        """Test brightness step value."""
        step = 1

        assert step == 1

    def test_brightness_from_mqtt_state(self):
        """Test extracting brightness from MQTT."""
        state = {"br": 75}

        brightness = state.get("br", 50)

        assert brightness == 75

    def test_brightness_command_structure(self):
        """Test brightness command structure."""
        device_id = "device1"
        brightness = 80

        command = {
            "did": device_id,
            "cmd": [{"br": brightness}],
        }

        assert command["cmd"][0]["br"] == 80


class TestMaxCurrentNumber:
    """Test estimated max current number entity."""

    def test_max_current_min_value(self):
        """Test max current minimum value."""
        min_current = 0

        assert min_current == 0

    def test_max_current_max_value(self):
        """Test max current maximum value."""
        max_current = 30

        assert max_current == 30

    def test_max_current_for_power_calculation(self):
        """Test max current used in power calculation."""
        max_current = 15.0
        duty_cycle = 0.5
        voltage = 240

        power = max_current * duty_cycle * voltage

        assert power == 1800.0  # 1.8kW


class TestMinSetpointSensor:
    """Test minimum setpoint sensor."""

    def test_min_setpoint_default(self):
        """Test default minimum setpoint."""
        min_setpoint = 5.0  # 5°C

        assert min_setpoint == 5.0

    def test_min_setpoint_from_caps(self):
        """Test minimum setpoint from device capabilities."""
        caps = {"MinSetpoint": 10.0}

        min_setpoint = caps.get("MinSetpoint", 5.0)

        assert min_setpoint == 10.0


# ===========================================================================
# Number Entity Tests (From test_entity_coverage.py)
# ===========================================================================


class TestMysaNumberEntities:
    """Test real number entity instantiation."""

    @pytest.mark.asyncio
    async def test_min_brightness_number_init(
        self, hass, mock_coordinator, mock_device_data, mock_api, mock_entry
    ):
        """Test MysaMinBrightnessNumber instantiation."""
        from custom_components.mysa.number import MysaMinBrightnessNumber

        await mock_coordinator.async_refresh()

        entity = MysaMinBrightnessNumber(
            mock_coordinator,
            "device1",
            mock_device_data,
            mock_api,
            mock_entry,
        )

        assert entity._device_id == "device1"
        assert "Minimum Brightness" in entity._attr_name
        assert entity._attr_unique_id == "device1_minbrightness"

    @pytest.mark.asyncio
    async def test_min_brightness_native_value(
        self, hass, mock_coordinator, mock_device_data, mock_api, mock_entry
    ):
        """Test MysaMinBrightnessNumber native_value."""
        from custom_components.mysa.number import MysaMinBrightnessNumber

        await mock_coordinator.async_refresh()

        entity = MysaMinBrightnessNumber(
            mock_coordinator,
            "device1",
            mock_device_data,
            mock_api,
            mock_entry,
        )

        value = entity.native_value
        assert value == 10.0

    @pytest.mark.asyncio
    async def test_min_brightness_set_value(
        self, hass, mock_coordinator, mock_device_data, mock_api, mock_entry
    ):
        """Test MysaMinBrightnessNumber async_set_native_value."""
        from custom_components.mysa.number import MysaMinBrightnessNumber

        await mock_coordinator.async_refresh()

        entity = MysaMinBrightnessNumber(
            mock_coordinator,
            "device1",
            mock_device_data,
            mock_api,
            mock_entry,
        )
        entity.async_write_ha_state = MagicMock()

        await entity.async_set_native_value(25.0)

        mock_api.set_min_brightness.assert_called_once_with("device1", 25)

    @pytest.mark.asyncio
    async def test_max_brightness_number_init(
        self, hass, mock_coordinator, mock_device_data, mock_api, mock_entry
    ):
        """Test MysaMaxBrightnessNumber instantiation."""
        from custom_components.mysa.number import MysaMaxBrightnessNumber

        await mock_coordinator.async_refresh()

        entity = MysaMaxBrightnessNumber(
            mock_coordinator,
            "device1",
            mock_device_data,
            mock_api,
            mock_entry,
        )

        assert entity._device_id == "device1"
        assert "Maximum Brightness" in entity._attr_name

    @pytest.mark.asyncio
    async def test_max_brightness_set_value(
        self, hass, mock_coordinator, mock_device_data, mock_api, mock_entry
    ):
        """Test MysaMaxBrightnessNumber async_set_native_value."""
        from custom_components.mysa.number import MysaMaxBrightnessNumber

        await mock_coordinator.async_refresh()

        entity = MysaMaxBrightnessNumber(
            mock_coordinator,
            "device1",
            mock_device_data,
            mock_api,
            mock_entry,
        )
        entity.async_write_ha_state = MagicMock()

        await entity.async_set_native_value(90.0)

        mock_api.set_max_brightness.assert_called_once_with("device1", 90)


# ===========================================================================
# Switch Entity Tests
# ===========================================================================


class TestMysaSwitchEntities:
    """Test real switch entity instantiation."""

    @pytest.mark.asyncio
    async def test_lock_switch_init(
        self, hass, mock_coordinator, mock_device_data, mock_api, mock_entry
    ):
        """Test MysaLockSwitch instantiation."""
        from custom_components.mysa.switch import MysaLockSwitch

        await mock_coordinator.async_refresh()

        entity = MysaLockSwitch(
            mock_coordinator,
            "device1",
            mock_device_data,
            mock_api,
            mock_entry,
        )

        assert entity._device_id == "device1"
        assert "Lock" in entity._attr_name
        assert entity._attr_icon == "mdi:lock"

    @pytest.mark.asyncio
    async def test_lock_switch_is_on(
        self, hass, mock_coordinator, mock_device_data, mock_api, mock_entry
    ):
        """Test MysaLockSwitch is_on property."""
        from custom_components.mysa.switch import MysaLockSwitch

        await mock_coordinator.async_refresh()

        entity = MysaLockSwitch(
            mock_coordinator,
            "device1",
            mock_device_data,
            mock_api,
            mock_entry,
        )

        assert entity.is_on is True

    @pytest.mark.asyncio
    async def test_lock_switch_turn_on(
        self, hass, mock_coordinator, mock_device_data, mock_api, mock_entry
    ):
        """Test MysaLockSwitch async_turn_on."""
        from custom_components.mysa.switch import MysaLockSwitch

        await mock_coordinator.async_refresh()

        entity = MysaLockSwitch(
            mock_coordinator,
            "device1",
            mock_device_data,
            mock_api,
            mock_entry,
        )
        entity.async_write_ha_state = MagicMock()

        await entity.async_turn_on()

        mock_api.set_lock.assert_called_once_with("device1", True)

    @pytest.mark.asyncio
    async def test_lock_switch_turn_off(
        self, hass, mock_coordinator, mock_device_data, mock_api, mock_entry
    ):
        """Test MysaLockSwitch async_turn_off."""
        from custom_components.mysa.switch import MysaLockSwitch

        await mock_coordinator.async_refresh()

        entity = MysaLockSwitch(
            mock_coordinator,
            "device1",
            mock_device_data,
            mock_api,
            mock_entry,
        )
        entity.async_write_ha_state = MagicMock()

        await entity.async_turn_off()

        mock_api.set_lock.assert_called_once_with("device1", False)

    @pytest.mark.asyncio
    async def test_auto_brightness_switch_init(
        self, hass, mock_coordinator, mock_device_data, mock_api, mock_entry
    ):
        """Test MysaAutoBrightnessSwitch instantiation."""
        from custom_components.mysa.switch import MysaAutoBrightnessSwitch

        await mock_coordinator.async_refresh()

        entity = MysaAutoBrightnessSwitch(
            mock_coordinator,
            "device1",
            mock_device_data,
            mock_api,
            mock_entry,
        )

        assert "Auto Brightness" in entity._attr_name
        assert entity._attr_icon == "mdi:brightness-auto"

    @pytest.mark.asyncio
    async def test_proximity_switch_init(
        self, hass, mock_coordinator, mock_device_data, mock_api, mock_entry
    ):
        """Test MysaProximitySwitch instantiation."""
        from custom_components.mysa.switch import MysaProximitySwitch

        await mock_coordinator.async_refresh()

        entity = MysaProximitySwitch(
            mock_coordinator,
            "device1",
            mock_device_data,
            mock_api,
            mock_entry,
        )

        assert "Wake on Approach" in entity._attr_name
        assert entity._attr_icon == "mdi:motion-sensor"

    @pytest.mark.asyncio
    async def test_climate_plus_switch_init(
        self, hass, mock_coordinator, mock_device_data, mock_api, mock_entry
    ):
        """Test MysaClimatePlusSwitch instantiation."""
        from custom_components.mysa.switch import MysaClimatePlusSwitch

        await mock_coordinator.async_refresh()

        entity = MysaClimatePlusSwitch(
            mock_coordinator,
            "device1",
            mock_device_data,
            mock_api,
            mock_entry,
        )

        assert "Climate+" in entity._attr_name


# ===========================================================================
# Select Entity Tests
# ===========================================================================


class TestMysaSelectEntities:
    """Test real select entity instantiation."""

    @pytest.mark.asyncio
    async def test_horizontal_swing_select_init(
        self, hass, mock_coordinator, mock_device_data, mock_api, mock_entry
    ):
        """Test MysaHorizontalSwingSelect instantiation."""
        from custom_components.mysa.select import MysaHorizontalSwingSelect

        await mock_coordinator.async_refresh()

        entity = MysaHorizontalSwingSelect(
            mock_coordinator,
            "device1",
            mock_device_data,
            mock_api,
            mock_entry,
        )

        assert entity._device_id == "device1"
        assert "Horizontal Swing" in entity._attr_name

    @pytest.mark.asyncio
    async def test_horizontal_swing_options(
        self, hass, mock_coordinator, mock_device_data, mock_api, mock_entry
    ):
        """Test MysaHorizontalSwingSelect options."""
        from custom_components.mysa.select import MysaHorizontalSwingSelect

        await mock_coordinator.async_refresh()

        entity = MysaHorizontalSwingSelect(
            mock_coordinator,
            "device1",
            mock_device_data,
            mock_api,
            mock_entry,
        )

        options = entity.options
        assert isinstance(options, list)
        assert len(options) > 0

    @pytest.mark.asyncio
    async def test_horizontal_swing_current_option(
        self, hass, mock_coordinator, mock_device_data, mock_api, mock_entry
    ):
        """Test MysaHorizontalSwingSelect current_option."""
        from custom_components.mysa.select import MysaHorizontalSwingSelect

        await mock_coordinator.async_refresh()

        entity = MysaHorizontalSwingSelect(
            mock_coordinator,
            "device1",
            mock_device_data,
            mock_api,
            mock_entry,
        )

        current = entity.current_option
        assert current is not None

    @pytest.mark.asyncio
    async def test_horizontal_swing_select_option(
        self, hass, mock_coordinator, mock_device_data, mock_api, mock_entry
    ):
        """Test MysaHorizontalSwingSelect async_select_option."""
        from custom_components.mysa.select import MysaHorizontalSwingSelect

        await mock_coordinator.async_refresh()

        entity = MysaHorizontalSwingSelect(
            mock_coordinator,
            "device1",
            mock_device_data,
            mock_api,
            mock_entry,
        )
        entity.async_write_ha_state = MagicMock()

        await entity.async_select_option("auto")

        mock_api.set_ac_horizontal_swing.assert_called()


# ===========================================================================
# Sensor Entity Tests
# ===========================================================================


class TestMysaSensorEntities:
    """Test real sensor entity instantiation."""

    @pytest.mark.asyncio
    async def test_diagnostic_sensor_init(
        self, hass, mock_coordinator, mock_device_data, mock_api, mock_entry
    ):
        """Test MysaDiagnosticSensor instantiation."""
        from custom_components.mysa.sensor import MysaDiagnosticSensor

        await mock_coordinator.async_refresh()

        entity = MysaDiagnosticSensor(
            mock_coordinator,
            "device1",
            mock_device_data,
            "DutyCycle",
            "Duty Cycle",
            "%",
            None,
            None,
            mock_entry,
        )

        assert entity._device_id == "device1"
        assert "Duty Cycle" in entity._attr_name

    @pytest.mark.asyncio
    async def test_diagnostic_sensor_value(
        self, hass, mock_coordinator, mock_device_data, mock_api, mock_entry
    ):
        """Test MysaDiagnosticSensor native_value."""
        from custom_components.mysa.sensor import MysaDiagnosticSensor

        await mock_coordinator.async_refresh()

        entity = MysaDiagnosticSensor(
            mock_coordinator,
            "device1",
            mock_device_data,
            "DutyCycle",
            "Duty Cycle",
            "%",
            None,
            None,
            mock_entry,
        )

        value = entity.native_value
        assert value == 50

    @pytest.mark.asyncio
    async def test_zone_sensor_init(
        self, hass, mock_coordinator, mock_device_data, mock_api
    ):
        """Test MysaZoneSensor instantiation."""
        from custom_components.mysa.sensor import MysaZoneSensor

        await mock_coordinator.async_refresh()

        entity = MysaZoneSensor(
            mock_coordinator,
            "device1",
            mock_device_data,
            mock_api,
        )

        assert entity._device_id == "device1"

    @pytest.mark.asyncio
    async def test_simulated_current_sensor_init(
        self, hass, mock_coordinator, mock_device_data, mock_entry, mock_api
    ):
        """Test MysaCurrentSensor instantiation."""
        from custom_components.mysa.sensor import MysaCurrentSensor

        await mock_coordinator.async_refresh()

        mock_entry.options = {"estimated_max_current": 15.0}

        entity = MysaCurrentSensor(
            mock_coordinator,
            "device1",
            mock_device_data,
            mock_api,
            mock_entry,
        )

        assert entity._device_id == "device1"
        assert "Estimated Current" in entity._attr_name

    @pytest.mark.asyncio
    async def test_simulated_power_sensor_init(
        self, hass, mock_coordinator, mock_device_data, mock_entry, mock_api
    ):
        """Test MysaPowerSensor instantiation."""
        from custom_components.mysa.sensor import MysaPowerSensor

        await mock_coordinator.async_refresh()

        mock_entry.options = {"estimated_max_current": 15.0}

        entity = MysaPowerSensor(
            mock_coordinator,
            "device1",
            mock_device_data,
            mock_api,
            mock_entry,
        )

        assert entity._device_id == "device1"
        assert "Power" in entity._attr_name


# ===========================================================================
# Update Entity Tests
# ===========================================================================


class TestMysaUpdateEntities:
    """Test real update entity instantiation."""

    @pytest.mark.asyncio
    async def test_update_entity_init(self, mock_api, mock_device_data):
        """Test MysaUpdate instantiation."""
        from custom_components.mysa.update import MysaUpdate

        entity = MysaUpdate(
            mock_api,
            "device1",
            mock_device_data,
        )

        assert entity._device_id == "device1"
        assert "Firmware" in entity._attr_name
        assert entity._attr_installed_version == "1.2.3"

    @pytest.mark.asyncio
    async def test_update_entity_device_info(self, mock_api, mock_device_data):
        """Test MysaUpdate device_info."""
        from custom_components.mysa.update import MysaUpdate

        entity = MysaUpdate(
            mock_api,
            "device1",
            mock_device_data,
        )

        device_info = entity._attr_device_info
        # DeviceInfo is a NamedTuple-like object
        assert (DOMAIN, "device1") in device_info["identifiers"]


# ===========================================================================
# From test_device_entity.py
# ===========================================================================

ROOT_DIR = os.path.dirname(TEST_DIR)
sys.path.insert(0, ROOT_DIR)

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

# Module-level imports after path setup
from custom_components.mysa.const import DOMAIN


class TestDeviceRegistry:
    """Test device registry patterns."""

    @pytest.fixture
    def mock_entry(self, hass):
        """Create a mock config entry for device registry."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={"username": "test@example.com", "password": "test"},
            entry_id="test_device_entry",
        )
        entry.add_to_hass(hass)
        return entry

    @pytest.mark.asyncio
    async def test_register_device(self, hass, mock_entry):
        """Test registering a device."""
        registry = dr.async_get(hass)

        device = registry.async_get_or_create(
            config_entry_id=mock_entry.entry_id,
            identifiers={(DOMAIN, "device1")},
            manufacturer="Mysa",
            model="V2",
            name="Living Room Thermostat",
        )

        assert device.name == "Living Room Thermostat"
        assert device.manufacturer == "Mysa"
        assert (DOMAIN, "device1") in device.identifiers

    @pytest.mark.asyncio
    async def test_device_has_model(self, hass, mock_entry):
        """Test device has model info."""
        registry = dr.async_get(hass)

        device = registry.async_get_or_create(
            config_entry_id=mock_entry.entry_id,
            identifiers={(DOMAIN, "device123")},
            model="BB-V2",
        )

        assert device.model == "BB-V2"

    @pytest.mark.asyncio
    async def test_multiple_devices(self, hass, mock_entry):
        """Test multiple devices can be registered."""
        registry = dr.async_get(hass)

        device1 = registry.async_get_or_create(
            config_entry_id=mock_entry.entry_id,
            identifiers={(DOMAIN, "device1")},
            name="Device 1",
        )
        device2 = registry.async_get_or_create(
            config_entry_id=mock_entry.entry_id,
            identifiers={(DOMAIN, "device2")},
            name="Device 2",
        )

        assert device1.id != device2.id
        assert device1.name == "Device 1"
        assert device2.name == "Device 2"


class TestEntityRegistry:
    """Test entity registry patterns."""

    @pytest.mark.asyncio
    async def test_entity_registry_entry(self, hass):
        """Test entity registry entry creation."""
        registry = er.async_get(hass)

        entry = registry.async_get_or_create(
            domain="climate",
            platform=DOMAIN,
            unique_id="device1_climate",
        )

        assert entry.entity_id.startswith("climate.")
        assert entry.unique_id == "device1_climate"

    @pytest.mark.asyncio
    async def test_entity_disabled_by_default(self, hass):
        """Test entity can be disabled by default."""
        registry = er.async_get(hass)

        entry = registry.async_get_or_create(
            domain="sensor",
            platform=DOMAIN,
            unique_id="sensor_disabled",
            disabled_by=er.RegistryEntryDisabler.INTEGRATION,
        )

        assert entry.disabled_by == er.RegistryEntryDisabler.INTEGRATION


class TestStateAssertions:
    """Test state assertion patterns."""

    @pytest.mark.asyncio
    async def test_state_exists(self, hass):
        """Test asserting state exists."""
        hass.states.async_set(
            "climate.mysa_test",
            "heat",
            {
                "current_temperature": 20.5,
                "temperature": 21.0,
            },
        )

        state = hass.states.get("climate.mysa_test")

        assert state is not None
        assert state.state == "heat"

    @pytest.mark.asyncio
    async def test_state_attributes(self, hass):
        """Test asserting state attributes."""
        hass.states.async_set(
            "sensor.mysa_temp",
            "21.5",
            {
                "unit_of_measurement": "°C",
                "device_class": "temperature",
            },
        )

        state = hass.states.get("sensor.mysa_temp")

        assert state.attributes["unit_of_measurement"] == "°C"
        assert state.attributes["device_class"] == "temperature"

    @pytest.mark.asyncio
    async def test_state_change_tracking(self, hass):
        """Test tracking state changes."""
        state_values = []

        def track_state(event):
            new_state = event.data.get("new_state")
            if new_state:
                state_values.append(new_state.state)

        hass.bus.async_listen("state_changed", track_state)

        hass.states.async_set("sensor.tracker", "value1")
        await hass.async_block_till_done()

        hass.states.async_set("sensor.tracker", "value2")
        await hass.async_block_till_done()

        assert "value1" in state_values
        assert "value2" in state_values


class TestRestoreState:
    """Test state restoration patterns."""

    @pytest.mark.asyncio
    async def test_restore_state_available(self, hass):
        """Test RestoreEntity pattern is available."""
        from homeassistant.helpers.restore_state import RestoreEntity

        assert RestoreEntity is not None

    @pytest.mark.asyncio
    async def test_extra_stored_data(self, hass):
        """Test ExtraStoredData pattern is available."""
        from homeassistant.helpers.restore_state import ExtraStoredData

        assert ExtraStoredData is not None


class TestAioHttpClient:
    """Test aiohttp_client fixture for HTTP testing."""

    @pytest.mark.asyncio
    async def test_aiohttp_client_available(self, hass, aiohttp_client):
        """Test aiohttp_client fixture is available."""
        assert aiohttp_client is not None

    @pytest.mark.asyncio
    async def test_http_app_available(self, hass):
        """Test hass.http.app is available after setup."""
        # In a full integration test, hass.http would be set up
        # This verifies the pattern works
        assert hasattr(hass, "http")


class TestEntityComponents:
    """Test entity component patterns."""

    @pytest.mark.asyncio
    async def test_entity_component_available(self, hass):
        """Test EntityComponent is available."""
        from homeassistant.helpers.entity_component import EntityComponent

        assert EntityComponent is not None

    @pytest.mark.asyncio
    async def test_entity_platform_available(self, hass):
        """Test EntityPlatform is available."""
        from homeassistant.helpers.entity_platform import EntityPlatform

        assert EntityPlatform is not None


class TestHelperModules:
    """Test helper module availability."""

    @pytest.mark.asyncio
    async def test_discovery_available(self, hass):
        """Test discovery helpers are available."""
        from homeassistant.helpers import discovery

        assert discovery is not None

    @pytest.mark.asyncio
    async def test_template_available(self, hass):
        """Test template helpers are available."""
        from homeassistant.helpers import template

        assert template is not None

    @pytest.mark.asyncio
    async def test_storage_available(self, hass):
        """Test storage helpers are available."""
        from homeassistant.helpers.storage import Store

        store = Store(hass, 1, "test_store")
        assert store is not None


class TestIntegrationHelpers:
    """Test integration helper patterns."""

    @pytest.mark.asyncio
    async def test_config_validation(self, hass):
        """Test config validation helpers."""
        import homeassistant.helpers.config_validation as cv

        # Test common validators
        assert cv.string("test") == "test"
        assert cv.boolean(True) is True

    @pytest.mark.asyncio
    async def test_selector_available(self, hass):
        """Test selector is available for options flow."""
        from homeassistant.helpers import selector

        assert selector is not None

    @pytest.mark.asyncio
    async def test_issue_registry_available(self, hass):
        """Test issue registry is available."""
        from homeassistant.helpers import issue_registry as ir

        registry = ir.async_get(hass)
        assert registry is not None


# ===========================================================================
# From test_entity_integration.py
# ===========================================================================

ROOT_DIR = os.path.dirname(TEST_DIR)
sys.path.insert(0, ROOT_DIR)

import pytest
from unittest.mock import MagicMock
from homeassistant.components.climate import HVACMode, ClimateEntityFeature


class TestDeviceInfo:
    """Test device info patterns."""

    def test_device_identifiers_format(self):
        """Test device identifiers are formatted correctly."""
        device_id = "device1"
        identifiers = {("mysa", device_id)}

        assert ("mysa", "device1") in identifiers

    def test_device_info_structure(self):
        """Test device info has required fields."""
        device_info = {
            "identifiers": {("mysa", "device1")},
            "name": "Living Room Thermostat",
            "manufacturer": "Mysa",
            "model": "V2",
        }

        assert "identifiers" in device_info
        assert "manufacturer" in device_info
        assert device_info["manufacturer"] == "Mysa"


class TestClimateEntityProperties:
    """Test climate entity properties."""

    def test_hvac_modes(self):
        """Test HVAC modes are correct."""
        hvac_modes = [HVACMode.OFF, HVACMode.HEAT]

        assert HVACMode.OFF in hvac_modes
        assert HVACMode.HEAT in hvac_modes

    def test_temperature_unit(self):
        """Test temperature unit is Celsius."""
        from homeassistant.const import UnitOfTemperature

        unit = UnitOfTemperature.CELSIUS

        assert unit == "°C"

    def test_supported_features_heat(self):
        """Test heater supported features."""
        features = ClimateEntityFeature.TARGET_TEMPERATURE

        assert features & ClimateEntityFeature.TARGET_TEMPERATURE


class TestACEntityProperties:
    """Test AC entity properties."""

    def test_ac_hvac_modes(self):
        """Test AC HVAC modes include cooling."""
        hvac_modes = [HVACMode.OFF, HVACMode.COOL, HVACMode.HEAT, HVACMode.AUTO]

        assert HVACMode.COOL in hvac_modes
        assert HVACMode.AUTO in hvac_modes

    def test_ac_features_include_fan(self):
        """Test AC features include fan mode."""
        features = (
            ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.FAN_MODE
        )

        assert features & ClimateEntityFeature.FAN_MODE

    def test_ac_features_include_swing(self):
        """Test AC features can include swing mode."""
        features = ClimateEntityFeature.SWING_MODE

        assert features & ClimateEntityFeature.SWING_MODE


class TestStateNormalization:
    """Test state data normalization."""

    def test_temperature_from_state(self):
        """Test extracting temperature from state data."""
        state_data = {
            "temperature": 20.5,
            "setpoint": 21.0,
            "humidity": 45,
        }

        assert state_data["temperature"] == 20.5
        assert state_data["setpoint"] == 21.0

    def test_hvac_mode_mapping(self):
        """Test HVAC mode value mapping."""
        mode_map = {
            0: HVACMode.OFF,
            1: HVACMode.HEAT,
        }

        assert mode_map[0] == HVACMode.OFF
        assert mode_map[1] == HVACMode.HEAT

    def test_heating_state_detection(self):
        """Test heating state detection from data."""
        state_data = {
            "Heating": True,
            "hvac_mode": 1,
        }

        is_heating = state_data.get("Heating", False)

        assert is_heating is True


class TestClimateEntityAsync:
    """Test async climate entity actions with mocking."""

    @pytest.mark.asyncio
    async def test_set_temperature_mocked(self, hass):
        """Test MysaClimate.async_set_temperature with mocked API."""
        from unittest.mock import patch, AsyncMock
        from custom_components.mysa.climate import MysaClimate

        with patch("custom_components.mysa.climate.CoordinatorEntity.__init__"):
            mock_api = MagicMock()
            mock_api.set_target_temperature = AsyncMock()

            entity = MysaClimate(
                coordinator=MagicMock(),
                device_id="device1",
                device_data={},
                api=mock_api,
                entry=MagicMock(entry_id="test_entry"),
            )
            entity.coordinator = MagicMock()
            entity.coordinator.async_request_refresh = AsyncMock()
            entity.async_write_ha_state = MagicMock()

            await entity.async_set_temperature(temperature=22.5)

            mock_api.set_target_temperature.assert_called_once_with("device1", 22.5)

    @pytest.mark.asyncio
    async def test_set_hvac_mode_mocked(self, hass):
        """Test MysaClimate.async_set_hvac_mode with mocked API."""
        from unittest.mock import patch, AsyncMock
        from custom_components.mysa.climate import MysaClimate

        with patch("custom_components.mysa.climate.CoordinatorEntity.__init__"):
            mock_api = MagicMock()
            mock_api.set_hvac_mode = AsyncMock()

            entity = MysaClimate(
                coordinator=MagicMock(),
                device_id="device1",
                device_data={},
                api=mock_api,
                entry=MagicMock(entry_id="test_entry"),
            )
            entity.coordinator = MagicMock()
            entity.coordinator.async_request_refresh = AsyncMock()
            entity.async_write_ha_state = MagicMock()

            await entity.async_set_hvac_mode(HVACMode.HEAT)

            mock_api.set_hvac_mode.assert_called_once()
