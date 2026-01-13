"""
Sensor Entity Coverage Tests.

Tests that instantiate and test real sensor entity classes
to improve code coverage for sensor.py.
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
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import EntityCategory

# Module-level imports after path setup
from custom_components.mysa.const import DOMAIN


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def mock_coordinator(hass, mock_entry):
    """Create a mock coordinator with comprehensive test data."""

    async def async_update():
        return {
            "device1": {
                "Zone": "zone123",
                "Rssi": -65,
                "rssi": -65,
                "Brightness": 50,
                "br": 50,
                "TimeZone": "America/Toronto",
                "tz": "America/Toronto",
                "MinSetpoint": 5,
                "mns": 5,
                "MaxSetpoint": 30,
                "mxs": 30,
                "Duty": 50,
                "dc": 50,
                "MaxCurrent": 15.0,
                "mxc": 15.0,
                "HeatSink": 45,
                "hs": 45,
                "Infloor": 28,
                "if": 28,
                "Voltage": 240,
                "volts": 240,
                "Current": 10.5,
                "amps": 10.5,
                "MinBrightness": 10,
                "mnbr": 10,
                "MaxBrightness": 80,
                "mxbr": 80,
            },
            "lite_device": {
                "Zone": "zone456",
                "Duty": 75,
                "dc": 75,
                "Voltage": 240,
            },
        }

    coordinator = DataUpdateCoordinator(
        hass,
        MagicMock(),
        name="mysa_test",
        update_method=async_update,
        config_entry=mock_entry
    )
    return coordinator


@pytest.fixture
def mock_device_data():
    """Create mock device data."""
    return {
        "Id": "device1",
        "Name": "Living Room",
        "Model": "BB-V2",
    }


@pytest.fixture
def mock_lite_device_data():
    """Create mock Lite device data."""
    return {
        "Id": "lite_device",
        "Name": "Bedroom",
        "Model": "BB-V2-0-L",
    }


@pytest.fixture
def mock_api():
    """Create mock API."""
    api = MagicMock()
    api.get_zone_name = MagicMock(return_value="Living Room Zone")
    api.get_devices = AsyncMock(
        return_value={
            "device1": {"Id": "device1", "Name": "Living Room", "Model": "BB-V2"},
            "ac_device": {
                "Id": "ac_device",
                "Name": "Bedroom AC",
                "Model": "AC-V1",
                "SupportedCaps": {"modes": {"4": {}}},
            },
            "lite_device": {
                "Id": "lite_device",
                "Name": "Office",
                "Model": "BB-V2-0-L",
            },
        }
    )
    return api


@pytest.fixture
def mock_entry():
    """Create mock config entry."""
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    entry.options = {}
    return entry


# ===========================================================================
# MysaDiagnosticSensor Tests
# ===========================================================================


class TestMysaDiagnosticSensorInit:
    """Test MysaDiagnosticSensor initialization."""

    @pytest.mark.asyncio
    async def test_rssi_sensor_init(
        self, hass, mock_coordinator, mock_device_data, mock_entry
    ):
        """Test RSSI sensor initialization."""
        from custom_components.mysa.sensor import MysaDiagnosticSensor
        from homeassistant.const import SIGNAL_STRENGTH_DECIBELS_MILLIWATT

        await mock_coordinator.async_refresh()

        entity = MysaDiagnosticSensor(
            mock_coordinator,
            "device1",
            mock_device_data,
            "Rssi",
            "RSSI",
            SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
            SensorStateClass.MEASUREMENT,
            SensorDeviceClass.SIGNAL_STRENGTH,
            mock_entry,
        )

        assert entity._device_id == "device1"
        assert "RSSI" in entity._attr_name

    @pytest.mark.asyncio
    async def test_duty_sensor_init(
        self, hass, mock_coordinator, mock_device_data, mock_entry
    ):
        """Test Duty Cycle sensor initialization."""
        from custom_components.mysa.sensor import MysaDiagnosticSensor
        from homeassistant.const import PERCENTAGE

        await mock_coordinator.async_refresh()

        entity = MysaDiagnosticSensor(
            mock_coordinator,
            "device1",
            mock_device_data,
            "Duty",
            "Duty Cycle",
            PERCENTAGE,
            SensorStateClass.MEASUREMENT,
            None,
            mock_entry,
        )

        assert "Duty Cycle" in entity._attr_name
        assert entity._attr_entity_category == EntityCategory.DIAGNOSTIC


class TestMysaDiagnosticSensorValues:
    """Test MysaDiagnosticSensor native_value for various sensor types."""

    @pytest.fixture
    def create_sensor(self, hass, mock_coordinator, mock_device_data, mock_entry):
        """Factory to create diagnostic sensors."""
        from custom_components.mysa.sensor import MysaDiagnosticSensor

        def _create(
            sensor_key, name_suffix, unit=None, state_class=None, device_class=None
        ):
            return MysaDiagnosticSensor(
                mock_coordinator,
                "device1",
                mock_device_data,
                sensor_key,
                name_suffix,
                unit,
                state_class,
                device_class,
                mock_entry,
            )

        return _create

    @pytest.mark.asyncio
    async def test_rssi_value(self, hass, mock_coordinator, create_sensor):
        """Test RSSI sensor value."""
        await mock_coordinator.async_refresh()

        entity = create_sensor("Rssi", "RSSI")

        assert entity.native_value == -65

    @pytest.mark.asyncio
    async def test_brightness_value(self, hass, mock_coordinator, create_sensor):
        """Test Brightness sensor value."""
        await mock_coordinator.async_refresh()

        entity = create_sensor("Brightness", "Brightness")

        assert entity.native_value == 50

    @pytest.mark.asyncio
    async def test_timezone_value(self, hass, mock_coordinator, create_sensor):
        """Test TimeZone sensor value."""
        await mock_coordinator.async_refresh()

        entity = create_sensor("TimeZone", "Time Zone")

        assert entity.native_value == "America/Toronto"

    @pytest.mark.asyncio
    async def test_min_setpoint_value(self, hass, mock_coordinator, create_sensor):
        """Test MinSetpoint sensor value."""
        await mock_coordinator.async_refresh()

        entity = create_sensor("MinSetpoint", "Minimum Setpoint")

        assert entity.native_value == 5

    @pytest.mark.asyncio
    async def test_max_setpoint_value(self, hass, mock_coordinator, create_sensor):
        """Test MaxSetpoint sensor value."""
        await mock_coordinator.async_refresh()

        entity = create_sensor("MaxSetpoint", "Maximum Setpoint")

        assert entity.native_value == 30

    @pytest.mark.asyncio
    async def test_duty_value(self, hass, mock_coordinator, create_sensor):
        """Test Duty Cycle sensor value."""
        await mock_coordinator.async_refresh()

        entity = create_sensor("Duty", "Duty Cycle")

        # Duty 50 should remain 50 (>1 so no *100)
        assert entity.native_value == 50

    @pytest.mark.asyncio
    async def test_max_current_value(self, hass, mock_coordinator, create_sensor):
        """Test MaxCurrent sensor value."""
        await mock_coordinator.async_refresh()

        entity = create_sensor("MaxCurrent", "Maximum Current")

        assert entity.native_value == 15.0

    @pytest.mark.asyncio
    async def test_heatsink_value(self, hass, mock_coordinator, create_sensor):
        """Test HeatSink sensor value."""
        await mock_coordinator.async_refresh()

        entity = create_sensor("HeatSink", "HeatSink Temperature")

        assert entity.native_value == 45

    @pytest.mark.asyncio
    async def test_infloor_value(self, hass, mock_coordinator, create_sensor):
        """Test Infloor sensor value."""
        await mock_coordinator.async_refresh()

        entity = create_sensor("Infloor", "Infloor Temperature")

        assert entity.native_value == 28

    @pytest.mark.asyncio
    async def test_voltage_value(self, hass, mock_coordinator, create_sensor):
        """Test Voltage sensor value."""
        await mock_coordinator.async_refresh()

        entity = create_sensor("Voltage", "Voltage")

        assert entity.native_value == 240

    @pytest.mark.asyncio
    async def test_current_value(self, hass, mock_coordinator, create_sensor):
        """Test Current sensor value."""
        await mock_coordinator.async_refresh()

        entity = create_sensor("Current", "Current")

        assert entity.native_value == 10.5

    @pytest.mark.asyncio
    async def test_min_brightness_value(self, hass, mock_coordinator, create_sensor):
        """Test MinBrightness sensor value."""
        await mock_coordinator.async_refresh()

        entity = create_sensor("MinBrightness", "Minimum Brightness")

        assert entity.native_value == 10

    @pytest.mark.asyncio
    async def test_max_brightness_value(self, hass, mock_coordinator, create_sensor):
        """Test MaxBrightness sensor value."""
        await mock_coordinator.async_refresh()

        entity = create_sensor("MaxBrightness", "Maximum Brightness")

        assert entity.native_value == 80


class TestMysaDiagnosticSensorProperties:
    """Test MysaDiagnosticSensor properties."""

    @pytest.fixture
    def sensor_entity(self, hass, mock_coordinator, mock_device_data, mock_entry):
        """Create a sensor entity."""
        from custom_components.mysa.sensor import MysaDiagnosticSensor

        return MysaDiagnosticSensor(
            mock_coordinator,
            "device1",
            mock_device_data,
            "Rssi",
            "RSSI",
            None,
            None,
            None,
            mock_entry,
        )

    @pytest.mark.asyncio
    async def test_device_info(self, hass, mock_coordinator, sensor_entity):
        """Test device_info property."""
        await mock_coordinator.async_refresh()

        info = sensor_entity.device_info

        assert "identifiers" in info
        assert info["manufacturer"] == "Mysa"

    @pytest.mark.asyncio
    async def test_extra_state_attributes(self, hass, mock_coordinator, sensor_entity):
        """Test extra_state_attributes property."""
        await mock_coordinator.async_refresh()

        attrs = sensor_entity.extra_state_attributes

        assert "device_id" in attrs
        assert "zone_id" in attrs


# ===========================================================================
# MysaZoneSensor Tests
# ===========================================================================


class TestMysaZoneSensor:
    """Test MysaZoneSensor."""

    @pytest.mark.asyncio
    async def test_zone_sensor_init(
        self, hass, mock_coordinator, mock_device_data, mock_api
    ):
        """Test MysaZoneSensor initialization."""
        from custom_components.mysa.sensor import MysaZoneSensor

        await mock_coordinator.async_refresh()

        entity = MysaZoneSensor(
            mock_coordinator,
            "device1",
            mock_device_data,
            mock_api,
        )

        assert entity._device_id == "device1"
        assert "Zone" in entity._attr_name

    @pytest.mark.asyncio
    async def test_zone_sensor_value(
        self, hass, mock_coordinator, mock_device_data, mock_api
    ):
        """Test MysaZoneSensor native_value."""
        from custom_components.mysa.sensor import MysaZoneSensor

        await mock_coordinator.async_refresh()

        entity = MysaZoneSensor(
            mock_coordinator,
            "device1",
            mock_device_data,
            mock_api,
        )

        value = entity.native_value

        assert value == "Living Room Zone"

    @pytest.mark.asyncio
    async def test_zone_sensor_device_info(
        self, hass, mock_coordinator, mock_device_data, mock_api
    ):
        """Test MysaZoneSensor device_info."""
        from custom_components.mysa.sensor import MysaZoneSensor

        await mock_coordinator.async_refresh()

        entity = MysaZoneSensor(
            mock_coordinator,
            "device1",
            mock_device_data,
            mock_api,
        )

        info = entity.device_info

        assert "identifiers" in info

    @pytest.mark.asyncio
    async def test_zone_sensor_extra_attributes(
        self, hass, mock_coordinator, mock_device_data, mock_api
    ):
        """Test MysaZoneSensor extra_state_attributes."""
        from custom_components.mysa.sensor import MysaZoneSensor

        await mock_coordinator.async_refresh()

        entity = MysaZoneSensor(
            mock_coordinator,
            "device1",
            mock_device_data,
            mock_api,
        )

        attrs = entity.extra_state_attributes

        assert "zone_id" in attrs


# ===========================================================================
# MysaSimulatedCurrentSensor Tests
# ===========================================================================


class TestMysaSimulatedCurrentSensor:
    """Test MysaSimulatedCurrentSensor."""

    @pytest.mark.asyncio
    async def test_simulated_current_init(
        self, hass, mock_coordinator, mock_lite_device_data, mock_entry
    ):
        """Test MysaSimulatedCurrentSensor initialization."""
        from custom_components.mysa.sensor import MysaSimulatedCurrentSensor

        await mock_coordinator.async_refresh()

        entity = MysaSimulatedCurrentSensor(
            mock_coordinator,
            "lite_device",
            mock_lite_device_data,
            15.0,  # estimated max current
            mock_entry,
        )

        assert entity._device_id == "lite_device"
        assert entity._estimated_max_current == 15.0
        assert "Estimated Current" in entity._attr_name

    @pytest.mark.asyncio
    async def test_simulated_current_value(
        self, hass, mock_coordinator, mock_lite_device_data, mock_entry
    ):
        """Test MysaSimulatedCurrentSensor native_value."""
        from custom_components.mysa.sensor import MysaSimulatedCurrentSensor

        await mock_coordinator.async_refresh()

        entity = MysaSimulatedCurrentSensor(
            mock_coordinator,
            "lite_device",
            mock_lite_device_data,
            15.0,
            mock_entry,
        )

        value = entity.native_value

        # Duty 75% * 15A = 11.25A
        assert value == 11.25

    @pytest.mark.asyncio
    async def test_simulated_current_device_info(
        self, hass, mock_coordinator, mock_lite_device_data, mock_entry
    ):
        """Test MysaSimulatedCurrentSensor device_info."""
        from custom_components.mysa.sensor import MysaSimulatedCurrentSensor

        await mock_coordinator.async_refresh()

        entity = MysaSimulatedCurrentSensor(
            mock_coordinator,
            "lite_device",
            mock_lite_device_data,
            15.0,
            mock_entry,
        )

        info = entity.device_info

        assert "identifiers" in info

    @pytest.mark.asyncio
    async def test_simulated_current_extra_attrs(
        self, hass, mock_coordinator, mock_lite_device_data, mock_entry
    ):
        """Test MysaSimulatedCurrentSensor extra_state_attributes."""
        from custom_components.mysa.sensor import MysaSimulatedCurrentSensor

        await mock_coordinator.async_refresh()

        entity = MysaSimulatedCurrentSensor(
            mock_coordinator,
            "lite_device",
            mock_lite_device_data,
            15.0,
            mock_entry,
        )

        attrs = entity.extra_state_attributes

        assert "estimated_max_current" in attrs
        assert attrs["estimated_max_current"] == 15.0


# ===========================================================================
# MysaSimulatedPowerSensor Tests
# ===========================================================================


class TestMysaSimulatedPowerSensor:
    """Test MysaSimulatedPowerSensor."""

    @pytest.mark.asyncio
    async def test_simulated_power_init(
        self, hass, mock_coordinator, mock_lite_device_data, mock_entry
    ):
        """Test MysaSimulatedPowerSensor initialization."""
        from custom_components.mysa.sensor import MysaSimulatedPowerSensor

        await mock_coordinator.async_refresh()

        entity = MysaSimulatedPowerSensor(
            mock_coordinator,
            "lite_device",
            mock_lite_device_data,
            15.0,
            mock_entry,
        )

        assert entity._device_id == "lite_device"
        assert "Estimated Power" in entity._attr_name

    @pytest.mark.asyncio
    async def test_simulated_power_value(
        self, hass, mock_coordinator, mock_lite_device_data, mock_entry
    ):
        """Test MysaSimulatedPowerSensor native_value."""
        from custom_components.mysa.sensor import MysaSimulatedPowerSensor

        await mock_coordinator.async_refresh()

        entity = MysaSimulatedPowerSensor(
            mock_coordinator,
            "lite_device",
            mock_lite_device_data,
            15.0,
            mock_entry,
        )

        value = entity.native_value

        # Duty 75% * 15A * 240V = 2700W
        assert value == 2700.0

    @pytest.mark.asyncio
    async def test_simulated_power_device_info(
        self, hass, mock_coordinator, mock_lite_device_data, mock_entry
    ):
        """Test MysaSimulatedPowerSensor device_info."""
        from custom_components.mysa.sensor import MysaSimulatedPowerSensor

        await mock_coordinator.async_refresh()

        entity = MysaSimulatedPowerSensor(
            mock_coordinator,
            "lite_device",
            mock_lite_device_data,
            15.0,
            mock_entry,
        )

        info = entity.device_info

        assert "identifiers" in info

    @pytest.mark.asyncio
    async def test_simulated_power_extra_attrs(
        self, hass, mock_coordinator, mock_lite_device_data, mock_entry
    ):
        """Test MysaSimulatedPowerSensor extra_state_attributes."""
        from custom_components.mysa.sensor import MysaSimulatedPowerSensor

        await mock_coordinator.async_refresh()

        entity = MysaSimulatedPowerSensor(
            mock_coordinator,
            "lite_device",
            mock_lite_device_data,
            15.0,
            mock_entry,
        )

        attrs = entity.extra_state_attributes

        assert "estimated_max_current" in attrs
        assert "assumed_voltage" in attrs


# ===========================================================================
# Helper Method Tests
# ===========================================================================


class TestSensorHelperMethods:
    """Test sensor helper methods."""

    @pytest.fixture
    def sensor_entity(self, hass, mock_coordinator, mock_device_data, mock_entry):
        """Create a sensor entity."""
        from custom_components.mysa.sensor import MysaDiagnosticSensor

        return MysaDiagnosticSensor(
            mock_coordinator,
            "device1",
            mock_device_data,
            "Rssi",
            "RSSI",
            None,
            None,
            None,
            mock_entry,
        )

    @pytest.mark.asyncio
    async def test_extract_value_direct(self, hass, mock_coordinator, sensor_entity):
        """Test _extract_value with direct value."""
        await mock_coordinator.async_refresh()

        state = {"rssi": -70}
        value = sensor_entity._extract_value(state, ["rssi"])

        assert value == -70

    @pytest.mark.asyncio
    async def test_extract_value_dict(self, hass, mock_coordinator, sensor_entity):
        """Test _extract_value with dict containing v."""
        await mock_coordinator.async_refresh()

        state = {"Rssi": {"v": -65}}
        value = sensor_entity._extract_value(state, ["Rssi"])

        assert value == -65

    @pytest.mark.asyncio
    async def test_extract_value_fallback(self, hass, mock_coordinator, sensor_entity):
        """Test _extract_value fallback to second key."""
        await mock_coordinator.async_refresh()

        state = {"RSSI": -60}
        value = sensor_entity._extract_value(state, ["rssi", "Rssi", "RSSI"])

        assert value == -60


class TestSensorSetup:
    """Test sensor.py async_setup_entry."""

    @pytest.mark.asyncio
    async def test_async_setup_entry_creates_sensors(
        self, hass, mock_coordinator, mock_api, mock_entry
    ):
        """Test setup creates sensors for all devices."""
        from custom_components.mysa.sensor import async_setup_entry

        await mock_coordinator.async_refresh()

        hass.data[DOMAIN] = {
            "test_entry_id": {"coordinator": mock_coordinator, "api": mock_api}
        }

        entities = []
        async_add_entities = MagicMock(side_effect=lambda e: entities.extend(e))

        await async_setup_entry(hass, mock_entry, async_add_entities)

        assert async_add_entities.called
        # Many sensors created for each device
        assert len(entities) > 10

    @pytest.mark.asyncio
    async def test_async_setup_entry_no_data(self, hass, mock_entry):
        """Test setup handles missing data gracefully."""
        from custom_components.mysa.sensor import async_setup_entry

        hass.data[DOMAIN] = {}  # No entry data

        async_add_entities = MagicMock()

        # Should not raise, just log error and return
        await async_setup_entry(hass, mock_entry, async_add_entities)

        # async_add_entities should NOT be called
        assert not async_add_entities.called

    @pytest.mark.asyncio
    async def test_async_setup_entry_heating_sensors(
        self, hass, mock_coordinator, mock_entry
    ):
        """Test setup creates heating-specific sensors."""
        from custom_components.mysa.sensor import (
            async_setup_entry,
            MysaDiagnosticSensor,
        )

        await mock_coordinator.async_refresh()

        mock_api = MagicMock()
        mock_api.get_devices = AsyncMock(
            return_value={
                "device1": {"Id": "device1", "Name": "Heater", "Model": "BB-V2"}
            }
        )
        mock_api.is_ac_device = MagicMock(return_value=False)

        hass.data[DOMAIN] = {
            "test_entry_id": {"coordinator": mock_coordinator, "api": mock_api}
        }

        entities = []
        async_add_entities = MagicMock(side_effect=lambda e: entities.extend(e))

        await async_setup_entry(hass, mock_entry, async_add_entities)

        # Should include heating sensors like Duty, Voltage, Current, HeatSink, Infloor
        sensor_keys = [e._sensor_key for e in entities if hasattr(e, "_sensor_key")]
        assert "Duty" in sensor_keys
        assert "MaxCurrent" in sensor_keys

    @pytest.mark.asyncio
    async def test_async_setup_entry_heatsink_infloor_current(self, hass, mock_entry):
        """Test setup creates HeatSink, Infloor, and Current sensors when keys are in state."""
        from custom_components.mysa.sensor import async_setup_entry

        # Create coordinator with HeatSink, Infloor, Current in state
        async def async_update():
            return {
                "device1": {
                    "HeatSink": 45.0,
                    "Infloor": 28.0,
                    "Current": 10.5,
                    "Voltage": 240,
                }
            }

        coordinator = DataUpdateCoordinator(
            hass, MagicMock(), name="test", update_method=async_update, config_entry=MagicMock(entry_id="test")
        )
        await coordinator.async_refresh()

        mock_api = MagicMock()
        mock_api.get_devices = AsyncMock(
            return_value={
                "device1": {"Id": "device1", "Name": "Heater", "Model": "BB-V2"}
            }
        )
        mock_api.is_ac_device = MagicMock(return_value=False)

        hass.data[DOMAIN] = {
            "test_entry_id": {"coordinator": coordinator, "api": mock_api}
        }

        entities = []
        async_add_entities = MagicMock(side_effect=lambda e: entities.extend(e))

        await async_setup_entry(hass, mock_entry, async_add_entities)

        # Should include HeatSink, Infloor, Current sensors (lines 73, 77, 83)
        sensor_keys = [e._sensor_key for e in entities if hasattr(e, "_sensor_key")]
        assert "HeatSink" in sensor_keys
        assert "Infloor" in sensor_keys
        assert "Current" in sensor_keys

    @pytest.mark.asyncio
    async def test_async_setup_entry_lite_simulated_sensors(
        self, hass, mock_coordinator, mock_entry
    ):
        """Test setup creates simulated sensors for Lite devices."""
        from custom_components.mysa.sensor import (
            async_setup_entry,
            MysaSimulatedCurrentSensor,
            MysaSimulatedPowerSensor,
        )

        mock_entry.options = {
            "upgraded_lite_devices": ["lite_device"],
            "estimated_max_current": 15.0,
        }

        await mock_coordinator.async_refresh()

        mock_api = MagicMock()
        mock_api.get_devices = AsyncMock(
            return_value={
                "lite_device": {
                    "Id": "lite_device",
                    "Name": "Lite",
                    "Model": "BB-V2-0-L",
                }
            }
        )
        mock_api.is_ac_device = MagicMock(return_value=False)

        hass.data[DOMAIN] = {
            "test_entry_id": {"coordinator": mock_coordinator, "api": mock_api}
        }

        entities = []
        async_add_entities = MagicMock(side_effect=lambda e: entities.extend(e))

        await async_setup_entry(hass, mock_entry, async_add_entities)

        # Should include simulated current and power sensors
        entity_types = [type(e).__name__ for e in entities]
        assert "MysaSimulatedCurrentSensor" in entity_types
        assert "MysaSimulatedPowerSensor" in entity_types

    @pytest.mark.asyncio
    async def test_async_setup_entry_ac_skips_heating_sensors(
        self, hass, mock_coordinator, mock_entry
    ):
        """Test setup skips heating sensors for AC devices."""
        from custom_components.mysa.sensor import async_setup_entry

        await mock_coordinator.async_refresh()

        mock_api = MagicMock()
        mock_api.get_devices = AsyncMock(
            return_value={
                "ac_device": {"Id": "ac_device", "Name": "AC", "Model": "AC-V1"}
            }
        )
        mock_api.is_ac_device = MagicMock(return_value=True)

        hass.data[DOMAIN] = {
            "test_entry_id": {"coordinator": mock_coordinator, "api": mock_api}
        }

        entities = []
        async_add_entities = MagicMock(side_effect=lambda e: entities.extend(e))

        await async_setup_entry(hass, mock_entry, async_add_entities)

        # Should NOT include heating-only sensors
        sensor_keys = [e._sensor_key for e in entities if hasattr(e, "_sensor_key")]
        assert "Duty" not in sensor_keys
        assert "MaxCurrent" not in sensor_keys
        assert "HeatSink" not in sensor_keys


class TestSensorEdgeCases:
    """Test sensor entity edge cases."""

    @pytest.mark.asyncio
    async def test_zone_sensor_no_zone(self, hass, mock_entry):
        """Test zone sensor when zone is None."""
        from custom_components.mysa.sensor import MysaZoneSensor

        async def async_update():
            return {"device1": {}}  # No Zone key

        coordinator = DataUpdateCoordinator(
            hass, MagicMock(), name="test", update_method=async_update, config_entry=mock_entry
        )
        await coordinator.async_refresh()

        mock_api = MagicMock()
        mock_api.get_zone_name = MagicMock(return_value=None)

        device_data = {"Id": "device1", "Name": "Test", "Model": "BB-V2"}
        entity = MysaZoneSensor(coordinator, "device1", device_data, mock_api)

        # Should return None or "Unassigned"
        value = entity.native_value
        assert value is None or value == "Unassigned"

    @pytest.mark.asyncio
    async def test_diagnostic_sensor_duty_normalization(self, hass, mock_entry):
        """Test duty cycle normalization from 0-1 to 0-100."""
        from custom_components.mysa.sensor import MysaDiagnosticSensor

        async def async_update():
            return {"device1": {"Duty": 0.5}}  # 0-1 range

        coordinator = DataUpdateCoordinator(
            hass, MagicMock(), name="test", update_method=async_update, config_entry=mock_entry
        )
        await coordinator.async_refresh()

        device_data = {"Id": "device1", "Name": "Test", "Model": "BB-V2"}
        entity = MysaDiagnosticSensor(
            coordinator,
            "device1",
            device_data,
            "Duty",
            "Duty Cycle",
            "%",
            None,
            None,
            mock_entry,
        )

        # Should normalize 0.5 to 50.0
        assert entity.native_value == 50.0

    @pytest.mark.asyncio
    async def test_simulated_current_calculation(self, hass, mock_entry):
        """Test simulated current sensor calculation."""
        from custom_components.mysa.sensor import MysaSimulatedCurrentSensor

        async def async_update():
            return {"device1": {"Duty": 50}}  # 50% duty cycle

        coordinator = DataUpdateCoordinator(
            hass, MagicMock(), name="test", update_method=async_update, config_entry=mock_entry
        )
        await coordinator.async_refresh()

        device_data = {"Id": "device1", "Name": "Test", "Model": "BB-V2-L"}
        entity = MysaSimulatedCurrentSensor(
            coordinator, "device1", device_data, 15.0, mock_entry
        )

        # 50% of 15A = 7.5A
        assert entity.native_value == 7.5

    @pytest.mark.asyncio
    async def test_simulated_power_calculation(self, hass, mock_entry):
        """Test simulated power sensor calculation."""
        from custom_components.mysa.sensor import MysaSimulatedPowerSensor

        async def async_update():
            return {"device1": {"Duty": 100}}  # 100% duty cycle

        coordinator = DataUpdateCoordinator(
            hass, MagicMock(), name="test", update_method=async_update, config_entry=mock_entry
        )
        await coordinator.async_refresh()

        device_data = {"Id": "device1", "Name": "Test", "Model": "BB-V2-L"}
        entity = MysaSimulatedPowerSensor(
            coordinator, "device1", device_data, 15.0, mock_entry
        )

        # 100% * 15A * 240V = 3600W
        assert entity.native_value == 3600.0


# ===========================================================================
class TestSensorFinalEdgeCases:
    """Final edge cases for sensor.py."""

    @pytest.mark.asyncio
    async def test_diagnostic_sensor_zone_name_present(self, hass, mock_entry):
        """Test device_info includes zone_name when configured."""
        from custom_components.mysa.sensor import MysaDiagnosticSensor

        async def async_update():
            return {"device1": {"Zone": "zone123", "Rssi": -65}}

        entry = MagicMock()
        entry.entry_id = "test"
        entry.options = {"zone_name_zone123": "Kitchen"}

        coordinator = DataUpdateCoordinator(
            hass, MagicMock(), name="test", update_method=async_update, config_entry=entry
        )
        await coordinator.async_refresh()

        device_data = {"Id": "device1", "Name": "Test", "Model": "BB-V2"}
        entity = MysaDiagnosticSensor(
            coordinator,
            "device1",
            device_data,
            "Rssi",
            "RSSI",
            "dBm",
            None,
            None,
            entry,
        )

        info = entity.device_info
        assert info.get("suggested_area") == "Kitchen"

    @pytest.mark.asyncio
    async def test_diagnostic_sensor_no_state(self, hass, mock_entry):
        """Test native_value returns None when no state."""
        from custom_components.mysa.sensor import MysaDiagnosticSensor

        async def async_update():
            return {}  # No device state

        coordinator = DataUpdateCoordinator(
            hass, MagicMock(), name="test", update_method=async_update, config_entry=mock_entry
        )
        await coordinator.async_refresh()

        device_data = {"Id": "device1", "Name": "Test", "Model": "BB-V2"}
        entity = MysaDiagnosticSensor(
            coordinator,
            "device1",
            device_data,
            "Rssi",
            "RSSI",
            "dBm",
            None,
            None,
            mock_entry,
        )

        # Line 161
        assert entity.native_value is None

    @pytest.mark.asyncio
    async def test_diagnostic_sensor_value_error(self, hass, mock_entry):
        """Test native_value handles non-numeric values."""
        from custom_components.mysa.sensor import MysaDiagnosticSensor

        async def async_update():
            return {"device1": {"TimeZone": "America/Toronto"}}  # String value

        coordinator = DataUpdateCoordinator(
            hass, MagicMock(), name="test", update_method=async_update, config_entry=mock_entry
        )
        await coordinator.async_refresh()

        device_data = {"Id": "device1", "Name": "Test", "Model": "BB-V2"}
        entity = MysaDiagnosticSensor(
            coordinator,
            "device1",
            device_data,
            "TimeZone",
            "Time Zone",
            None,
            None,
            None,
            mock_entry,
        )

        # Should return string (line 196)
        assert entity.native_value == "America/Toronto"

    @pytest.mark.asyncio
    async def test_extract_value_dict_id_fallback(self, hass, mock_entry):
        """Test _extract_value falls back to 'Id' key in dict."""
        from custom_components.mysa.sensor import MysaDiagnosticSensor

        async def async_update():
            return {"device1": {"Zone": {"Id": "zone_id_123"}}}  # Dict with Id, no v

        coordinator = DataUpdateCoordinator(
            hass, MagicMock(), name="test", update_method=async_update, config_entry=mock_entry
        )
        await coordinator.async_refresh()

        device_data = {"Id": "device1", "Name": "Test", "Model": "BB-V2"}
        entity = MysaDiagnosticSensor(
            coordinator,
            "device1",
            device_data,
            "Zone",
            "Zone",
            None,
            None,
            None,
            mock_entry,
        )

        state = coordinator.data.get("device1")
        val = entity._extract_value(state, ["Zone"])
        assert val == "zone_id_123"

    @pytest.mark.asyncio
    async def test_extract_value_none_fallback(self, hass, mock_entry):
        """Test _extract_value returns None when key not found."""
        from custom_components.mysa.sensor import MysaDiagnosticSensor

        async def async_update():
            return {"device1": {"SomeOther": 123}}

        coordinator = DataUpdateCoordinator(
            hass, MagicMock(), name="test", update_method=async_update, config_entry=mock_entry
        )
        await coordinator.async_refresh()

        device_data = {"Id": "device1", "Name": "Test", "Model": "BB-V2"}
        entity = MysaDiagnosticSensor(
            coordinator,
            "device1",
            device_data,
            "Rssi",
            "RSSI",
            "dBm",
            None,
            None,
            mock_entry,
        )

        state = coordinator.data.get("device1")
        val = entity._extract_value(state, ["NonExistent"])
        assert val is None

    @pytest.mark.asyncio
    async def test_zone_sensor_no_zone_id(self, hass, mock_api):
        """Test zone sensor returns Unassigned when no zone_id."""
        from custom_components.mysa.sensor import MysaZoneSensor

        async def async_update():
            return {"device1": {"SomeOther": 123}}  # No Zone key

        coordinator = DataUpdateCoordinator(
            hass, MagicMock(), name="test", update_method=async_update, config_entry=MagicMock(entry_id="test")
        )
        await coordinator.async_refresh()

        device_data = {"Id": "device1", "Name": "Test", "Model": "BB-V2"}
        entity = MysaZoneSensor(coordinator, "device1", device_data, mock_api)

        # Line 257
        assert entity.native_value == "Unassigned"

    @pytest.mark.asyncio
    async def test_simulated_current_no_duty(self, hass, mock_entry):
        """Test simulated current returns 0 when no duty cycle."""
        from custom_components.mysa.sensor import MysaSimulatedCurrentSensor

        async def async_update():
            return {"device1": {"SomeOther": 123}}  # No duty

        coordinator = DataUpdateCoordinator(
            hass, MagicMock(), name="test", update_method=async_update, config_entry=mock_entry
        )
        await coordinator.async_refresh()

        device_data = {"Id": "device1", "Name": "Test", "Model": "BB-V2-L"}
        entity = MysaSimulatedCurrentSensor(
            coordinator, "device1", device_data, 15.0, mock_entry
        )

        # Line 318
        assert entity.native_value == 0.0

    @pytest.mark.asyncio
    async def test_simulated_current_dict_value(self, hass, mock_entry):
        """Test simulated current extracts from dict with 'v' key."""
        from custom_components.mysa.sensor import MysaSimulatedCurrentSensor

        async def async_update():
            return {"device1": {"Duty": {"v": 0.5}}}  # Dict format

        coordinator = DataUpdateCoordinator(
            hass, MagicMock(), name="test", update_method=async_update, config_entry=mock_entry
        )
        await coordinator.async_refresh()

        device_data = {"Id": "device1", "Name": "Test", "Model": "BB-V2-L"}
        entity = MysaSimulatedCurrentSensor(
            coordinator, "device1", device_data, 15.0, mock_entry
        )

        # 50% of 15A = 7.5A (line 312)
        assert entity.native_value == 7.5

    @pytest.mark.asyncio
    async def test_simulated_power_no_state(self, hass, mock_entry):
        """Test simulated power returns None when no state."""
        from custom_components.mysa.sensor import MysaSimulatedPowerSensor

        async def async_update():
            return {}  # No device state

        coordinator = DataUpdateCoordinator(
            hass, MagicMock(), name="test", update_method=async_update, config_entry=mock_entry
        )
        await coordinator.async_refresh()

        device_data = {"Id": "device1", "Name": "Test", "Model": "BB-V2-L"}
        entity = MysaSimulatedPowerSensor(
            coordinator, "device1", device_data, 15.0, mock_entry
        )

        # Line 366
        assert entity.native_value is None

    @pytest.mark.asyncio
    async def test_simulated_power_no_duty(self, hass, mock_entry):
        """Test simulated power returns 0 when no duty cycle."""
        from custom_components.mysa.sensor import MysaSimulatedPowerSensor

        async def async_update():
            return {"device1": {"SomeOther": 123}}  # No duty

        coordinator = DataUpdateCoordinator(
            hass, MagicMock(), name="test", update_method=async_update, config_entry=mock_entry
        )
        await coordinator.async_refresh()

        device_data = {"Id": "device1", "Name": "Test", "Model": "BB-V2-L"}
        entity = MysaSimulatedPowerSensor(
            coordinator, "device1", device_data, 15.0, mock_entry
        )

        # Line 380
        assert entity.native_value == 0.0

    @pytest.mark.asyncio
    async def test_simulated_power_dict_voltage(self, hass, mock_entry):
        """Test simulated power extracts voltage from dict."""
        from custom_components.mysa.sensor import MysaSimulatedPowerSensor

        async def async_update():
            return {
                "device1": {"Duty": 50, "Voltage": {"v": 220}}
            }  # Dict format voltage

        coordinator = DataUpdateCoordinator(
            hass, MagicMock(), name="test", update_method=async_update, config_entry=mock_entry
        )
        await coordinator.async_refresh()

        device_data = {"Id": "device1", "Name": "Test", "Model": "BB-V2-L"}
        entity = MysaSimulatedPowerSensor(
            coordinator, "device1", device_data, 15.0, mock_entry
        )

        # 50% of 15A * 220V = 1650W (line 392)
        assert entity.native_value == 1650.0


# ===========================================================================
# Final Coverage Tests
# ===========================================================================


class TestSensorFinalCoverage:
    """Final tests to ensure 100% coverage."""

    @pytest.mark.asyncio
    async def test_diagnostic_sensor_value_error_exception(self, hass, mock_entry):
        """Test native_value returns str when float conversion fails (lines 204-205)."""
        from custom_components.mysa.sensor import MysaDiagnosticSensor

        async def async_update():
            return {
                "device1": {"CustomKey": [1, 2, 3]}
            }  # List cannot be converted to float

        coordinator = DataUpdateCoordinator(
            hass, MagicMock(), name="test", update_method=async_update, config_entry=mock_entry
        )
        await coordinator.async_refresh()

        device_data = {"Id": "device1", "Name": "Test", "Model": "BB-V2"}
        entity = MysaDiagnosticSensor(
            coordinator,
            "device1",
            device_data,
            "CustomKey",
            "Custom",
            None,
            None,
            None,
            mock_entry,
        )

        # Should return string representation (line 205)
        result = entity.native_value
        assert result == "[1, 2, 3]"

    @pytest.mark.asyncio
    async def test_simulated_current_no_state(self, hass, mock_entry):
        """Test simulated current returns None when no state (line 304)."""
        from custom_components.mysa.sensor import MysaSimulatedCurrentSensor

        async def async_update():
            return {}  # No device state at all

        coordinator = DataUpdateCoordinator(
            hass, MagicMock(), name="test", update_method=async_update, config_entry=mock_entry
        )
        await coordinator.async_refresh()

        device_data = {"Id": "device1", "Name": "Test", "Model": "BB-V2-L"}
        entity = MysaSimulatedCurrentSensor(
            coordinator, "device1", device_data, 15.0, mock_entry
        )

        # Line 304: return None when no state
        assert entity.native_value is None

    @pytest.mark.asyncio
    async def test_simulated_power_dict_duty(self, hass, mock_entry):
        """Test simulated power extracts duty from dict format (line 374)."""
        from custom_components.mysa.sensor import MysaSimulatedPowerSensor

        async def async_update():
            return {"device1": {"Duty": {"v": 0.5}}}  # Dict format with 'v' key

        coordinator = DataUpdateCoordinator(
            hass, MagicMock(), name="test", update_method=async_update, config_entry=mock_entry
        )
        await coordinator.async_refresh()

        device_data = {"Id": "device1", "Name": "Test", "Model": "BB-V2-L"}
        entity = MysaSimulatedPowerSensor(
            coordinator, "device1", device_data, 15.0, mock_entry
        )

        # 50% duty * 15A * 240V = 1800W (line 374)
        assert entity.native_value == 1800.0

    @pytest.mark.asyncio
    async def test_diagnostic_sensor_key_not_found(self, hass, mock_entry):
        """Test native_value returns None when sensor key not in state (line 206)."""
        from custom_components.mysa.sensor import MysaDiagnosticSensor

        async def async_update():
            return {
                "device1": {"OtherKey": 123}
            }  # State exists but sensor key not found

        coordinator = DataUpdateCoordinator(
            hass, MagicMock(), name="test", update_method=async_update, config_entry=mock_entry
        )
        await coordinator.async_refresh()

        device_data = {"Id": "device1", "Name": "Test", "Model": "BB-V2"}
        entity = MysaDiagnosticSensor(
            coordinator,
            "device1",
            device_data,
            "Rssi",
            "RSSI",
            None,
            None,
            None,
            mock_entry,
        )

        # Line 206: return None when key not found
        assert entity.native_value is None
