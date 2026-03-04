"""Number platform for Mysa."""

from __future__ import annotations

# pylint: disable=abstract-method
# Justification: Inherits from HA NumberEntity and RestoreEntity which have abstract methods.
# Justification: HA Entity properties implement the required abstracts.
import logging
import time
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory
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
    """Set up Mysa number entities."""
    coordinator = entry.runtime_data.coordinator
    api = entry.runtime_data.api
    # Get devices to create entities
    devices = api.devices

    entities: list[NumberEntity] = []
    for device_id, device_data in devices.items():
        # Min/Max Brightness
        entities.append(
            MysaMinBrightnessNumber(coordinator, device_id, device_data, api, entry)
        )
        entities.append(
            MysaMaxBrightnessNumber(coordinator, device_id, device_data, api, entry)
        )

        # Min/Max Setpoint limits for all heating devices
        entities.append(
            MysaMinSetpointNumber(coordinator, device_id, device_data, api, entry)
        )
        entities.append(
            MysaMaxSetpointNumber(coordinator, device_id, device_data, api, entry)
        )

        # ST-V1-0 Auto Deadband
        if MysaDeviceLogic.is_stv10_device(device_data):
            entities.append(
                MysaAutoDeadbandNumber(coordinator, device_id, device_data, api, entry)
            )

    async_add_entities(entities)


class MysaNumber(
    NumberEntity, CoordinatorEntity[DataUpdateCoordinator[dict[str, Any]]]
):
    """Base class for Mysa number entities.

    TODO: Refactor MysaNumber to reduce instance attributes,
    duplicate code, and implement abstract methods.
    """

    _attr_native_min_value: float = 0.0
    _attr_native_max_value: float = 100.0
    _attr_native_step: float = 1.0
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER
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
        self._pending_value: float | None = (
            None  # Track pending value to avoid 'unknown' state
        )
        self._pending_time: float | None = None  # Timestamp when pending was set

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

    def _get_value_with_pending(self, keys: list[str]) -> float | None:
        """Get value using sticky optimistic logic."""
        # Cloud value
        state = None
        if self.coordinator.data:
            state = self.coordinator.data.get(self._device_id)
        val = self._extract_value(state, keys) if state else None

        current_val: float | None = None
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
            "MinBrightness",
            "min_brightness",
        )

    @property
    def native_value(self) -> float | None:
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
            "MaxBrightness",
            "max_brightness",
        )

    @property
    def native_value(self) -> float | None:
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


class MysaAutoDeadbandNumber(MysaNumber):
    """Number entity for ST-V1-0 Auto Mode Deadband."""

    _attr_native_min_value = 2.0
    _attr_native_max_value = 6.0
    _attr_native_step = 0.5
    _attr_native_unit_of_measurement = "°C"

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, Any]],
        device_id: str,
        device_data: dict[str, Any],
        api: MysaApi,
        entry: ConfigEntry[MysaData],
    ) -> None:
        """Initialize."""
        super().__init__(
            coordinator,
            device_id,
            device_data,
            api,
            entry,
            "AutoDeadband",
            "auto_deadband",
        )
        # Inherit available from coordinator?
        # CoordinatorEntity by default is available if coordinator.last_update_success
        # We want to override this to also check auto_mode_enabled

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # 1. Check parent availability (coordinator success)
        if not super().available:
            return False

        # 2. Only hide when Auto Mode is explicitly disabled (app-parity).
        # If the key is absent (e.g. just after reboot, before first poll),
        # we treat the state as unknown and keep the entity available to
        # avoid a false "unavailable" flash on startup.
        state = self.coordinator.data.get(self._device_id, {})

        # Check simple key: only hide if explicitly 0
        val = state.get("auto_mode_enabled")
        if val is not None:
            return bool(val)

        # Check shadow structure: only hide if explicitly 0
        target_auto = state.get("targetAuto")
        if isinstance(target_auto, dict) and "enabled" in target_auto:
            return bool(target_auto["enabled"])

        # Key absent entirely → state unknown, keep available (avoid false flash)
        return True

    @property
    def native_value(self) -> float | None:
        """Return current deadband value."""
        # ST-V1-0 usually reports auto_deadband in degrees, autoDeadband in centidegrees
        val = self._get_value_with_pending(["auto_deadband", "autoDeadband"])
        if val is None:
            return None
        # Heuristic: if > 50, it's likely centidegrees (2.0-6.0 range expected)
        return float(val) / 100.0 if float(val) > 50 else float(val)

    async def async_set_native_value(self, value: float) -> None:
        """Set deadband value."""
        self._pending_value = float(value)
        self._pending_time = time.time()
        self.async_write_ha_state()
        try:
            await self._api.set_stv10_auto_deadband(self._device_id, float(value))
        except Exception as e:
            self._pending_value = None
            self.async_write_ha_state()
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="set_target_failed",
                translation_placeholders={"error": str(e)},
            ) from e


