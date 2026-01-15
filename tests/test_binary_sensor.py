"""
Binary Sensor Entity Coverage Tests.

Tests for custom_components/mysa/binary_sensor.py
"""

import sys
import os

# Add project root to path for imports
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(TEST_DIR)
sys.path.insert(0, ROOT_DIR)

import pytest
from unittest.mock import MagicMock, AsyncMock
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.const import EntityCategory

from custom_components.mysa.const import DOMAIN
from custom_components.mysa.binary_sensor import (
    async_setup_entry,
    MysaConnectionSensor,
)

@pytest.fixture
def mock_coordinator(hass, mock_config_entry):
    """Create a mock coordinator with test data."""
    async def async_update():
        return {
            "device1": {
                "Connected": True,
                "Name": "Test Device",
                "Model": "BB-V2",
            },
            "device2": {
                "Connected": False,
                "Name": "Offline Device",
                "Model": "BB-V1",
            }
        }

    coordinator = DataUpdateCoordinator(
        hass, MagicMock(), name="test", update_method=async_update, config_entry=mock_config_entry
    )
    return coordinator

@pytest.mark.asyncio
class TestMysaBinarySensor:
    """Test MysaConnectionSensor."""

    async def test_async_setup_entry(self, hass, mock_coordinator, mock_config_entry):
        """Test setup creates binary sensors."""
        mock_api = MagicMock()
        mock_api.get_devices = AsyncMock(
            return_value={
                "device1": {"Id": "device1", "Name": "Test Device", "Model": "BB-V2"},
                "device2": {"Id": "device2", "Name": "Offline Device", "Model": "BB-V1"},
            }
        )

        hass.data[DOMAIN] = {
            "test_entry_id": {"coordinator": mock_coordinator, "api": mock_api}
        }

        entities = []
        async_add_entities = MagicMock(side_effect=lambda e: entities.extend(e))

        await async_setup_entry(hass, mock_config_entry, async_add_entities)

        assert len(entities) == 2
        assert isinstance(entities[0], MysaConnectionSensor)

    async def test_sensor_attributes(self, hass, mock_coordinator):
        """Test sensor status attributes."""
        await mock_coordinator.async_refresh()

        device_data = {"Id": "device1", "Name": "Test Device", "Model": "BB-V2"}
        entity = MysaConnectionSensor(mock_coordinator, "device1", device_data)

        assert entity.name == "Test Device Connection"
        assert entity.unique_id == "device1_connection"
        assert entity.device_class == BinarySensorDeviceClass.CONNECTIVITY
        assert entity.entity_category == EntityCategory.DIAGNOSTIC

        info = entity.device_info
        assert info["identifiers"] == {(DOMAIN, "device1")}
        assert info["manufacturer"] == "Mysa"
        assert info["model"] == "BB-V2"
        assert info["name"] == "Test Device"

    async def test_is_on_state(self, hass, mock_coordinator):
        """Test is_on property based on Connected state."""
        await mock_coordinator.async_refresh()

        # Device 1: Connected = True
        device1_data = {"Id": "device1", "Name": "Test Device"}
        entity1 = MysaConnectionSensor(mock_coordinator, "device1", device1_data)
        assert entity1.is_on is True

        # Device 2: Connected = False
        device2_data = {"Id": "device2", "Name": "Offline Device"}
        entity2 = MysaConnectionSensor(mock_coordinator, "device2", device2_data)
        assert entity2.is_on is False

    async def test_is_on_missing_state(self, hass, mock_config_entry):
        """Test is_on returns False when state is missing."""
        async def async_update():
            return {} # Empty data

        coordinator = DataUpdateCoordinator(
            hass, MagicMock(), name="test", update_method=async_update, config_entry=mock_config_entry
        )
        await coordinator.async_refresh()

        device_data = {"Id": "device1", "Name": "Test Device"}
        entity = MysaConnectionSensor(coordinator, "device1", device_data)

        assert entity.is_on is False

    async def test_setup_no_data(self, hass, mock_config_entry):
        """Test setup does nothing if data missing."""
        hass.data[DOMAIN] = {} # Empty
        async_add_entities = MagicMock()
        await async_setup_entry(hass, mock_config_entry, async_add_entities)
        async_add_entities.assert_not_called()
