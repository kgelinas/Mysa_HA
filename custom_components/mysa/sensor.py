"""Sensor platform for Mysa."""
import logging
from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfTemperature,
    EntityCategory,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .mysa_api import MysaApi

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Mysa sensors."""
    data = hass.data[DOMAIN].get(entry.entry_id)
    if not data:
        _LOGGER.error("Mysa data not found in hass.data. Sensor setup failed.")
        return

    coordinator = data["coordinator"]
    api = data["api"]
    devices = await api.get_devices()

    entities = []
    for device_id, device_data in devices.items():
        is_ac = api.is_ac_device(device_id)
        
        # Zone Name Sensor (all devices)
        entities.append(MysaZoneSensor(coordinator, device_id, device_data, entry))
        
        # RSSI (all devices)
        entities.append(MysaDiagnosticSensor(coordinator, device_id, device_data, "Rssi", "RSSI", SIGNAL_STRENGTH_DECIBELS_MILLIWATT, SensorStateClass.MEASUREMENT, SensorDeviceClass.SIGNAL_STRENGTH, entry))
        
        # Brightness (all devices - current display brightness)
        entities.append(MysaDiagnosticSensor(coordinator, device_id, device_data, "Brightness", "Brightness", PERCENTAGE, SensorStateClass.MEASUREMENT, None, entry))
        
        # TimeZone (all devices)
        entities.append(MysaDiagnosticSensor(coordinator, device_id, device_data, "TimeZone", "Time Zone", None, None, None, entry))
        
        # Min/Max Setpoint (all devices)
        entities.append(MysaDiagnosticSensor(coordinator, device_id, device_data, "MinSetpoint", "Minimum Setpoint", UnitOfTemperature.CELSIUS, None, SensorDeviceClass.TEMPERATURE, entry))
        entities.append(MysaDiagnosticSensor(coordinator, device_id, device_data, "MaxSetpoint", "Maximum Setpoint", UnitOfTemperature.CELSIUS, None, SensorDeviceClass.TEMPERATURE, entry))
        
        # === Heating thermostat only sensors (skip for AC) ===
        if not is_ac:
            # Duty Cycle (heating only)
            entities.append(MysaDiagnosticSensor(coordinator, device_id, device_data, "Duty", "Duty Cycle", PERCENTAGE, SensorStateClass.MEASUREMENT, None, entry))
            
            # Maximum Current (heating only)
            entities.append(MysaDiagnosticSensor(coordinator, device_id, device_data, "MaxCurrent", "Maximum Current", UnitOfElectricCurrent.AMPERE, None, SensorDeviceClass.CURRENT, entry))
            
            state = coordinator.data.get(device_id, {})
            
            # HeatSink (heating only)
            if "HeatSink" in state:
                entities.append(MysaDiagnosticSensor(coordinator, device_id, device_data, "HeatSink", "HeatSink Temperature", UnitOfTemperature.CELSIUS, SensorStateClass.MEASUREMENT, SensorDeviceClass.TEMPERATURE, entry))
            
            # Infloor (floor heating only)
            if "Infloor" in state:
                entities.append(MysaDiagnosticSensor(coordinator, device_id, device_data, "Infloor", "Infloor Temperature", UnitOfTemperature.CELSIUS, SensorStateClass.MEASUREMENT, SensorDeviceClass.TEMPERATURE, entry))
                
            # Voltage/Current (heating only)
            if "Voltage" in state or "LineVoltage" in state:
                entities.append(MysaDiagnosticSensor(coordinator, device_id, device_data, "Voltage", "Voltage", UnitOfElectricPotential.VOLT, SensorStateClass.MEASUREMENT, SensorDeviceClass.VOLTAGE, entry))
            if "Current" in state:
                entities.append(MysaDiagnosticSensor(coordinator, device_id, device_data, "Current", "Current", UnitOfElectricCurrent.AMPERE, SensorStateClass.MEASUREMENT, SensorDeviceClass.CURRENT, entry))

    async_add_entities(entities)

class MysaDiagnosticSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Mysa Diagnostic Sensor."""

    def __init__(self, coordinator, device_id, device_data, sensor_key, name_suffix, unit, state_class, device_class, entry):
        """Initialize."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._sensor_key = sensor_key
        self._entry = entry
        self._device_data = device_data
        self._attr_name = f"{device_data.get('Name', 'Mysa')} {name_suffix}"
        self._attr_unique_id = f"{device_id}_{sensor_key.lower()}"
        self._attr_native_unit_of_measurement = unit
        self._attr_state_class = state_class
        self._attr_device_class = device_class
        self._attr_extra_state_attributes = {}

        # Categorize as Diagnostic AND Disable by default
        if sensor_key in ["Current", "Duty", "HeatSink", "Infloor", "MaxCurrent", "MinSetpoint", "MaxSetpoint", "Rssi", "TimeZone", "Voltage"]:
             self._attr_entity_category = EntityCategory.DIAGNOSTIC
             self._attr_entity_registry_enabled_default = False
    @property
    def device_info(self):
        """Return device info."""
        state = self.coordinator.data.get(self._device_id)
        zone_id = state.get("Zone") if state else None
        zone_name = self._entry.options.get(f"zone_name_{zone_id}") if zone_id else None
        
        info = {
            "identifiers": {(DOMAIN, self._device_id)},
            "manufacturer": "Mysa",
            "model": self._device_data.get("Model"),
        }
        if zone_name:
            info["suggested_area"] = zone_name
        return info

    @property
    def extra_state_attributes(self):
        """Return extra state attributes."""
        state = self.coordinator.data.get(self._device_id)
        zone_id = state.get("Zone") if state else None
        zone_name = self._entry.options.get(f"zone_name_{zone_id}") if zone_id else None
        
        return {
            "device_id": self._device_id,
            "zone_id": zone_id,
            "zone_name": zone_name if zone_name else "Unassigned",
        }

    @property
    def native_value(self):
        """Return the state of the sensor."""
        state = self.coordinator.data.get(self._device_id)
        if not state:
            return None
            
        # Mapping variants
        keys = [self._sensor_key]
        if self._sensor_key == "Duty":
            keys = ["dc", "Duty", "dtyCycle", "DutyCycle"]
        elif self._sensor_key == "Rssi":
            keys = ["rssi", "Rssi", "RSSI"]
        elif self._sensor_key == "Voltage":
            keys = ["volts", "Voltage", "LineVoltage"]
        elif self._sensor_key == "Current":
            keys = ["amps", "Current"]
        elif self._sensor_key == "Brightness":
            keys = ["Brightness", "br"]
        elif self._sensor_key == "HeatSink":
            keys = ["HeatSink", "hs"]
        elif self._sensor_key == "Infloor":
            keys = ["Infloor", "if"]
        elif self._sensor_key == "MaxSetpoint":
            keys = ["MaxSetpoint", "mxs"]
        elif self._sensor_key == "MinSetpoint":
            keys = ["MinSetpoint", "mns"]
        elif self._sensor_key == "MaxCurrent":
            keys = ["MaxCurrent", "mxc"]
        elif self._sensor_key == "MinBrightness":
            keys = ["MinBrightness", "mnbr"]
        elif self._sensor_key == "MaxBrightness":
            keys = ["MaxBrightness", "mxbr"]
        elif self._sensor_key == "TimeZone":
            keys = ["TimeZone", "tz"]

        val = self._extract_value(state, keys)
        if val is not None:
            # TimeZone is a string
            if self._sensor_key == "TimeZone":
                return str(val)
                
            # Handle percentage conversion if 0-1 range
            if self._sensor_key == "Duty" and float(val) <= 1.0 and float(val) >= 0:
                 return float(val) * 100.0
            
            try:
                return float(val)
            except (ValueError, TypeError):
                return str(val)
        return None

    def _extract_value(self, state, keys):
        """Helper to extract a value from state dictionary."""
        for key in keys:
            val = state.get(key)
            if val is not None:
                if isinstance(val, dict):
                    v = val.get('v')
                    if v is None:
                        v = val.get('Id')
                    return v
                return val
        return None

class MysaZoneSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Mysa Zone Sensor."""

    def __init__(self, coordinator, device_id, device_data, entry):
        """Initialize."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._entry = entry
        self._device_data = device_data
        self._attr_name = f"{device_data.get('Name', 'Mysa')} Zone"
        self._attr_unique_id = f"{device_id}_zone"

    @property
    def device_info(self):
        """Return device info."""
        state = self.coordinator.data.get(self._device_id)
        zone_id = state.get("Zone") if state else None
        zone_name = self._entry.options.get(f"zone_name_{zone_id}") if zone_id else None
        
        info = {
            "identifiers": {(DOMAIN, self._device_id)},
            "manufacturer": "Mysa",
            "model": self._device_data.get("Model"),
        }
        if zone_name:
            info["suggested_area"] = zone_name
        return info

    @property
    def native_value(self):
        """Return the state of the sensor."""
        state = self.coordinator.data.get(self._device_id)
        if not state:
            return None
        zone_id = state.get("Zone")
        if not zone_id:
            return "Unassigned"
        
        return self._entry.options.get(f"zone_name_{zone_id}", zone_id)

    @property
    def extra_state_attributes(self):
        """Return extra state attributes."""
        state = self.coordinator.data.get(self._device_id)
        zone_id = state.get("Zone") if state else None
        
        return {
            "zone_id": zone_id,
        }
