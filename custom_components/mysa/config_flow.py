"""Config flow for Mysa integration."""
from __future__ import annotations

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

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                # Validate credentials
                await self._validate_credentials(
                    user_input[CONF_USERNAME], 
                    user_input[CONF_PASSWORD]
                )
                
                return self.async_create_entry(
                    title=user_input[CONF_USERNAME], data=user_input
                )
            except Exception as e:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "invalid_auth"

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def _validate_credentials(self, username, password):
        """Validate credentials and return API instance."""
        api = MysaApi(username, password, self.hass)
        await api.authenticate()
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
            return self.async_create_entry(title="", data=user_input)

        # Get the API instance to find current devices
        # This assumes the integration is already setup and running
        try:
            api = self.hass.data[DOMAIN][self._config_entry.entry_id]["api"]
            device_options = {
                d_id: f"{d_data.get('Name', d_id)} ({d_id})"
                for d_id, d_data in api.devices.items()
            }
        except KeyError:
            # Fallback if API not loaded (should generally process)
            device_options = {}

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(
                    "upgraded_lite_devices", 
                    default=self._config_entry.options.get("upgraded_lite_devices", [])
                ): cv.multi_select(device_options)
            }),
            description_placeholders={}
        )
