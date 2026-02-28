"""Sensor platform for Mysa."""

# pylint: disable=too-many-branches,too-many-lines
# Justification: Handles setup for many different sensor types and platforms in a single file.

# Justification: Sensor mapping requires handling many device types and attributes in a single pass.
import logging
import time
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from . import MysaData
from .capabilities import DeviceCapabilities
from .device import MysaDeviceLogic
from .mysa_api import MysaApi

PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: ConfigEntry[MysaData],
    async_add_entities: AddEntitiesCallback,
) -> None:
    # pylint: disable=too-many-locals
    # Justification: Entity factory function needs locals for each sensor type.
    """Set up Mysa sensors."""
    coordinator = entry.runtime_data.coordinator
    api = entry.runtime_data.api
    # Get devices to create entities
    devices = api.devices

    entities: list[SensorEntity] = []
    for device_id, device_data in devices.items():
        # Get cached capabilities (defensive lookup for tests)
        if hasattr(api, "device_caps") and device_id in api.device_caps:
            caps = api.device_caps[device_id]
        else:
            # Fallback for tests or unexpected missing cache

            state = coordinator.data.get(device_id, {}) if coordinator.data else {}
            caps = DeviceCapabilities.from_device(device_id, device_data, state, api)

        is_stv10 = caps.is_stv10

        # Ambient Temperature (all devices - inlined is_ac check)
        entities.append(
            MysaTemperatureSensor(coordinator, device_id, device_data, api, entry)
        )

        # Humidity (all devices - if available)
        # Check if device supports humidity (ACs do, some thermostats do)
        # We'll create it and let it be unavailable if data missing, or check logic?
        # Better to always add and let it report None/Unavailable if key missing,
        # unless we know for sure. ACs definitely have it. V1/V2 thermostats might.
        entities.append(
            MysaHumiditySensor(coordinator, device_id, device_data, api, entry)
        )

        # Free Heap (All devices)
        entities.append(
            MysaDiagnosticSensor(
                coordinator,
                device_id,
                device_data,
                "free_heap",
                "free_heap",
                "B",
                SensorStateClass.MEASUREMENT,
                None,
                entry,
            )
        )

        # RSSI (baseboard only - not available for ST-V1-0 HVAC)
        if not is_stv10:
            entities.append(
                MysaDiagnosticSensor(
                    coordinator,
                    device_id,
                    device_data,
                    "Rssi",
                    "rssi",
                    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
                    SensorStateClass.MEASUREMENT,
                    SensorDeviceClass.SIGNAL_STRENGTH,
                    entry,
                )
            )

        # Brightness (baseboard only - not available for ST-V1-0)
        if not is_stv10:
            entities.append(
                MysaDiagnosticSensor(
                    coordinator,
                    device_id,
                    device_data,
                    "Brightness",
                    "brightness",
                    PERCENTAGE,
                    SensorStateClass.MEASUREMENT,
                    None,
                    entry,
                )
            )

            # TimeZone (baseboard only)
            entities.append(
                MysaDiagnosticSensor(
                    coordinator,
                    device_id,
                    device_data,
                    "TimeZone",
                    "timezone",
                    None,
                    None,
                    None,
                    entry,
                )
            )

        entities.append(
            MysaDiagnosticSensor(
                coordinator,
                device_id,
                device_data,
                "MinSetpoint",
                "min_setpoint",
                UnitOfTemperature.CELSIUS,
                SensorStateClass.MEASUREMENT,
                SensorDeviceClass.TEMPERATURE,
                entry,
            )
        )
        entities.append(
            MysaDiagnosticSensor(
                coordinator,
                device_id,
                device_data,
                "MaxSetpoint",
                "max_setpoint",
                UnitOfTemperature.CELSIUS,
                SensorStateClass.MEASUREMENT,
                SensorDeviceClass.TEMPERATURE,
                entry,
            )
        )
        # === Baseboard heater only sensors (skip for AC and ST-V1-0 HVAC) ===
        if not api.is_ac_device(device_id) and not is_stv10:
            state = coordinator.data.get(device_id, {}) if coordinator.data else {}

            # Duty Cycle (heating only)
            entities.append(
                MysaDiagnosticSensor(
                    coordinator,
                    device_id,
                    device_data,
                    "Duty",
                    "duty_cycle",
                    PERCENTAGE,
                    SensorStateClass.MEASUREMENT,
                    None,
                    entry,
                )
            )

            # Maximum Current (heating only)
            entities.append(
                MysaDiagnosticSensor(
                    coordinator,
                    device_id,
                    device_data,
                    "MaxCurrent",
                    "max_current",
                    UnitOfElectricCurrent.AMPERE,
                    SensorStateClass.MEASUREMENT,
                    SensorDeviceClass.CURRENT,
                    entry,
                )
            )

            # HeatSink (heating only)
            if "HeatSink" in state:
                entities.append(
                    MysaDiagnosticSensor(
                        coordinator,
                        device_id,
                        device_data,
                        "HeatSink",
                        "heatsink_temperature",
                        UnitOfTemperature.CELSIUS,
                        SensorStateClass.MEASUREMENT,
                        SensorDeviceClass.TEMPERATURE,
                        entry,
                    )
                )

            # Infloor (floor heating only)
            if "Infloor" in state or "flrSnsrTemp" in state:
                entities.append(
                    MysaDiagnosticSensor(
                        coordinator,
                        device_id,
                        device_data,
                        "Infloor",
                        "infloor_temperature",
                        UnitOfTemperature.CELSIUS,
                        SensorStateClass.MEASUREMENT,
                        SensorDeviceClass.TEMPERATURE,
                        entry,
                    )
                )

            # Voltage/Current (heating only)
            if "Voltage" in state or "LineVoltage" in state:
                entities.append(
                    MysaDiagnosticSensor(
                        coordinator,
                        device_id,
                        device_data,
                        "Voltage",
                        "voltage",
                        UnitOfElectricPotential.VOLT,
                        SensorStateClass.MEASUREMENT,
                        SensorDeviceClass.VOLTAGE,
                        entry,
                    )
                )
            if "Current" in state:
                entities.append(
                    MysaDiagnosticSensor(
                        coordinator,
                        device_id,
                        device_data,
                        "Current",
                        "current",
                        UnitOfElectricCurrent.AMPERE,
                        SensorStateClass.MEASUREMENT,
                        SensorDeviceClass.CURRENT,
                        entry,
                    )
                )

        # Power and Current sensors (simulated or real) - supported for Baseboard and HVAC (ST-V1)
        if not api.is_ac_device(device_id):
            state = coordinator.data.get(device_id, {}) if coordinator.data else {}

            power_sensor = MysaPowerSensor(
                coordinator, device_id, device_data, api, entry
            )
            entities.append(power_sensor)

            # Virtual Energy Sensor (kWh)
            entities.append(
                MysaEnergySensor(
                    coordinator, device_id, device_data, api, entry, power_sensor
                )
            )

            # If current wasn't added as a diagnostic sensor (e.g. Lite), add it as simulated
            if "Current" not in state:
                entities.append(
                    MysaCurrentSensor(coordinator, device_id, device_data, api, entry)
                )

            # Electricity Rate (Cost) Sensor - based on device's home rate
            entities.append(
                MysaElectricityRateSensor(
                    coordinator, device_id, device_data, api, entry
                )
            )

        # === Network Diagnostic Sensors (all devices except ST-V1) ===
        # IP Address (Not available for ST-V1 cloud API)
        if not is_stv10:
            entities.append(MysaIpSensor(coordinator, device_id, device_data, entry))

        # === ST-V1-0 HVAC Specific Sensors ===
        if is_stv10:
            st_sensors = _get_stv10_diagnostic_sensors(
                coordinator.data.get(device_id, {}) if coordinator.data else {}
            )
            for _, key, unit, state_class in st_sensors:
                entities.append(
                    MysaDiagnosticSensor(
                        coordinator,
                        device_id,
                        device_data,
                        key,  # sensor_key
                        key,  # translation_key
                        unit,
                        state_class,
                        None,  # device_class
                        entry,
                    )
                )

    async_add_entities(entities)