class MysaMinSetpointNumber(MysaNumber):
    """Number entity for minimum setpoint limit."""

    _attr_native_min_value = 5.0
    _attr_native_max_value = 30.0
    _attr_native_step = 0.5
    _attr_native_unit_of_measurement = "°C"

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, Any]],
        device_id: str,
        device_data: dict[str, Any],
        api: MysaApi,
        entry: ConfigEntry[MysaData],
    ) -> None:
        """Initialize."""
        super().__init__(
            coordinator,
            device_id,
            device_data,
            api,
            entry,
            "MinSetpoint",
            "min_setpoint",
        )

    @property
    def native_value(self) -> float | None:
        """Return current min setpoint value."""
        # Note: legacy devices usually report mnsp/MinSetpoint in centidegrees
        # ST-V1-0 reports min_setpoint in degrees and MinSetpoint/lockoutMin in centidegrees
        val = self._get_value_with_pending(["min_setpoint", "mns", "MinSetpoint"])
        if val is None:
            return None
        # Heuristic: if > 100, it's likely centidegrees
        return float(val) / 100.0 if float(val) > 100 else float(val)

    async def async_set_native_value(self, value: float) -> None:
        """Set minimum setpoint."""
        self._pending_value = float(
            value * 100
        )  # Store as centidegrees for pending check
        self._pending_time = time.time()
        self.async_write_ha_state()
        try:
            await self._api.set_min_setpoint(self._device_id, value)
        except Exception as e:
            self._pending_value = None
            self.async_write_ha_state()
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="set_min_setpoint_failed",
                translation_placeholders={"error": str(e)},
            ) from e


class MysaMaxSetpointNumber(MysaNumber):
    """Number entity for maximum setpoint limit."""

    _attr_native_min_value = 5.0
    _attr_native_max_value = 30.0
    _attr_native_step = 0.5
    _attr_native_unit_of_measurement = "°C"

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, Any]],
        device_id: str,
        device_data: dict[str, Any],
        api: MysaApi,
        entry: ConfigEntry[MysaData],
    ) -> None:
        """Initialize."""
        super().__init__(
            coordinator,
            device_id,
            device_data,
            api,
            entry,
            "MaxSetpoint",
            "max_setpoint",
        )

    @property
    def native_value(self) -> float | None:
        """Return current max setpoint value."""
        # Note: legacy devices usually report mxsp/MaxSetpoint in centidegrees
        # ST-V1-0 reports max_setpoint in degrees and MaxSetpoint/lockoutMax in centidegrees
        val = self._get_value_with_pending(["max_setpoint", "mxs", "MaxSetpoint"])
        if val is None:
            return None
        # Heuristic: if > 100, it's likely centidegrees
        return float(val) / 100.0 if float(val) > 100 else float(val)

    async def async_set_native_value(self, value: float) -> None:
        """Set maximum setpoint."""
        self._pending_value = float(value * 100)
        self._pending_time = time.time()
        self.async_write_ha_state()
        try:
            await self._api.set_max_setpoint(self._device_id, value)
        except Exception as e:
            self._pending_value = None
            self.async_write_ha_state()
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="set_max_setpoint_failed",
                translation_placeholders={"error": str(e)},
            ) from e
