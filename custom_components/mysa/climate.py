"""Climate platform for Mysa."""

from __future__ import annotations

# pylint: disable=abstract-method, too-many-lines, too-many-public-methods
# Justification:
# abstract-method: Inherits from HA mixins (RestoreEntity) which may have abstract methods.
# too-many-lines: Handles multiple climate device types (Baseboard, AC, ST-V1-0) in one file.
# too-many-public-methods: Climate entities require many property overrides.
import asyncio
from datetime import datetime
import logging
import time
from typing import Any, cast

import voluptuous as vol

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_TEMPERATURE,
    PRECISION_TENTHS,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from homeassistant.util import dt as dt_util

from . import MysaData
from .const import (
    AC_FAN_AUTO,
    AC_FAN_HIGH,
    AC_FAN_LOW,
    AC_FAN_MEDIUM,
    AC_FAN_MODES,
    AC_FAN_MODES_REVERSE,
    AC_KEY_FAN_AUTO,
    AC_KEY_FAN_HIGH,
    AC_KEY_FAN_LOW,
    AC_KEY_FAN_MEDIUM,
    AC_KEY_SWING_V_ON,
    AC_MODE_AUTO,
    AC_MODE_COOL,
    AC_MODE_DRY,
    AC_MODE_FAN_ONLY,
    AC_MODE_HEAT,
    AC_MODE_OFF,
    AC_SWING_MODES,
    DOMAIN,
    PRESET_HOLD,
    PRESET_SCHEDULE,
    SCHEDULE_MODE_FOLLOWING,
    SCHEDULE_MODE_HOLD,
    SERVICE_HOLD_UNTIL,
)
from .device import MysaDeviceLogic
from .mysa_api import MysaApi

PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: ConfigEntry[MysaData],
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Mysa climate devices."""
    coordinator = entry.runtime_data.coordinator
    api = entry.runtime_data.api

    # Get devices to create entities
    devices = api.devices
    entities: list[ClimateEntity] = []
    for device_id, device_data in devices.items():
        # Use appropriate entity class based on device type
        model = device_data.get("Model", "")
        if "ST-V1-0" in model:
            _LOGGER.debug("Creating ST-V1-0 climate entity for %s", device_id)
            entities.append(
                MysaSTV10Climate(coordinator, device_id, device_data, api, entry)
            )
        elif api.is_ac_device(device_id):
            _LOGGER.debug("Creating AC climate entity for %s", device_id)
            entities.append(
                MysaACClimate(coordinator, device_id, device_data, api, entry)
            )
        else:
            entities.append(
                MysaClimate(coordinator, device_id, device_data, api, entry)
            )

    async_add_entities(entities)

    # Register the hold-until entity service (a timed hold can't be a preset, since
    # it needs a timestamp argument). Applies to the climate platform's entities.
    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_HOLD_UNTIL,
        {
            vol.Required("until"): cv.datetime,
            vol.Optional("temperature"): vol.Coerce(float),
        },
        "async_hold_until",
    )


class MysaClimate(
    ClimateEntity,
    CoordinatorEntity[DataUpdateCoordinator[dict[str, Any]]],
):
    """Representation of a Mysa Thermostat."""

    _attr_supported_features: Any = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_OFF
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.PRESET_MODE
    )
    _attr_preset_modes = [PRESET_SCHEDULE, PRESET_HOLD]
    _attr_min_temp = 5.0
    _attr_max_temp = 30.0
    _attr_precision = PRECISION_TENTHS
    _attr_target_temperature_step = 0.5

    _attr_has_entity_name = True
    _attr_name = None
    _attr_translation_key = "thermostat"

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
        self._device_data = device_data
        self._api = api
        self._entry = entry
        self._attr_unique_id = device_id
        self._pending_updates: dict[str, dict[str, Any]] = {}
        self._has_logged_sensortemp_warning = False

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        state = self._get_state_data()
        return MysaDeviceLogic.get_device_info(
            self._device_id, self._device_data, state
        )

    def _get_value(self, key: str) -> Any:
        """Get value from state, handling both dict (v/t) and direct value."""
        if self.coordinator.data is None:
            return None
        state = self.coordinator.data.get(self._device_id)
        if not state:
            return None
        val = state.get(key)
        if isinstance(val, dict):
            return val.get("v")
        return val

    @property
    def temperature_unit(self) -> str:
        """Return the unit of measurement."""
        state = self._get_state_data()
        if state and state.get("temperature_format") == "F":
            return UnitOfTemperature.FAHRENHEIT
        return UnitOfTemperature.CELSIUS

    @property
    def target_temperature_step(self) -> float:
        """Return the supported step of target temperature."""
        if self.temperature_unit == UnitOfTemperature.FAHRENHEIT:
            return 1.0
        return 0.5  # Default for Celsius

    def _convert_to_display(self, temp_c: float | None) -> float | None:
        """Convert Celsius value to display unit (F or C)."""
        if temp_c is None:
            return None
        if self.temperature_unit == UnitOfTemperature.FAHRENHEIT:
            return round(temp_c * 9 / 5 + 32)
        return round(temp_c, 1)  # Round to 1 decimal place for Celsius

    def _convert_from_display(self, temp: float) -> float:
        """Convert display value (F or C) to Celsius."""
        if self.temperature_unit == UnitOfTemperature.FAHRENHEIT:
            return (temp - 32) * 5 / 9
        return temp

    @property
    def current_temperature(self) -> float | None:
        """Return current temperature."""
        state = self._get_state_data()
        if not state:
            return None

        # Determine which temperature to use
        # For Infloor devices, follow SensorMode preference (0=Ambient/Air, 1=Floor)
        model = str(self._device_data.get("Model", ""))
        is_infloor = "INF-V1" in model or "Floor" in model
        sensor_mode = state.get("SensorMode")

        if is_infloor and sensor_mode == 1:
            # Floor Mode: prioritize Infloor temp
            primary_keys = ["Infloor", "if", "flrSnsrTemp"]
            _LOGGER.debug(
                "Device %s is in Floor Mode, using Infloor sensor", self._device_id
            )
        else:
            # Ambient Mode or non-Infloor device: prioritize Ambient temp
            primary_keys = [
                "current_temp",
                "current_temp_raw",
                "CorrectedTemp",
                "ambTemp",
                "ambient_t",
            ]

        val = self._extract_value(state, primary_keys)

        if val is None:
            # Fallback to SensorTemp if primary choice is unavailable
            val = self._extract_value(state, ["SensorTemp"])
            if val is not None:
                if not self._has_logged_sensortemp_warning:
                    _LOGGER.warning(
                        "Device %s is using 'SensorTemp' as a temperature fallback. "
                        "Note: This raw sensor value is often inaccurate/elevated due to "
                        "heat from the device's own electronics.",
                        self._device_id,
                    )
                    self._has_logged_sensortemp_warning = True
        else:
            # We found a primary key, reset the warning flag
            self._has_logged_sensortemp_warning = False

        _LOGGER.debug(
            "Device %s current_temp raw value: %s (mode: %s)",
            self._device_id,
            val,
            sensor_mode,
        )
        if val is not None:
            try:
                f_val = float(val)
                # Apply conversion
                return self._convert_to_display(f_val if f_val != 0 else None)
            except (ValueError, TypeError):
                pass
        return None

    @property
    def target_temperature(self) -> float | None:
        """Return target temperature."""
        state = self._get_state_data()
        if not state:
            return None

        # Priority: MQTT keys then HTTP keys
        val = self._extract_value(state, ["stpt", "setpoint_t", "SetPoint"])

        _LOGGER.debug("Device %s target_temp raw value: %s", self._device_id, val)
        # Avoid resetting to 0.0 if device reports 0 (common in Dry mode)
        current = float(val) if val is not None and float(val) != 0 else None
        val = self._get_sticky_value("target_temperature", current)
        return self._convert_to_display(float(val)) if val is not None else None

    @property
    def target_temperature_low(self) -> float | None:
        """Return the lower bound target temperature (Heat)."""
        state = self._get_state_data()
        if not state:
            return None
        val = self._extract_value(
            state, ["target_heat", "heatSetpoint", "heatsetpoint"]
        )
        val = self._get_sticky_value("target_temperature_low", val)
        return self._convert_to_display(float(val)) if val is not None else None

    @property
    def target_temperature_high(self) -> float | None:
        """Return the upper bound target temperature (Cool)."""
        state = self._get_state_data()
        if not state:
            return None
        val = self._extract_value(
            state, ["target_cool", "coolSetpoint", "coolsetpoint"]
        )
        val = self._get_sticky_value("target_temperature_high", val)
        return self._convert_to_display(float(val)) if val is not None else None

    @property
    def current_humidity(self) -> float | None:
        """Return humidity."""
        state = self._get_state_data()
        if not state:
            return None

        val = self._extract_value(state, ["current_humidity", "hum", "Humidity"])
        if val is not None:
            return float(val)
        return None

    def _get_state_data(self) -> dict[str, Any] | None:
        """Helper to get state data from coordinator."""
        if self.coordinator.data is None:
            _LOGGER.debug("MysaClimate %s: coordinator.data is None", self._device_id)
            return None
        data = cast(dict[str, Any] | None, self.coordinator.data.get(self._device_id))
        if data is None:
            _LOGGER.debug(
                "MysaClimate %s: device not in coordinator.data", self._device_id
            )
        return data

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
                        # Fallback for some structures like ACState
                        # But typically 'v' is what we want.
                        # Or if it's a device object inside zone?
                        v = val.get("Id")
                    return v
                return val
        return None

    async def _update_state_cache(self, key: str, value: Any) -> None:
        """Update local state cache immediately."""
        if self.coordinator.data is None:
            # Fixing the previous bad cast: we want to assign an empty dict to data,
            # and cast it to Any to satisfy the linter's 'Never' inferred type if needed.
            self.coordinator.data = cast(Any, {})
        if self._device_id not in self.coordinator.data:
            self.coordinator.data[self._device_id] = {}

        # Safely update the dictionary item
        device_data = self.coordinator.data[self._device_id]
        if isinstance(device_data, dict):
            device_data[key] = value

    def _get_sticky_value(self, key: str, current_value: Any) -> Any:
        """Get value with optimistic 'sticky' logic.

        When a user changes a setting in UI, we want to show that new value immediately
        (optimistic update) and keep showing it until the device confirms the change
        via MQTT/HTTP update. This prevents the UI 'snap-back' effect where the slider
        jumps back to the old value while waiting for the cloud round-trip.
        """
        if key in self._pending_updates:
            pending = self._pending_updates[key]
            # Expire pending update after 10 seconds
            if time.time() - pending["ts"] < 10:
                # If current value matches pending, update is confirmed
                if current_value == pending["value"]:
                    del self._pending_updates[key]
                    return current_value
                return pending["value"]
            del self._pending_updates[key]
        return current_value

    def _set_sticky_value(self, key: str, value: Any) -> None:
        """Set a pending optimistic value."""
        self._pending_updates[key] = {"value": value, "ts": time.time()}

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return hvac mode."""
        state = self._get_state_data()
        if not state:
            return HVACMode.HEAT  # Default fallback

        # Priority: MQTT key (md) then user-confirmed source (TstatMode) then generic (Mode)
        mode_id = self._extract_value(state, ["md", "mode", "TstatMode", "Mode"])

        # Determine Enum result
        if mode_id == 1:
            result = HVACMode.OFF
        elif mode_id == 3:
            result = HVACMode.HEAT
        else:
            result = HVACMode.HEAT

        _LOGGER.debug(
            "Device %s hvac_mode: mode_id=%s -> result=%s",
            self._device_id,
            mode_id,
            result,
        )

        val = self._get_sticky_value("hvac_mode", result)
        try:
            return HVACMode(str(val))
        except (ValueError, TypeError):
            return result

    @property
    def hvac_action(self) -> HVACAction:
        """Return hvac action."""
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF

        state = self._get_state_data()
        if not state:
            return HVACAction.IDLE

        # User Request: Dynamic Idle/Heating based on temperature setpoint
        current_str = self._extract_value(
            state, ["ambTemp", "CorrectedTemp", "SensorTemp"]
        )
        target_str = self._extract_value(state, ["stpt", "SetPoint"])

        if current_str is not None and target_str is not None:
            try:
                current = float(current_str)
                target = float(target_str)

                # If actively heating mode is on
                if self.hvac_mode == HVACMode.HEAT:
                    # If we are below target, we are heating (or trying to)
                    if current < target:
                        return HVACAction.HEATING
                    # If we are over or equal, we are idle
                    return HVACAction.IDLE
            except (ValueError, TypeError):
                pass

        # Fallback: Priority checking Duty Cycle if temps unavailable
        duty = self._extract_value(state, ["dc", "Duty", "dtyCycle", "DutyCycle"])
        if duty is not None and float(duty) > 0:
            return HVACAction.HEATING

        return HVACAction.IDLE

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return {
            "model": self._device_data.get("Model"),
        }

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Return supported hvac modes."""
        return [HVACMode.HEAT, HVACMode.OFF]

    @property
    def preset_mode(self) -> str | None:
        """Return the current preset: following the schedule vs. an indefinite hold.

        Read from the device's reported ScheduleMode (1=following, 2=indefinite hold);
        falls back to None when the device hasn't reported it yet.
        """
        state = self._get_state_data()
        sched = self._extract_value(state, ["ScheduleMode"]) if state else None
        if sched == SCHEDULE_MODE_HOLD:
            result: str | None = PRESET_HOLD
        elif sched == SCHEDULE_MODE_FOLLOWING:
            result = PRESET_SCHEDULE
        else:
            result = None
        return self._get_sticky_value("preset_mode", result)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return
        try:
            # Round to target step (default 0.5 C or 1.0 F)
            # Logic: Input `temp` is in display unit (F or C).
            # We want to store sticky in display unit, but send C to API.
            step = self.target_temperature_step
            temp = round(temp / step) * step

            # Optimistic update (in display unit)
            self._set_sticky_value("target_temperature", temp)

            # Convert to Celsius for API
            temp_c = self._convert_from_display(temp)
            # Ensure 0.5 precision for device
            temp_c = round(temp_c * 2) / 2

            await self._api.set_target_temperature(self._device_id, temp_c)
            self.async_write_ha_state()
        except Exception as e:
            if "target_temperature" in self._pending_updates:
                del self._pending_updates["target_temperature"]
            self.async_write_ha_state()
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="set_temperature_failed",
                translation_placeholders={"error": str(e)},
            ) from e

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target hvac mode."""
        try:
            # Optimistic update
            self._set_sticky_value("hvac_mode", hvac_mode)

            await self._api.set_hvac_mode(self._device_id, str(hvac_mode))
            self.async_write_ha_state()
        except Exception as e:
            if "hvac_mode" in self._pending_updates:
                del self._pending_updates["hvac_mode"]
            self.async_write_ha_state()
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="set_hvac_mode_failed",
                translation_placeholders={"error": str(e)},
            ) from e

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set preset mode: follow the schedule or hold indefinitely."""
        try:
            self._set_sticky_value("preset_mode", preset_mode)
            if preset_mode == PRESET_SCHEDULE:
                await self._api.resume_schedule(self._device_id)
            elif preset_mode == PRESET_HOLD:
                await self._api.set_hold(self._device_id)
            else:
                raise ValueError(f"Unsupported preset_mode: {preset_mode}")
            self.async_write_ha_state()
        except Exception as e:
            if "preset_mode" in self._pending_updates:
                del self._pending_updates["preset_mode"]
            self.async_write_ha_state()
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="set_preset_mode_failed",
                translation_placeholders={"error": str(e)},
            ) from e

    async def async_hold_until(
        self, until: datetime, temperature: float | None = None
    ) -> None:
        """Service handler: hold (optionally at a temperature) until a time, then resume the schedule."""
        try:
            ts = int(dt_util.as_timestamp(until))
            temp_c: float | None = None
            if temperature is not None:
                temp_c = round(self._convert_from_display(float(temperature)) * 2) / 2
                self._set_sticky_value(
                    "target_temperature", self._convert_to_display(temp_c)
                )
            await self._api.hold_until(self._device_id, ts, temp_c)
            self.async_write_ha_state()
        except Exception as e:
            if "target_temperature" in self._pending_updates:
                del self._pending_updates["target_temperature"]
            self.async_write_ha_state()
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="hold_until_failed",
                translation_placeholders={"error": str(e)},
            ) from e

    async def async_turn_off(self) -> None:
        """Turn the entity off."""
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_turn_on(self) -> None:
        """Turn the entity on."""
        await self.async_set_hvac_mode(HVACMode.HEAT)


class MysaACClimate(MysaClimate):
    """Mysa AC Climate Entity with fan and swing mode support."""

    @property
    def supported_features(self) -> ClimateEntityFeature:
        """Return supported features for AC."""
        features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.TURN_OFF
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.FAN_MODE
            | ClimateEntityFeature.SWING_MODE
        )
        # Enable range support if in HEAT_COOL mode for ST-V1-0 devices
        if self.hvac_mode == HVACMode.HEAT_COOL:
            features |= ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
        return features

    # AC temperature range (from SupportedCaps)
    _attr_min_temp = 16.0
    _attr_max_temp = 31.0
    # _attr_target_temperature_step removed in favor of dynamic property

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, Any]],
        device_id: str,
        device_data: dict[str, Any],
        api: MysaApi,
        entry: ConfigEntry[MysaData],
    ) -> None:
        """Initialize AC climate entity."""
        super().__init__(coordinator, device_id, device_data, api, entry)
        # self._attr_name = None # Inherits None from MysaClimate
        # which is correct for primary entity

        # Get supported capabilities from device data
        self._supported_caps = device_data.get("SupportedCaps", {})

        # Initialize supported mode lists (to avoid W0201)
        self._supported_hvac_modes: list[HVACMode] = [HVACMode.OFF]
        self._supported_fan_modes: list[str] = ["auto"]
        self._supported_swing_modes: list[str] = ["auto"]

        # Build dynamic mode/fan/swing lists from SupportedCaps
        self._build_supported_options()

        # Track last used mode for smart turn-on
        self._last_mode: HVACMode | None = None

    def _build_supported_options(self) -> None:
        """Build lists of supported modes from SupportedCaps."""
        modes = self._supported_caps.get("modes", {})

        # Extract dynamic temperature limits if available
        temp_range = self._supported_caps.get("tempRange")
        if isinstance(temp_range, list) and len(temp_range) >= 2:
            self._attr_min_temp = float(temp_range[0])
            self._attr_max_temp = float(temp_range[1])

        # Extract temperature step (usually 1.0 for AC units)
        self._temp_step = float(self._supported_caps.get("temperatureStep", 1.0))

        self._build_hvac_modes(modes)
        self._build_fan_modes(modes)
        self._build_swing_modes(modes)

        _LOGGER.debug(
            "AC %s supported modes: hvac=%s, fan=%s, swing=%s, limits=[%s, %s], step=%s",
            self._device_id,
            self._supported_hvac_modes,
            self._supported_fan_modes,
            self._supported_swing_modes,
            self._attr_min_temp,
            self._attr_max_temp,
            self._temp_step,
        )

    @property
    def target_temperature_step(self) -> float:
        """Return the supported step of target temperature for AC."""
        return getattr(self, "_temp_step", 1.0)

    def _build_hvac_modes(self, modes: dict[str, Any]) -> None:
        """Map SupportedCaps mode keys to HVAC modes."""
        mode_mapping = {
            2: HVACMode.HEAT_COOL,  # Auto
            3: HVACMode.HEAT,
            4: HVACMode.COOL,
            5: HVACMode.FAN_ONLY,
            6: HVACMode.DRY,
        }

        for mode_key in modes:
            try:
                mode_int = int(mode_key)
                if mode_int in mode_mapping:
                    self._supported_hvac_modes.append(mode_mapping[mode_int])
            except ValueError:
                pass

    def _build_fan_modes(self, modes: dict[str, Any]) -> None:
        """Aggregate fan speeds from all available mode's capabilities."""
        supported_fan_speeds: set[int] = set()
        for mode_caps in modes.values():
            fan_speeds = mode_caps.get("fanSpeeds", [])
            if fan_speeds:
                supported_fan_speeds.update(fan_speeds)

        self._supported_fan_modes = []
        if supported_fan_speeds:
            for speed in sorted(supported_fan_speeds):
                fan_name = AC_FAN_MODES.get(speed)
                if fan_name:
                    self._supported_fan_modes.append(fan_name)

        # Discovery via KeyIDs (as seen in APK) if SupportedCaps has limited data
        keys = self._supported_caps.get("keys", [])
        if keys:
            key_to_speed = {
                AC_KEY_FAN_AUTO: AC_FAN_AUTO,
                AC_KEY_FAN_LOW: AC_FAN_LOW,
                AC_KEY_FAN_MEDIUM: AC_FAN_MEDIUM,
                AC_KEY_FAN_HIGH: AC_FAN_HIGH,
            }
            for speed_key, speed_val in key_to_speed.items():
                if speed_key in keys:
                    fan_name = AC_FAN_MODES.get(speed_val)
                    if fan_name and fan_name not in self._supported_fan_modes:
                        self._supported_fan_modes.append(fan_name)

        # Sort the final list to maintain consistent UI order
        self._supported_fan_modes.sort(
            key=lambda x: list(AC_FAN_MODES.values()).index(x)
            if x in AC_FAN_MODES.values()
            else 99
        )

    def _build_swing_modes(self, modes: dict[str, Any]) -> None:
        """Aggregate swing positions from all available mode's capabilities."""
        supported_swings: set[int] = set()
        for mode_caps in modes.values():
            vertical_swings = mode_caps.get("verticalSwing", [])
            if vertical_swings:
                supported_swings.update(vertical_swings)

        self._supported_swing_modes = []
        if supported_swings:
            for pos in sorted(supported_swings):
                swing_name = AC_SWING_MODES.get(pos)
                if swing_name:
                    self._supported_swing_modes.append(swing_name)

        # Discovery via KeyIDs for swing if missing in modes
        keys = self._supported_caps.get("keys", [])
        if not self._supported_swing_modes and keys:
            if AC_KEY_SWING_V_ON in keys:
                # If vertical swing key is present, provide core modes
                for mode in ["off", "auto"]:
                    if mode not in self._supported_swing_modes:
                        self._supported_swing_modes.append(mode)

        # Sort the final list
        self._supported_swing_modes.sort(
            key=lambda x: list(AC_SWING_MODES.values()).index(x)
            if x in AC_SWING_MODES.values()
            else 99
        )

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Return supported hvac modes for AC."""
        return self._supported_hvac_modes

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return current hvac mode for AC."""
        state = self._get_state_data()
        if not state:
            return HVACMode.OFF

        # Get mode from TstatMode or ACMode
        mode_id = self._extract_value(
            state, ["md", "mode", "TstatMode", "ACMode", "Mode"]
        )

        # Map Mysa mode to HA mode
        mode_mapping = {
            AC_MODE_OFF: HVACMode.OFF,
            AC_MODE_AUTO: HVACMode.HEAT_COOL,
            AC_MODE_HEAT: HVACMode.HEAT,
            AC_MODE_COOL: HVACMode.COOL,
            AC_MODE_FAN_ONLY: HVACMode.FAN_ONLY,
            AC_MODE_DRY: HVACMode.DRY,
        }

        if mode_id is not None:
            try:
                result = mode_mapping.get(int(mode_id), HVACMode.OFF)
            except (ValueError, TypeError):
                result = HVACMode.OFF
        else:
            result = HVACMode.OFF

        _LOGGER.debug(
            "AC %s hvac_mode: mode_id=%s -> result=%s", self._device_id, mode_id, result
        )
        return result

    @property
    def hvac_action(self) -> HVACAction:
        """Return hvac action for AC."""
        mode = self.hvac_mode
        action = HVACAction.IDLE

        mode_to_action: dict[HVACMode | None, HVACAction] = {
            HVACMode.OFF: HVACAction.OFF,
            HVACMode.COOL: HVACAction.COOLING,
            HVACMode.HEAT: HVACAction.HEATING,
            HVACMode.DRY: HVACAction.DRYING,
            HVACMode.FAN_ONLY: HVACAction.FAN,
        }

        if mapped_action := mode_to_action.get(mode):
            return mapped_action

        if mode == HVACMode.HEAT_COOL:
            state = self._get_state_data() or {}
            current = self._extract_value(
                state, ["ambTemp", "CorrectedTemp", "SensorTemp"]
            )
            target = self._extract_value(state, ["stpt", "SetPoint"])

            # 1. Check for IDLE (Temperature Satisfied)
            if current is not None and target is not None:
                try:
                    # If within 1.0 degree deadband, consider IDLE
                    if abs(float(current) - float(target)) < 1.0:
                        return HVACAction.IDLE
                except (ValueError, TypeError):
                    pass

            ac_mode = state.get("ACMode")
            # 2. Check internal ACMode (3=Heat, 4=Cool)
            if ac_mode == 3:
                action = HVACAction.HEATING
            elif ac_mode == 4:
                action = HVACAction.COOLING
            # 3. Fallback based on temperature difference if ACMode is missing
            elif current and target:
                if float(current) > float(target):
                    action = HVACAction.COOLING
                elif float(current) < float(target):
                    action = HVACAction.HEATING

        return action

    @property
    def fan_modes(self) -> list[str]:
        """Return supported fan modes."""
        return self._supported_fan_modes

    @property
    def fan_mode(self) -> str | None:
        """Return current fan mode."""
        state = self._get_state_data()
        if not state:
            return "auto"

        # Get fan speed value
        fan_val = self._extract_value(state, ["fn", "FanSpeed"])
        if fan_val is not None:
            return str(AC_FAN_MODES.get(int(fan_val), "auto"))

        # Try from normalized FanMode
        cloud_val = state.get("FanMode", "auto")
        return str(self._get_sticky_value("fan_mode", cloud_val))

    @property
    def swing_modes(self) -> list[str]:
        """Return supported swing modes."""
        return self._supported_swing_modes

    @property
    def swing_mode(self) -> str | None:
        """Return current swing mode (vertical)."""
        # Hide swing mode if not in a mode that typically supports it
        if self.hvac_mode not in (
            HVACMode.HEAT,
            HVACMode.COOL,
            HVACMode.HEAT_COOL,
            HVACMode.FAN_ONLY,
        ):
            return None

        state = self._get_state_data()
        if not state:
            return "auto"

        # Get swing state value
        swing_val = self._extract_value(state, ["ss", "SwingState"])
        if swing_val is not None:
            return str(AC_SWING_MODES.get(int(swing_val), "auto"))

        # Try from normalized SwingMode
        cloud_val = state.get("SwingMode", "auto")
        return str(self._get_sticky_value("swing_mode", cloud_val))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes for AC."""
        attrs = super().extra_state_attributes
        state = self._get_state_data()

        if state:
            # Add AC-specific attributes
            attrs["horizontal_swing"] = self._extract_value(
                state, ["ssh", "SwingStateHorizontal"]
            )
            attrs["ac_power"] = state.get("ACPower")

        return attrs

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new HVAC mode for AC."""
        try:
            # Optimistic update
            self._set_sticky_value("hvac_mode", hvac_mode)
            if hvac_mode != HVACMode.OFF:
                self._last_mode = hvac_mode

            await self._api.set_hvac_mode(self._device_id, str(hvac_mode))
            self.async_write_ha_state()
        except Exception as e:
            if "hvac_mode" in self._pending_updates:
                del self._pending_updates["hvac_mode"]
            self.async_write_ha_state()
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="set_ac_hvac_mode_failed",
                translation_placeholders={"error": str(e)},
            ) from e

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        try:
            step = self.target_temperature_step

            # Handle range if provided (Heat/Cool Auto)
            if (low := kwargs.get(ATTR_TARGET_TEMP_LOW)) is not None and (
                high := kwargs.get(ATTR_TARGET_TEMP_HIGH)
            ) is not None:
                # Optimistic update
                self._set_sticky_value("target_temperature_low", low)
                self._set_sticky_value("target_temperature_high", high)

                # Convert to C for API (AC usually expects int C)
                low_c = self._convert_from_display(low)
                high_c = self._convert_from_display(high)
                # Ensure int for AC? API seems to handle floats but usually ACs use ints.
                # Mysa app likely sends ints for AC.
                # Let's round to nearest int for AC specifically to be safe?
                # The API layer set_target_temperature_range just passes float.
                # Let's keep consistent with MysaClimate base logic: round to step then convert.

                await self._api.set_target_temperature_range(
                    self._device_id, low_c, high_c
                )
                self.async_write_ha_state()
                return

            if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
                return

            temp = round(temperature / step) * step

            # Optimistic update
            self._set_sticky_value("target_temperature", temp)

            # Convert to C
            temp_c = self._convert_from_display(temp)

            await self._api.set_target_temperature(self._device_id, temp_c)
            self.async_write_ha_state()
        except Exception as e:
            if "target_temperature" in self._pending_updates:
                del self._pending_updates["target_temperature"]
            self.async_write_ha_state()
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="set_ac_temperature_failed",
                translation_placeholders={"error": str(e)},
            ) from e

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set new fan mode."""
        try:
            # Optimistic update
            fan_val = AC_FAN_MODES_REVERSE.get(fan_mode.lower())
            state = self._get_state_data()
            if state is not None and fan_val is not None:
                state["fn"] = fan_val
                state["FanSpeed"] = {"v": fan_val, "t": int(time.time())}
                state["FanMode"] = fan_mode.lower()

            await self._api.set_ac_fan_speed(self._device_id, fan_mode)
            self.async_write_ha_state()
        except Exception as e:
            if "fan_mode" in self._pending_updates:
                del self._pending_updates["fan_mode"]
            self.async_write_ha_state()
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="set_ac_fan_mode_failed",
                translation_placeholders={"error": str(e)},
            ) from e

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Set new swing mode (vertical)."""
        try:
            # Optimistic update
            self._set_sticky_value("swing_mode", swing_mode)

            await self._api.set_ac_swing_mode(self._device_id, swing_mode)
            self.async_write_ha_state()
        except Exception as e:
            if "swing_mode" in self._pending_updates:
                del self._pending_updates["swing_mode"]
            self.async_write_ha_state()
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="set_ac_swing_mode_failed",
                translation_placeholders={"error": str(e)},
            ) from e

    async def async_turn_on(self) -> None:
        """Turn the AC on (restoring last mode if available)."""
        target_mode = self._last_mode

        if (
            target_mode is None
            or target_mode == HVACMode.OFF
            or target_mode not in self.hvac_modes
        ):
            # Try to use Auto if available, else Heat, else Cool
            target_mode = HVACMode.HEAT_COOL
            if HVACMode.HEAT_COOL not in self.hvac_modes:
                target_mode = (
                    HVACMode.HEAT if HVACMode.HEAT in self.hvac_modes else HVACMode.COOL
                )

        await self.async_set_hvac_mode(target_mode)


