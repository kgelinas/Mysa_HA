"""Sensor platform for Mysa."""
# pylint: disable=too-many-branches
import logging
import time
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
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN


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

    entities: list[SensorEntity] = []
    for device_id, device_data in devices.items():
        is_ac = api.is_ac_device(device_id)
        state = {}

        # Zone Name Sensor (all devices)
        entities.append(MysaZoneSensor(coordinator, device_id, device_data, api))
        # RSSI (all devices)
        entities.append(
            MysaDiagnosticSensor(
                coordinator, device_id, device_data, "Rssi", "RSSI",
                SIGNAL_STRENGTH_DECIBELS_MILLIWATT, SensorStateClass.MEASUREMENT,
                SensorDeviceClass.SIGNAL_STRENGTH, entry
            )
        )

        # Brightness (all devices - current display brightness)
        entities.append(
            MysaDiagnosticSensor(
                coordinator, device_id, device_data, "Brightness", "Brightness",
                PERCENTAGE, SensorStateClass.MEASUREMENT, None, entry
            )
        )

        # TimeZone (all devices)
        entities.append(
            MysaDiagnosticSensor(
                coordinator, device_id, device_data, "TimeZone", "Time Zone",
                None, None, None, entry
            )
        )

        # Min/Max Setpoint (all devices)
        entities.append(
            MysaDiagnosticSensor(
                coordinator, device_id, device_data, "MinSetpoint", "Minimum Setpoint",
                UnitOfTemperature.CELSIUS, None, SensorDeviceClass.TEMPERATURE, entry
            )
        )
        entities.append(
            MysaDiagnosticSensor(
                coordinator, device_id, device_data, "MaxSetpoint", "Maximum Setpoint",
                UnitOfTemperature.CELSIUS, None, SensorDeviceClass.TEMPERATURE, entry
            )
        )
        # === Heating thermostat only sensors (skip for AC) ===
        if not is_ac:
            # Duty Cycle (heating only)
            entities.append(
                MysaDiagnosticSensor(
                    coordinator, device_id, device_data, "Duty", "Duty Cycle",
                    PERCENTAGE, SensorStateClass.MEASUREMENT, None, entry
                )
            )

            # Maximum Current (heating only)
            entities.append(
                MysaDiagnosticSensor(
                    coordinator, device_id, device_data, "MaxCurrent", "Maximum Current",
                    UnitOfElectricCurrent.AMPERE, None, SensorDeviceClass.CURRENT, entry
                )
            )
            state = coordinator.data.get(device_id, {})

            # HeatSink (heating only)
            if "HeatSink" in state:
                entities.append(
                    MysaDiagnosticSensor(
                        coordinator, device_id, device_data, "HeatSink", "HeatSink Temperature",
                        UnitOfTemperature.CELSIUS, SensorStateClass.MEASUREMENT,
                        SensorDeviceClass.TEMPERATURE, entry
                    )
                )

            # Infloor (floor heating only)
            if "Infloor" in state or "flrSnsrTemp" in state:
                entities.append(
                    MysaDiagnosticSensor(
                        coordinator, device_id, device_data, "Infloor", "Infloor Temperature",
                        UnitOfTemperature.CELSIUS, SensorStateClass.MEASUREMENT,
                        SensorDeviceClass.TEMPERATURE, entry
                    )
                )

            # Voltage/Current (heating only)
            if "Voltage" in state or "LineVoltage" in state:
                entities.append(
                    MysaDiagnosticSensor(
                        coordinator, device_id, device_data, "Voltage", "Voltage",
                        UnitOfElectricPotential.VOLT, SensorStateClass.MEASUREMENT,
                        SensorDeviceClass.VOLTAGE, entry
                    )
                )
            if "Current" in state:
                entities.append(
                    MysaDiagnosticSensor(
                        coordinator, device_id, device_data, "Current", "Current",
                        UnitOfElectricCurrent.AMPERE, SensorStateClass.MEASUREMENT,
                        SensorDeviceClass.CURRENT, entry
                    )
                )

        # Power and Current sensors (simulated or real)
        if not is_ac:
            power_sensor = MysaPowerSensor(coordinator, device_id, device_data, api, entry)
            entities.append(power_sensor)

            # Virtual Energy Sensor (kWh)
            entities.append(
                MysaEnergySensor(coordinator, device_id, device_data, api, entry, power_sensor)
            )

            # If current wasn't added as a diagnostic sensor (e.g. Lite), add it as simulated
            if "Current" not in state:
                entities.append(MysaCurrentSensor(coordinator, device_id, device_data, api, entry))

            # Electricity Rate (Cost) Sensor - based on device's home rate
            entities.append(
                MysaElectricityRateSensor(coordinator, device_id, device_data, api, entry)
            )

        # === Network Diagnostic Sensors (all devices) ===
        # Network sensors (IP, MAC, SSID) are not reliably available via API
        # Removed per user request

    async_add_entities(entities)

