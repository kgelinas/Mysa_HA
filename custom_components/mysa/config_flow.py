"""Config flow for Mysa integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN
from .mysa_api import MysaApi

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Mysa."""

    VERSION = 1

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

