"""Diagnostics support for Mysa."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .const import DOMAIN

TO_REDACT = {CONF_PASSWORD, CONF_USERNAME}

async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    api = data["api"]

    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "devices": api.devices,
        "states": api.states,
        "homes": api.homes,
        "zones": api.zones,
        "upgraded_lite_devices": api.upgraded_lite_devices,
        "estimated_max_current": api.estimated_max_current,
    }