class MysaDiagnosticSensor(
    SensorEntity, CoordinatorEntity
):
    """Representation of a Mysa Diagnostic Sensor."""

    def __init__(
        self, coordinator, device_id, device_data, sensor_key, name_suffix,
        unit, state_class, device_class, entry
    ):
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
        if sensor_key in [
            "Current", "Duty", "HeatSink", "MaxCurrent",
            "MinSetpoint", "MaxSetpoint", "Rssi", "TimeZone", "Voltage",
        ]:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
            self._attr_entity_registry_enabled_default = False
    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        state = self.coordinator.data.get(self._device_id)
        zone_id = state.get("Zone") if state else None
        zone_name = self._entry.options.get(f"zone_name_{zone_id}") if zone_id else None
        info = DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            manufacturer="Mysa",
            model=self._device_data.get("Model"),
        )
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
            keys = ["Infloor", "if", "flrSnsrTemp"]
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
            if self._sensor_key == "Duty" and 0 <= float(val) <= 1.0:
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

class MysaZoneSensor(SensorEntity, CoordinatorEntity):
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
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        state = self.coordinator.data.get(self._device_id)
        zone_id = state.get("Zone") if state else None
        zone_name = self._api.get_zone_name(zone_id) if zone_id else None

        info = DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            manufacturer="Mysa",
            model=self._device_data.get("Model"),
        )
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


class MysaPowerSensor(SensorEntity, CoordinatorEntity):
    """Representation of a Mysa Power Sensor (Real or Simulated)."""

    def __init__(self, coordinator, device_id, device_data, api, entry):
        """Initialize."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._api = api
        self._entry = entry
        self._device_data = device_data
        self._attr_name = f"{device_data.get('Name', 'Mysa')} Power"
        self._attr_unique_id = f"{device_id}_power"
        self._attr_native_unit_of_measurement = "W"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_device_class = SensorDeviceClass.POWER

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            manufacturer="Mysa",
            model=self._device_data.get("Model"),
        )

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

    @property
    def native_value(self):
        """Calculate power from real data or simulated wattage."""
        state = self.coordinator.data.get(self._device_id)
        if not state:
            return None

        # Check simulated energy flag
        force_simulated = getattr(self._api, "simulated_energy", False)

        # Get duty cycle (used in both real and simulated calculations)
        duty = self._extract_value(state, ["Duty", "dc", "DutyCycle"]) or 0
        try:
            duty_float = float(duty)
            if duty_float > 1:
                duty_float = duty_float / 100.0
        except (ValueError, TypeError):
            duty_float = 0.0

        # 1. Try real data (Voltage * Current * DutyCycle)
        # Note: Current sensor reports "last on" value, not instantaneous.
        # We must multiply by duty cycle to get actual power consumption.
        if not force_simulated:
            voltage = self._extract_value(state, ["Voltage", "LineVoltage"])
            current = self._extract_value(state, ["Current"])

            if voltage and current:
                try:
                    # Max power when heater is on
                    max_power = float(voltage) * float(current)
                    # Actual average power = max_power * duty cycle
                    return round(max_power * duty_float, 1)
                except (ValueError, TypeError):
                    pass

        # 2. Fallback to simulated data (Wattage * DutyCycle)
        safe_id = self._device_id.replace(":", "").lower()
        wattage = self._entry.options.get(f"wattage_{safe_id}", 0)

        # If no per-device wattage, try old global setting (backward compat)
        if wattage == 0:
            est_current = self._entry.options.get("estimated_max_current", 0)
            # Default voltage to 240 if not reported
            voltage = self._extract_value(state, ["Voltage", "LineVoltage"])
            v_val = voltage if voltage else 240
            try:
                wattage = est_current * float(v_val)
            except (ValueError, TypeError):
                wattage = 0

        if wattage > 0:
            return round(wattage * duty_float, 1)

        return 0.0


    @property
    def extra_state_attributes(self):
        """Return extra state attributes."""
        state = self.coordinator.data.get(self._device_id)
        current = self._extract_value(state, ["Current"]) if state else None
        safe_id = self._device_id.replace(":", "").lower()
        wattage = self._entry.options.get(f"wattage_{safe_id}", 0)
        force_simulated = getattr(self._api, "simulated_energy", False)

        mode = "Real"
        if force_simulated:
            mode = "Forced Simulated"
        elif current is None:
            mode = "Simulated"

        attrs = {"tracking_mode": mode}
        if mode in ["Simulated", "Forced Simulated"]:
            attrs["configured_wattage"] = wattage
        return attrs


class MysaCurrentSensor(SensorEntity, CoordinatorEntity):
    """Representation of a Mysa Current Sensor (Simulated)."""

    def __init__(self, coordinator, device_id, device_data, api, entry):
        """Initialize."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._api = api
        self._entry = entry
        self._device_data = device_data
        self._attr_name = f"{device_data.get('Name', 'Mysa')} Estimated Current"
        self._attr_unique_id = f"{device_id}_estimated_current"
        self._attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_device_class = SensorDeviceClass.CURRENT
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            manufacturer="Mysa",
            model=self._device_data.get("Model"),
        )

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

    @property
    def native_value(self):
        """Calculate current from wattage and duty cycle."""
        state = self.coordinator.data.get(self._device_id)
        if not state:
            return None

        # Check simulated energy flag
        force_simulated = getattr(self._api, "simulated_energy", False)

        # 1. Real current check (though this class is for when it's missing)
        if not force_simulated:
            current = self._extract_value(state, ["Current"])
            if current is not None:
                try:
                    return float(current)
                except (ValueError, TypeError):
                    pass

        # 2. Simulated current
        safe_id = self._device_id.replace(":", "").lower()
        wattage = self._entry.options.get(f"wattage_{safe_id}", 0)

        if wattage == 0:
            est_current = self._entry.options.get("estimated_max_current", 0)
            if est_current > 0:
                duty = self._extract_value(state, ["Duty", "dc", "DutyCycle"])
                if duty is not None:
                    try:
                        duty_float = float(duty)
                        if duty_float > 1:
                            duty_float = duty_float / 100.0
                        return round(est_current * duty_float, 2)
                    except (ValueError, TypeError):
                        pass
            return 0.0

        voltage = self._extract_value(state, ["Voltage", "LineVoltage"]) or 240
        duty = self._extract_value(state, ["Duty", "dc", "DutyCycle"])

        if duty is not None:
            try:
                duty_float = float(duty)
                v_float = float(voltage)
                if duty_float > 1:
                    duty_float = duty_float / 100.0
                # I = P / V
                if v_float > 0:
                    return round((wattage / v_float) * duty_float, 2)
            except (ValueError, TypeError):
                pass

        return 0.0

    @property
    def extra_state_attributes(self):
        """Return extra state attributes."""
        state = self.coordinator.data.get(self._device_id)
        current = self._extract_value(state, ["Current"]) if state else None
        safe_id = self._device_id.replace(":", "").lower()
        wattage = self._entry.options.get(f"wattage_{safe_id}", 0)
        force_simulated = getattr(self._api, "simulated_energy", False)

        mode = "Real"
        if force_simulated:
            mode = "Forced Simulated"
        elif current is None:
            mode = "Simulated"

        attrs = {"tracking_mode": mode}
        if mode in ["Simulated", "Forced Simulated"]:
            attrs["configured_wattage"] = wattage
        return attrs


