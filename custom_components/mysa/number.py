"""Number platform for Mysa."""
# pylint: disable=abstract-method
# Justification: HA Entity properties implement the required abstracts.
import time
import logging
from typing import Any, Dict, List, Optional

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from . import MysaData
from .mysa_api import MysaApi
from .device import MysaDeviceLogic

PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: ConfigEntry[MysaData],
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Mysa number entities."""
    coordinator = entry.runtime_data.coordinator
    api = entry.runtime_data.api
    devices = await api.get_devices()

    entities: list[NumberEntity] = []
    for device_id, device_data in devices.items():
        # Min/Max Brightness are settable configuration values
        entities.append(MysaMinBrightnessNumber(coordinator, device_id, device_data, api, entry))
        entities.append(MysaMaxBrightnessNumber(coordinator, device_id, device_data, api, entry))

    async_add_entities(entities)


class MysaNumber(
    NumberEntity, CoordinatorEntity[DataUpdateCoordinator[Dict[str, Any]]]
):
    """Base class for Mysa number entities.

    TODO: Refactor MysaNumber to reduce instance attributes,
    duplicate code, and implement abstract methods.
    """

    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[Dict[str, Any]],
        device_id: str,
        device_data: Dict[str, Any],
        api: MysaApi,
        entry: ConfigEntry[MysaData],
        sensor_key: str,
        translation_key: str
    ) -> None:
        # TODO: Refactor __init__ to reduce arguments
        """Initialize."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._sensor_key = sensor_key
        self._api = api
        self._entry = entry
        self._device_data = device_data
        self._attr_translation_key = translation_key
        self._attr_unique_id = f"{device_id}_{sensor_key.lower()}"
        self._pending_value: Optional[float] = None  # Track pending value to avoid 'unknown' state
        self._pending_time: Optional[float] = None   # Timestamp when pending was set

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        state = self.coordinator.data.get(self._device_id) if self.coordinator.data else None
        return MysaDeviceLogic.get_device_info(self._device_id, self._device_data, state)

    def _extract_value(self, state: Optional[Dict[str, Any]], keys: List[str]) -> Any:
        """Helper to extract a value from state dictionary."""
        if state is None:
            return None
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

    def _get_value_with_pending(self, keys: List[str]) -> Optional[float]:
        """Get value using sticky optimistic logic."""
        # Cloud value
        state = None
        if self.coordinator.data:
            state = self.coordinator.data.get(self._device_id)
        val = self._extract_value(state, keys) if state else None

        current_val: Optional[float] = None
        if val is not None:
            try:
                current_val = float(val)
            except (ValueError, TypeError):
                pass

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

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[Dict[str, Any]],
        device_id: str,
        device_data: Dict[str, Any],
        api: MysaApi,
        entry: ConfigEntry[MysaData]
    ) -> None:
        # TODO: Refactor __init__ to reduce arguments
        """Initialize."""
        super().__init__(
            coordinator, device_id, device_data, api, entry, "MinBrightness", "min_brightness"
        )

    @property
    def native_value(self) -> Optional[float]:
        """Return current min brightness value."""
        return self._get_value_with_pending(["mnbr", "MinBrightness"])

    async def async_set_native_value(self, value: float) -> None:
        """Set minimum brightness."""
        self._pending_value = float(value)
        self._pending_time = time.time()
        self.async_write_ha_state()  # Update UI immediately
        try:
            await self._api.set_min_brightness(self._device_id, int(value))
        except Exception as e:
            self._pending_value = None
            self.async_write_ha_state()
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="set_min_brightness_failed",
                translation_placeholders={"error": str(e)},
            ) from e
        # Don't clear pending - let it expire or converge


class MysaMaxBrightnessNumber(MysaNumber):
    """Number entity for maximum brightness.

    TODO: Implement abstract methods.
    """

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[Dict[str, Any]],
        device_id: str,
        device_data: Dict[str, Any],
        api: MysaApi,
        entry: ConfigEntry[MysaData]
    ) -> None:
        # TODO: Refactor __init__ to reduce arguments
        """Initialize."""
        super().__init__(
            coordinator, device_id, device_data, api, entry, "MaxBrightness", "max_brightness"
        )

    @property
    def native_value(self) -> Optional[float]:
        """Return current max brightness value."""
        return self._get_value_with_pending(["mxbr", "MaxBrightness"])

    async def async_set_native_value(self, value: float) -> None:
        """Set maximum brightness."""
        self._pending_value = float(value)
        self._pending_time = time.time()
        self.async_write_ha_state()  # Update UI immediately
        try:
            await self._api.set_max_brightness(self._device_id, int(value))
        except Exception as e:
            self._pending_value = None
            self.async_write_ha_state()
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="set_max_brightness_failed",
                translation_placeholders={"error": str(e)},
            ) from e
        # Don't clear pending - let it expire or converge
