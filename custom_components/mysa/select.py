"""Select platform for Mysa AC horizontal swing."""
# pylint: disable=abstract-method
# Justification: HA Entity properties implement the required abstracts.
import logging
import time
from typing import Any, Dict, List, Optional

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator
from homeassistant.exceptions import HomeAssistantError

from .const import (
    DOMAIN,
    AC_HORIZONTAL_SWING_MODES,
    AC_HORIZONTAL_SWING_MODES_REVERSE,
    SENSOR_MODES,
    SENSOR_MODES_REVERSE,
)
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
    """Set up Mysa select entities."""
    coordinator = entry.runtime_data.coordinator
    api = entry.runtime_data.api
    devices = await api.get_devices()

    entities: list[SelectEntity] = []
    for device_id, device_data in devices.items():
        # Add horizontal swing select only for AC devices
        if api.is_ac_device(device_id):
            entities.append(
                MysaHorizontalSwingSelect(coordinator, device_id, device_data, api, entry)
            )

        # Add sensor mode select for In-Floor devices
        model = str(device_data.get("Model", ""))
        is_infloor = "INF-V1" in model or "Floor" in model
        if is_infloor:
            entities.append(
                MysaSensorModeSelect(coordinator, device_id, device_data, api, entry)
            )

    if entities:
        async_add_entities(entities)


class MysaHorizontalSwingSelect(
    SelectEntity, CoordinatorEntity[DataUpdateCoordinator[Dict[str, Any]]]
):
    """Select entity for AC horizontal swing position.

    TODO: Refactor MysaHorizontalSwingSelect to reduce instance attributes,
    duplicate code, and implement abstract methods.
    """
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

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
        super().__init__(coordinator)
        self._device_id = device_id
        self._device_data = device_data
        self._api = api
        self._entry = entry
        self._attr_translation_key = "horizontal_swing"
        self._attr_unique_id = f"{device_id}_horizontal_swing"
        self._pending_option: Optional[str] = None
        self._pending_timestamp: Optional[float] = None
        self._options: List[str] = []

        # Build options from SupportedCaps or defaults
        self._build_options(device_data)

    def _build_options(self, device_data: Dict[str, Any]) -> None:
        """Build list of available horizontal swing options."""
        supported_caps = device_data.get("SupportedCaps", {})
        modes = supported_caps.get("modes", {})

        # Get horizontal swing positions from first available mode
        self._options = []
        for mode_caps in modes.values():
            horizontal_swings = mode_caps.get("horizontalSwing", [])
            if horizontal_swings:
                for pos in horizontal_swings:
                    name = AC_HORIZONTAL_SWING_MODES.get(pos)
                    if name and name not in self._options:
                        self._options.append(name)
                break
        # Fallback to defaults if not found
        if not self._options:
            self._options = list(AC_HORIZONTAL_SWING_MODES.values())

        _LOGGER.debug(
            "Horizontal swing options for %s: %s", self._device_id, self._options
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        state = self.coordinator.data.get(self._device_id) if self.coordinator.data else None
        return MysaDeviceLogic.get_device_info(self._device_id, self._device_data, state)

    @property
    def options(self) -> List[str]:
        """Return list of available options."""
        return self._options

    @property
    def current_option(self) -> Optional[str]:
        """Return current horizontal swing position using sticky optimistic logic."""
        # Calculate current cloud option
        state = None
        if self.coordinator.data:
            state = self.coordinator.data.get(self._device_id)
        current_cloud_option: Optional[str] = None
        if state:
            # Priority: MQTT (ssh), then HTTP (SwingStateHorizontal)
            val = state.get("ssh")
            if val is None:
                val = state.get("SwingStateHorizontal")

            if isinstance(val, dict):
                val = val.get('v')
            if val is not None:
                current_cloud_option = str(AC_HORIZONTAL_SWING_MODES.get(int(val), "auto"))

        if self._pending_option is not None:
            # 1. Check expiration
            if self._pending_timestamp and (time.time() - self._pending_timestamp > 30):
                self._pending_option = None
                self._pending_timestamp = None
                return current_cloud_option if current_cloud_option else "auto"

            # 2. Check convergence
            if current_cloud_option is not None and current_cloud_option == self._pending_option:
                self._pending_option = None
                self._pending_timestamp = None
                return current_cloud_option

            # 3. Sticky return
            return self._pending_option

        return current_cloud_option if current_cloud_option else "auto"

    async def async_select_option(self, option: str) -> None:
        """Set horizontal swing position."""
        try:
            position = AC_HORIZONTAL_SWING_MODES_REVERSE.get(option.lower())
            if position is None:
                _LOGGER.error("Unknown horizontal swing option: %s", option)
                return
            # Optimistic update
            self._pending_option = option
            self._pending_timestamp = time.time()
            self.async_write_ha_state()

            await self._api.set_ac_horizontal_swing(self._device_id, position)

        except Exception as e:
            _LOGGER.error("Failed to set horizontal swing: %s", e)
            self._pending_option = None
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="set_horizontal_swing_failed",
                translation_placeholders={"error": str(e)},
            ) from e