def _get_stv10_diagnostic_sensors(
    current_state: dict[str, Any],
) -> list[tuple[Any, ...]]:
    """Get list of diagnostic sensors for ST-V1-0 based on config."""
    # 1. Common ST-V1-0 Sensors (Always create)
    sensors = [
        ("HVAC Config Index", "hvac_config_index", None, None),
        ("Heat Uses Fan", "adv_heat_uses_fan", None, None),
        ("Cool Uses Fan", "adv_cool_uses_fan", None, None),
        ("Aux Uses Fan", "adv_aux_uses_fan", None, None),
        (
            "Fan Runtime",
            "adv_fan_runtime",
            "s",
            SensorStateClass.MEASUREMENT,
        ),
        (
            "Fan Period",
            "adv_fan_period",
            "s",
            SensorStateClass.MEASUREMENT,
        ),
        ("Fan Ramp", "adv_fan_ramp", "min", SensorStateClass.MEASUREMENT),
        ("Cool Fan Delay", "adv_cool_fan_delay", "min", SensorStateClass.MEASUREMENT),
        ("Heat Fan Delay", "adv_heat_fan_delay", "min", SensorStateClass.MEASUREMENT),
        ("Cool Fan Run-on", "adv_cool_fan_run_on", "min", SensorStateClass.MEASUREMENT),
        ("Heat Fan Run-on", "adv_heat_fan_run_on", "min", SensorStateClass.MEASUREMENT),
        ("Multiple Fan Speeds", "multiple_fan_speeds", None, None),
        ("Fan Sequence", "fan_sequence", None, None),
        ("Runtime Total", "on_time", "s", SensorStateClass.TOTAL_INCREASING),
        ("Runtime Fan", "fan_on_time", "s", SensorStateClass.TOTAL_INCREASING),
        (
            "Runtime Stage 2",
            "stage_two_on_time",
            "s",
            SensorStateClass.TOTAL_INCREASING,
        ),
        (
            "Runtime Cool Stage 1",
            "stage_one_cool_on_time",
            "s",
            SensorStateClass.TOTAL_INCREASING,
        ),
        (
            "Runtime Cool Stage 2",
            "stage_two_cool_on_time",
            "s",
            SensorStateClass.TOTAL_INCREASING,
        ),
        (
            "Runtime Emergency Heat",
            "emergency_heat_on_time",
            "s",
            SensorStateClass.TOTAL_INCREASING,
        ),
        ("Secure Boot", "secure_boot", None, None),
        ("Encryption Enabled", "encryption_enabled", None, None),
        ("Private Key Status", "priv_key_ok", None, None),
        ("Public Key Hash", "pub_key_hash", None, None),
        ("Fault Test", "fault_test", None, None),
    ]

    # 2. Config-Specific Sensors (Feature Flag Based)
    # Check flags for Stage 2 Heating
    if current_state.get("heating_stage_two_exists") == 1:
        sensors.extend(
            [
                (
                    "Stage 2 Heat Delta",
                    "adv_heat_stage_two_delta",
                    UnitOfTemperature.CELSIUS,
                    SensorStateClass.MEASUREMENT,
                ),
                (
                    "Stage 2 Heat Delay",
                    "adv_heat_stage_two_delay",
                    "min",
                    SensorStateClass.MEASUREMENT,
                ),
            ]
        )

    # Check flags for Stage 2 Cooling
    if current_state.get("cooling_stage_two_exists") == 1:
        sensors.extend(
            [
                (
                    "Stage 2 Cool Delta",
                    "adv_cool_stage_two_delta",
                    UnitOfTemperature.CELSIUS,
                    SensorStateClass.MEASUREMENT,
                ),
                (
                    "Stage 2 Cool Delay",
                    "adv_cool_stage_two_delay",
                    "min",
                    SensorStateClass.MEASUREMENT,
                ),
            ]
        )

    # Check flags for Heat Pump (Reversing Valve)
    if current_state.get("is_reversible_heat_pump") == 1:
        sensors.append(
            (
                "Cool When Reversed",
                "adv_cool_when_reversed",
                None,
                None,
            )
        )

    # Filter sensors based on availability in current_state
    available_sensors = []
    for name, key, unit, state_class in sensors:
        # Check if key exists in state (handling direct value or nested dict)
        if key in current_state:
            available_sensors.append((name, key, unit, state_class))
            continue

        # Specific handling for mapped keys (fallback logic)
        # e.g. some keys might be mapped differently, but for ST-V1 most match directly
        # If any special handling is needed, add it here.
        # For now, strict key matching cleans up the "Unknown" entities.

    return available_sensors


