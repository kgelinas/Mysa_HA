"""Switch platform for Mysa."""

# pylint: disable=abstract-method
# Justification: HA Entity properties implement the required abstracts.
import logging
import time
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from . import MysaData
from .const import DOMAIN
from .device import MysaDeviceLogic
from .mysa_api import MysaApi

PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: ConfigEntry[MysaData],
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Mysa switches."""
    coordinator = entry.runtime_data.coordinator
    api = entry.runtime_data.api
    devices = await api.get_devices()
    entities: list[SwitchEntity] = []
    for device_id, device_data in devices.items():
        is_ac = api.is_ac_device(device_id)
        # Lock switch (all devices)
        entities.append(MysaLockSwitch(coordinator, device_id, device_data, api, entry))
        # Heating thermostat only switches
        if not is_ac:
            entities.append(
                MysaAutoBrightnessSwitch(
                    coordinator, device_id, device_data, api, entry
                )
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


class MysaSwitch(
    SwitchEntity, CoordinatorEntity[DataUpdateCoordinator[dict[str, Any]]]
):
    """Base class for Mysa switches.

    TODO: Refactor MysaSwitch to reduce instance attributes and duplicate code.
    """

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, Any]],
        device_id: str,
        device_data: dict[str, Any],
        api: MysaApi,
        entry: ConfigEntry[MysaData],
        sensor_key: str,
        translation_key: str,
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
        self._pending_state: bool | None = None
        self._pending_timestamp: float | None = None

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

    def _extract_value(self, state: dict[str, Any] | None, keys: list[str]) -> Any:
        """Helper to extract a value from state dictionary."""
        if state is None:
            return None
        for key in keys:
            val = state.get(key)
            if val is not None:
                if isinstance(val, dict):
                    v = val.get("v")
                    if v is None:
                        v = val.get("Id")
                    return v
                return val
        return None

    def _get_state_with_pending(self, keys: list[str]) -> bool:
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

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, Any]],
        device_id: str,
        device_data: dict[str, Any],
        api: MysaApi,
        entry: ConfigEntry[MysaData],
    ) -> None:
        # TODO: Refactor __init__ to reduce arguments
        """Initialize."""
        super().__init__(
            coordinator, device_id, device_data, api, entry, "Lock", "lock"
        )

    @property
    def is_on(self) -> bool | None:
        """Return true if locked."""
        return self._get_state_with_pending(["lk", "alk", "lc", "Lock", "ButtonState"])

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Lock the thermostat."""
        self._pending_state = True
        self._pending_timestamp = time.time()
        self.async_write_ha_state()
        try:
            await self._api.set_lock(self._device_id, True)
        except Exception as e:
            self._pending_state = None
            self.async_write_ha_state()
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="set_lock_failed",
                translation_placeholders={"error": str(e)},
            ) from e

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Unlock the thermostat."""
        self._pending_state = False
        self._pending_timestamp = time.time()
        self.async_write_ha_state()
        try:
            await self._api.set_lock(self._device_id, False)
        except Exception as e:
            self._pending_state = None
            self.async_write_ha_state()
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="set_lock_failed",
                translation_placeholders={"error": str(e)},
            ) from e


class MysaAutoBrightnessSwitch(MysaSwitch):  # TODO: Implement abstract methods
    """Switch for auto brightness."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, Any]],
        device_id: str,
        device_data: dict[str, Any],
        api: MysaApi,
        entry: ConfigEntry[MysaData],
    ) -> None:
        # TODO: Refactor __init__ to reduce arguments
        """Initialize."""
        super().__init__(
            coordinator,
            device_id,
            device_data,
            api,
            entry,
            "AutoBrightness",
            "auto_brightness",
        )

    @property
    def is_on(self) -> bool | None:
        """Return true if auto brightness is enabled."""
        return self._get_state_with_pending(["ab", "AutoBrightness"])

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable auto brightness."""
        self._pending_state = True
        self._pending_timestamp = time.time()
        self.async_write_ha_state()
        try:
            await self._api.set_auto_brightness(self._device_id, True)
        except Exception as e:
            self._pending_state = None
            self.async_write_ha_state()
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="set_auto_brightness_failed",
                translation_placeholders={"error": str(e)},
            ) from e

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable auto brightness."""
        self._pending_state = False
        self._pending_timestamp = time.time()
        self.async_write_ha_state()
        try:
            await self._api.set_auto_brightness(self._device_id, False)
        except Exception as e:
            self._pending_state = None
            self.async_write_ha_state()
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="set_auto_brightness_failed",
                translation_placeholders={"error": str(e)},
            ) from e


class MysaProximitySwitch(MysaSwitch):  # TODO: Implement abstract methods
    """Switch for proximity mode (wake on approach)."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, Any]],
        device_id: str,
        device_data: dict[str, Any],
        api: MysaApi,
        entry: ConfigEntry[MysaData],
    ) -> None:
        # TODO: Refactor __init__ to reduce arguments
        """Initialize."""
        super().__init__(
            coordinator,
            device_id,
            device_data,
            api,
            entry,
            "ProximityMode",
            "proximity",
        )

    @property
    def is_on(self) -> bool | None:
        """Return true if proximity mode is enabled."""
        return self._get_state_with_pending(["px", "pr", "ProximityMode", "Proximity"])

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable proximity mode."""
        self._pending_state = True
        self._pending_timestamp = time.time()
        self.async_write_ha_state()
        try:
            await self._api.set_proximity(self._device_id, True)
        except Exception as e:
            self._pending_state = None
            self.async_write_ha_state()
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="set_proximity_failed",
                translation_placeholders={"error": str(e)},
            ) from e

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable proximity mode."""
        self._pending_state = False
        self._pending_timestamp = time.time()
        self.async_write_ha_state()
        try:
            await self._api.set_proximity(self._device_id, False)
        except Exception as e:
            self._pending_state = None
            self.async_write_ha_state()
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="set_proximity_failed",
                translation_placeholders={"error": str(e)},
            ) from e


class MysaClimatePlusSwitch(MysaSwitch):  # TODO: Implement abstract methods
    """Switch for AC Climate+ mode (IsThermostatic).

    When enabled, the Mysa uses its temperature sensor to control the AC.
    When disabled, it acts as a simple IR remote.
    """

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, Any]],
        device_id: str,
        device_data: dict[str, Any],
        api: MysaApi,
        entry: ConfigEntry[MysaData],
    ) -> None:
        # TODO: Refactor __init__ to reduce arguments
        """Initialize."""
        super().__init__(
            coordinator,
            device_id,
            device_data,
            api,
            entry,
            "IsThermostatic",
            "climate_plus",
        )

    @property
    def is_on(self) -> bool | None:
        """Return true if Climate+ is enabled."""
        return self._get_state_with_pending(["EcoMode", "it", "IsThermostatic"])

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable Climate+ mode."""
        self._pending_state = True
        self._pending_timestamp = time.time()
        self.async_write_ha_state()
        try:
            await self._api.set_ac_climate_plus(self._device_id, True)
        except Exception as e:
            self._pending_state = None
            self.async_write_ha_state()
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="set_climate_plus_failed",
                translation_placeholders={"error": str(e)},
            ) from e

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable Climate+ mode."""
        self._pending_state = False
        self._pending_timestamp = time.time()
        self.async_write_ha_state()
        try:
            await self._api.set_ac_climate_plus(self._device_id, False)
        except Exception as e:
            self._pending_state = None
            self.async_write_ha_state()
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="set_climate_plus_failed",
                translation_placeholders={"error": str(e)},
            ) from e
