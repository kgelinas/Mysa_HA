"""Binary sensor platform for Mysa."""
import logging
from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
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
    """Set up Mysa binary sensors."""
    data = hass.data[DOMAIN].get(entry.entry_id)
    if not data:
        return

    coordinator = data["coordinator"]
    api = data["api"]
    devices = await api.get_devices()

    entities = []
    for device_id, device_data in devices.items():
        # Connection status sensor (all devices)
        entities.append(MysaConnectionSensor(coordinator, device_id, device_data))

    async_add_entities(entities)


class MysaConnectionSensor(CoordinatorEntity, BinarySensorEntity):
    """Representation of a Mysa Connection Status sensor."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, device_id, device_data):
        """Initialize."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._device_data = device_data
        self._attr_name = f"{device_data.get('Name', 'Mysa')} Connection"
        self._attr_unique_id = f"{device_id}_connection"

    @property
    def device_info(self):
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "manufacturer": "Mysa",
            "model": self._device_data.get("Model"),
            "name": self._device_data.get("Name"),
        }

    @property
    def is_on(self):
        """Return true if the device is connected."""
        state = self.coordinator.data.get(self._device_id)
        if not state:
            return False
        return state.get("Connected", False)