class MysaDiagnosticSensor(
    SensorEntity,
    CoordinatorEntity[DataUpdateCoordinator[dict[str, Any]]],
):
    """Representation of a Mysa Diagnostic Sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, Any]],
        device_id: str,
        device_data: dict[str, Any],
        sensor_key: str,
        translation_key: str,
        unit: str | None,
        state_class: SensorStateClass | None,
        device_class: SensorDeviceClass | None,
        entry: ConfigEntry[MysaData],
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._sensor_key = sensor_key
        self._entry = entry
        self._device_data = device_data
        self._attr_translation_key = translation_key
        self._attr_translation_key = translation_key

        self._attr_unique_id = f"{device_id}_{sensor_key.lower()}"
        self._attr_native_unit_of_measurement = unit
        self._attr_state_class = state_class
        self._attr_device_class: Any = device_class
        self._attr_extra_state_attributes: dict[str, Any] = {}
        self._attr_should_poll = False

        # Set suggested display precision
        precision_map = {
            "Duty": 1,
            "Rssi": 0,
            "Voltage": 1,
            "Current": 2,
            "Brightness": 0,
            "HeatSink": 1,
            "Infloor": 1,
            "MaxSetpoint": 1,
            "MinSetpoint": 1,
            "MaxCurrent": 2,
            "adv_heat_stage_two_delta": 1,
            "free_heap": 0,
        }
        if sensor_key in precision_map:
            self._attr_suggested_display_precision = precision_map[sensor_key]

        # Mapping variants
        self._keys = [sensor_key]
        if sensor_key == "Duty":
            self._keys = ["dc", "Duty", "dtyCycle", "DutyCycle"]
        elif sensor_key == "Rssi":
            self._keys = ["rssi", "Rssi", "RSSI"]
        elif sensor_key == "Voltage":
            self._keys = ["volts", "Voltage", "LineVoltage"]
        elif sensor_key == "Current":
            self._keys = ["amps", "Current"]
        elif sensor_key == "Brightness":
            self._keys = ["br", "Brightness"]
        elif sensor_key == "HeatSink":
            self._keys = ["hs", "HeatSink"]
        elif sensor_key == "Infloor":
            self._keys = ["if", "Infloor", "flrSnsrTemp"]
        elif sensor_key == "MaxSetpoint":
            self._keys = ["mxs", "MaxSetpoint"]
        elif sensor_key == "MinSetpoint":
            self._keys = ["mns", "MinSetpoint"]
        elif sensor_key == "MaxCurrent":
            self._keys = ["mxc", "MaxCurrent"]
        elif sensor_key == "MinBrightness":
            self._keys = ["mnbr", "MinBrightness"]
        elif sensor_key == "MaxBrightness":
            self._keys = ["mxbr", "MaxBrightness"]
        elif sensor_key == "TimeZone":
            self._keys = ["tz", "TimeZone"]
        elif sensor_key == "free_heap":
            self._keys = ["free_heap", "freeHeap", "FreeHeap"]

        # Categorize as Diagnostic AND Disable by default
        if (
            sensor_key
            in [
                "Current",
                "Duty",
                "HeatSink",
                "MaxCurrent",
                "MinSetpoint",
                "MaxSetpoint",
                "Rssi",
                "TimeZone",
                "Voltage",
            ]
            or sensor_key.startswith("adv_")
            or sensor_key
            in [
                "hvac_config_index",
                "multiple_fan_speeds",
                "fan_sequence",
                "heating_stage_two_exists",
                "cooling_stage_two_exists",
                "is_reversible_heat_pump",
                "free_heap",
                "secure_boot",
                "encryption_enabled",
                "priv_key_ok",
                "pub_key_hash",
                "fault_test",
            ]
        ):
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
            self._attr_entity_registry_enabled_default = False

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        state = (
            self.coordinator.data.get(self._device_id)
            if self.coordinator.data
            else None
        )
        return MysaDeviceLogic.get_device_info(
            self._device_id, self._device_data, state
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        data = {"device_id": self._device_id}
        return data

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        state = (
            self.coordinator.data.get(self._device_id)
            if self.coordinator.data
            else None
        )
        if not state or (val := self._extract_value(state, self._keys)) is None:
            return None

        # Allow booleans to pass through (e.g. for HVAC fan settings)
        if isinstance(val, bool):
            return val

        # Handle percentage conversion if 0-1 range
        if self._sensor_key == "Duty":
            try:
                fval = float(val)
                return fval * 100.0 if 0 <= fval <= 1.0 else fval
            except (ValueError, TypeError):
                pass

        if self._sensor_key == "hvac_config_index":
            try:
                return int(float(val))
            except (ValueError, TypeError):
                pass

        try:
            return float(val)
        except (ValueError, TypeError):
            return str(val)

    def _extract_value(self, state: dict[str, Any] | None, keys: list[str]) -> Any:
        """Helper to extract a value from state dictionary."""
        if state is None:
            return None
        for key in keys:
            val = state.get(key)
            if val is not None:
                if isinstance(val, dict):
                    v = val.get("v")
                    if v is None:
                        v = val.get("Id")
                    return v
                return val
        return None


class MysaPowerSensor(
    SensorEntity, CoordinatorEntity[DataUpdateCoordinator[dict[str, Any]]]
):
    """Representation of a Mysa Power Sensor (Real or Simulated)."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, Any]],
        device_id: str,
        device_data: dict[str, Any],
        api: MysaApi,
        entry: ConfigEntry[MysaData],
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._api = api
        self._entry = entry
        self._device_data = device_data
        self._attr_translation_key = "power"
        self._attr_translation_key = "power"
        self._attr_unique_id = f"{device_id}_power"
        self._attr_native_unit_of_measurement = "W"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_device_class: Any = SensorDeviceClass.POWER
        self._attr_suggested_display_precision = 1
        # Use simple numeric types for native_value if possible,
        # but the base class SensorEntity expects StateType.

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        state = (
            self.coordinator.data.get(self._device_id)
            if self.coordinator.data
            else None
        )
        return MysaDeviceLogic.get_device_info(
            self._device_id, self._device_data, state
        )

    def _extract_value(self, state: dict[str, Any] | None, keys: list[str]) -> Any:
        """Helper to extract a value from state dictionary."""
        if state is None:
            return None
        for key in keys:
            val = state.get(key)
            if val is not None:
                if isinstance(val, dict):
                    v = val.get("v")
                    if v is None:
                        v = val.get("Id")
                    return v
                return val
        return None

    @property
    def native_value(self) -> StateType:
        """Calculate power from real data or simulated wattage."""
        if self.coordinator.data is None:
            return None
        state = self.coordinator.data.get(self._device_id)
        if state is None:
            return None

        # Check simulated energy flag
        force_simulated = getattr(self._api, "simulated_energy", False)

        # Get duty cycle (used in both real and simulated calculations)
        duty = self._extract_value(state, ["dc", "Duty", "dtyCycle", "DutyCycle"]) or 0
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
        wattage = float(self._entry.options.get(f"wattage_{safe_id}", 0))

        # If no per-device wattage, try old global setting (backward compat)
        if wattage == 0:
            est_current = float(self._entry.options.get("estimated_max_current", 0))
            # Default voltage to 240 if not reported
            voltage = self._extract_value(state, ["Voltage", "LineVoltage"])
            v_val = voltage if voltage else 240
            try:
                wattage = est_current * float(v_val)
            except (ValueError, TypeError):
                wattage = 0.0

        if wattage > 0:
            return round(wattage * duty_float, 1)

        return 0.0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        if self.coordinator.data is None:
            return {}
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

        attrs: dict[str, Any] = {"tracking_mode": mode}
        if mode in ["Simulated", "Forced Simulated"]:
            attrs["configured_wattage"] = wattage
        return attrs


