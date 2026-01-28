"""Update platform for Mysa."""

# pylint: disable=abstract-method
# Justification: HA Entity properties implement the required abstracts.
import logging
from datetime import timedelta
from typing import Any

from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MysaData
from .device import MysaDeviceLogic
from .mysa_api import MysaApi

PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(hours=1)  # Check for updates every 1 hour


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: ConfigEntry[MysaData],
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Mysa update entities."""
    api = entry.runtime_data.api
    await api.get_devices()

    entities = []
    for device_id, device_data in api.devices.items():
        entities.append(MysaUpdate(api, device_id, device_data))

    async_add_entities(entities, update_before_add=True)


class MysaUpdate(UpdateEntity):
    # pylint: disable=too-many-instance-attributes
    # Justification: Entity requires tracking multiple version/status attributes.
    """Mysa Firmware Update Entity."""

    _attr_device_class = UpdateDeviceClass.FIRMWARE
    _attr_supported_features = UpdateEntityFeature(0)
    _attr_has_entity_name = True

    def __init__(
        self, api: MysaApi, device_id: str, device_data: dict[str, Any]
    ) -> None:
        """Initialize."""
        self._api = api
        self._device_id = device_id
        self._device_data = device_data

        self._attr_translation_key = "firmware"
        self._attr_unique_id = f"{device_id}_firmware"

        self._attr_installed_version = str(device_data.get("FirmwareVersion"))
        self._attr_latest_version = (
            self._attr_installed_version
        )  # Default to current until check
        self._attr_in_progress = False

        # Link to Device
        self._attr_device_info = MysaDeviceLogic.get_device_info(device_id, device_data)

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()
        # Force an immediate update on startup to ensure we have valid firmware info
        # This fixes the "None" issue if MQTT fails to report version on connect.
        await self.async_update()

    async def async_update(self) -> None:
        """Update the entity."""
        # This runs every SCAN_INTERVAL (4 hours)
        try:
            info = await self._api.fetch_firmware_info(self._device_id)
            if info:
                self._attr_installed_version = str(
                    info.get("installedVersion", self._attr_installed_version)
                )
                self._attr_latest_version = str(
                    info.get("allowedVersion", self._attr_installed_version)
                )

                if self._attr_installed_version != self._device_data.get(
                    "FirmwareVersion"
                ):
                    self._device_data["FirmwareVersion"] = self._attr_installed_version
                    # Update our own device_info (though usually static)
                    self._attr_device_info = MysaDeviceLogic.get_device_info(
                        self._device_id, self._device_data
                    )

                _LOGGER.debug(
                    "Firmware check for %s: installed=%s, latest=%s, update_avail=%s",
                    self._device_id,
                    self._attr_installed_version,
                    self._attr_latest_version,
                    info.get("update"),
                )

        except Exception as e:
            _LOGGER.warning("Error fetching firmware info: %s", e)
