"""Config flow for the Loxone integration."""

from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResult

from .const import CONF_USE_TLS, CONF_VERIFY_SSL, DEFAULT_TITLE, DOMAIN


class LoxoneConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Loxone."""

    VERSION = 1

    async def async_step_user(self, user_input=None) -> FlowResult:
        errors = {}
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_HOST])
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=DEFAULT_TITLE, data=user_input)

        data_schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Optional(CONF_PORT, default=443): int,
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Optional(CONF_USE_TLS, default=True): bool,
                vol.Optional(CONF_VERIFY_SSL, default=True): bool,
            }
        )
        return self.async_show_form(step_id="user", data_schema=data_schema, errors=errors)

    async def async_step_import(self, user_input) -> FlowResult:
        return await self.async_step_user(user_input)
