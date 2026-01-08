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

from .const import DOMAIN
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
        entities.append(MysaClimate(coordinator, device_id, device_data, api, entry))

    async_add_entities(entities)



class MysaClimate(CoordinatorEntity, ClimateEntity):
    """Mysa Climate Entity."""

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
        zone_name = self._entry.options.get(f"zone_name_{zone_id}") if zone_id else None
        
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
        
        # Get friendly name from options if mapped
        zone_name = None
        if zone_id:
            zone_name = self._entry.options.get(f"zone_name_{zone_id}")
        
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