class MysaSTV10Climate(MysaClimate):
    """Mysa ST-V1-0 Climate Entity (AWS Shadow)."""

    @property
    def supported_features(self) -> ClimateEntityFeature:
        """Return supported features for ST-V1-0."""
        features = ClimateEntityFeature.TURN_OFF | ClimateEntityFeature.TURN_ON
        mode = self.hvac_mode
        if mode == HVACMode.HEAT_COOL:
            features |= ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
        elif mode in (HVACMode.HEAT, HVACMode.COOL):
            features |= ClimateEntityFeature.TARGET_TEMPERATURE

        # Linc devices often support fan mode
        features |= ClimateEntityFeature.FAN_MODE

        return features

    # ST-V1-0 HVAC modes: 0=Off, 1=Auto, 3=Cool, 4=Heat, 7=Fan
    _attr_hvac_modes = [
        HVACMode.OFF,
        HVACMode.HEAT_COOL,  # Auto
        HVACMode.COOL,
        HVACMode.HEAT,
        HVACMode.FAN_ONLY,
    ]

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, Any]],
        device_id: str,
        device_data: dict[str, Any],
        api: MysaApi,
        entry: ConfigEntry[MysaData],
    ) -> None:
        """Initialize the ST-V1-0 climate entity."""
        super().__init__(coordinator, device_id, device_data, api, entry)
        self._last_mode: HVACMode | None = None
        self._retry_fetch_task: asyncio.Task[None] | None = None

        # Initialize temperature step from capabilities
        cap = api.device_caps.get(device_id)
        if cap:
            self._attr_target_temperature_step = cap.target_temperature_step
        else:
            self._attr_target_temperature_step = 0.5

    @property
    def target_temperature_step(self) -> float:
        """Return the supported step of target temperature from capabilities."""
        if self.temperature_unit == UnitOfTemperature.FAHRENHEIT:
            return 1.0
        return float(self._attr_target_temperature_step or 0.5)

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity will be removed from hass."""
        if self._retry_fetch_task:
            self._retry_fetch_task.cancel()
            self._retry_fetch_task = None
        await super().async_will_remove_from_hass()

    def _async_ensure_data(self) -> None:
        """Ensure data exists by retrying fetch with Fibonacci backoff."""
        if self._retry_fetch_task and not self._retry_fetch_task.done():
            return

        async def _fetch_loop() -> None:
            # Fibonacci sequence: 1, 1, 2, 3, 5, 8, 13, 21, 34, 34...
            delays = [1, 1, 2, 3, 5, 8, 13, 21, 34]
            idx = 0
            # ST-V1-0 shadows (heatSetpoint/coolSetpoint) are critical but sometimes slow to arrive.
            # We fetch until we have at least one or hit a max attempt limit.
            max_attempts = 20
            for _attempt in range(max_attempts):
                # Check if data arrived
                state = self._get_state_data()
                if state and ("target_heat" in state or "target_cool" in state):
                    _LOGGER.debug(
                        "MysaSTV10Climate %s: Setpoint data arrived, stopping fetch loop",
                        self._device_id,
                    )
                    break

                # Using public fetch method
                await self._api.fetch_stv10_shadows(self._device_id)

                # Wait for next delay
                delay = delays[idx] if idx < len(delays) else 34
                if idx < len(delays):
                    idx += 1

                await asyncio.sleep(delay)

        self._retry_fetch_task = self.hass.async_create_task(_fetch_loop())

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return hvac mode for ST-V1-0."""
        state = self._get_state_data()

        # Priority: Optimistic -> MQTT (md/mode) -> HTTP (Mode)
        mode_id = self._extract_value(state, ["md", "mode", "Mode"])

        mapping = {
            0: HVACMode.OFF,
            1: HVACMode.HEAT_COOL,
            3: HVACMode.COOL,
            4: HVACMode.HEAT,
            7: HVACMode.FAN_ONLY,
        }

        # If getting a valid mode, resolve it
        current_mode = None
        if mode_id is not None:
            current_mode = mapping.get(int(mode_id))

        # Handle sticky/optimistic updates
        val = self._get_sticky_value("hvac_mode", current_mode)

        # If sticky value is valid, return it
        if isinstance(val, HVACMode):
            if current_mode is not None:
                self._last_mode = current_mode
            return val

        # If data is missing (temporarily), stick to last known if available to prevent flapping
        # This prevents 'capabilities updating too often' if the mode key flickers
        if self._last_mode is not None:
            return self._last_mode

        return None

    @property
    def target_temperature(self) -> float | None:
        """Return target temperature."""
        state = self._get_state_data()
        if not state:
            _LOGGER.warning(
                "MysaSTV10Climate %s: No state data available", self._device_id
            )
            if self.hass:
                self._async_ensure_data()
            return None

        # ST-V1-0 has separate Heat/Cool targets
        mode = self.hvac_mode

        _LOGGER.debug(
            "MysaSTV10Climate %s: determining target_temperature for mode '%s'",
            self._device_id,
            mode,
        )

        if mode in (HVACMode.OFF, HVACMode.FAN_ONLY, HVACMode.HEAT_COOL):
            _LOGGER.debug(
                "MysaSTV10Climate %s: target_temperature is None because mode is %s",
                self._device_id,
                mode,
            )
            return None

        if mode == HVACMode.COOL:
            temp = self._extract_value(
                state, ["target_cool", "stpt", "sp", "SetPoint", "TstatSetpoint"]
            )
            _LOGGER.debug(
                "MysaSTV10Climate %s: Cool mode, extracted target_temp=%s",
                self._device_id,
                temp,
            )
            if temp is not None:
                return self._convert_to_display(float(temp))

            # Fallback for UI visibility at startup
            _LOGGER.debug(
                "MysaSTV10Climate %s: Cool target is None, waiting for update",
                self._device_id,
            )
            if self.hass:
                self._async_ensure_data()
            return None

        # Default to Heat or generic
        temp = self._extract_value(
            state, ["target_heat", "stpt", "sp", "SetPoint", "TstatSetpoint"]
        )
        _LOGGER.debug(
            "MysaSTV10Climate %s: Heat mode, extracted target_temp=%s",
            self._device_id,
            temp,
        )
        if temp is not None:
            return self._convert_to_display(float(temp))

        # Fallback for UI visibility at startup
        _LOGGER.debug(
            "MysaSTV10Climate %s: Heat target is None, waiting for update",
            self._device_id,
        )
        if self.hass:
            self._async_ensure_data()
        return None

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature."""
        state = self._get_state_data()
        if state:
            val = self._extract_value(state, ["min_setpoint"])
            if val is not None:
                return cast(float, self._convert_to_display(float(val)))
        if self.hass:
            self._async_ensure_data()
        return cast(float, self._convert_to_display(self._attr_min_temp))

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature."""
        state = self._get_state_data()
        if state:
            val = self._extract_value(state, ["max_setpoint"])
            if val is not None:
                return cast(float, self._convert_to_display(float(val)))
        if self.hass:
            self._async_ensure_data()
        return cast(float, self._convert_to_display(self._attr_max_temp))

    @property
    def target_temperature_low(self) -> float | None:
        """Return the lower bound target temperature."""
        if self.hvac_mode != HVACMode.HEAT_COOL:
            return None

        state = self._get_state_data()
        if not state:
            return None
        temp = self._extract_value(
            state, ["target_heat", "heatSetpoint", "stpt", "sp", "SetPoint"]
        )
        if temp is not None:
            return self._convert_to_display(float(temp))
        return None

    @property
    def target_temperature_high(self) -> float | None:
        """Return the upper bound target temperature."""
        if self.hvac_mode != HVACMode.HEAT_COOL:
            return None

        state = self._get_state_data()
        if not state:
            return None
        temp = self._extract_value(
            state, ["target_cool", "coolSetpoint", "stpt", "sp", "SetPoint"]
        )
        if temp is not None:
            return self._convert_to_display(float(temp))
        return None

    @property
    def fan_mode(self) -> str | None:
        """Return current fan mode for ST-V1-0."""
        state = self._get_state_data()
        if not state:
            return "auto"

        fan_val = self._extract_value(state, ["fan_mode", "fanMode"])
        # ST-V1-0 Fan Modes: 0=Auto, 1=Low, 2=Medium, 3=High
        mapping = {0: "auto", 1: "low", 2: "medium", 3: "high"}

        if fan_val is not None:
            return mapping.get(int(fan_val), "auto")

        return "auto"

    @property
    def fan_modes(self) -> list[str]:
        """Return list of supported fan modes."""
        return ["auto", "low", "medium", "high"]

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set new fan mode."""
        await self._api.set_stv10_fan_mode(self._device_id, fan_mode)
        self.async_write_ha_state()

    @property
    # Justification: Handling multiple disjoint state checks for accurate HVAC action mapping.
    def hvac_action(self) -> HVACAction:  # pylint: disable=too-many-return-statements, too-many-locals
        """Return the current running hvac operation."""
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF

        state = self._get_state_data()
        # ST-V1-0 hvacState bitmask: Bit 2 (val 4) = Compressor/Heat Running
        hvac_state = (
            self._extract_value(state, ["hvac_state", "hvacState"]) if state else None
        )

        if not state:
            return HVACAction.IDLE

        if hvac_state is not None:
            is_running = int(hvac_state) & 4 != 0
            if not is_running:
                return HVACAction.IDLE
        else:
            # Fallback to direct relay state if bitmask is unavailable
            w1 = self._extract_value(state, ["hvac_raw_W1"])
            w2 = self._extract_value(state, ["hvac_raw_W2"])
            y1 = self._extract_value(state, ["hvac_raw_Y1"])
            y2 = self._extract_value(state, ["hvac_raw_Y2"])

            heat_running = bool(w1 or w2)
            cool_running = bool(y1 or y2)

            if heat_running:
                return HVACAction.HEATING
            if cool_running:
                return HVACAction.COOLING

            # Not heating or cooling
            return HVACAction.IDLE

        # Determine from reported active_mode/mode (most accurate for ST-V1-0)
        active_mode = self._extract_value(
            state, ["active_mode", "activeMode", "mode", "md"]
        )
        active_mapping = {
            0: HVACAction.IDLE,
            1: HVACAction.HEATING,  # Auto -> Heating (default if running)
            3: HVACAction.COOLING,
            4: HVACAction.HEATING,
            7: HVACAction.FAN,
        }

        if active_mode is not None and int(active_mode) != 1:
            return active_mapping.get(int(active_mode), HVACAction.HEATING)

        # Fallback to configured mode if active_mode is missing
        mode = self.hvac_mode
        simple_actions = {
            HVACMode.COOL: HVACAction.COOLING,
            HVACMode.FAN_ONLY: HVACAction.FAN,
            HVACMode.HEAT: HVACAction.HEATING,
        }
        if mode and (action := simple_actions.get(mode)):
            return action

        # Auto Mode Inference
        current = self.current_temperature
        low = self.target_temperature_low
        high = self.target_temperature_high

        if current is not None:
            if low is not None and current < low + 1.0:
                return HVACAction.HEATING
            if high is not None and current > high - 1.0:
                return HVACAction.COOLING

        # Fallback for Auto/Unknown
        return HVACAction.HEATING

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attrs = super().extra_state_attributes
        state = self._get_state_data()
        if state:
            attrs["ip_address"] = state.get("ip")
            attrs["firmware_version"] = state.get("FirmwareVersion")
            attrs["lockout_modes"] = state.get("lockout_modes")
            attrs["filter_life"] = state.get("filter_life")
            attrs["rssi"] = state.get("rssi")
        return attrs

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Return supported hvac modes."""
        return self._attr_hvac_modes

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target hvac mode."""
        try:
            # ST-V1-0 Mapping
            modes = {
                HVACMode.OFF: 0,
                HVACMode.HEAT_COOL: 1,
                HVACMode.COOL: 3,
                HVACMode.HEAT: 4,
                HVACMode.FAN_ONLY: 7,
            }
            mode_int = modes.get(hvac_mode, 4)

            # Optimistic update
            self._set_sticky_value("hvac_mode", hvac_mode)

            await self._api.set_stv10_hvac_mode(self._device_id, mode_int)
            self.async_write_ha_state()
        except Exception as e:
            if "hvac_mode" in self._pending_updates:
                del self._pending_updates["hvac_mode"]
            self.async_write_ha_state()
            raise HomeAssistantError(f"Failed to set mode: {e}") from e

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        temp_low = kwargs.get(ATTR_TARGET_TEMP_LOW)
        temp_high = kwargs.get(ATTR_TARGET_TEMP_HIGH)

        if temp_low is not None or temp_high is not None:
            # Range setting (Auto Mode)
            try:
                step = self.target_temperature_step
                if temp_low is not None:
                    temp_low = round(temp_low / step) * step
                if temp_high is not None:
                    temp_high = round(temp_high / step) * step

                if temp_low is not None and temp_high is not None:
                    # Optimistic update
                    self._set_sticky_value("target_temperature_low", temp_low)
                    self._set_sticky_value("target_temperature_high", temp_high)

                    # Convert to C for API
                    low_c = self._convert_from_display(temp_low)
                    high_c = self._convert_from_display(temp_high)
                    # Round to 0.5 for device
                    low_c = round(low_c * 2) / 2
                    high_c = round(high_c * 2) / 2

                    await self._api.set_target_temperature_range(
                        self._device_id, low_c, high_c
                    )
                elif temp_low is not None:
                    self._set_sticky_value("target_temperature_low", temp_low)
                    val_c = round(self._convert_from_display(temp_low) * 2) / 2
                    await self._api.set_stv10_heat_setpoint(self._device_id, val_c)
                elif temp_high is not None:
                    self._set_sticky_value("target_temperature_high", temp_high)
                    val_c = round(self._convert_from_display(temp_high) * 2) / 2
                    await self._api.set_stv10_cool_setpoint(self._device_id, val_c)

                self.async_write_ha_state()
                return  # Exit early
            except Exception as e:
                self.async_write_ha_state()
                raise HomeAssistantError(f"Failed to set temp range: {e}") from e

        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return
        try:
            step = self.target_temperature_step
            temp = round(temp / step) * step

            # Optimistic update
            self._set_sticky_value("target_temperature", temp)

            val_c = round(self._convert_from_display(temp) * 2) / 2
            await self._api.set_stv10_target_temperature(self._device_id, val_c)
            self.async_write_ha_state()
        except Exception as e:
            if "target_temperature" in self._pending_updates:
                del self._pending_updates["target_temperature"]
            self.async_write_ha_state()
            raise HomeAssistantError(f"Failed to set temp: {e}") from e
