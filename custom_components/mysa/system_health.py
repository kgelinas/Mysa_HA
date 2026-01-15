"""Provide info to system health for Mysa."""
from __future__ import annotations

from typing import Any

from homeassistant.components import system_health
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN


@callback
def async_register(
    _hass: HomeAssistant, register: system_health.SystemHealthRegistration
) -> None:
    """Register system health callbacks."""
    register.async_register_info(system_health_info)


async def system_health_info(hass: HomeAssistant) -> dict[str, Any]:
    """Get info for the info page."""
    data = hass.data.get(DOMAIN, {})

    # Find first entry's API
    api = None
    for entry_data in data.values():
        if isinstance(entry_data, dict) and "api" in entry_data:
            api = entry_data["api"]
            break

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
