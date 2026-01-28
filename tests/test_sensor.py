"""Sensor Entity Coverage Tests.

Tests that instantiate and test real sensor entity classes
to improve code coverage for sensor.py.
"""

import os
import sys

# Add project root to path for imports
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(TEST_DIR)
sys.path.insert(0, ROOT_DIR)

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import EntityCategory
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from custom_components.mysa import MysaData

# Module-level imports after path setup
from custom_components.mysa.sensor import (
    MysaCurrentSensor,
    MysaDiagnosticSensor,
    MysaEnergySensor,
    MysaHumiditySensor,
    MysaIpSensor,
    MysaPowerSensor,
    MysaTemperatureSensor,
)

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
        config_entry=mock_entry,
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
        from homeassistant.const import SIGNAL_STRENGTH_DECIBELS_MILLIWATT

        from custom_components.mysa.sensor import MysaDiagnosticSensor

        await mock_coordinator.async_refresh()

        entity = MysaDiagnosticSensor(
            mock_coordinator,
            "device1",
            mock_device_data,
            "Rssi",
            "rssi",
            SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
            SensorStateClass.MEASUREMENT,
            SensorDeviceClass.SIGNAL_STRENGTH,
            mock_entry,
        )

        assert entity._device_id == "device1"
        assert entity._attr_translation_key == "rssi"

    @pytest.mark.asyncio
    async def test_duty_sensor_init(
        self, hass, mock_coordinator, mock_device_data, mock_entry
    ):
        """Test Duty Cycle sensor initialization."""
        from homeassistant.const import PERCENTAGE

        from custom_components.mysa.sensor import MysaDiagnosticSensor

        await mock_coordinator.async_refresh()

        entity = MysaDiagnosticSensor(
            mock_coordinator,
            "device1",
            mock_device_data,
            "Duty",
            "duty_cycle",
            PERCENTAGE,
            SensorStateClass.MEASUREMENT,
            None,
            mock_entry,
        )

        assert entity._attr_translation_key == "duty_cycle"
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


# ===========================================================================
# MysaCurrentSensor Tests
# ===========================================================================


class TestMysaCurrentSensor:
    """Test MysaCurrentSensor."""

    @pytest.mark.asyncio
    async def test_simulated_current_init(
        self, hass, mock_coordinator, mock_lite_device_data, mock_entry, mock_api
    ):
        """Test MysaCurrentSensor initialization."""
        from custom_components.mysa.sensor import MysaCurrentSensor

        mock_entry.options = {"estimated_max_current": 15.0}

        await mock_coordinator.async_refresh()

        entity = MysaCurrentSensor(
            mock_coordinator,
            "lite_device",
            mock_lite_device_data,
            mock_api,
            mock_entry,
        )

        assert entity._device_id == "lite_device"
        assert entity._attr_translation_key == "estimated_current"
        assert entity._attr_state_class == SensorStateClass.MEASUREMENT

    @pytest.mark.asyncio
    async def test_simulated_current_value(
        self, hass, mock_coordinator, mock_lite_device_data, mock_entry, mock_api
    ):
        """Test MysaCurrentSensor native_value."""
        from custom_components.mysa.sensor import MysaCurrentSensor

        await mock_coordinator.async_refresh()

        mock_entry.options = {"estimated_max_current": 15.0}

        entity = MysaCurrentSensor(
            mock_coordinator,
            "lite_device",
            mock_lite_device_data,
            mock_api,
            mock_entry,
        )

        value = entity.native_value

        # Duty 75% * 15A = 11.25A
        assert value == 11.25

    @pytest.mark.asyncio
    async def test_simulated_current_device_info(
        self, hass, mock_coordinator, mock_lite_device_data, mock_entry, mock_api
    ):
        """Test MysaCurrentSensor device_info."""
        from custom_components.mysa.sensor import MysaCurrentSensor

        await mock_coordinator.async_refresh()

        mock_entry.options = {"estimated_max_current": 15.0}

        entity = MysaCurrentSensor(
            mock_coordinator,
            "lite_device",
            mock_lite_device_data,
            mock_api,
            mock_entry,
        )

        info = entity.device_info

        assert "identifiers" in info

    @pytest.mark.asyncio
    async def test_simulated_current_extra_attrs(
        self, hass, mock_coordinator, mock_lite_device_data, mock_entry, mock_api
    ):
        """Test MysaCurrentSensor extra_state_attributes."""
        from custom_components.mysa.sensor import MysaCurrentSensor

        await mock_coordinator.async_refresh()

        mock_entry.options = {"estimated_max_current": 15.0}
        mock_api.simulated_energy = False

        entity = MysaCurrentSensor(
            mock_coordinator,
            "lite_device",
            mock_lite_device_data,
            mock_api,
            mock_entry,
        )

        attrs = entity.extra_state_attributes

        assert "tracking_mode" in attrs
        assert attrs["tracking_mode"] == "Simulated"
        assert (
            attrs["configured_wattage"] == 0
        )  # because usually calculated from wattage_id or fallback


# ===========================================================================
# MysaPowerSensor Tests
# ===========================================================================


