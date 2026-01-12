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
        entities.append(MysaZoneSensor(coordinator, device_id, device_data, api))
        
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
        
        # Simulated sensors for Lite devices (upgraded or not)
        upgraded_lite_devices = entry.options.get("upgraded_lite_devices", [])
        estimated_max_current = entry.options.get("estimated_max_current", 0)
        
        # Check if this device is a Lite model OR manually marked as upgraded Lite
        model = device_data.get("Model", "")
        is_lite_model = "BB-V2-0-L" in model or "-L" in model
        
        normalized_id = device_id.replace(":", "").lower()
        is_upgraded_lite = any(
            uid.replace(":", "").lower() == normalized_id 
            for uid in upgraded_lite_devices
        )
        
        # Show simulated sensors for any Lite device if estimated current is configured
        if (is_lite_model or is_upgraded_lite) and estimated_max_current > 0:
            entities.append(MysaSimulatedCurrentSensor(coordinator, device_id, device_data, estimated_max_current, entry))
            entities.append(MysaSimulatedPowerSensor(coordinator, device_id, device_data, estimated_max_current, entry))

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

    def __init__(self, coordinator, device_id, device_data, api):
        """Initialize."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._api = api
        self._device_data = device_data
        self._attr_name = f"{device_data.get('Name', 'Mysa')} Zone"
        self._attr_unique_id = f"{device_id}_zone"

    @property
    def device_info(self):
        """Return device info."""
        state = self.coordinator.data.get(self._device_id)
        zone_id = state.get("Zone") if state else None
        zone_name = self._api.get_zone_name(zone_id) if zone_id else None
        
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
        
        zone_name = self._api.get_zone_name(zone_id)
        return zone_name if zone_name else zone_id

    @property
    def extra_state_attributes(self):
        """Return extra state attributes."""
        state = self.coordinator.data.get(self._device_id)
        zone_id = state.get("Zone") if state else None
        
        return {
            "zone_id": zone_id,
        }


class MysaSimulatedCurrentSensor(CoordinatorEntity, SensorEntity):
    """Simulated current sensor for upgraded Lite devices."""

    def __init__(self, coordinator, device_id, device_data, estimated_max_current, entry):
        """Initialize."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._estimated_max_current = estimated_max_current
        self._entry = entry
        self._device_data = device_data
        self._attr_name = f"{device_data.get('Name', 'Mysa')} Estimated Current"
        self._attr_unique_id = f"{device_id}_estimated_current"
        self._attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_device_class = SensorDeviceClass.CURRENT
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def device_info(self):
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "manufacturer": "Mysa",
            "model": self._device_data.get("Model"),
        }

    @property
    def native_value(self):
        """Calculate current from duty cycle and estimated max current."""
        state = self.coordinator.data.get(self._device_id)
        if not state:
            return None
        
        # Get duty cycle (0-1 or 0-100)
        duty = None
        for key in ["dc", "Duty", "dtyCycle", "DutyCycle"]:
            val = state.get(key)
            if val is not None:
                if isinstance(val, dict):
                    duty = val.get('v')
                else:
                    duty = val
                break
        
        if duty is None:
            return 0.0
        
        # Normalize to 0-1 range
        if duty > 1:
            duty = duty / 100.0
        
        return round(self._estimated_max_current * duty, 2)

    @property
    def extra_state_attributes(self):
        """Return extra state attributes."""
        return {
            "estimated_max_current": self._estimated_max_current,
            "note": "Simulated based on duty cycle - Lite hardware has no current sensor",
        }


class MysaSimulatedPowerSensor(CoordinatorEntity, SensorEntity):
    """Simulated power sensor for upgraded Lite devices."""

    def __init__(self, coordinator, device_id, device_data, estimated_max_current, entry):
        """Initialize."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._estimated_max_current = estimated_max_current
        self._entry = entry
        self._device_data = device_data
        self._attr_name = f"{device_data.get('Name', 'Mysa')} Estimated Power"
        self._attr_unique_id = f"{device_id}_estimated_power"
        self._attr_native_unit_of_measurement = "W"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def device_info(self):
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "manufacturer": "Mysa",
            "model": self._device_data.get("Model"),
        }

    @property
    def native_value(self):
        """Calculate power from duty cycle, estimated current, and assumed voltage."""
        state = self.coordinator.data.get(self._device_id)
        if not state:
            return None
        
        # Get duty cycle
        duty = None
        for key in ["dc", "Duty", "dtyCycle", "DutyCycle"]:
            val = state.get(key)
            if val is not None:
                if isinstance(val, dict):
                    duty = val.get('v')
                else:
                    duty = val
                break
        
        if duty is None:
            return 0.0
        
        # Normalize to 0-1 range
        if duty > 1:
            duty = duty / 100.0
        
        # Get voltage (default 240V if not available)
        voltage = 240
        for key in ["volts", "Voltage", "LineVoltage"]:
            val = state.get(key)
            if val is not None:
                if isinstance(val, dict):
                    voltage = val.get('v', 240)
                else:
                    voltage = val
                break
        
        current = self._estimated_max_current * duty
        return round(voltage * current, 1)

    @property
    def extra_state_attributes(self):
        """Return extra state attributes."""
        return {
            "estimated_max_current": self._estimated_max_current,
            "assumed_voltage": 240,
            "note": "Simulated based on duty cycle - Lite hardware has no current sensor",
        }