class MysaEnergySensor(SensorEntity, RestoreEntity, CoordinatorEntity):
    """Integrates Power over time to provide native kWh tracking."""

    def __init__(self, coordinator, device_id, device_data, api, entry, power_sensor):
        """Initialize."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._api = api
        self._entry = entry
        self._device_data = device_data
        self._power_sensor = power_sensor
        self._attr_name = f"{device_data.get('Name', 'Mysa')} Energy"
        self._attr_unique_id = f"{device_id}_energy"
        self._attr_native_unit_of_measurement = "kWh"
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_native_value = 0.0
        self._last_update = None

    async def async_added_to_hass(self):
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if state and state.state not in (None, "unknown", "unavailable"):
            try:
                self._attr_native_value = float(state.state)
            except ValueError:
                self._attr_native_value = 0.0
        self._last_update = time.time()

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            manufacturer="Mysa",
            model=self._device_data.get("Model"),
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # Calculate integration
        now = time.time()
        if self._last_update is not None:
            # Time delta in hours
            diff = (now - self._last_update) / 3600.0

            # Get current power (W)
            power = self._power_sensor.native_value
            if power is not None and power > 0:
                # Energy (kWh) = (Power (W) / 1000) * Time (h)
                added_energy = (power / 1000.0) * diff
                self._attr_native_value = round(self._attr_native_value + added_energy, 4)

        self._last_update = now
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self):
        """Return extra state attributes."""
        return {
            "last_integration_time": self._last_update,
            "note": "Virtual Riemann sum integration of power sensor"
        }


class MysaElectricityRateSensor(SensorEntity, CoordinatorEntity):
    """Representation of the Electricity Rate for a device's home."""

    def __init__(self, coordinator, device_id, device_data, api, entry):
        """Initialize."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._api = api
        self._entry = entry
        self._device_data = device_data
        self._attr_name = f"{device_data.get('Name', 'Mysa')} Electricity Rate"
        self._attr_unique_id = f"{device_id}_electricity_rate"
        # We use a generic currency/kWh unit. Since we don't know the currency,
        # we try to be generic, or assume local currency units.
        # But 'monetary' device class usually requires ISO currency code in unit?
        # Actually 'monetary' is for total balance.
        # Energy price is usually just invalid for device_class=monetary
        # unless it is the total cost.
        # We will use no device class, but provide the unit.
        self._attr_native_unit_of_measurement = "$/kWh"  # Generic symbol per protocol
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_icon = "mdi:currency-usd"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            manufacturer="Mysa",
            model=self._device_data.get("Model"),
        )

    @property
    def native_value(self):
        """Return the electricity rate."""
        # Rate is static per home, but we fetch via API helper that checks mapping
        rate = self._api.get_electricity_rate(self._device_id)
        if rate is not None:
            return rate
        return None