class MysaCurrentSensor(
    SensorEntity, CoordinatorEntity[DataUpdateCoordinator[dict[str, Any]]]
):
    """Representation of a Mysa Current Sensor (Simulated)."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, Any]],
        device_id: str,
        device_data: dict[str, Any],
        api: MysaApi,
        entry: ConfigEntry[MysaData],
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._api = api
        self._entry = entry
        self._device_data = device_data
        self._attr_translation_key = "estimated_current"
        self._attr_unique_id = f"{device_id}_estimated_current"
        self._attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_device_class: Any = SensorDeviceClass.CURRENT
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_suggested_display_precision = 2

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        state = (
            self.coordinator.data.get(self._device_id)
            if self.coordinator.data
            else None
        )
        return MysaDeviceLogic.get_device_info(
            self._device_id, self._device_data, state
        )

    def _extract_value(self, state: dict[str, Any] | None, keys: list[str]) -> Any:
        """Helper to extract a value from state dictionary."""
        if state is None:
            return None
        for key in keys:
            val = state.get(key)
            if val is not None:
                if isinstance(val, dict):
                    v = val.get("v")
                    if v is None:
                        v = val.get("Id")
                    return v
                return val
        return None

    @property
    def native_value(self) -> StateType:
        """Calculate current from wattage and duty cycle."""
        state = (
            self.coordinator.data.get(self._device_id)
            if self.coordinator.data
            else None
        )
        if state is None:
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

        result = 0.0
        if wattage == 0:
            est_current = float(self._entry.options.get("estimated_max_current", 0))
            if est_current > 0:
                duty = self._extract_value(state, ["dc", "Duty", "DutyCycle"])
                if duty is not None:
                    try:
                        duty_float = float(duty)
                        if duty_float > 1:
                            duty_float = duty_float / 100.0
                        result = round(est_current * duty_float, 2)
                    except (ValueError, TypeError):
                        pass
        else:
            voltage = self._extract_value(state, ["Voltage", "LineVoltage"]) or 240
            duty = self._extract_value(state, ["dc", "Duty", "DutyCycle"])

            if duty is not None:
                try:
                    duty_float = float(duty)
                    v_float = float(voltage)
                    if duty_float > 1:
                        duty_float = duty_float / 100.0
                    # I = P / V
                    if v_float > 0:
                        result = round((wattage / v_float) * duty_float, 2)
                except (ValueError, TypeError):
                    pass

        return result

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        if self.coordinator.data is None:
            return {}
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

        attrs: dict[str, Any] = {"tracking_mode": mode}
        if mode in ["Simulated", "Forced Simulated"]:
            attrs["configured_wattage"] = wattage
        return attrs


class MysaEnergySensor(
    SensorEntity,
    RestoreEntity,
    CoordinatorEntity[DataUpdateCoordinator[dict[str, Any]]],
):
    """Integrates Power over time to provide native kWh tracking."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, Any]],
        device_id: str,
        device_data: dict[str, Any],
        api: MysaApi,
        entry: ConfigEntry[MysaData],
        power_sensor: MysaPowerSensor,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._api = api
        self._entry = entry
        self._device_data = device_data
        self._power_sensor = power_sensor
        self._attr_translation_key = "energy"
        self._attr_unique_id = f"{device_id}_energy"
        self._attr_native_unit_of_measurement = "kWh"
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_device_class: Any = SensorDeviceClass.ENERGY
        self._attr_native_value: Any = 0.0
        self._last_update: float | None = None
        self._attr_suggested_display_precision = 4

    async def async_added_to_hass(self) -> None:
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
        state = (
            self.coordinator.data.get(self._device_id)
            if self.coordinator.data
            else None
        )
        return MysaDeviceLogic.get_device_info(
            self._device_id, self._device_data, state
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
            # Power sensor native value is StateType, could be string or None
            power_val = self._power_sensor.native_value
            power: float = 0.0
            if isinstance(power_val, (int, float)):
                power = float(power_val)

            if power > 0:
                # Energy (kWh) = (Power (W) / 1000) * Time (h)
                added_energy = (power / 1000.0) * diff
                # Ensure native value is numeric before adding
                current_energy = 0.0
                if isinstance(self._attr_native_value, (int, float)):
                    current_energy = float(self._attr_native_value)
                self._attr_native_value = round(current_energy + added_energy, 4)

        self._last_update = now
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return {
            "last_integration_time": self._last_update,
            "note": "Virtual Riemann sum integration of power sensor",
        }


class MysaElectricityRateSensor(
    CoordinatorEntity[DataUpdateCoordinator[dict[str, Any]]], SensorEntity
):
    """Representation of the Electricity Rate for a device's home."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, Any]],
        device_id: str,
        device_data: dict[str, Any],
        api: MysaApi,
        entry: ConfigEntry[MysaData],
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._api = api
        self._entry = entry
        self._device_data = device_data
        self._attr_translation_key = "cost"
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
        self._attr_suggested_display_precision = 4

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        state = (
            self.coordinator.data.get(self._device_id)
            if self.coordinator.data
            else None
        )
        return MysaDeviceLogic.get_device_info(
            self._device_id, self._device_data, state
        )

    @property
    def native_value(self) -> StateType:
        """Return the electricity rate."""
        rate = self._api.get_electricity_rate(self._device_id)
        if rate is not None:
            return rate
        return None


class MysaIpSensor(
    SensorEntity, CoordinatorEntity[DataUpdateCoordinator[dict[str, Any]]]
):
    """Representation of the Device Local IP Sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, Any]],
        device_id: str,
        device_data: dict[str, Any],
        entry: ConfigEntry[MysaData],
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._device_data = device_data
        self._entry = entry
        self._attr_translation_key = "ip_address"
        self._attr_unique_id = f"{device_id}_ip_address"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        state = (
            self.coordinator.data.get(self._device_id)
            if self.coordinator.data
            else None
        )
        return MysaDeviceLogic.get_device_info(
            self._device_id, self._device_data, state
        )

    def _extract_value(self, state: dict[str, Any] | None, keys: list[str]) -> Any:
        """Helper to extract a value from state dictionary."""
        if state is None:
            return None
        for key in keys:
            val = state.get(key)
            if val is not None:
                if isinstance(val, dict):
                    v = val.get("v")
                    if v is None:
                        v = val.get("Id")
                    return v
                return val
        return None

    @property
    def native_value(self) -> StateType:
        """Return the local IP address."""
        if self.coordinator.data is None:
            return None
        state = self.coordinator.data.get(self._device_id)
        # Check multiple possible keys for IP, including space-separated
        val = self._extract_value(
            state, ["ip", "Local IP", "IPAddress", "LocalIP", "IP"]
        )
        return str(val) if val else None


