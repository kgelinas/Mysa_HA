"""Number platform for Mysa."""
# pylint: disable=abstract-method
import time
import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
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


class MysaNumber(CoordinatorEntity, NumberEntity):
    """Base class for Mysa number entities.

    TODO: Refactor MysaNumber to reduce instance attributes,
    duplicate code, and implement abstract methods.
    """

    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER

    def __init__(
        self, coordinator, device_id, device_data, api, entry, sensor_key, name_suffix
    ):
        # TODO: Refactor __init__ to reduce arguments
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

        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            manufacturer="Mysa",
            model=self._device_data.get("Model"),
            suggested_area=zone_name,
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

    def _get_value_with_pending(self, keys):
        """Get value using sticky optimistic logic."""
        # Cloud value
        state = None
        if self.coordinator.data:
            state = self.coordinator.data.get(self._device_id)
        val = self._extract_value(state, keys) if state else None
        current_val = float(val) if val is not None else None

        if self._pending_value is not None:
             # 1. Check expiration (30s)
            if self._pending_time and (time.time() - self._pending_time > 30):
                self._pending_value = None
                self._pending_time = None
                return current_val

            # 2. Check convergence
            if current_val is not None and current_val == self._pending_value:
                self._pending_value = None
                self._pending_time = None
                return current_val

            # 3. Sticky return
            return self._pending_value

        return current_val


class MysaMinBrightnessNumber(MysaNumber):
    """Number entity for minimum brightness.

    TODO: Implement abstract methods.
    """

    _attr_icon = "mdi:brightness-5"

    def __init__(self, coordinator, device_id, device_data, api, entry):
        # TODO: Refactor __init__ to reduce arguments
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
        # Don't clear pending - let it expire or converge


class MysaMaxBrightnessNumber(MysaNumber):
    """Number entity for maximum brightness.

    TODO: Implement abstract methods.
    """

    _attr_icon = "mdi:brightness-7"

    def __init__(self, coordinator, device_id, device_data, api, entry):
        # TODO: Refactor __init__ to reduce arguments
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
        # Don't clear pending - let it expire or converge