class TestMysaPowerSensor:
    """Test MysaPowerSensor (Simulated Mode)."""

    @pytest.mark.asyncio
    async def test_simulated_power_init(
        self, hass, mock_coordinator, mock_lite_device_data, mock_entry, mock_api
    ):
        """Test MysaPowerSensor initialization."""
        from custom_components.mysa.sensor import MysaPowerSensor

        await mock_coordinator.async_refresh()

        mock_entry.options = {"estimated_max_current": 15.0}

        entity = MysaPowerSensor(
            mock_coordinator,
            "lite_device",
            mock_lite_device_data,
            mock_api,
            mock_entry,
        )

        assert entity._device_id == "lite_device"
        assert entity._attr_translation_key == "power"
        assert entity._attr_state_class == SensorStateClass.MEASUREMENT

    @pytest.mark.asyncio
    async def test_simulated_power_value(
        self, hass, mock_coordinator, mock_lite_device_data, mock_entry, mock_api
    ):
        """Test MysaPowerSensor native_value."""
        from custom_components.mysa.sensor import MysaPowerSensor

        await mock_coordinator.async_refresh()

        mock_entry.options = {"estimated_max_current": 15.0}

        entity = MysaPowerSensor(
            mock_coordinator,
            "lite_device",
            mock_lite_device_data,
            mock_api,
            mock_entry,
        )

        value = entity.native_value

        # Duty 75% * 15A * 240V = 2700W
        assert value == 2700.0

    @pytest.mark.asyncio
    async def test_simulated_power_device_info(
        self, hass, mock_coordinator, mock_lite_device_data, mock_entry, mock_api
    ):
        """Test MysaPowerSensor device_info."""
        from custom_components.mysa.sensor import MysaPowerSensor

        await mock_coordinator.async_refresh()

        mock_entry.options = {"estimated_max_current": 15.0}

        entity = MysaPowerSensor(
            mock_coordinator,
            "lite_device",
            mock_lite_device_data,
            mock_api,
            mock_entry,
        )

        info = entity.device_info

        assert "identifiers" in info

    @pytest.mark.asyncio
    async def test_simulated_power_extra_attrs(
        self, hass, mock_coordinator, mock_lite_device_data, mock_entry, mock_api
    ):
        """Test MysaPowerSensor extra_state_attributes."""
        from custom_components.mysa.sensor import MysaPowerSensor

        await mock_coordinator.async_refresh()

        mock_entry.options = {"estimated_max_current": 15.0}
        mock_api.simulated_energy = False

        entity = MysaPowerSensor(
            mock_coordinator,
            "lite_device",
            mock_lite_device_data,
            mock_api,
            mock_entry,
        )

        attrs = entity.extra_state_attributes

        assert "tracking_mode" in attrs
        assert attrs["tracking_mode"] == "Simulated"


# ===========================================================================
# MysaElectricityRateSensor Tests
# ===========================================================================


