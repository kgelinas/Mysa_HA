"""The Mysa integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, PLATFORMS
from .mysa_api import MysaApi

_LOGGER = logging.getLogger(__name__)


@dataclass
class MysaData:
    """Class to hold Mysa data."""

    api: MysaApi
    coordinator: DataUpdateCoordinator[Any]


# pylint: disable=too-many-locals,too-many-statements


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry[MysaData]) -> bool:
    # Justification: Setup function handles many config params, repair issues, device tracking.
    """Set up Mysa from a config entry."""

    username = entry.data["username"]
    password = entry.data["password"]

    first_refresh = True
    unavailable_logged = False

    async def async_update_data() -> dict[str, Any]:
        nonlocal first_refresh, unavailable_logged
        try:
            data = await api.get_state()
            if unavailable_logged:
                _LOGGER.info("Communication with API restored")
                unavailable_logged = False
            first_refresh = False
            return data
        except Exception as e:
            if not unavailable_logged:
                if first_refresh:
                    _LOGGER.error(
                        "Error communicating with API during initial setup: %s", e
                    )
                else:
                    _LOGGER.warning("Error communicating with API: %s", e)
                unavailable_logged = True
            raise UpdateFailed(f"Error communicating with API: {e}") from e

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="mysa_integration",
        update_method=async_update_data,
        # Slower polling since MQTT provides real-time updates
        update_interval=timedelta(seconds=120),
        config_entry=entry,
    )

    # Pass coordinator callback to API for MQTT updates
    # Get upgraded lite devices and wattages from options
    upgraded_lite_devices = entry.options.get("upgraded_lite_devices", [])
    estimated_max_current = entry.options.get("estimated_max_current", 0)
    simulated_energy = entry.options.get("simulated_energy", False)
    # Extract wattages (key format: wattage_deviceid)
    wattages = {k[8:]: v for k, v in entry.options.items() if k.startswith("wattage_")}

    # Get websession
    session = async_get_clientsession(hass)

    api = MysaApi(
        username,
        password,
        hass,
        # coordinator_callback will be set shortly
        upgraded_lite_devices=upgraded_lite_devices,
        estimated_max_current=estimated_max_current,
        wattages=wattages,
        simulated_energy=simulated_energy,
        websession=session,
    )

    async def async_push_update() -> None:
        """Push updated state to coordinator listeners without polling."""
        # This notifies HA that data has changed, updating the UI immediately.
        # We use api.states as the source of truth.
        coordinator.async_set_updated_data(api.states)

    api.coordinator_callback = async_push_update

    try:
        await api.authenticate()
        # Clear any existing auth issues on successful authentication
        ir.async_delete_issue(hass, DOMAIN, "auth_failed")
    except Exception as e:
        _LOGGER.error("Failed to authenticate with Mysa API: %s", e)
        # Create a repair issue for authentication failure
        ir.async_create_issue(
            hass,
            DOMAIN,
            "auth_failed",
            is_fixable=True,
            is_persistent=True,
            severity=ir.IssueSeverity.ERROR,
            translation_key="auth_failed",
            translation_placeholders={"error": str(e)},
        )
        raise ConfigEntryAuthFailed(f"Authentication failed: {e}") from e

    await coordinator.async_config_entry_first_refresh()

    # Start MQTT listener for real-time updates
    await api.start_mqtt_listener()

    entry.runtime_data = MysaData(api=api, coordinator=coordinator)

    # Maintain hass.data[DOMAIN] for backward compatibility and integration with mysa_extended
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Monitor for device changes during polling and remove stale devices
    previous_devices: set[str] = (
        set(coordinator.data.keys()) if coordinator.data else set()
    )

    def check_device_changes() -> None:
        """Check if devices were added or removed and handle stale device removal."""
        nonlocal previous_devices
        if not coordinator.data:
            return
        current_devices = set(coordinator.data.keys())

        # Handle new devices - reload to add them
        new_devices = current_devices - previous_devices
        if new_devices:
            _LOGGER.info(
                "New devices detected: %s. Reloading integration.", new_devices
            )
            hass.async_create_task(hass.config_entries.async_reload(entry.entry_id))
            return

        # Handle stale devices - remove them from device registry
        stale_devices = previous_devices - current_devices
        if stale_devices:
            device_registry = dr.async_get(hass)
            for device_id in stale_devices:
                device = device_registry.async_get_device(
                    identifiers={(DOMAIN, device_id)}
                )
                if device:
                    _LOGGER.info("Removing stale device: %s", device_id)
                    device_registry.async_update_device(
                        device_id=device.id,
                        remove_config_entry_id=entry.entry_id,
                    )

        previous_devices = current_devices

    entry.async_on_unload(coordinator.async_add_listener(check_device_changes))

    # Listen for options updates (no reload required)
    entry.async_on_unload(entry.add_update_listener(async_options_updated))

    return True


async def async_options_updated(
    _hass: HomeAssistant, entry: ConfigEntry[MysaData]
) -> None:
    """Handle options update."""
    api = entry.runtime_data.api
    api.upgraded_lite_devices = entry.options.get("upgraded_lite_devices", [])
    api.estimated_max_current = entry.options.get("estimated_max_current", 0)
    api.simulated_energy = entry.options.get("simulated_energy", False)
    api.wattages = {
        k[8:]: v for k, v in entry.options.items() if k.startswith("wattage_")
    }

    _LOGGER.info(
        "Options updated: upgraded_lite_devices=%s, wattages=%s, simulated_energy=%s",
        api.upgraded_lite_devices,
        api.wattages,
        api.simulated_energy,
    )


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry[MysaData]) -> bool:
    """Unload a config entry."""
    # Stop MQTT listener before unloading
    if entry.runtime_data:
        api = entry.runtime_data.api
        if api:
            await api.stop_mqtt_listener()

    return bool(await hass.config_entries.async_unload_platforms(entry, PLATFORMS))


async def async_remove_config_entry_device(
    _hass: HomeAssistant,
    config_entry: ConfigEntry[MysaData],
    device_entry: dr.DeviceEntry,
) -> bool:
    """Allow device removal if the device is no longer in the cloud API.

    This enables the delete button in the UI for devices that have been
    removed from the Mysa cloud but still exist in the device registry.
    """
    # Check if the device is still in the current API data
    if not config_entry.runtime_data:
        return True  # Allow removal if no runtime data

    api = config_entry.runtime_data.api
    if not api or not api.devices:
        return True  # Allow removal if no devices loaded

    # Check if any identifier matches a current device
    for identifier in device_entry.identifiers:
        if identifier[0] == DOMAIN and identifier[1] in api.devices:
            # Device still exists in cloud - don't allow removal
            return False

    # Device not found in cloud - allow removal
    return True
