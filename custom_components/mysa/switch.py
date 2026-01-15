"""Switch platform for Mysa."""
import logging
import time
from typing import Any
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN
_LOGGER = logging.getLogger(__name__)
async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Mysa switches."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    api = data["api"]
    devices = await api.get_devices()
    entities: list[SwitchEntity] = []
    for device_id, device_data in devices.items():
        is_ac = api.is_ac_device(device_id)
        # Lock switch (all devices)
        entities.append(
            MysaLockSwitch(coordinator, device_id, device_data, api, entry)
        )
        # Heating thermostat only switches
        if not is_ac:
            entities.append(
                MysaAutoBrightnessSwitch(coordinator, device_id, device_data, api, entry)
            )
            entities.append(
                MysaProximitySwitch(coordinator, device_id, device_data, api, entry)
            )
        # AC only switches
        if is_ac:
            entities.append(
                MysaClimatePlusSwitch(coordinator, device_id, device_data, api, entry)
            )
    async_add_entities(entities)
class MysaSwitch(CoordinatorEntity, SwitchEntity):  # TODO: Refactor MysaSwitch to reduce instance attributes and duplicate code
    """Base class for Mysa switches."""
    def __init__(
        self, coordinator, device_id, device_data, api, entry, sensor_key, name_suffix
    ):  # TODO: Refactor __init__ to reduce arguments
        """Initialize."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._sensor_key = sensor_key
        self._api = api
        self._entry = entry
        self._device_data = device_data
        self._attr_name = f"{device_data.get('Name', 'Mysa')} {name_suffix}"
        self._attr_unique_id = f"{device_id}_{sensor_key.lower()}"
        self._pending_state = None
        self._pending_timestamp = None
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

    def _get_state_with_pending(self, keys):
        """Get boolean state using sticky optimistic logic."""
        if self.coordinator.data is None:
             return self._pending_state or False
        state = self.coordinator.data.get(self._device_id)
        if not state:
            return self._pending_state or False
        val = self._extract_value(state, keys)
        current_val = bool(val) if val is not None else None

        if self._pending_state is not None:
            # 1. Check if pending state has expired (30s)
            if self._pending_timestamp and (time.time() - self._pending_timestamp > 30):
                self._pending_state = None
                self._pending_timestamp = None
                return current_val if current_val is not None else False

            # 2. Check for convergence (cloud matches pending)
            if current_val is not None and current_val == self._pending_state:
                self._pending_state = None
                self._pending_timestamp = None
                return current_val

            # 3. Return pending state (Sticky)
            return self._pending_state

        return current_val if current_val is not None else False
class MysaLockSwitch(MysaSwitch):  # TODO: Implement abstract methods
    """Switch for thermostat button lock."""
    _attr_icon = "mdi:lock"
    def __init__(
        self, coordinator, device_id, device_data, api, entry
    ):  # TODO: Refactor __init__ to reduce arguments
        """Initialize."""
        super().__init__(coordinator, device_id, device_data, api, entry, "Lock", "Lock")
    @property
    def is_on(self):
        """Return true if locked."""
        return self._get_state_with_pending(["Lock", "ButtonState", "alk", "lk", "lc"])
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Lock the thermostat."""
        self._pending_state = True
        self._pending_timestamp = time.time()
        self.async_write_ha_state()
        await self._api.set_lock(self._device_id, True)
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Unlock the thermostat."""
        self._pending_state = False
        self._pending_timestamp = time.time()
        self.async_write_ha_state()
        await self._api.set_lock(self._device_id, False)
class MysaAutoBrightnessSwitch(MysaSwitch):  # TODO: Implement abstract methods
    """Switch for auto brightness."""
    _attr_icon = "mdi:brightness-auto"
    def __init__(
        self, coordinator, device_id, device_data, api, entry
    ):  # TODO: Refactor __init__ to reduce arguments
        """Initialize."""
        super().__init__(
            coordinator, device_id, device_data, api, entry, "AutoBrightness",
            "Auto Brightness"
        )
    @property
    def is_on(self):
        """Return true if auto brightness is enabled."""
        return self._get_state_with_pending(["AutoBrightness", "ab"])
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable auto brightness."""
        self._pending_state = True
        self._pending_timestamp = time.time()
        self.async_write_ha_state()
        await self._api.set_auto_brightness(self._device_id, True)
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable auto brightness."""
        self._pending_state = False
        self._pending_timestamp = time.time()
        self.async_write_ha_state()
        await self._api.set_auto_brightness(self._device_id, False)
class MysaProximitySwitch(MysaSwitch):  # TODO: Implement abstract methods
    """Switch for proximity mode (wake on approach)."""
    _attr_icon = "mdi:motion-sensor"
    def __init__(
        self, coordinator, device_id, device_data, api, entry
    ):  # TODO: Refactor __init__ to reduce arguments
        """Initialize."""
        super().__init__(
            coordinator, device_id, device_data, api, entry, "ProximityMode",
            "Wake on Approach"
        )
    @property
    def is_on(self):
        """Return true if proximity mode is enabled."""
        return self._get_state_with_pending(["ProximityMode", "Proximity", "px", "pr"])
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable proximity mode."""
        self._pending_state = True
        self._pending_timestamp = time.time()
        self.async_write_ha_state()
        await self._api.set_proximity(self._device_id, True)
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable proximity mode."""
        self._pending_state = False
        self._pending_timestamp = time.time()
        self.async_write_ha_state()
        await self._api.set_proximity(self._device_id, False)
class MysaClimatePlusSwitch(MysaSwitch):  # TODO: Implement abstract methods
    """Switch for AC Climate+ mode (IsThermostatic).
    When enabled, the Mysa uses its temperature sensor to control the AC.
    When disabled, it acts as a simple IR remote.
    """
    _attr_icon = "mdi:thermostat-auto"
    def __init__(
        self, coordinator, device_id, device_data, api, entry
    ):  # TODO: Refactor __init__ to reduce arguments
        """Initialize."""
        super().__init__(
            coordinator, device_id, device_data, api, entry, "IsThermostatic",
            "Climate+"
        )
    @property
    def is_on(self):
        """Return true if Climate+ is enabled."""
        return self._get_state_with_pending(["IsThermostatic", "it"])
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable Climate+ mode."""
        self._pending_state = True
        self._pending_timestamp = time.time()
        self.async_write_ha_state()
        await self._api.set_ac_climate_plus(self._device_id, True)
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable Climate+ mode."""
        self._pending_state = False
        self._pending_timestamp = time.time()
        self.async_write_ha_state()
        await self._api.set_ac_climate_plus(self._device_id, False)