class MysaSensorModeSelect(
    SelectEntity, CoordinatorEntity[DataUpdateCoordinator[Dict[str, Any]]]
):
    """Select entity for In-Floor Sensor Mode."""
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "sensor_mode"

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[Dict[str, Any]],
        device_id: str,
        device_data: Dict[str, Any],
        api: MysaApi,
        entry: ConfigEntry[MysaData]
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._device_data = device_data
        self._api = api
        self._entry = entry
        self._attr_unique_id = f"{device_id}_sensor_mode"
        self._pending_option: Optional[str] = None
        self._pending_timestamp: Optional[float] = None
        self._options = list(SENSOR_MODES.values())

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        state = self.coordinator.data.get(self._device_id) if self.coordinator.data else None
        return MysaDeviceLogic.get_device_info(self._device_id, self._device_data, state)

    @property
    def options(self) -> List[str]:
        """Return list of available options."""
        return self._options

    @property
    def current_option(self) -> Optional[str]:
        """Return current sensor mode using sticky optimistic logic."""
        # Calculate current cloud option
        state = None
        if self.coordinator.data:
            state = self.coordinator.data.get(self._device_id)

        current_cloud_option: Optional[str] = None
        if state:
            # Check SensorMode/ControlMode
            val = state.get("SensorMode")
            # Fallback if SensorMode missing but ControlMode present?
            # device.py normalizes to SensorMode so we should rely on it.
            if val is not None:
                current_cloud_option = SENSOR_MODES.get(int(val))

        if self._pending_option is not None:
            # 1. Check expiration
            if self._pending_timestamp and (time.time() - self._pending_timestamp > 30):
                self._pending_option = None
                self._pending_timestamp = None
                return current_cloud_option if current_cloud_option else "ambient"

            # 2. Check convergence
            if current_cloud_option is not None and current_cloud_option == self._pending_option:
                self._pending_option = None
                self._pending_timestamp = None
                return current_cloud_option

            # 3. Sticky return
            return self._pending_option

        # Default to ambient if unknown
        return current_cloud_option if current_cloud_option else "ambient"

    async def async_select_option(self, option: str) -> None:
        """Set sensor mode."""
        try:
            mode = SENSOR_MODES_REVERSE.get(option.lower())
            if mode is None:
                _LOGGER.error("Unknown sensor mode option: %s", option)
                return

            # Optimistic update
            self._pending_option = option
            self._pending_timestamp = time.time()
            self.async_write_ha_state()

            await self._api.set_sensor_mode(self._device_id, mode)

        except Exception as e:
            _LOGGER.error("Failed to set sensor mode: %s", e)
            self._pending_option = None
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="set_sensor_mode_failed",
                translation_placeholders={"error": str(e)},
            ) from e
