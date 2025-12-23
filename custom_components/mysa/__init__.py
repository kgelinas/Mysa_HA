"""The Mysa integration."""
from __future__ import annotations

import logging
import sys
import os

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Add lib folder to path for vendored dependencies
# This is needed because we are vendoring mysotherm and mqttpacket
current_path = os.path.dirname(os.path.abspath(__file__))
lib_path = os.path.join(current_path, "lib")
if lib_path not in sys.path:
    sys.path.insert(0, lib_path)

# Now imports from lib/ should work if we construct the package correctly
# However, usually vendoring in HA requires namespacing or modifying imports.
# For simplicity in this custom component, we will try to rely on path insertion
# or we might need to adjust imports in the vendored code if they use absolute imports.

# TODO: Check if mysotherm uses absolute imports that might conflict or fail.

PLATFORMS: list[Platform] = [Platform.CLIMATE]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Mysa from a config entry."""
    
    hass.data.setdefault(DOMAIN, {})
    
    # Initialization of API client will happen here
    # For now just passing
    
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id, None)

    return unload_ok
