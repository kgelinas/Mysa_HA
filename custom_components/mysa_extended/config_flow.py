"""Config flow for Mysa Extended integration."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import callback

from .const import DOMAIN


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Mysa Extended."""

    VERSION = 1

    def is_matching(self, _other_flow: Any) -> bool:
        """Return True if other_flow is matching."""
        return False

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> MysaExtendedOptionsFlowHandler:
        """Get the options flow for this handler."""
        return MysaExtendedOptionsFlowHandler(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")

        if user_input is not None:
            return self.async_create_entry(title="Mysa Extended", data={})

        return self.async_show_form(step_id="user")


class MysaExtendedOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Mysa Extended."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_rate = self._config_entry.options.get("custom_erate")

        schema = vol.Schema(
            {
                vol.Optional(
                    "custom_erate",
                    description={"suggested_value": current_rate},
                ): vol.All(vol.Coerce(float), vol.Range(min=0.0, max=100.0)),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            description_placeholders={
                "note": "Leave empty to use the rate from your Mysa cloud account."
            },
        )