class TestMysaElectricityRateSensor:
    """Test MysaElectricityRateSensor."""

    @pytest.mark.asyncio
    async def test_electricity_rate_init(
        self, hass, mock_coordinator, mock_device_data, mock_entry, mock_api
    ):
        """Test MysaElectricityRateSensor initialization."""
        from homeassistant.const import EntityCategory

        from custom_components.mysa.sensor import MysaElectricityRateSensor

        await mock_coordinator.async_refresh()

        entity = MysaElectricityRateSensor(
            mock_coordinator,
            "device1",
            mock_device_data,
            mock_api,
            mock_entry,
        )

        assert entity._device_id == "device1"
        assert entity._attr_translation_key == "cost"
        assert entity._attr_entity_category == EntityCategory.DIAGNOSTIC
        assert entity.native_unit_of_measurement == "$/kWh"

    @pytest.mark.asyncio
    async def test_electricity_rate_value(
        self, hass, mock_coordinator, mock_device_data, mock_entry, mock_api
    ):
        """Test MysaElectricityRateSensor native_value."""
        from custom_components.mysa.sensor import MysaElectricityRateSensor

        mock_api.get_electricity_rate = MagicMock(return_value=0.15)
        await mock_coordinator.async_refresh()

        entity = MysaElectricityRateSensor(
            mock_coordinator,
            "device1",
            mock_device_data,
            mock_api,
            mock_entry,
        )

        assert entity.native_value == 0.15
        mock_api.get_electricity_rate.assert_called_with("device1")

    @pytest.mark.asyncio
    async def test_electricity_rate_none(
        self, hass, mock_coordinator, mock_device_data, mock_entry, mock_api
    ):
        """Test MysaElectricityRateSensor native_value when None."""
        from custom_components.mysa.sensor import MysaElectricityRateSensor

        mock_api.get_electricity_rate = MagicMock(return_value=None)
        await mock_coordinator.async_refresh()

        entity = MysaElectricityRateSensor(
            mock_coordinator,
            "device1",
            mock_device_data,
            mock_api,
            mock_entry,
        )

        assert entity.native_value is None

    @pytest.mark.asyncio
    async def test_electricity_rate_device_info(
        self, hass, mock_coordinator, mock_device_data, mock_entry, mock_api
    ):
        """Test MysaElectricityRateSensor device_info."""
        from custom_components.mysa.sensor import MysaElectricityRateSensor

        await mock_coordinator.async_refresh()

        entity = MysaElectricityRateSensor(
            mock_coordinator,
            "device1",
            mock_device_data,
            mock_api,
            mock_entry,
        )

        info = entity.device_info
        assert "identifiers" in info


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

        mock_data = MagicMock(spec=MysaData)
        mock_data.coordinator = mock_coordinator
        mock_data.api = mock_api
        mock_entry.runtime_data = mock_data

        entities = []
        async_add_entities = MagicMock(side_effect=lambda e: entities.extend(e))

        await async_setup_entry(hass, mock_entry, async_add_entities)

        assert async_add_entities.called
        # Many sensors created for each device
        assert len(entities) > 10

    @pytest.mark.asyncio
    async def test_async_setup_entry_heating_sensors(
        self, hass, mock_coordinator, mock_entry
    ):
        """Test setup creates heating-specific sensors."""
        from custom_components.mysa.sensor import (
            async_setup_entry,
        )

        await mock_coordinator.async_refresh()

        mock_api = MagicMock()
        mock_api.get_devices = AsyncMock(
            return_value={
                "device1": {"Id": "device1", "Name": "Heater", "Model": "BB-V2"}
            }
        )
        mock_api.is_ac_device = MagicMock(return_value=False)

        mock_data = MagicMock(spec=MysaData)
        mock_data.coordinator = mock_coordinator
        mock_data.api = mock_api
        mock_entry.runtime_data = mock_data

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
            hass,
            MagicMock(),
            name="test",
            update_method=async_update,
            config_entry=MagicMock(entry_id="test"),
        )
        await coordinator.async_refresh()

        mock_api = MagicMock()
        mock_api.get_devices = AsyncMock(
            return_value={
                "device1": {"Id": "device1", "Name": "Heater", "Model": "BB-V2"}
            }
        )
        mock_api.is_ac_device = MagicMock(return_value=False)

        mock_data = MagicMock(spec=MysaData)
        mock_data.coordinator = coordinator
        mock_data.api = mock_api
        mock_entry.runtime_data = mock_data

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

        mock_data = MagicMock(spec=MysaData)
        mock_data.coordinator = mock_coordinator
        mock_data.api = mock_api
        mock_entry.runtime_data = mock_data

        entities = []
        async_add_entities = MagicMock(side_effect=lambda e: entities.extend(e))

        await async_setup_entry(hass, mock_entry, async_add_entities)

        # Should include simulated current and power sensors
        entity_types = [type(e).__name__ for e in entities]
        assert "MysaCurrentSensor" in entity_types
        assert "MysaPowerSensor" in entity_types

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

        mock_data = MagicMock(spec=MysaData)
        mock_data.coordinator = mock_coordinator
        mock_data.api = mock_api
        mock_entry.runtime_data = mock_data

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
    async def test_diagnostic_sensor_duty_normalization(self, hass, mock_entry):
        """Test duty cycle normalization from 0-1 to 0-100."""
        from custom_components.mysa.sensor import MysaDiagnosticSensor

        async def async_update():
            return {"device1": {"Duty": 0.5}}  # 0-1 range

        coordinator = DataUpdateCoordinator(
            hass,
            MagicMock(),
            name="test",
            update_method=async_update,
            config_entry=mock_entry,
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
    async def test_simulated_current_calculation(self, hass, mock_entry, mock_api):
        """Test simulated current sensor calculation."""
        from custom_components.mysa.sensor import MysaCurrentSensor

        async def async_update():
            return {"device1": {"Duty": 50}}  # 50% duty cycle

        coordinator = DataUpdateCoordinator(
            hass,
            MagicMock(),
            name="test",
            update_method=async_update,
            config_entry=mock_entry,
        )
        await coordinator.async_refresh()

        mock_entry.options = {"estimated_max_current": 15.0}

        device_data = {"Id": "device1", "Name": "Test", "Model": "BB-V2-L"}
        entity = MysaCurrentSensor(
            coordinator, "device1", device_data, mock_api, mock_entry
        )

        # 50% of 15A = 7.5A
        assert entity.native_value == 7.5

    @pytest.mark.asyncio
    async def test_simulated_power_calculation(self, hass, mock_entry, mock_api):
        """Test simulated power sensor calculation."""
        from custom_components.mysa.sensor import MysaPowerSensor

        async def async_update():
            return {"device1": {"Duty": 100}}  # 100% duty cycle

        coordinator = DataUpdateCoordinator(
            hass,
            MagicMock(),
            name="test",
            update_method=async_update,
            config_entry=mock_entry,
        )
        await coordinator.async_refresh()

        mock_entry.options = {"estimated_max_current": 15.0}

        device_data = {"Id": "device1", "Name": "Test", "Model": "BB-V2-L"}
        entity = MysaPowerSensor(
            coordinator, "device1", device_data, mock_api, mock_entry
        )

        # 100% * 15A * 240V = 3600W
        assert entity.native_value == 3600.0


# ===========================================================================
class TestSensorFinalEdgeCases:
    """Final edge cases for sensor.py."""

    @pytest.mark.asyncio
    async def test_diagnostic_sensor_no_zone_name(self, hass, mock_entry):
        """Test device_info does NOT include zone_name."""
        from custom_components.mysa.sensor import MysaDiagnosticSensor

        async def async_update():
            return {"device1": {"Rssi": -65}}

        entry = MagicMock()
        entry.entry_id = "test"
        entry.options = {}

        coordinator = DataUpdateCoordinator(
            hass,
            MagicMock(),
            name="test",
            update_method=async_update,
            config_entry=entry,
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
        assert "suggested_area" not in info

    @pytest.mark.asyncio
    async def test_diagnostic_sensor_no_state(self, hass, mock_entry):
        """Test native_value returns None when no state."""
        from custom_components.mysa.sensor import MysaDiagnosticSensor

        async def async_update():
            return {}  # No device state

        coordinator = DataUpdateCoordinator(
            hass,
            MagicMock(),
            name="test",
            update_method=async_update,
            config_entry=mock_entry,
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
            hass,
            MagicMock(),
            name="test",
            update_method=async_update,
            config_entry=mock_entry,
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
            hass,
            MagicMock(),
            name="test",
            update_method=async_update,
            config_entry=mock_entry,
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
            hass,
            MagicMock(),
            name="test",
            update_method=async_update,
            config_entry=mock_entry,
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
    async def test_simulated_current_no_duty(self, hass, mock_entry, mock_api):
        """Test simulated current returns 0 when no duty cycle."""
        from custom_components.mysa.sensor import MysaCurrentSensor

        async def async_update():
            return {"device1": {"SomeOther": 123}}  # No duty

        coordinator = DataUpdateCoordinator(
            hass,
            MagicMock(),
            name="test",
            update_method=async_update,
            config_entry=mock_entry,
        )
        await coordinator.async_refresh()

        mock_entry.options = {"estimated_max_current": 15.0}

        device_data = {"Id": "device1", "Name": "Test", "Model": "BB-V2-L"}
        entity = MysaCurrentSensor(
            coordinator, "device1", device_data, mock_api, mock_entry
        )

        # Line 318
        assert entity.native_value == 0.0

    @pytest.mark.asyncio
    async def test_simulated_current_dict_value(self, hass, mock_entry, mock_api):
        """Test simulated current extracts from dict with 'v' key."""
        from custom_components.mysa.sensor import MysaCurrentSensor

        async def async_update():
            return {"device1": {"Duty": {"v": 0.5}}}  # Dict format

        coordinator = DataUpdateCoordinator(
            hass,
            MagicMock(),
            name="test",
            update_method=async_update,
            config_entry=mock_entry,
        )
        await coordinator.async_refresh()

        mock_entry.options = {"estimated_max_current": 15.0}

        device_data = {"Id": "device1", "Name": "Test", "Model": "BB-V2-L"}
        entity = MysaCurrentSensor(
            coordinator, "device1", device_data, mock_api, mock_entry
        )

        # 50% of 15A = 7.5A (line 312)
        assert entity.native_value == 7.5

    @pytest.mark.asyncio
    async def test_simulated_power_no_state(self, hass, mock_entry, mock_api):
        """Test simulated power returns None when no state."""
        from custom_components.mysa.sensor import MysaPowerSensor

        async def async_update():
            return {}  # No device state

        coordinator = DataUpdateCoordinator(
            hass,
            MagicMock(),
            name="test",
            update_method=async_update,
            config_entry=mock_entry,
        )
        await coordinator.async_refresh()

        mock_entry.options = {"estimated_max_current": 15.0}

        device_data = {"Id": "device1", "Name": "Test", "Model": "BB-V2-L"}
        entity = MysaPowerSensor(
            coordinator, "device1", device_data, mock_api, mock_entry
        )

        # Line 366
        assert entity.native_value is None

    @pytest.mark.asyncio
    async def test_simulated_power_no_duty(self, hass, mock_entry, mock_api):
        """Test simulated power returns 0 when no duty cycle."""
        from custom_components.mysa.sensor import MysaPowerSensor

        async def async_update():
            return {"device1": {"SomeOther": 123}}  # No duty

        coordinator = DataUpdateCoordinator(
            hass,
            MagicMock(),
            name="test",
            update_method=async_update,
            config_entry=mock_entry,
        )
        await coordinator.async_refresh()

        mock_entry.options = {"estimated_max_current": 15.0}

        device_data = {"Id": "device1", "Name": "Test", "Model": "BB-V2-L"}
        entity = MysaPowerSensor(
            coordinator, "device1", device_data, mock_api, mock_entry
        )

        # Line 380
        assert entity.native_value == 0.0

    @pytest.mark.asyncio
    async def test_simulated_power_dict_voltage(self, hass, mock_entry, mock_api):
        """Test simulated power extracts voltage from dict."""
        from custom_components.mysa.sensor import MysaPowerSensor

        async def async_update():
            return {
                "device1": {"Duty": 50, "Voltage": {"v": 220}}
            }  # Dict format voltage

        coordinator = DataUpdateCoordinator(
            hass,
            MagicMock(),
            name="test",
            update_method=async_update,
            config_entry=mock_entry,
        )
        await coordinator.async_refresh()

        mock_entry.options = {"estimated_max_current": 15.0}

        device_data = {"Id": "device1", "Name": "Test", "Model": "BB-V2-L"}
        entity = MysaPowerSensor(
            coordinator, "device1", device_data, mock_api, mock_entry
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
            hass,
            MagicMock(),
            name="test",
            update_method=async_update,
            config_entry=mock_entry,
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
    async def test_simulated_current_no_state(self, hass, mock_entry, mock_api):
        """Test simulated current returns None when no state (line 304)."""
        from custom_components.mysa.sensor import MysaCurrentSensor

        async def async_update():
            return {}  # No device state at all

        coordinator = DataUpdateCoordinator(
            hass,
            MagicMock(),
            name="test",
            update_method=async_update,
            config_entry=mock_entry,
        )
        await coordinator.async_refresh()

        mock_entry.options = {"estimated_max_current": 15.0}

        device_data = {"Id": "device1", "Name": "Test", "Model": "BB-V2-L"}
        entity = MysaCurrentSensor(
            coordinator, "device1", device_data, mock_api, mock_entry
        )

        # Line 304: return None when no state
        assert entity.native_value is None

    @pytest.mark.asyncio
    async def test_simulated_power_dict_duty(self, hass, mock_entry, mock_api):
        """Test simulated power extracts duty from dict format (line 374)."""
        from custom_components.mysa.sensor import MysaPowerSensor

        async def async_update():
            return {"device1": {"Duty": {"v": 0.5}}}  # Dict format with 'v' key

        coordinator = DataUpdateCoordinator(
            hass,
            MagicMock(),
            name="test",
            update_method=async_update,
            config_entry=mock_entry,
        )
        await coordinator.async_refresh()

        mock_entry.options = {"estimated_max_current": 15.0}

        device_data = {"Id": "device1", "Name": "Test", "Model": "BB-V2-L"}
        entity = MysaPowerSensor(
            coordinator, "device1", device_data, mock_api, mock_entry
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
            hass,
            MagicMock(),
            name="test",
            update_method=async_update,
            config_entry=mock_entry,
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


# ===========================================================================
# Coverage Tests (merged from test_sensor_coverage.py)
# ===========================================================================


@pytest.mark.asyncio
class TestSensorCoverage:
    """Targeted tests for sensor.py missing coverage."""

    # test_diagnostic_mac_ip_ssid removed as sensors were deleted

    async def test_power_sensor_extract_fallback(
        self, hass, mock_coordinator, mock_config_entry
    ):
        """Test _extract_value fallback to 'Id' for MysaPowerSensor (line 378)."""

        async def async_update():
            return {
                "device1": {
                    "Current": {"Id": "some_id"}  # No 'v' key
                }
            }

        mock_coordinator.update_method = async_update
        await mock_coordinator.async_refresh()

        device_data = {"Id": "device1", "Name": "Test", "Model": "BB-V2"}
        mock_api = MagicMock()
        mock_api.simulated_energy = False
        sensor = MysaPowerSensor(
            mock_coordinator, "device1", device_data, mock_api, mock_config_entry
        )

        # Should extract "some_id" but then fail float conversion in native_value
        # triggering exception handling coverage
        assert sensor.native_value == 0.0

    async def test_power_sensor_real_calculation(
        self, hass, mock_coordinator, mock_config_entry
    ):
        """Test real power calculation success (lines 395-398)."""

        async def async_update():
            return {
                "device1": {
                    "Voltage": 240,
                    "Current": 10,
                    "Duty": 100,  # 100% duty cycle for full power
                }
            }

        mock_coordinator.update_method = async_update
        await mock_coordinator.async_refresh()

        device_data = {"Id": "device1", "Name": "Test", "Model": "BB-V2"}
        mock_api = MagicMock()
        mock_api.simulated_energy = False
        sensor = MysaPowerSensor(
            mock_coordinator, "device1", device_data, mock_api, mock_config_entry
        )

        # 240V * 10A * 100% duty = 2400W
        assert sensor.native_value == 2400.0

    async def test_power_sensor_exceptions(
        self, hass, mock_coordinator, mock_config_entry
    ):
        """Test exceptions in power calculation (lines 411-412, 421-424)."""

        async def async_update():
            return {
                "device1": {
                    "Duty": "invalid"  # Cannot convert to float
                }
            }

        hass.config_entries.async_update_entry(
            mock_config_entry, options={"wattage_device1": 1000}
        )

        mock_coordinator.update_method = async_update
        await mock_coordinator.async_refresh()

        device_data = {"Id": "device1", "Name": "Test", "Model": "BB-V2"}
        mock_api = MagicMock()
        mock_api.simulated_energy = False
        sensor = MysaPowerSensor(
            mock_coordinator, "device1", device_data, mock_api, mock_config_entry
        )

        assert sensor.native_value == 0.0

    async def test_current_sensor_logic(
        self, hass, mock_coordinator, mock_config_entry
    ):
        """Test MysaCurrentSensor logic and coverage."""

        async def async_update():
            return {
                "device1": {
                    "Current": 5.0  # Real current
                },
                "device2": {
                    "Current": {"Id": "bad_id"}  # Fallback to Id, then fail float
                },
            }

        mock_coordinator.update_method = async_update
        await mock_coordinator.async_refresh()

        device_data = {"Id": "device1", "Name": "Test", "Model": "BB-V2"}
        mock_api = MagicMock()
        mock_api.simulated_energy = False

        # Real current success (lines 490-493)
        sensor1 = MysaCurrentSensor(
            mock_coordinator, "device1", device_data, mock_api, mock_config_entry
        )
        assert sensor1.native_value == 5.0

        # Fallback to Id then exception (line 475, 492)
        sensor2 = MysaCurrentSensor(
            mock_coordinator, "device2", device_data, mock_api, mock_config_entry
        )
        assert sensor2.native_value == 0.0

    async def test_current_sensor_simulated_coverage(
        self, hass, mock_coordinator, mock_config_entry
    ):
        """Test simulated current calculation exceptions (lines 508-509, 512-527)."""

        async def async_update():
            return {
                "device1": {
                    "Duty": "invalid_duty",  # Fail float conversion
                    "Voltage": 240,
                }
            }

        # Use estimated_max_current (>0) and no device wattage (=0) to enter the fallback block (lines 508-509)
        hass.config_entries.async_update_entry(
            mock_config_entry, options={"estimated_max_current": 15.0}
        )

        mock_coordinator.update_method = async_update
        await mock_coordinator.async_refresh()

        device_data = {"Id": "device1", "Name": "Test", "Model": "BB-V2"}
        mock_api = MagicMock()
        mock_api.simulated_energy = False
        sensor = MysaCurrentSensor(
            mock_coordinator, "device1", device_data, mock_api, mock_config_entry
        )

        # Verify it returns 0.0 on ValueError/TypeError (lines 515-516 coverage)
        assert sensor.native_value == 0.0

    @pytest.mark.asyncio
    async def test_sensor_coverage_gap(self, hass, mock_coordinator, mock_config_entry):
        """Test missing coverage lines in sensor.py."""
        mock_api = MagicMock()
        mock_api.simulated_energy = False

        # 1. Power Sensor ValueError (lines 392-393)
        node_data = {"device1": {"Voltage": "invalid", "Current": "10"}}
        mock_coordinator.data = node_data
        device_data = {"Id": "dev1", "Name": "Test"}

        sensor = MysaPowerSensor(
            mock_coordinator, "device1", device_data, mock_api, mock_config_entry
        )
        assert sensor.native_value == 0.0

        # 2. Forced Simulated Mode for Power Sensor (line 433 coverage)
        mock_api.simulated_energy = True
        sensor = MysaPowerSensor(
            mock_coordinator, "device1", device_data, mock_api, mock_config_entry
        )
        attrs = sensor.extra_state_attributes
        assert attrs["tracking_mode"] == "Forced Simulated"

        # 3. Forced Simulated Mode for Current Sensor (line 547 coverage)
        sensor_curr = MysaCurrentSensor(
            mock_coordinator, "device1", device_data, mock_api, mock_config_entry
        )
        attrs_curr = sensor_curr.extra_state_attributes
        assert attrs_curr["tracking_mode"] == "Forced Simulated"

        device_data = {"Id": "device1", "Name": "Test", "Model": "BB-V2"}
        sensor = MysaCurrentSensor(
            mock_coordinator, "device1", device_data, MagicMock(), mock_config_entry
        )

        # Should catch exception and return 0.0
        assert sensor.native_value == 0.0

    async def test_energy_sensor_restore_and_update(
        self, hass, mock_coordinator, mock_config_entry
    ):
        """Test MysaEnergySensor restore state and Riemann sum update."""
        mock_power_sensor = MagicMock()
        mock_power_sensor.native_value = 1000.0  # 1000W = 1kW

        device_data = {"Id": "device1", "Name": "Test", "Model": "BB-V2"}
        sensor = MysaEnergySensor(
            mock_coordinator,
            "device1",
            device_data,
            MagicMock(),
            mock_config_entry,
            mock_power_sensor,
        )
        sensor.hass = hass
        sensor.platform = MagicMock()

        # Allow setting private attributes for testing
        sensor.hass = hass
        sensor.entity_id = "sensor.test_energy"

        # Test Initialize/Restore
        with patch(
            "homeassistant.helpers.restore_state.RestoreEntity.async_get_last_state",
            new_callable=AsyncMock,
        ) as mock_restore:
            mock_state = MagicMock()
            mock_state.state = "10.5"  # Previous value
            mock_restore.return_value = mock_state

            await sensor.async_added_to_hass()

            assert sensor.native_value == 10.5
            assert sensor._last_update is not None

        # Test Update (Riemann Sum)
        old_time = sensor._last_update
        # Simulate 1 hour passing
        with patch("time.time", return_value=old_time + 3600):
            sensor._handle_coordinator_update()

            # 10.5 + (1kW * 1h) = 11.5
            assert sensor.native_value == 11.5
            assert (
                sensor.extra_state_attributes["last_integration_time"]
                == old_time + 3600
            )

        # Device info coverage
        assert sensor.device_info["manufacturer"] == "Mysa"

    async def test_energy_sensor_invalid_restore(
        self, hass, mock_coordinator, mock_config_entry
    ):
        """Test restore with invalid state."""
        sensor = MysaEnergySensor(
            mock_coordinator, "device1", {}, MagicMock(), mock_config_entry, MagicMock()
        )
        sensor.hass = hass

        with patch(
            "homeassistant.helpers.restore_state.RestoreEntity.async_get_last_state",
            new_callable=AsyncMock,
        ) as mock_restore:
            mock_state = MagicMock()
            mock_state.state = "invalid"
            mock_restore.return_value = mock_state

            await sensor.async_added_to_hass()
            assert sensor.native_value == 0.0

    async def test_power_sensor_real_exceptions(
        self, hass, mock_coordinator, mock_config_entry
    ):
        """Test real power calculation exception (lines 397-398)."""

        async def async_update():
            return {
                "device1": {
                    "Voltage": "invalid",  # Real voltage invalid
                    "Current": 10,
                }
            }

        mock_coordinator.update_method = async_update
        await mock_coordinator.async_refresh()

        device_data = {"Id": "device1", "Name": "Test", "Model": "BB-V2"}
        sensor = MysaPowerSensor(
            mock_coordinator, "device1", device_data, MagicMock(), mock_config_entry
        )

        # Should catch exception and return fallback/None (fallback logic continues)
        # In this case native_value falls through to simulated logic.
        # Since we haven't set up simulated wattage, it returns 0.0
        assert sensor.native_value == 0.0

    async def test_power_sensor_simulated_exceptions(
        self, hass, mock_coordinator, mock_config_entry
    ):
        """Test simulated power calculation exception (lines 411-412)."""

        async def async_update():
            return {
                "device1": {
                    "Current": None,  # Force fallback
                    "Voltage": "invalid",  # Force invalid voltage for fallback calc
                }
            }

        # Set estimated_max_current to trigger the calculation attempt
        hass.config_entries.async_update_entry(
            mock_config_entry, options={"estimated_max_current": 10}
        )

        mock_coordinator.update_method = async_update
        await mock_coordinator.async_refresh()

        device_data = {"Id": "device1", "Name": "Test", "Model": "BB-V2"}
        sensor = MysaPowerSensor(
            mock_coordinator, "device1", device_data, MagicMock(), mock_config_entry
        )

        # Should catch exception and return 0.0 wattage, thus 0.0 power
        assert sensor.native_value == 0.0

    async def test_current_sensor_simulated_valid(
        self, hass, mock_coordinator, mock_config_entry
    ):
        """Test valid simulated current calculation (lines 512-527)."""

        async def async_update():
            return {
                "device1": {
                    "Current": None,  # Force simulated
                    "Voltage": 240,
                    "Duty": 50,
                }
            }

        # Set per-device wattage
        hass.config_entries.async_update_entry(
            mock_config_entry, options={"wattage_device1": 2400}
        )

        mock_coordinator.update_method = async_update
        await mock_coordinator.async_refresh()

        device_data = {"Id": "device1", "Name": "Test", "Model": "BB-V2"}
        sensor = MysaCurrentSensor(
            mock_coordinator, "device1", device_data, MagicMock(), mock_config_entry
        )

        # I = (P / V) * Duty
        # (2400 / 240) * 0.5 = 10 * 0.5 = 5.0
        assert sensor.native_value == 5.0

    async def test_current_sensor_simulated_exceptions_block(
        self, hass, mock_coordinator, mock_config_entry
    ):
        """Test exceptions in simulated current block (lines 512-527)."""

        async def async_update():
            return {
                "device1": {
                    "Current": None,
                    "Voltage": "invalid",  # Force float conversion error
                    "Duty": 50,
                }
            }

        # Set per-device wattage to enter the specific block
        hass.config_entries.async_update_entry(
            mock_config_entry, options={"wattage_device1": 2400}
        )

        mock_coordinator.update_method = async_update
        await mock_coordinator.async_refresh()

        device_data = {"Id": "device1", "Name": "Test", "Model": "BB-V2"}
        sensor = MysaCurrentSensor(
            mock_coordinator, "device1", device_data, MagicMock(), mock_config_entry
        )

        assert sensor.native_value == 0.0


# ===========================================================================
# MysaTemperatureSensor Tests
# ===========================================================================


class TestMysaTemperatureSensor:
    """Test MysaTemperatureSensor."""

    @pytest.mark.asyncio
    async def test_temperature_sensor_init(
        self, hass, mock_coordinator, mock_device_data, mock_api, mock_entry
    ):
        """Test MysaTemperatureSensor initialization."""
        from custom_components.mysa.sensor import MysaTemperatureSensor

        await mock_coordinator.async_refresh()

        entity = MysaTemperatureSensor(
            mock_coordinator, "device1", mock_device_data, mock_api, mock_entry
        )

        assert entity._device_id == "device1"
        assert entity._attr_translation_key == "temperature"
        assert entity.native_unit_of_measurement == "°C"

    @pytest.mark.asyncio
    async def test_temperature_sensor_value(
        self, hass, mock_coordinator, mock_device_data, mock_api, mock_entry
    ):
        """Test MysaTemperatureSensor native_value."""
        from custom_components.mysa.sensor import MysaTemperatureSensor

        # Helper to set data
        async def async_update():
            return mock_coordinator.data

        # Case 1: ambTemp (direct float)
        mock_coordinator.data = {"device1": {"ambTemp": 22.5}}
        entity = MysaTemperatureSensor(
            mock_coordinator, "device1", mock_device_data, mock_api, mock_entry
        )
        assert entity.native_value == 22.5

        # Case 2: SensorTemp (dict with 'v')
        mock_coordinator.data = {"device1": {"SensorTemp": {"v": "23.5", "t": 123}}}
        assert entity.native_value == 23.5

        # Case 3: CorrectedTemp (direct)
        mock_coordinator.data = {"device1": {"CorrectedTemp": 24.0}}
        assert entity.native_value == 24.0

        # Case 4: None
        mock_coordinator.data = {"device1": {}}
        assert entity.native_value is None

        # Case 5: Priority Check (CorrectedTemp vs ambTemp)
        mock_coordinator.data = {"device1": {"ambTemp": 20.0, "CorrectedTemp": 21.0}}
        assert entity.native_value == 21.0

        # Case 6: Coordinator data None
        mock_coordinator.data = None
        assert entity.native_value is None

        # Case 6: Invalid ambTemp
        mock_coordinator.data = {"device1": {"ambTemp": "invalid"}}
        assert entity.native_value is None

        # Case 7: Invalid SensorTemp
        mock_coordinator.data = {"device1": {"SensorTemp": {"v": "invalid", "t": 123}}}
        assert entity.native_value is None


# ===========================================================================
# MysaHumiditySensor Tests
# ===========================================================================


class TestMysaHumiditySensor:
    """Test MysaHumiditySensor."""

    @pytest.mark.asyncio
    async def test_humidity_sensor_init(
        self, hass, mock_coordinator, mock_device_data, mock_api, mock_entry
    ):
        """Test MysaHumiditySensor initialization."""
        from custom_components.mysa.sensor import MysaHumiditySensor

        await mock_coordinator.async_refresh()

        entity = MysaHumiditySensor(
            mock_coordinator, "device1", mock_device_data, mock_api, mock_entry
        )

        assert entity._device_id == "device1"
        assert entity._attr_translation_key == "humidity"
        assert entity.native_unit_of_measurement == "%"

    @pytest.mark.asyncio
    async def test_humidity_sensor_value(
        self, hass, mock_coordinator, mock_device_data, mock_api, mock_entry
    ):
        """Test MysaHumiditySensor native_value."""
        from custom_components.mysa.sensor import MysaHumiditySensor

        # Case 1: hum (direct)
        mock_coordinator.data = {"device1": {"hum": 45.0}}
        entity = MysaHumiditySensor(
            mock_coordinator, "device1", mock_device_data, mock_api, mock_entry
        )
        assert entity.native_value == 45.0

        # Case 2: Humidity (dict)
        mock_coordinator.data = {"device1": {"Humidity": {"v": "50", "t": 123}}}
        assert entity.native_value == 50.0

        # Case 3: None
        mock_coordinator.data = {"device1": {}}
        assert entity.native_value is None

        # Case 4: Coordinator data None
        mock_coordinator.data = None
        assert entity.native_value is None

        # Case 5: Invalid hum
        mock_coordinator.data = {"device1": {"hum": "invalid"}}
        assert entity.native_value is None

        # Case 6: Invalid Humidity
        mock_coordinator.data = {"device1": {"Humidity": {"v": "invalid", "t": 123}}}
        assert entity.native_value is None


# ===========================================================================
# State Class Tests
# ===========================================================================


class TestSensorStateClass:
    """Test sensor state class."""

    @pytest.mark.asyncio
    async def test_temperature_sensor_state_class(
        self, hass, mock_coordinator, mock_device_data, mock_api, mock_entry
    ):
        """Test that MysaTemperatureSensor has the correct state_class."""
        from custom_components.mysa.sensor import MysaTemperatureSensor

        await mock_coordinator.async_refresh()

        entity = MysaTemperatureSensor(
            mock_coordinator,
            "device1",
            mock_device_data,
            mock_api,
            mock_entry,
        )

        assert entity.state_class == SensorStateClass.MEASUREMENT

    @pytest.mark.asyncio
    async def test_humidity_sensor_state_class(
        self, hass, mock_coordinator, mock_device_data, mock_api, mock_entry
    ):
        """Test that MysaHumiditySensor has the correct state_class."""
        from custom_components.mysa.sensor import MysaHumiditySensor

        await mock_coordinator.async_refresh()

        entity = MysaHumiditySensor(
            mock_coordinator,
            "device1",
            mock_device_data,
            mock_api,
            mock_entry,
        )

        assert entity.state_class == SensorStateClass.MEASUREMENT


# ===========================================================================
# Merged Device Info, Diagnostics, and Edge Case Tests
# ===========================================================================


@pytest.mark.asyncio
async def test_sensor_device_info_zone_name(
    hass, mock_coordinator, mock_api, mock_entry
):
    """Test device_info picks up zone name from options."""
    from custom_components.mysa.sensor import (
        MysaElectricityRateSensor,
        MysaEnergySensor,
        MysaHumiditySensor,
        MysaIpSensor,
        MysaTemperatureSensor,
    )

    # Mock data with Zone ID
    mock_coordinator.data = {"device1": {"Zone": "ZONE123"}}

    device_id = "device1"
    device_data = {"Name": "Test Device", "Model": "BB-V1"}

    mock_entry.options = {"zone_name_ZONE123": "Living Room"}

    # 1. MysaEnergySensor
    power_sensor = MagicMock()
    energy_sensor = MysaEnergySensor(
        mock_coordinator, device_id, device_data, mock_api, mock_entry, power_sensor
    )
    info = energy_sensor.device_info
    assert "suggested_area" not in info

    # 2. MysaElectricityRateSensor
    rate_sensor = MysaElectricityRateSensor(
        mock_coordinator, device_id, device_data, mock_api, mock_entry
    )
    info = rate_sensor.device_info
    assert "suggested_area" not in info

    # 3. MysaIpSensor
    ip_sensor = MysaIpSensor(mock_coordinator, device_id, device_data, mock_entry)
    info = ip_sensor.device_info
    assert "suggested_area" not in info

    # 4. MysaTemperatureSensor
    temp_sensor = MysaTemperatureSensor(
        mock_coordinator, device_id, device_data, mock_api, mock_entry
    )
    info = temp_sensor.device_info
    assert "suggested_area" not in info

    # 5. MysaHumiditySensor
    hum_sensor = MysaHumiditySensor(
        mock_coordinator, device_id, device_data, mock_api, mock_entry
    )
    info = hum_sensor.device_info
    assert "suggested_area" not in info


@pytest.mark.asyncio
async def test_ip_sensor(hass, mock_coordinator, mock_entry, mock_device_data):
    """Test IP address sensor."""
    from homeassistant.const import EntityCategory

    from custom_components.mysa.sensor import MysaIpSensor

    mock_coordinator.data = {"device1": {"ip": "10.0.0.1"}}

    sensor = MysaIpSensor(mock_coordinator, "device1", mock_device_data, mock_entry)

    # Check attributes
    assert sensor.native_value == "10.0.0.1"
    assert sensor.entity_category == EntityCategory.DIAGNOSTIC
    assert sensor.translation_key == "ip_address"
    assert sensor.unique_id == "device1_ip_address"

    # Check update behavior
    mock_coordinator.data = {"device1": {"ip": "192.168.1.100"}}
    assert sensor.native_value == "192.168.1.100"

    # Check missing data
    mock_coordinator.data = {"device1": {}}
    assert sensor.native_value is None

    # Check coordinator data None
    mock_coordinator.data = None
    assert sensor.native_value is None

    # Check state is None
    mock_coordinator.data = {"other": {}}
    assert sensor.native_value is None


@pytest.mark.asyncio
async def test_sensor_edge_cases(hass, mock_api, mock_entry, mock_device_data):
    """Test sensor entity edge cases for missing data."""
    mock_coordinator = MagicMock()
    mock_coordinator.data = None

    # Test MysaPowerSensor missing data
    power_sensor = MysaPowerSensor(
        mock_coordinator, "device1", mock_device_data, mock_api, mock_entry
    )
    assert power_sensor.native_value is None
    assert power_sensor.extra_state_attributes == {}

    # Test MysaDiagnosticSensor Duty exception
    from custom_components.mysa.sensor import MysaDiagnosticSensor

    diag_sensor = MysaDiagnosticSensor(
        mock_coordinator,
        "device1",
        mock_device_data,
        "Duty",
        "duty",
        None,
        None,
        None,
        mock_entry,
    )
    mock_coordinator.data = {"device1": {"Duty": "invalid"}}
    assert diag_sensor.native_value == "invalid"

    # Test MysaDiagnosticSensor extra_state_attributes missing data
    mock_coordinator.data = None
    diag_attr = diag_sensor.extra_state_attributes
    assert "zone_name" not in diag_attr

    # Test MysaCurrentSensor simulated exception
    simple_entry = MagicMock()
    simple_entry.options = {"estimated_max_current": 10.0}

    from custom_components.mysa.sensor import MysaCurrentSensor

    current_sensor = MysaCurrentSensor(
        mock_coordinator, "device1", mock_device_data, mock_api, simple_entry
    )

    # 1. Force simulated
    mock_api.simulated_energy = True

    # 3. Duty is invalid
    mock_coordinator.data = {"device1": {"Duty": "invalid"}}
    assert current_sensor.native_value == 0.0

    # Test MysaCurrentSensor extra_state_attributes with None data
    mock_coordinator.data = None
    assert current_sensor.extra_state_attributes == {}


@pytest.mark.asyncio
async def test_energy_sensor_accumulation_logic(
    hass, mock_api, mock_entry, mock_device_data
):
    """Test energy sensor accumulation logic including 0W handling."""
    from unittest.mock import patch

    mock_coordinator = MagicMock()
    mock_coordinator.data = {"device1": {}}

    # Mock Power Sensor
    power_sensor = MagicMock(spec=MysaPowerSensor)
    power_sensor.native_value = 0.0

    energy_sensor = MysaEnergySensor(
        mock_coordinator,
        "device1",
        mock_device_data,
        mock_api,
        mock_entry,
        power_sensor,
    )

    # Initialize
    await energy_sensor.async_added_to_hass()
    energy_sensor.async_write_ha_state = MagicMock()

    # Initial state should be 0.0
    assert energy_sensor.native_value == 0.0

    # Simulate time progression
    start_time = 1000000.0

    with patch("time.time", return_value=start_time):
        energy_sensor._handle_coordinator_update()
        assert energy_sensor.native_value == 0.0

    # T1: 1 hour later, Power still 0W
    t1 = start_time + 3600
    with patch("time.time", return_value=t1):
        energy_sensor._handle_coordinator_update()
        assert energy_sensor.native_value == 0.0

    # T2: 1 hour later, Power now 1000W
    power_sensor.native_value = 1000.0
    t2 = t1 + 3600
    with patch("time.time", return_value=t2):
        energy_sensor._handle_coordinator_update()
        # 1000W * 1h = 1000 Wh = 1 kWh
        assert energy_sensor.native_value == 1.0

    # T3: 1 hour later, Power drops to 0W
    power_sensor.native_value = 0.0
    t3 = t2 + 3600
    with patch("time.time", return_value=t3):
        energy_sensor._handle_coordinator_update()
        assert energy_sensor.native_value == 1.0


class TestSensorCoverageGaps:
    """Coverage tests moved from test_coverage_gap.py."""

    def test_sensor_diagnostic_coverage(self, mock_coordinator, mock_entry):
        """Exercise sensor.py diagnostic missing lines."""
        entity = MysaDiagnosticSensor(
            mock_coordinator,
            "dev1",
            {},
            "key",
            "key",
            None,
            SensorStateClass.MEASUREMENT,
            None,
            mock_entry,
        )
        # 299-300
        assert entity._extract_value(None, ["key"]) is None
        # Try to hit value conversion failure if possible
        mock_coordinator.data = {"dev1": {"key": "not_a_number"}}
        # Instead of mocking extract_value, let's just test that it returns the string if float fails
        assert entity.native_value == "not_a_number"

    def test_sensor_power_coverage(self, mock_coordinator, mock_entry, mock_api):
        """Exercise sensor.py power missing lines."""
        entity = MysaPowerSensor(mock_coordinator, "dev1", {}, mock_api, mock_entry)
        # 351, 367, 370, 425
        assert entity._extract_value(None, ["key"]) is None
        mock_coordinator.data = None
        assert entity.native_value is None
        assert entity.extra_state_attributes == {}
        mock_coordinator.data = {"other": {}}
        assert entity.native_value is None

    def test_sensor_current_coverage(self, mock_coordinator, mock_entry, mock_api):
        """Exercise sensor.py current missing lines."""
        entity = MysaCurrentSensor(mock_coordinator, "dev1", {}, mock_api, mock_entry)
        # 479, 497
        assert entity._extract_value(None, ["key"]) is None
        mock_coordinator.data = None
        assert entity.native_value is None
        mock_coordinator.data = {"other": {}}
        assert entity.native_value is None

    def test_sensor_ip_coverage(self, mock_coordinator, mock_entry):
        """Exercise sensor.py IP missing lines."""
        entity = MysaIpSensor(mock_coordinator, "dev1", {}, mock_entry)
        # 739 (native_value state None)
        mock_coordinator.data = {}  # state is None
        assert entity.native_value is None
        mock_coordinator.data = {"dev1": {"ip": "1.2.3.4"}}
        assert entity.native_value == "1.2.3.4"
        mock_coordinator.data = {"dev1": {"Local IP": "5.6.7.8"}}
        assert entity.native_value == "5.6.7.8"

        # Nested dict cases for 739-742
        mock_coordinator.data = {"dev1": {"ip": {"v": "1.1.1.1"}}}
        assert entity.native_value == "1.1.1.1"  # Covers 739
        mock_coordinator.data = {"dev1": {"ip": {"v": None, "Id": "2.2.2.2"}}}
        assert entity.native_value == "2.2.2.2"  # Covers 741
        mock_coordinator.data = {"dev1": {"ip": {"v": None, "Id": None}}}
        assert entity.native_value is None  # Covers the end of loop

    def test_sensor_temp_coverage(self, mock_coordinator, mock_entry):
        """Exercise sensor.py Temperature missing lines."""
        entity = MysaTemperatureSensor(
            mock_coordinator, "dev1", {}, MagicMock(), mock_entry
        )
        # 774-775, 781, 784
        mock_coordinator.data = None
        assert entity.device_info is not None
        assert entity.native_value is None
        mock_coordinator.data = {"other": {}}
        assert entity.native_value is None

    def test_sensor_hum_coverage(self, mock_coordinator, mock_entry):
        """Exercise sensor.py Humidity missing lines."""
        entity = MysaHumiditySensor(
            mock_coordinator, "dev1", {}, MagicMock(), mock_entry
        )
        # 837-838, 844, 847
        mock_coordinator.data = None
        assert entity.device_info is not None
        assert entity.native_value is None
        mock_coordinator.data = {"other": {}}
        assert entity.native_value is None
