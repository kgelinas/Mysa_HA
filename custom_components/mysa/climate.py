"""Climate platform for Mysa."""

# pylint: disable=abstract-method, too-many-lines, too-many-public-methods
# Justification:
# abstract-method: HA Entity properties implement the required abstracts.
# too-many-lines/methods: Climate entity handles complex HVAC logic and many protocol features.
import logging
import time
from typing import Any, cast

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
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
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from . import MysaData
from .const import (
    AC_FAN_MODES,
    AC_FAN_MODES_REVERSE,
    AC_MODE_AUTO,
    AC_MODE_COOL,
    AC_MODE_DRY,
    AC_MODE_FAN_ONLY,
    AC_MODE_HEAT,
    AC_MODE_OFF,
    AC_SWING_MODES,
    DOMAIN,
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
    devices = await api.get_devices()
    entities: list[ClimateEntity] = []
    for device_id, device_data in devices.items():
        # Use appropriate entity class based on device type
        if api.is_ac_device(device_id):
            _LOGGER.debug("Creating AC climate entity for %s", device_id)
            entities.append(
                MysaACClimate(coordinator, device_id, device_data, api, entry)
            )
        else:
            entities.append(
                MysaClimate(coordinator, device_id, device_data, api, entry)
            )

    async_add_entities(entities)


class MysaClimate(
    ClimateEntity, CoordinatorEntity[DataUpdateCoordinator[dict[str, Any]]]
):
    """Representation of a Mysa Thermostat."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features: Any = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_OFF
        | ClimateEntityFeature.TURN_ON
    )
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
            primary_keys = ["CorrectedTemp", "ambTemp", "ambient_t"]

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
                return f_val if f_val != 0 else None
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
        return float(val) if val is not None else None

    @property
    def current_humidity(self) -> float | None:
        """Return humidity."""
        state = self._get_state_data()
        if not state:
            return None

        val = self._extract_value(state, ["hum", "Humidity"])
        if val is not None:
            return float(val)
        return None

    def _get_state_data(self) -> dict[str, Any] | None:
        """Helper to get state data from coordinator."""
        if self.coordinator.data is None:
            return None
        return cast(dict[str, Any] | None, self.coordinator.data.get(self._device_id))

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
            self.coordinator.data = {}
        if self._device_id not in self.coordinator.data:
            self.coordinator.data[self._device_id] = {}

        self.coordinator.data[self._device_id][key] = value

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
            "Device %s hvac_mode: mode_id=%s -> result=%s (raw keys: %s)",
            self._device_id,
            mode_id,
            result,
            list(state.keys()),
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

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return
        try:
            # Round to target step (default 0.5)
            step = self._attr_target_temperature_step or 0.5
            temp = round(temp / step) * step

            # Optimistic update
            self._set_sticky_value("target_temperature", temp)

            await self._api.set_target_temperature(self._device_id, temp)
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

    async def async_turn_off(self) -> None:
        """Turn the entity off."""
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_turn_on(self) -> None:
        """Turn the entity on."""
        await self.async_set_hvac_mode(HVACMode.HEAT)


class MysaACClimate(MysaClimate):
    """Mysa AC Climate Entity with fan and swing mode support."""

    _attr_supported_features: Any = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_OFF
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.SWING_MODE
    )
    # AC temperature range (from SupportedCaps)
    _attr_min_temp = 16.0
    _attr_max_temp = 31.0
    _attr_target_temperature_step = 1.0  # AC typically uses 1 degree steps

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

        # Build dynamic mode/fan/swing lists from SupportedCaps
        self._build_supported_options()

        # Track last used mode for smart turn-on
        self._last_mode: HVACMode | None = None

    def _build_supported_options(self) -> None:
        """Build lists of supported modes from SupportedCaps."""
        # Default supported modes if not in SupportedCaps
        self._supported_hvac_modes: list[HVACMode] = [HVACMode.OFF]
        self._supported_fan_modes: list[str] = ["auto"]
        self._supported_swing_modes: list[str] = ["auto"]

        modes = self._supported_caps.get("modes", {})

        # Map SupportedCaps mode keys to HVAC modes
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

        # Get fan speeds from first available mode's capabilities
        for mode_caps in modes.values():
            fan_speeds = mode_caps.get("fanSpeeds", [])
            if fan_speeds:
                self._supported_fan_modes = []
                for speed in fan_speeds:
                    fan_name = AC_FAN_MODES.get(speed)
                    if fan_name:
                        self._supported_fan_modes.append(fan_name)
                break

        # Get swing positions from first available mode's capabilities
        for mode_caps in modes.values():
            vertical_swings = mode_caps.get("verticalSwing", [])
            if vertical_swings:
                self._supported_swing_modes = []
                for pos in vertical_swings:
                    swing_name = AC_SWING_MODES.get(pos)
                    if swing_name:
                        self._supported_swing_modes.append(swing_name)
                break

        _LOGGER.debug(
            "AC %s supported modes: hvac=%s, fan=%s, swing=%s",
            self._device_id,
            self._supported_hvac_modes,
            self._supported_fan_modes,
            self._supported_swing_modes,
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

    async def async_set_target_temperature(self, temperature: float) -> None:
        """Set new target temperature."""
        try:
            step = self._attr_target_temperature_step or 1.0
            temp = round(temperature / step) * step

            # Optimistic update
            self._set_sticky_value("target_temperature", temp)

            await self._api.set_target_temperature(self._device_id, temp)
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
