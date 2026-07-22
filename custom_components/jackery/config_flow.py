"""Config flow for Jackery SolarVault integration."""
import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components import mqtt
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from . import DOMAIN

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required("device_sn"): str,
        vol.Required("token"): str,
        vol.Optional("topic_prefix", default="hb"): str,
    }
)

REAUTH_SCHEMA = vol.Schema({vol.Required("token"): str})


class JackeryConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Jackery."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            device_sn = user_input.get("device_sn", "").strip()

            # Multi-instance: abort if this SN is already configured
            await self.async_set_unique_id(device_sn)
            self._abort_if_unique_id_configured()

            if not await mqtt.async_wait_for_mqtt_client(self.hass):
                errors["base"] = "mqtt_not_configured"
            else:
                _LOGGER.info(
                    "Creating Jackery config entry for device_sn=%s topic_prefix=%s",
                    device_sn,
                    user_input.get("topic_prefix", "hb"),
                )
                return self.async_create_entry(
                    title=f"Jackery {device_sn}",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=DATA_SCHEMA,
            errors=errors,
            description_placeholders={
                "topic_prefix": "Protocol root topic (default: hb)",
            },
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> FlowResult:
        """Handle re-authentication when the device reports a token mismatch."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Let the user enter a new token."""
        errors: dict[str, str] = {}

        if user_input is not None:
            return self.async_update_reload_and_abort(
                self._get_reauth_entry(),
                data_updates={"token": user_input["token"]},
            )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=REAUTH_SCHEMA,
            errors=errors,
        )

    async def async_step_import(self, import_config: dict[str, Any]) -> FlowResult:
        """Import a config entry from configuration.yaml."""
        return await self.async_step_user(import_config)
