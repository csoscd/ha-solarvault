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

    _pending_user_input: dict[str, Any] | None = None

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> JackeryOptionsFlowHandler:
        """Return the options flow handler."""
        return JackeryOptionsFlowHandler(config_entry)

    @staticmethod
    def _confirm_sn_schema(suggested_sn: str) -> vol.Schema:
        """Schema for the confirm_sn step — only asks for the SN."""
        return vol.Schema({vol.Required("device_sn", default=suggested_sn): str})

    async def _finish_setup(
        self,
        device_sn: str,
        token: str,
        topic_prefix: str,
        errors: dict[str, str],
    ) -> config_entries.ConfigFlowResult | None:
        """Validate inputs, check MQTT, create entry. Returns None when errors were added."""
        if not device_sn:
            errors["device_sn"] = "invalid_sn"
            return None

        await self.async_set_unique_id(device_sn)
        self._abort_if_unique_id_configured()

        if not await mqtt.async_wait_for_mqtt_client(self.hass):
            errors["base"] = "mqtt_not_configured"
            return None

        _LOGGER.info(
            "Creating Jackery config entry for device_sn=%s topic_prefix=%s",
            device_sn,
            topic_prefix,
        )
        return self.async_create_entry(
            title=f"Jackery {device_sn}",
            data={"device_sn": device_sn, "token": token, "topic_prefix": topic_prefix},
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            device_sn = user_input.get("device_sn", "").strip()
            token = user_input.get("token", "").strip()
            topic_prefix = user_input.get("topic_prefix", "hb").strip()

            if device_sn != device_sn.upper():
                # SN contains lowercase letters — route through confirm step so the user
                # can review and correct the uppercase version before the entry is created.
                # Token and topic_prefix are stored and carried over; only the SN is shown.
                self._pending_user_input = {
                    "device_sn": device_sn,
                    "token": token,
                    "topic_prefix": topic_prefix,
                }
                return await self.async_step_confirm_sn()

            result = await self._finish_setup(device_sn, token, topic_prefix, errors)
            if result is not None:
                return result

        return self.async_show_form(
            step_id="user",
            data_schema=DATA_SCHEMA,
            errors=errors,
            description_placeholders={
                "topic_prefix": "Protocol root topic (default: hb)",
            },
        )

    async def async_step_confirm_sn(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Confirm (and optionally correct) a serial number that contains lowercase letters.

        Only the SN is shown; token and topic_prefix are carried over from _pending_user_input.
        async_set_unique_id runs here, on the final SN, not in async_step_user.
        """
        errors: dict[str, str] = {}
        pending = self._pending_user_input or {}
        token = pending.get("token", "")
        topic_prefix = pending.get("topic_prefix", "hb")

        if user_input is not None:
            device_sn = user_input.get("device_sn", "").strip()

            result = await self._finish_setup(device_sn, token, topic_prefix, errors)
            if result is not None:
                return result

            return self.async_show_form(
                step_id="confirm_sn",
                data_schema=self._confirm_sn_schema(device_sn),
                errors=errors,
                description_placeholders={"original_sn": pending.get("device_sn", "")},
            )

        # First display: pre-fill SN with uppercase version so the user can verify
        suggested_sn = pending.get("device_sn", "").upper()
        return self.async_show_form(
            step_id="confirm_sn",
            data_schema=self._confirm_sn_schema(suggested_sn),
            errors=errors,
            description_placeholders={"original_sn": pending.get("device_sn", "")},
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
                data_updates={"token": user_input["token"].strip()},
            )

        entry = self._get_reauth_entry()
        device_sn = entry.data.get("device_sn", "")
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=REAUTH_SCHEMA,
            errors=errors,
            description_placeholders={"device_sn": device_sn},
        )


class JackeryOptionsFlowHandler(config_entries.OptionsFlowWithReload):
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
            new_options = {
                "smartmeter_http_poll": user_input["smartmeter_http_poll"],
                "smartmeter_poll_interval": user_input["smartmeter_poll_interval"],
            }
            options_changed = any(
                new_options[key] != current_options.get(key, default)
                for key, default in (
                    ("smartmeter_http_poll", False),
                    ("smartmeter_poll_interval", DEFAULT_SMARTMETER_POLL_INTERVAL),
                )
            )
            data_updates: dict[str, Any] = {}
            if user_input["token"] != current_data.get("token"):
                data_updates["token"] = user_input["token"]
            if user_input["topic_prefix"] != current_data.get("topic_prefix", "hb"):
                data_updates["topic_prefix"] = user_input["topic_prefix"]
            if data_updates:
                self.hass.config_entries.async_update_entry(
                    self._config_entry, data={**current_data, **data_updates}
                )
                # OptionsFlowWithReload only reloads when options change; trigger reload
                # explicitly for data-only changes (token / topic_prefix).
                if not options_changed:
                    self.hass.config_entries.async_schedule_reload(
                        self._config_entry.entry_id
                    )
            return self.async_create_entry(
                title="",
                data=new_options if options_changed else dict(current_options),
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
