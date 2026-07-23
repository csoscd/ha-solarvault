"""Integration tests for the Jackery config flow (uses real HA test framework)."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.jackery import DOMAIN

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_USER_INPUT = {
    "device_sn": "TEST001",
    "token": "secret-token",
    "topic_prefix": "hb",
}

_PATCH_MQTT = "homeassistant.components.mqtt.async_wait_for_mqtt_client"


async def _start_flow(hass):
    """Open the config flow and return the FORM result."""
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )


# ---------------------------------------------------------------------------
# Initial form
# ---------------------------------------------------------------------------


async def test_shows_user_form(hass):
    """Config flow shows the user input form on first call."""
    result = await _start_flow(hass)

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert "flow_id" in result


# ---------------------------------------------------------------------------
# Successful entry creation
# ---------------------------------------------------------------------------


async def test_creates_entry_with_valid_input(hass):
    """Valid user input creates a config entry with the submitted data."""
    result = await _start_flow(hass)

    with patch(_PATCH_MQTT, return_value=True):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input=_VALID_USER_INPUT,
        )
        await hass.async_block_till_done()

    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["title"] == "Jackery TEST001"
    assert result2["data"]["device_sn"] == "TEST001"
    assert result2["data"]["token"] == "secret-token"
    assert result2["data"]["topic_prefix"] == "hb"


# ---------------------------------------------------------------------------
# Duplicate device_sn is rejected
# ---------------------------------------------------------------------------


async def test_duplicate_sn_aborts_flow(hass):
    """A second setup attempt with the same SN is aborted."""
    with patch(_PATCH_MQTT, return_value=True):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data=_VALID_USER_INPUT,
        )
        await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY

    # Second flow with same SN
    result2 = await _start_flow(hass)
    with patch(_PATCH_MQTT, return_value=True):
        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            user_input=_VALID_USER_INPUT,
        )

    assert result3["type"] == FlowResultType.ABORT
    assert result3["reason"] == "already_configured"


# ---------------------------------------------------------------------------
# MQTT not available → shows form with error
# ---------------------------------------------------------------------------


async def test_mqtt_not_available_shows_error(hass):
    """When MQTT is not configured, the form is re-shown with an error."""
    result = await _start_flow(hass)

    with patch(_PATCH_MQTT, return_value=False):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input=_VALID_USER_INPUT,
        )

    assert result2["type"] == FlowResultType.FORM
    assert result2["errors"]["base"] == "mqtt_not_configured"
