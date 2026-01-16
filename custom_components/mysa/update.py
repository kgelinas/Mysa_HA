"""Update platform for Mysa."""
# pylint: disable=abstract-method
import logging
from datetime import timedelta

from homeassistant.components.update import (
    UpdateEntity,
    UpdateDeviceClass,
    UpdateEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN
from .mysa_api import MysaApi

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(hours=4)  # Check for updates every 4 hours

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Mysa update entities."""
    data = hass.data[DOMAIN][entry.entry_id]
    api: MysaApi = data["api"]
    await api.get_devices()


    entities = []
    for device_id, device_data in api.devices.items():
        entities.append(MysaUpdate(api, device_id, device_data))

    async_add_entities(entities, update_before_add=True)


class MysaUpdate(
    UpdateEntity
):  # TODO: Refactor MysaUpdate to implement abstract methods...
    # pylint: disable=too-many-instance-attributes
    """Mysa Firmware Update Entity."""

    _attr_device_class = UpdateDeviceClass.FIRMWARE
    _attr_supported_features = UpdateEntityFeature(0)


    def __init__(self, api: MysaApi, device_id: str, device_data: dict) -> None:
        """Initialize."""
        self._api = api
        self._device_id = device_id
        self._device_data = device_data


        self._attr_name = f"{device_data.get('Name', 'Mysa')} Firmware"
        self._attr_unique_id = f"{device_id}_firmware"


        self._attr_installed_version = device_data.get("FirmwareVersion")
        self._attr_latest_version = self._attr_installed_version  # Default to current until check
        self._attr_in_progress = False


        # Link to Device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            manufacturer="Mysa",
            model=device_data.get("Model"),
            name=device_data.get("Name"),
        )

    async def async_update(self) -> None:
        """Update the entity."""
        # This runs every SCAN_INTERVAL (4 hours)
        try:
            info = await self._api.hass.async_add_executor_job(
                self._api.fetch_firmware_info, self._device_id
            )


            if info:
                self._attr_installed_version = info.get("installedVersion")
                self._attr_latest_version = info.get("allowedVersion")


                _LOGGER.debug(
                    "Firmware check for %s: installed=%s, latest=%s, update_avail=%s",
                    self._device_id,
                    self._attr_installed_version,
                    self._attr_latest_version,
                    info.get("update")
                )


        except Exception as e:
            _LOGGER.warning("Error fetching firmware info: %s", e)
