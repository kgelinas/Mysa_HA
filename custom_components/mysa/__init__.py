"""The Mysa integration."""
from __future__ import annotations

import logging
import traceback
from datetime import timedelta
from functools import partial

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN, PLATFORMS
from .mysa_api import MysaApi

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Mysa from a config entry."""

    username = entry.data["username"]
    password = entry.data["password"]

    async def async_update_data():
        try:
            return await api.get_state()
        except Exception as e:

            traceback.print_exc()
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
    # Extract zone overrides (key format: zone_name_zoneid)
    zone_overrides = {k[10:]: v for k, v in entry.options.items() if k.startswith("zone_name_")}

    api = MysaApi(
        username,
        password,
        hass,
        coordinator_callback=coordinator.async_request_refresh,
        upgraded_lite_devices=upgraded_lite_devices,
        estimated_max_current=estimated_max_current,
        wattages=wattages,
        simulated_energy=simulated_energy,
        zone_overrides=zone_overrides
    )

    try:
        await api.authenticate()
    except Exception as e:
        _LOGGER.error("Failed to authenticate with Mysa API: %s", e)
        raise ConfigEntryNotReady(f"Unable to connect to Mysa API: {e}") from e

    await coordinator.async_config_entry_first_refresh()

    # Start MQTT listener for real-time updates
    await api.start_mqtt_listener()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Listen for options updates (no reload required)
    entry.async_on_unload(entry.add_update_listener(async_options_updated))

    # Register Magic Upgrade Service
    hass.services.async_register(
        DOMAIN, "upgrade_lite_device", partial(async_service_handle, hass)
    )
    hass.services.async_register(
        DOMAIN, "downgrade_lite_device", partial(async_service_handle, hass)
    )

    return True


async def async_service_handle(hass: HomeAssistant, call) -> None:
    """Handle the Magic Upgrade service."""
    device_id = call.data.get("device_id")
    mysa_device_id = _get_mysa_device_id(hass, device_id)

    if not mysa_device_id:
        _LOGGER.error("Service called for unknown device: %s", device_id)
        return

    _LOGGER.info(
        "Magic Upgrade called for device: %s (Mysa ID: %s)",
        device_id, mysa_device_id
    )

    api_instance, entry = _get_api_instance(hass, mysa_device_id)

    if not api_instance or not entry:
        _LOGGER.error("No API instance found managing device %s", mysa_device_id)
        return

    if call.service == "upgrade_lite_device":
        await _handle_upgrade(hass, api_instance, entry, mysa_device_id)
    elif call.service == "downgrade_lite_device":
        await _handle_downgrade(hass, api_instance, entry, mysa_device_id)


def _get_mysa_device_id(hass: HomeAssistant, device_id: str) -> str | None:
    """Resolve HA device ID to Mysa device ID."""
    device_registry = dr.async_get(hass)
    device_entry = device_registry.async_get(device_id)
    if device_entry:
        for identifiers in device_entry.identifiers:
            if identifiers[0] == DOMAIN:
                return identifiers[1]
    return None


def _get_api_instance(hass: HomeAssistant, mysa_device_id: str):
    """Find the API instance and config entry for a device."""
    formatted_id = mysa_device_id if ":" in mysa_device_id else mysa_device_id
    # Try both formatted and unformatted just in case, though usually one specific type matches
    for config_entry_id, data in hass.data[DOMAIN].items():
        if "api" in data:
            api_instance = data["api"]
            # Check devices list
            if formatted_id in api_instance.devices:
                entry = hass.config_entries.async_get_entry(config_entry_id)
                return api_instance, entry
    return None, None


async def _handle_upgrade(hass, api, entry, device_id):
    """Handle upgrade logic."""
    if await api.async_upgrade_lite_device(device_id):
        _update_lite_options(hass, entry, device_id, add=True)
        _LOGGER.info(
            "Auto-configured %s as Upgraded Lite device in integration options",
            device_id
        )


async def _handle_downgrade(hass, api, entry, device_id):
    """Handle downgrade logic."""
    if await api.async_downgrade_lite_device(device_id):
        _update_lite_options(hass, entry, device_id, add=False)
        _LOGGER.info(
            "Auto-configured: Removed %s from Upgraded Lite devices",
            device_id
        )


def _update_lite_options(hass, entry, device_id, add=True):
    """Update the upgraded_lite_devices option."""
    current = list(entry.options.get("upgraded_lite_devices", []))
    changed = False
    if add and device_id not in current:
        current.append(device_id)
        changed = True
    elif not add and device_id in current:
        current.remove(device_id)
        changed = True

    if changed:
        new_options = entry.options.copy()
        new_options["upgraded_lite_devices"] = current
        hass.config_entries.async_update_entry(entry, options=new_options)

async def async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    api = hass.data[DOMAIN][entry.entry_id]["api"]
    api.upgraded_lite_devices = entry.options.get("upgraded_lite_devices", [])
    api.estimated_max_current = entry.options.get("estimated_max_current", 0)
    api.simulated_energy = entry.options.get("simulated_energy", False)
    api.wattages = {k[8:]: v for k, v in entry.options.items() if k.startswith("wattage_")}
    api.zone_overrides = {k[10:]: v for k, v in entry.options.items() if k.startswith("zone_name_")}

    _LOGGER.info("Options updated: upgraded_lite_devices=%s, wattages=%s, simulated_energy=%s",
                 api.upgraded_lite_devices, api.wattages, api.simulated_energy)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Stop MQTT listener before unloading
    data = hass.data[DOMAIN].get(entry.entry_id)
    if data:
        api = data.get("api")
        if api:
            await api.stop_mqtt_listener()

    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id, None)

    return unload_ok
