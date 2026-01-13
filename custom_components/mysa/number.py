"""Number platform for Mysa."""
import time
import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
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
    """Set up Mysa number entities."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    api = data["api"]
    devices = await api.get_devices()

    entities: list[NumberEntity] = []
    for device_id, device_data in devices.items():
        # Min/Max Brightness are settable configuration values
        entities.append(MysaMinBrightnessNumber(coordinator, device_id, device_data, api, entry))
        entities.append(MysaMaxBrightnessNumber(coordinator, device_id, device_data, api, entry))

    async_add_entities(entities)


class MysaNumber(CoordinatorEntity, NumberEntity):  # TODO: Refactor MysaNumber to reduce instance attributes, duplicate code, and implement abstract methods
    """Base class for Mysa number entities."""

    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER

    def __init__(  # TODO: Refactor __init__ to reduce arguments
        self, coordinator, device_id, device_data, api, entry, sensor_key, name_suffix
    ):
        """Initialize."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._sensor_key = sensor_key
        self._api = api
        self._entry = entry
        self._device_data = device_data
        self._attr_name = f"{device_data.get('Name', 'Mysa')} {name_suffix}"
        self._attr_unique_id = f"{device_id}_{sensor_key.lower()}"
        self._pending_value = None  # Track pending value to avoid 'unknown' state
        self._pending_time = None   # Timestamp when pending was set

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

    def _get_value_with_pending(self, keys):
        """Get value from state or pending value if state is not yet updated."""
        # If we have a pending value that's less than 60 seconds old, use it
        if self._pending_value is not None and self._pending_time is not None:
            if time.time() - self._pending_time < 60:
                return self._pending_value

            # Pending expired, clear it
            self._pending_value = None
            self._pending_time = None

        # Get from coordinator
        state = self.coordinator.data.get(self._device_id)
        if not state:
            return None
        val = self._extract_value(state, keys)
        return float(val) if val is not None else None


class MysaMinBrightnessNumber(MysaNumber):  # TODO: Implement abstract methods
    """Number entity for minimum brightness."""

    _attr_icon = "mdi:brightness-5"

    def __init__(self, coordinator, device_id, device_data, api, entry):  # TODO: Refactor __init__ to reduce arguments
        """Initialize."""
        super().__init__(
            coordinator, device_id, device_data, api, entry, "MinBrightness", "Minimum Brightness"
        )

    @property
    def native_value(self):
        """Return current min brightness value."""
        return self._get_value_with_pending(["MinBrightness", "mnbr"])

    async def async_set_native_value(self, value: float) -> None:
        """Set minimum brightness."""
        self._pending_value = float(value)
        self._pending_time = time.time()
        self.async_write_ha_state()  # Update UI immediately
        await self._api.set_min_brightness(self._device_id, int(value))
        # Don't clear pending - let it expire after 60 seconds


class MysaMaxBrightnessNumber(MysaNumber):  # TODO: Implement abstract methods
    """Number entity for maximum brightness."""

    _attr_icon = "mdi:brightness-7"

    def __init__(self, coordinator, device_id, device_data, api, entry):  # TODO: Refactor __init__ to reduce arguments
        """Initialize."""
        super().__init__(
            coordinator, device_id, device_data, api, entry, "MaxBrightness", "Maximum Brightness"
        )

    @property
    def native_value(self):
        """Return current max brightness value."""
        return self._get_value_with_pending(["MaxBrightness", "mxbr"])

    async def async_set_native_value(self, value: float) -> None:
        """Set maximum brightness."""
        self._pending_value = float(value)
        self._pending_time = time.time()
        self.async_write_ha_state()  # Update UI immediately
        await self._api.set_max_brightness(self._device_id, int(value))
        # Don't clear pending - let it expire after 60 seconds
