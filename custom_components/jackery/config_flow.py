"""Config flow for Jackery SolarVault integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components import mqtt

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

DEFAULT_SMARTMETER_POLL_INTERVAL = 10


class JackeryConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):  # type: ignore[call-arg]
    """Handle a config flow for Jackery."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> JackeryOptionsFlowHandler:
        """Return the options flow handler."""
        return JackeryOptionsFlowHandler(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
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
    ) -> config_entries.ConfigFlowResult:
        """Handle re-authentication when the device reports a token mismatch."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
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


class JackeryOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle Jackery options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Manage options."""
        current_data = self._config_entry.data
        current_options = self._config_entry.options

        if user_input is not None:
            data_updates: dict[str, Any] = {}
            if user_input["token"] != current_data.get("token"):
                data_updates["token"] = user_input["token"]
            if user_input["topic_prefix"] != current_data.get("topic_prefix", "hb"):
                data_updates["topic_prefix"] = user_input["topic_prefix"]
            if data_updates:
                self.hass.config_entries.async_update_entry(
                    self._config_entry, data={**current_data, **data_updates}
                )
            return self.async_create_entry(
                title="",
                data={
                    "smartmeter_http_poll": user_input["smartmeter_http_poll"],
                    "smartmeter_poll_interval": user_input["smartmeter_poll_interval"],
                },
            )

        schema = vol.Schema(
            {
                vol.Required("token", default=current_data.get("token", "")): str,
                vol.Required("topic_prefix", default=current_data.get("topic_prefix", "hb")): str,
                vol.Required(
                    "smartmeter_http_poll",
                    default=current_options.get("smartmeter_http_poll", False),
                ): bool,
                vol.Required(
                    "smartmeter_poll_interval",
                    default=current_options.get("smartmeter_poll_interval", DEFAULT_SMARTMETER_POLL_INTERVAL),
                ): vol.All(int, vol.Range(min=2, max=60)),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)

