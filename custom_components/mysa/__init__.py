"""The Mysa integration."""
from __future__ import annotations

import logging
import sys
import os

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS

_LOGGER = logging.getLogger(__name__)

# Add lib folder to path for vendored dependencies
# Add lib folder to path for vendored mysotherm dependency
current_path = os.path.dirname(os.path.abspath(__file__))
lib_path = os.path.join(current_path, "lib")
if lib_path not in sys.path:
    sys.path.insert(0, lib_path)



from datetime import timedelta
from .mysa_api import MysaApi
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed



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
        update_interval=timedelta(seconds=120),  # Slower polling since MQTT provides real-time updates
    )
    
    # Pass coordinator callback to API for MQTT updates
    # Get upgraded lite devices from options
    upgraded_lite_devices = entry.options.get("upgraded_lite_devices", [])
    
    api = MysaApi(
        username, 
        password, 
        hass, 
        coordinator_callback=coordinator.async_request_refresh,
        upgraded_lite_devices=upgraded_lite_devices
    )
    
    try:
        await api.authenticate()
    except Exception as e:
        raise UpdateFailed(f"Authentication failed: {e}") from e

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
    
    return True


async def async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    api = hass.data[DOMAIN][entry.entry_id]["api"]
    api.upgraded_lite_devices = entry.options.get("upgraded_lite_devices", [])
    _LOGGER.info("Options updated: upgraded_lite_devices = %s", api.upgraded_lite_devices)

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
