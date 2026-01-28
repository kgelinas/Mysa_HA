"""Diagnostics support for Mysa."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from . import MysaData

TO_REDACT = {CONF_PASSWORD, CONF_USERNAME}


async def async_get_config_entry_diagnostics(
    _: HomeAssistant, entry: ConfigEntry[MysaData]
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    api = entry.runtime_data.api

    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "devices": api.devices,
        "states": api.states,
        "homes": api.homes,
        "upgraded_lite_devices": api.upgraded_lite_devices,
        "estimated_max_current": api.estimated_max_current,
    }
