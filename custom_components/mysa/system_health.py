"""Provide info to system health for Mysa."""

from __future__ import annotations

from typing import Any, cast

from homeassistant.components import system_health
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN
from .mysa_api import MysaApi


@callback
def async_register(
    _hass: HomeAssistant, register: system_health.SystemHealthRegistration
) -> None:
    """Register system health callbacks."""
    register.async_register_info(system_health_info)


async def system_health_info(hass: HomeAssistant) -> dict[str, Any]:
    """Get info for the info page."""
    api: MysaApi | None = None

    # Prioritize hass.data[DOMAIN] for backward compatibility and test support
    # This matches the legacy structure expected by existing tests
    mysa_data = hass.data.get(DOMAIN, {})
    if isinstance(mysa_data, dict):
        for entry_id in mysa_data:
            data = mysa_data[entry_id]
            if isinstance(data, dict) and "api" in data:
                api = cast(MysaApi, data["api"])
                break

    # Fallback to config entries if not found in hass.data
    if not api:
        entries = hass.config_entries.async_entries(DOMAIN)
        for entry in entries:
            if hasattr(entry, "runtime_data") and entry.runtime_data:
                try:
                    api = entry.runtime_data.api
                    break
                except AttributeError:
                    pass

    if not api:
        return {
            "api_connected": False,
            "devices": 0,
            "mqtt_listener": "Not running",
        }

    return {
        "api_connected": api.is_connected,
        "devices": len(api.devices) if api.devices else 0,
        "mqtt_listener": "Running" if api.is_mqtt_running else "Stopped",
    }
