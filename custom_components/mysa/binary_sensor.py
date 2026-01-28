"""Binary sensor platform for Mysa."""

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from . import MysaData
from .device import MysaDeviceLogic

PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: ConfigEntry[MysaData],
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Mysa binary sensors."""
    coordinator = entry.runtime_data.coordinator
    api = entry.runtime_data.api
    devices = await api.get_devices()

    entities = []
    for device_id, device_data in devices.items():
        # Connection status sensor (all devices)
        entities.append(MysaConnectionSensor(coordinator, device_id, device_data))

    async_add_entities(entities)


class MysaConnectionSensor(
    BinarySensorEntity, CoordinatorEntity[DataUpdateCoordinator[dict[str, Any]]]
):
    """Representation of a Mysa Connection Status sensor."""

    _attr_device_class: Any = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, Any]],
        device_id: str,
        device_data: dict[str, Any],
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._device_data = device_data
        self._attr_translation_key = "connection"
        self._attr_unique_id = f"{device_id}_connection"

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
    def is_on(self) -> bool | None:
        """Return true if the device is connected."""
        if not self.coordinator.data:
            return False

        state = self.coordinator.data.get(self._device_id)
        if not state:
            return False
        return bool(state.get("Connected", False))
