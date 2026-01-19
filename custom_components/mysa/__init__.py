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

    return True


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
