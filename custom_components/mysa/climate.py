"""Climate platform for Mysa."""
import logging
import time
from datetime import timedelta
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
    HVACAction,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_TEMPERATURE,
    UnitOfTemperature,
    PRECISION_TENTHS,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    DOMAIN,
    AC_MODE_OFF, AC_MODE_AUTO, AC_MODE_HEAT, AC_MODE_COOL, AC_MODE_FAN_ONLY, AC_MODE_DRY,
    AC_FAN_MODES, AC_FAN_MODES_REVERSE,
    AC_SWING_MODES, AC_SWING_MODES_REVERSE,
)
from .mysa_api import MysaApi

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Mysa climate devices."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    api = data["api"]

    # Get devices to create entities
    devices = await api.get_devices()
    
    entities = []
    for device_id, device_data in devices.items():
        # Use appropriate entity class based on device type
        if api.is_ac_device(device_id):
            _LOGGER.info("Creating AC climate entity for %s", device_id)
            entities.append(MysaACClimate(coordinator, device_id, device_data, api, entry))
        else:
            entities.append(MysaClimate(coordinator, device_id, device_data, api, entry))

    async_add_entities(entities)



class MysaClimate(CoordinatorEntity, ClimateEntity):
    """Mysa Climate Entity for heating thermostats."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE |
        ClimateEntityFeature.TURN_OFF |
        ClimateEntityFeature.TURN_ON
    )
    _attr_min_temp = 5.0
    _attr_max_temp = 30.0
    _attr_precision = PRECISION_TENTHS
    _attr_target_temperature_step = 0.5

    def __init__(self, coordinator, device_id, device_data, api, entry):
        """Initialize."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._device_data = device_data
        self._api = api
        self._entry = entry
        self._attr_name = device_data.get("Name", "Mysa Thermostat")
        self._attr_unique_id = device_id

    @property
    def device_info(self):
        """Return device info."""
        state = self._get_state_data()
        zone_id = state.get("Zone") if state else None
        zone_name = self._api.get_zone_name(zone_id) if zone_id else None
        
        info = {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": self._attr_name,
            "manufacturer": "Mysa",
            "model": self._device_data.get("Model"),
            "sw_version": self._device_data.get("FirmwareVersion"),
        }
        if zone_name:
            info["suggested_area"] = zone_name
        return info

    def _get_value(self, key):
        """Get value from state, handling both dict (v/t) and direct value."""
        state = self.coordinator.data.get(self._device_id)
        if not state:
            return None
        val = state.get(key)
        if isinstance(val, dict):
            return val.get('v')
        return val

    @property
    def current_temperature(self):
        """Return current temperature."""
        state = self._get_state_data()
        if not state:
            return None
        
        # Priority: MQTT keys then HTTP keys
        val = self._extract_value(state, ["ambTemp", "ambient_t", "CorrectedTemp", "SensorTemp"])
        
        _LOGGER.debug("Device %s current_temp raw value: %s", self._device_id, val)
        if val is not None:
             return float(val) if val != 0 else None
        return None

    @property
    def target_temperature(self):
        """Return target temperature."""
        state = self._get_state_data()
        if not state:
            return None

        # Priority: MQTT keys then HTTP keys
        val = self._extract_value(state, ["stpt", "setpoint_t", "SetPoint"])
        
        _LOGGER.debug("Device %s target_temp raw value: %s", self._device_id, val)
        if val is not None:
             return float(val)
        return None

    @property
    def current_humidity(self):
        """Return humidity."""
        state = self._get_state_data()
        if not state:
            return None
            
        val = self._extract_value(state, ["hum", "Humidity"])
        if val is not None:
             return val
        return None

    def _get_state_data(self):
        """Helper to get state data from coordinator."""
        return self.coordinator.data.get(self._device_id)

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
    def hvac_mode(self):
        """Return hvac mode."""
        state = self._get_state_data()
        if not state:
            return HVACMode.HEAT  # Default fallback
        
        # Priority: MQTT key (md) then user-confirmed source of truth (TstatMode) then generic (Mode)
        mode_id = self._extract_value(state, ["md", "TstatMode", "Mode"])
        
        # Determine Enum result
        if mode_id == 1:
            result = HVACMode.OFF
        elif mode_id == 3:
            result = HVACMode.HEAT
        else:
            result = HVACMode.HEAT
            
        _LOGGER.debug("Device %s hvac_mode: mode_id=%s -> result=%s (raw keys: %s)", 
                      self._device_id, mode_id, result, list(state.keys()))

        return result

    @property
    def hvac_action(self):
        """Return hvac action."""
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        
        state = self._get_state_data()
        if not state:
            return HVACAction.IDLE
            
        # Priority: MQTT key (dc) then Cloud key (Duty, dtyCycle, DutyCycle)
        duty = self._extract_value(state, ["dc", "Duty", "dtyCycle", "DutyCycle"])
        if duty is not None and float(duty) > 0:
            return HVACAction.HEATING
            
        return HVACAction.IDLE

    @property
    def extra_state_attributes(self):
        """Return extra state attributes."""
        state = self._get_state_data()
        zone_id = state.get("Zone") if state else None
        
        # Get friendly name from API mapping
        zone_name = None
        if zone_id:
            zone_name = self._api.get_zone_name(zone_id)
        
        return {
            "model": self._device_data.get("Model"),
            "zone_id": zone_id,
            "zone_name": zone_name if zone_name else "Unassigned",
        }

    @property
    def hvac_modes(self):
        """Return supported hvac modes."""
        return [HVACMode.HEAT, HVACMode.OFF]

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        if (temp := kwargs.get(ATTR_TEMPERATURE)) is None:
            return
        try:
            # Optimistic update: set all sync-related keys
            state = self._get_state_data()
            if state is not None:
                # Wrap value if it looks like cloud API
                val_wrap = {"v": temp, "t": int(time.time())}
                state["sp"] = temp
                state["stpt"] = temp
                state["SetPoint"] = val_wrap
                
            await self._api.set_target_temperature(self._device_id, temp)
            self.async_write_ha_state() 
        except Exception as e:
            _LOGGER.error("Failed to set temperature: %s", e)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target hvac mode."""
        try:
            # Optimistic update: HEAT=3, OFF=1
            mode_val = 1 if hvac_mode == HVACMode.OFF else 3
            state = self._get_state_data()
            if state is not None:
                val_wrap = {"v": mode_val, "t": int(time.time())}
                state["md"] = mode_val
                state["TstatMode"] = val_wrap
                state["Mode"] = val_wrap
                
            await self._api.set_hvac_mode(self._device_id, hvac_mode)
            self.async_write_ha_state()
        except Exception as e:
             _LOGGER.error("Failed to set HVAC mode: %s", e)

    async def async_turn_off(self) -> None:
        """Turn the entity off."""
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_turn_on(self) -> None:
        """Turn the entity on."""
        await self.async_set_hvac_mode(HVACMode.HEAT)


class MysaACClimate(MysaClimate):
    """Mysa AC Climate Entity with fan and swing mode support."""

    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE |
        ClimateEntityFeature.TURN_OFF |
        ClimateEntityFeature.TURN_ON |
        ClimateEntityFeature.FAN_MODE |
        ClimateEntityFeature.SWING_MODE
    )
    # AC temperature range (from SupportedCaps)
    _attr_min_temp = 16.0
    _attr_max_temp = 31.0
    _attr_target_temperature_step = 1.0  # AC typically uses 1 degree steps

    def __init__(self, coordinator, device_id, device_data, api, entry):
        """Initialize AC climate entity."""
        super().__init__(coordinator, device_id, device_data, api, entry)
        self._attr_name = device_data.get("Name", "Mysa AC")
        
        # Get supported capabilities from device data
        self._supported_caps = device_data.get("SupportedCaps", {})
        
        # Build dynamic mode/fan/swing lists from SupportedCaps
        self._build_supported_options()

    def _build_supported_options(self):
        """Build lists of supported modes from SupportedCaps."""
        # Default supported modes if not in SupportedCaps
        self._supported_hvac_modes = [HVACMode.OFF]
        self._supported_fan_modes = ["auto"]
        self._supported_swing_modes = ["auto"]
        
        modes = self._supported_caps.get("modes", {})
        
        # Map SupportedCaps mode keys to HVAC modes
        mode_mapping = {
            2: HVACMode.HEAT_COOL,  # Auto
            3: HVACMode.HEAT,
            4: HVACMode.COOL,
            5: HVACMode.FAN_ONLY,
            6: HVACMode.DRY,
        }
        
        for mode_key in modes.keys():
            mode_int = int(mode_key)
            if mode_int in mode_mapping:
                self._supported_hvac_modes.append(mode_mapping[mode_int])
        
        # Get fan speeds from first available mode's capabilities
        for mode_key, mode_caps in modes.items():
            fan_speeds = mode_caps.get("fanSpeeds", [])
            if fan_speeds:
                self._supported_fan_modes = []
                for speed in fan_speeds:
                    fan_name = AC_FAN_MODES.get(speed)
                    if fan_name:
                        self._supported_fan_modes.append(fan_name)
                break
        
        # Get swing positions from first available mode's capabilities
        for mode_key, mode_caps in modes.items():
            vertical_swings = mode_caps.get("verticalSwing", [])
            if vertical_swings:
                self._supported_swing_modes = []
                for pos in vertical_swings:
                    swing_name = AC_SWING_MODES.get(pos)
                    if swing_name:
                        self._supported_swing_modes.append(swing_name)
                break

        _LOGGER.debug("AC %s supported modes: hvac=%s, fan=%s, swing=%s",
                      self._device_id, self._supported_hvac_modes, 
                      self._supported_fan_modes, self._supported_swing_modes)

    @property
    def hvac_modes(self):
        """Return supported hvac modes for AC."""
        return self._supported_hvac_modes

    @property
    def hvac_mode(self):
        """Return current hvac mode for AC."""
        state = self._get_state_data()
        if not state:
            return HVACMode.OFF
        
        # Get mode from TstatMode or ACMode
        mode_id = self._extract_value(state, ["md", "TstatMode", "ACMode", "Mode"])
        
        # Map Mysa mode to HA mode
        mode_mapping = {
            AC_MODE_OFF: HVACMode.OFF,
            AC_MODE_AUTO: HVACMode.HEAT_COOL,
            AC_MODE_HEAT: HVACMode.HEAT,
            AC_MODE_COOL: HVACMode.COOL,
            AC_MODE_FAN_ONLY: HVACMode.FAN_ONLY,
            AC_MODE_DRY: HVACMode.DRY,
        }
        
        result = mode_mapping.get(mode_id, HVACMode.OFF)
        _LOGGER.debug("AC %s hvac_mode: mode_id=%s -> result=%s", 
                      self._device_id, mode_id, result)
        return result

    @property
    def hvac_action(self):
        """Return hvac action for AC."""
        mode = self.hvac_mode
        if mode == HVACMode.OFF:
            return HVACAction.OFF
        elif mode == HVACMode.COOL:
            return HVACAction.COOLING
        elif mode == HVACMode.HEAT:
            return HVACAction.HEATING
        elif mode == HVACMode.DRY:
            return HVACAction.DRYING
        elif mode == HVACMode.FAN_ONLY:
            return HVACAction.FAN
        elif mode == HVACMode.HEAT_COOL:
            # For auto mode, determine based on temperature difference
            state = self._get_state_data()
            if state:
                current = self._extract_value(state, ["ambTemp", "CorrectedTemp", "SensorTemp"])
                target = self._extract_value(state, ["stpt", "SetPoint"])
                if current and target:
                    if float(current) > float(target):
                        return HVACAction.COOLING
                    elif float(current) < float(target):
                        return HVACAction.HEATING
            return HVACAction.IDLE
        return HVACAction.IDLE

    @property
    def fan_modes(self):
        """Return supported fan modes."""
        return self._supported_fan_modes

    @property
    def fan_mode(self):
        """Return current fan mode."""
        state = self._get_state_data()
        if not state:
            return "auto"
        
        # Get fan speed value
        fan_val = self._extract_value(state, ["fn", "FanSpeed"])
        if fan_val is not None:
            return AC_FAN_MODES.get(int(fan_val), "auto")
        
        # Try from normalized FanMode
        return state.get("FanMode", "auto")

    @property
    def swing_modes(self):
        """Return supported swing modes."""
        return self._supported_swing_modes

    @property
    def swing_mode(self):
        """Return current swing mode (vertical)."""
        state = self._get_state_data()
        if not state:
            return "auto"
        
        # Get swing state value
        swing_val = self._extract_value(state, ["ss", "SwingState"])
        if swing_val is not None:
            return AC_SWING_MODES.get(int(swing_val), "auto")
        
        # Try from normalized SwingMode
        return state.get("SwingMode", "auto")

    @property
    def extra_state_attributes(self):
        """Return extra state attributes for AC."""
        attrs = super().extra_state_attributes
        state = self._get_state_data()
        
        if state:
            # Add AC-specific attributes
            attrs["horizontal_swing"] = self._extract_value(state, ["ssh", "SwingStateHorizontal"])
            attrs["ac_power"] = state.get("ACPower")
            
        return attrs

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new HVAC mode for AC."""
        try:
            # Map HA mode to Mysa value for optimistic update
            mode_mapping = {
                HVACMode.OFF: AC_MODE_OFF,
                HVACMode.HEAT_COOL: AC_MODE_AUTO,
                HVACMode.HEAT: AC_MODE_HEAT,
                HVACMode.COOL: AC_MODE_COOL,
                HVACMode.FAN_ONLY: AC_MODE_FAN_ONLY,
                HVACMode.DRY: AC_MODE_DRY,
            }
            mode_val = mode_mapping.get(hvac_mode, AC_MODE_OFF)
            
            # Optimistic update
            state = self._get_state_data()
            if state is not None:
                val_wrap = {"v": mode_val, "t": int(time.time())}
                state["md"] = mode_val
                state["TstatMode"] = val_wrap
                
            await self._api.set_hvac_mode(self._device_id, hvac_mode)
            self.async_write_ha_state()
        except Exception as e:
            _LOGGER.error("Failed to set AC HVAC mode: %s", e)

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
            _LOGGER.error("Failed to set AC fan mode: %s", e)

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Set new swing mode (vertical)."""
        try:
            # Optimistic update
            swing_val = AC_SWING_MODES_REVERSE.get(swing_mode.lower())
            state = self._get_state_data()
            if state is not None and swing_val is not None:
                state["ss"] = swing_val
                state["SwingState"] = {"v": swing_val, "t": int(time.time())}
                state["SwingMode"] = swing_mode.lower()
                
            await self._api.set_ac_swing_mode(self._device_id, swing_mode)
            self.async_write_ha_state()
        except Exception as e:
            _LOGGER.error("Failed to set AC swing mode: %s", e)

    async def async_turn_on(self) -> None:
        """Turn the AC on (to cool mode by default)."""
        # Default to cool mode when turning on, or last used mode if available
        await self.async_set_hvac_mode(HVACMode.COOL)