class MysaTemperatureSensor(
    SensorEntity,
    CoordinatorEntity[DataUpdateCoordinator[dict[str, Any]]],
):
    """Representation of a Mysa ambient temperature sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, Any]],
        device_id: str,
        device_data: dict[str, Any],
        api: MysaApi,
        entry: ConfigEntry[MysaData],
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._api = api
        self._entry = entry
        self._device_data = device_data
        self._attr_translation_key = "temperature"
        self._attr_unique_id = f"{device_id}_temperature"
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_device_class: Any = SensorDeviceClass.TEMPERATURE
        self._attr_suggested_display_precision = 1
        self._keys = [
            "current_temp",
            "roomTemperature",
            "currentTemperature",
            "CorrectedTemp",
            "ambTemp",
            "ambient_t",
            "SensorTemp",
        ]

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        state = (
            self.coordinator.data.get(self._device_id)
            if self.coordinator.data
            else None
        )
        return MysaDeviceLogic.get_device_info(
            self._device_id, self._device_data, state
        )

    @property
    def native_value(self) -> StateType:
        """Return the ambient temperature."""
        if self.coordinator.data is None:
            return None
        state = self.coordinator.data.get(self._device_id)
        if not state:
            return None

        # Priority: CorrectedTemp, ambTemp, SensorTemp
        keys = [
            "current_temp",
            "roomTemperature",
            "currentTemperature",
            "CorrectedTemp",
            "ambTemp",
            "ambient_t",
            "SensorTemp",
        ]

        for key in keys:
            val = state.get(key)
            if val is not None:
                if isinstance(val, dict):
                    v = val.get("v")
                    if v is not None:
                        try:
                            f_val = float(v)
                            return (
                                f_val if f_val != 0 else None
                            )  # Filter 0 temp if invalid?
                        except (ValueError, TypeError):
                            pass
                else:
                    try:
                        f_val = float(val)
                        return f_val if f_val != 0 else None
                    except (ValueError, TypeError):
                        pass
        return None


class MysaHumiditySensor(
    SensorEntity,
    CoordinatorEntity[DataUpdateCoordinator[dict[str, Any]]],
):
    """Representation of a Mysa humidity sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, Any]],
        device_id: str,
        device_data: dict[str, Any],
        api: MysaApi,
        entry: ConfigEntry[MysaData],
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._api = api
        self._entry = entry
        self._device_data = device_data
        self._attr_translation_key = "humidity"
        self._attr_unique_id = f"{device_id}_humidity"
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_device_class: Any = SensorDeviceClass.HUMIDITY
        self._attr_suggested_display_precision = 1
        self._keys = ["current_humidity", "humidity", "hum", "Humidity"]

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        state = (
            self.coordinator.data.get(self._device_id)
            if self.coordinator.data
            else None
        )
        return MysaDeviceLogic.get_device_info(
            self._device_id, self._device_data, state
        )

    @property
    def native_value(self) -> StateType:
        """Return the humidity."""
        if self.coordinator.data is None:
            return None
        state = self.coordinator.data.get(self._device_id)
        if not state:
            return None

        keys = ["current_humidity", "humidity", "hum", "Humidity"]
        for key in keys:
            val = state.get(key)
            if val is not None:
                if isinstance(val, dict):
                    v = val.get("v")
                    if v is not None:
                        try:
                            return float(v)
                        except (ValueError, TypeError):
                            pass
                else:
                    try:
                        return float(val)
                    except (ValueError, TypeError):
                        pass
        return None
