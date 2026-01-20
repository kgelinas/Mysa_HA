"""
Mysa Extended Integration

Provides advanced/experimental features for Mysa thermostats.
Requires the base 'mysa' integration to be installed and configured.

WARNING: Features in this integration may void warranties or cause
unexpected behavior. Use at your own risk.
"""
from __future__ import annotations

import logging
from functools import partial
from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr

# Import from base mysa integration
from custom_components.mysa.const import DOMAIN as MYSA_DOMAIN

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


# pylint: disable=unused-argument
# Justification: Required by Home Assistant callback signature.
async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the Mysa Extended integration."""
    # Services registered via async_setup_services, but only once
    if not hass.services.has_service(DOMAIN, "upgrade_lite_device"):
        async_setup_services(hass)
    return True


# pylint: disable=unused-argument
# Justification: Required by Home Assistant callback signature.
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Mysa Extended from a config entry."""
    # Services registered via async_setup_services, but only once
    if not hass.services.has_service(DOMAIN, "upgrade_lite_device"):
        async_setup_services(hass)
    return True


# pylint: disable=unused-argument
# Justification: Required by Home Assistant callback signature.
async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return True


def _get_mysa_device_info(hass: HomeAssistant, device_id: str) -> tuple[str, ConfigEntry, Any]:
    """Resolve HA device ID to Mysa device ID and API instance."""
    # Get actual device registry entry
    device_registry = dr.async_get(hass)
    device_entry = device_registry.async_get(device_id)

    if not device_entry:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="device_not_found",
            translation_placeholders={"device_id": device_id}
        )

    # Find mysa device ID and config entry
    mysa_device_id: str | None = None
    mysa_entry: ConfigEntry | None = None

    # Check mysa domain data exists
    if MYSA_DOMAIN not in hass.data:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="mysa_integration_not_loaded"
        )

    for entry_id in device_entry.config_entries if device_entry else []:
        if entry_id in hass.data[MYSA_DOMAIN]:
            mysa_entry = hass.config_entries.async_get_entry(entry_id)
            for identifier in device_entry.identifiers if device_entry else []:
                if identifier[0] == MYSA_DOMAIN:
                    mysa_device_id = identifier[1]
                    break
            if mysa_device_id:
                break

    if not mysa_entry or not mysa_device_id:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="mysa_integration_not_found_for_device",
            translation_placeholders={"device_id": device_id}
        )

    mysa_data = hass.data[MYSA_DOMAIN].get(mysa_entry.entry_id)
    if not mysa_data or not isinstance(mysa_data, dict):
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="mysa_data_invalid"
        )

    api = mysa_data.get("api")
    if not api:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="mysa_api_not_initialized"
        )

    return mysa_device_id, mysa_entry, api


async def async_service_upgrade_lite(call: ServiceCall, hass: HomeAssistant) -> None:
    """Service to upgrade a Lite device to Full."""
    device_id = str(call.data["device_id"])

    try:
        mysa_device_id, mysa_entry, api = _get_mysa_device_info(hass, device_id)

        # Call the upgrade method
        if await api.async_upgrade_lite_device(mysa_device_id):
            # Update cache to persist this change
            current = list(mysa_entry.options.get("upgraded_lite_devices", []))
            if mysa_device_id not in current:
                current.append(mysa_device_id)
                new_options = dict(mysa_entry.options)
                new_options["upgraded_lite_devices"] = current
                hass.config_entries.async_update_entry(mysa_entry, options=new_options)

            _LOGGER.info("Successfully upgraded device %s and updated core options", mysa_device_id)
        else:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="upgrade_failed",
                translation_placeholders={"device_id": mysa_device_id}
            )

    except Exception as err:
        _LOGGER.error("Error upgrading device: %s", err)
        if isinstance(err, HomeAssistantError):
            raise
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="upgrade_error",
            translation_placeholders={"error": str(err)}
        ) from err


async def async_service_downgrade_lite(call: ServiceCall, hass: HomeAssistant) -> None:
    """Service to downgrade a device back to Lite."""
    device_id = str(call.data["device_id"])

    try:
        mysa_device_id, mysa_entry, api = _get_mysa_device_info(hass, device_id)

        # Call the downgrade method
        if await api.async_downgrade_lite_device(mysa_device_id):
            # Update core integration options (remove from list)
            current = list(mysa_entry.options.get("upgraded_lite_devices", []))
            if mysa_device_id in current:
                current.remove(mysa_device_id)
                new_options = dict(mysa_entry.options)
                new_options["upgraded_lite_devices"] = current
                hass.config_entries.async_update_entry(mysa_entry, options=new_options)

            _LOGGER.info("Successfully reverted device %s and updated core options", mysa_device_id)
        else:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="downgrade_failed",
                translation_placeholders={"device_id": mysa_device_id}
            )

    except Exception as err:
        _LOGGER.error("Error reverting device: %s", err)
        if isinstance(err, HomeAssistantError):
            raise
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="downgrade_error",
            translation_placeholders={"error": str(err)}
        ) from err


async def async_service_killer_ping(call: ServiceCall, hass: HomeAssistant) -> None:
    """Service to restart device into pairing mode."""
    device_id = str(call.data["device_id"])

    try:
        mysa_device_id, _mysa_entry, api = _get_mysa_device_info(hass, device_id)

        # Call the killer ping method
        success = await api.async_send_killer_ping(mysa_device_id)

        if success:
            _LOGGER.warning(
                "Killer Ping sent to %s. Device will restart into pairing mode!",
                mysa_device_id
            )
        else:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="killer_ping_failed",
                translation_placeholders={"device_id": mysa_device_id}
            )

    except Exception as err:
        _LOGGER.error("Error sending killer ping: %s", err)
        if isinstance(err, HomeAssistantError):
            raise
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="killer_ping_error",
            translation_placeholders={"error": str(err)}
        ) from err


# Auto-register services when integration loads
# This helper is called by both async_setup and async_setup_entry
@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Set up services for mysa_extended."""

    # Register upgrade service
    hass.services.async_register(
        DOMAIN, "upgrade_lite_device",
        partial(async_service_upgrade_lite, hass=hass)
    )

    # Register downgrade service
    hass.services.async_register(
        DOMAIN, "downgrade_lite_device",
        partial(async_service_downgrade_lite, hass=hass)
    )

    # Register killer ping service
    hass.services.async_register(
        DOMAIN, "killer_ping",
        partial(async_service_killer_ping, hass=hass)
    )

    _LOGGER.debug("Mysa Extended services registered")
