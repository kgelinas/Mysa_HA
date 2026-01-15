"""The Mysa integration."""
from __future__ import annotations

import logging
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
    # Extract wattages (key format: wattage_deviceid)
    wattages = {k[8:]: v for k, v in entry.options.items() if k.startswith("wattage_")}

    api = MysaApi(
        username,
        password,
        hass,
        coordinator_callback=coordinator.async_request_refresh,
        upgraded_lite_devices=upgraded_lite_devices,
        estimated_max_current=estimated_max_current,
        wattages=wattages
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
    
    # Resolve device_registry entry to Mysa device ID
    device_registry = dr.async_get(hass)
    device_entry = device_registry.async_get(device_id)
    
    mysa_device_id = None
    if device_entry:
        for identifiers in device_entry.identifiers:
            if identifiers[0] == DOMAIN:
                mysa_device_id = identifiers[1]
                break
    
    if not mysa_device_id:
            _LOGGER.error("Service called for unknown device: %s", device_id)
            return

    _LOGGER.info("Magic Upgrade called for device: %s (Mysa ID: %s)", device_id, mysa_device_id)
    
    # Find the API instance that owns this device
    target_api = None
    target_entry = None
    for config_entry_id, data in hass.data[DOMAIN].items():
        if "api" in data:
            api_instance = data["api"]
            if mysa_device_id in api_instance.devices:
                target_api = api_instance
                target_entry = hass.config_entries.async_get_entry(config_entry_id)
                break
    
    if target_api and target_entry:
        if call.service == "upgrade_lite_device":
            if await target_api.async_upgrade_lite_device(mysa_device_id):
                # Auto-configure: Add to "upgraded_lite_devices" option
                current_upgraded = list(target_entry.options.get("upgraded_lite_devices", []))
                if mysa_device_id not in current_upgraded:
                    current_upgraded.append(mysa_device_id)
                    new_options = target_entry.options.copy()
                    new_options["upgraded_lite_devices"] = current_upgraded
                    
                    hass.config_entries.async_update_entry(target_entry, options=new_options)
                    _LOGGER.info("Auto-configured %s as Upgraded Lite device in integration options", mysa_device_id)
        elif call.service == "downgrade_lite_device":
            if await target_api.async_downgrade_lite_device(mysa_device_id):
                # Auto-configure: Remove from "upgraded_lite_devices" option
                current_upgraded = list(target_entry.options.get("upgraded_lite_devices", []))
                if mysa_device_id in current_upgraded:
                    current_upgraded.remove(mysa_device_id)
                    new_options = target_entry.options.copy()
                    new_options["upgraded_lite_devices"] = current_upgraded
                    
                    hass.config_entries.async_update_entry(target_entry, options=new_options)
                    _LOGGER.info("Auto-configured: Removed %s from Upgraded Lite devices", mysa_device_id)
    else:
        _LOGGER.error("No API instance found managing device %s", mysa_device_id)


async def async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    api = hass.data[DOMAIN][entry.entry_id]["api"]
    api.upgraded_lite_devices = entry.options.get("upgraded_lite_devices", [])
    api.estimated_max_current = entry.options.get("estimated_max_current", 0)
    api.wattages = {k[8:]: v for k, v in entry.options.items() if k.startswith("wattage_")}

    _LOGGER.info("Options updated: upgraded_lite_devices=%s, wattages=%s",
                 api.upgraded_lite_devices, api.wattages)


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
