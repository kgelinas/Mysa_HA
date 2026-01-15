"""Select platform for Mysa AC horizontal swing."""
# pylint: disable=abstract-method
import logging
import time


from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    AC_HORIZONTAL_SWING_MODES,
    AC_HORIZONTAL_SWING_MODES_REVERSE,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Mysa select entities."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    api = data["api"]
    devices = await api.get_devices()

    entities = []
    for device_id, device_data in devices.items():
        # Add horizontal swing select only for AC devices
        if api.is_ac_device(device_id):
            entities.append(
                MysaHorizontalSwingSelect(coordinator, device_id, device_data, api, entry)
            )

    if entities:
        async_add_entities(entities)


class MysaHorizontalSwingSelect(
    CoordinatorEntity, SelectEntity
):  # TODO: Refactor MysaHorizontalSwingSelect to reduce instance attributes, duplicate code, and implement abstract methods
    """Select entity for AC horizontal swing position."""

    _attr_icon = "mdi:arrow-left-right"

    def __init__(  # TODO: Refactor __init__ to reduce arguments
        self, coordinator, device_id, device_data, api, entry
    ):
        """Initialize."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._device_data = device_data
        self._api = api
        self._entry = entry
        self._attr_name = f"{device_data.get('Name', 'Mysa AC')} Horizontal Swing"
        self._attr_unique_id = f"{device_id}_horizontal_swing"
        self._pending_option = None
        self._pending_timestamp = None

        # Build options from SupportedCaps or defaults
        self._build_options(device_data)

    def _build_options(self, device_data):
        """Build list of available horizontal swing options."""
        supported_caps = device_data.get("SupportedCaps", {})
        supported_caps = device_data.get("SupportedCaps", {})
        modes = supported_caps.get("modes", {})

        # Get horizontal swing positions from first available mode
        self._options = []
        for _, mode_caps in modes.items():
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

    @property
    def options(self) -> list[str]:
        """Return list of available options."""
        return self._options

    @property
    def current_option(self) -> str | None:
        """Return current horizontal swing position using sticky optimistic logic."""
        # Calculate current cloud option
        state = None
        if self.coordinator.data:
            state = self.coordinator.data.get(self._device_id)
        current_cloud_option = None
        if state:
            val = state.get("SwingStateHorizontal")
            if isinstance(val, dict):
                val = val.get('v')
            if val is not None:
                current_cloud_option = AC_HORIZONTAL_SWING_MODES.get(int(val), "auto")

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

        except Exception as e:  # TODO: Catch specific exceptions instead of Exception
            _LOGGER.error("Failed to set horizontal swing: %s", e)
            self._pending_option = None
