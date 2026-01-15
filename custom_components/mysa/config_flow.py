"""Config flow for Mysa integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import callback
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


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Mysa."""

    VERSION = 1
    entry: config_entries.ConfigEntry | None = None

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> MysaOptionsFlowHandler:
        """Get the options flow for this handler."""
        return MysaOptionsFlowHandler(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
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
            except Exception:  # TODO: Catch specific exceptions instead of Exception
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

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:  # TODO: Use or remove unused argument
        """Handle configuration by re-auth."""
        self.entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Dialog that informs the user that reauth is required."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                # Validate new credentials
                await self._validate_credentials(
                    user_input[CONF_USERNAME],
                    user_input[CONF_PASSWORD]
                )

                # Verify account match (email)
                if self.entry is None:
                    errors["base"] = "unknown"
                elif user_input[CONF_USERNAME].lower() != self.entry.data[CONF_USERNAME].lower():
                    errors["base"] = "reauth_account_mismatch"
                else:
                    self.hass.config_entries.async_update_entry(
                        self.entry,
                        data={
                            **self.entry.data,
                            CONF_PASSWORD: user_input[CONF_PASSWORD],
                        },
                    )
                    await self.hass.config_entries.async_reload(self.entry.entry_id)
                    return self.async_abort(reason="reauth_successful")

            except Exception:  # TODO: Catch specific exceptions instead of Exception
                errors["base"] = "invalid_auth"

        default_username = self.entry.data[CONF_USERNAME] if self.entry else ""
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME, default=default_username): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )


class MysaOptionsFlowHandler(config_entries.OptionsFlow):  # TODO: Add more public methods or refactor
    """Handle options flow for Mysa."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        # Get the API instance to find current devices
        try:
            api = self.hass.data[DOMAIN][self._config_entry.entry_id]["api"]
            devices = api.devices
        except KeyError:
            devices = {}

        device_options = {
            d_id: f"{d_data.get('Name', d_id)} ({d_id})"
            for d_id, d_data in devices.items()
        }

        # Build schema
        schema_dict = {
            vol.Optional(
                "upgraded_lite_devices",
                default=self._config_entry.options.get("upgraded_lite_devices", [])
            ): cv.multi_select(device_options),
        }

        # Add per-device wattage for heating thermostats
        for d_id, d_data in devices.items():
            if not api.is_ac_device(d_id):
                safe_id = d_id.replace(":", "").lower()
                key = f"wattage_{safe_id}"
                friendly_name = d_data.get('Name', d_id)
                schema_dict[
                    vol.Optional(
                        key,
                        default=self._config_entry.options.get(key, 0)
                    )
                ] = vol.All(vol.Coerce(int), vol.Range(min=0, max=5000))

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema_dict),
            description_placeholders={}
        )
