"""Config flow for Mysa integration."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv

from .const import DOMAIN
from .mysa_api import MysaApi

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)

from homeassistant.core import callback

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Mysa."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> MysaOptionsFlowHandler:
        """Get the options flow for this handler."""
        return MysaOptionsFlowHandler(config_entry)

    def __init__(self) -> None:
        """Initialize."""
        self._user_input: dict[str, Any] = {}
        self._zones_map: dict[str, list[str]] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                # Validate credentials and fetch devices/zones
                api = await self._validate_credentials(
                    user_input[CONF_USERNAME], 
                    user_input[CONF_PASSWORD]
                )
                self._user_input = user_input
                
                # Fetch zones from metadata
                self._zones_map = {}
                for d_id, d_data in api.devices.items():
                    # Check both device_data and potentially state if normalized
                    zone_id = d_data.get("Zone")
                    if zone_id:
                         if zone_id not in self._zones_map:
                             self._zones_map[zone_id] = []
                         self._zones_map[zone_id].append(d_data.get("Name", d_id))
                
                if self._zones_map:
                    return await self.async_step_zones()
                
                return self.async_create_entry(
                    title=user_input[CONF_USERNAME], data=user_input
                )
            except Exception as e:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "invalid_auth"

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_zones(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle zone naming step."""
        if user_input is not None:
            # Extract zone_id from the dynamic keys: "Zone name for ... (ID: ...)"
            options = {}
            for key, val in user_input.items():
                if " (ID: " in key and key.endswith(")"):
                    zone_id = key.split(" (ID: ")[-1][:-1]
                    options[f"zone_name_{zone_id}"] = val
            
            return self.async_create_entry(
                title=self._user_input[CONF_USERNAME],
                data=self._user_input,
                options=options
            )

        zones_info = ""
        for zid, devices in sorted(self._zones_map.items()):
            zones_info += f"[{zid}: {', '.join(devices)}] "

        fields = {}
        for zone_id, devices in sorted(self._zones_map.items()):
            # Use therapeutic labels that bypass translation lookups
            label = f"Zone name for {', '.join(devices)} (ID: {zone_id})"
            fields[vol.Optional(label, default="")] = str

        return self.async_show_form(
            step_id="zones",
            data_schema=vol.Schema(fields),
            description_placeholders={"zones_info": zones_info}
        )

    async def _validate_credentials(self, username, password):
        """Validate credentials and return API instance."""
        api = MysaApi(username, password, self.hass)
        await api.authenticate()
        await api.get_devices() # Ensure devices are fetched
        return api 

class MysaOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Mysa."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            options = {}
            
            # Extract zone names from dynamic keys
            for key, val in user_input.items():
                if " (ID: " in key and key.endswith(")"):
                    zone_id = key.split(" (ID: ")[-1][:-1]
                    options[f"zone_name_{zone_id}"] = val
            return self.async_create_entry(title="", data=options)

        # Get the API instance to find current zones
        api = self.hass.data[DOMAIN][self._config_entry.entry_id]["api"]
        
        # Mapping: zone_id -> list of device names
        zones_map: dict[str, list[str]] = {}
        for device_id, device_data in api.devices.items():
            # Check the raw device data first as it's more stable for ID mapping
            zone_id = device_data.get("Zone")
            if not zone_id:
                # Fallback to state normalization if present
                state = api.states.get(device_id, {})
                zone_id = state.get("Zone")

            if zone_id:
                if zone_id not in zones_map:
                    zones_map[zone_id] = []
                zones_map[zone_id].append(device_data.get("Name", device_id))

        # Create description text for zones
        zones_info = ""
        for zid, devices in sorted(zones_map.items()):
            zones_info += f"[{zid}: {', '.join(devices)}] "

        # Create schema with fields for each zone
        existing_options = self._config_entry.options
        fields = {}
        
        for zone_id, devices in sorted(zones_map.items()):
            # Use descriptive labels
            label = f"Zone name for {', '.join(devices)} (ID: {zone_id})"
            current_name = existing_options.get(f"zone_name_{zone_id}", "")
            fields[vol.Optional(label, default=current_name)] = str

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(fields),
            description_placeholders={
                "zones_info": zones_info
            }
        )

