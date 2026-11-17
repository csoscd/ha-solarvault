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


# ---------------------------------------------------------------------------
# Lowercase SN routes to confirm_sn step
# ---------------------------------------------------------------------------


async def test_lowercase_sn_routes_to_confirm_step(hass):
    """A SN with lowercase letters routes to the confirm_sn confirmation step."""
    result = await _start_flow(hass)

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            "device_sn": "test001",
            "token": "mytoken",
            "topic_prefix": "hb",
        },
    )

    assert result2["type"] == FlowResultType.FORM
    assert result2["step_id"] == "confirm_sn"


async def test_confirm_sn_step_accepts_uppercase_sn(hass):
    """After the confirm_sn step the entry is created with the corrected SN."""
    result = await _start_flow(hass)

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            "device_sn": "test001",
            "token": "mytoken",
            "topic_prefix": "hb",
        },
    )
    assert result2["step_id"] == "confirm_sn"

    with patch(_PATCH_MQTT, return_value=True):
        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            user_input={"device_sn": "TEST001"},
        )
        await hass.async_block_till_done()

    assert result3["type"] == FlowResultType.CREATE_ENTRY
    assert result3["data"]["device_sn"] == "TEST001"


async def test_confirm_sn_empty_sn_shows_error(hass):
    """An empty SN in the confirm_sn step shows an invalid_sn error."""
    result = await _start_flow(hass)

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            "device_sn": "test001",
            "token": "mytoken",
            "topic_prefix": "hb",
        },
    )
    assert result2["step_id"] == "confirm_sn"

    result3 = await hass.config_entries.flow.async_configure(
        result2["flow_id"],
        user_input={"device_sn": "   "},
    )

    assert result3["type"] == FlowResultType.FORM
    assert result3["errors"].get("device_sn") == "invalid_sn"


# ---------------------------------------------------------------------------
# Uppercase SN skips confirm_sn, goes directly to CREATE_ENTRY
# ---------------------------------------------------------------------------


async def test_uppercase_sn_no_confirm_step(hass):
    """An uppercase SN does not route through confirm_sn — creates entry directly."""
    result = await _start_flow(hass)

    with patch(_PATCH_MQTT, return_value=True):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input=_VALID_USER_INPUT,
        )
        await hass.async_block_till_done()

    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["data"]["device_sn"] == "TEST001"


# ---------------------------------------------------------------------------
# Token and topic_prefix whitespace is stripped
# ---------------------------------------------------------------------------


async def test_whitespace_in_token_and_prefix_is_stripped(hass):
    """Leading/trailing whitespace in token and topic_prefix is stripped on entry creation."""
    result = await _start_flow(hass)

    with patch(_PATCH_MQTT, return_value=True):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                "device_sn": "TEST001",
                "token": "  secret-token  ",
                "topic_prefix": "  hb  ",
            },
        )
        await hass.async_block_till_done()

    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["data"]["token"] == "secret-token"
    assert result2["data"]["topic_prefix"] == "hb"


# ---------------------------------------------------------------------------
# Duplicate abort via confirm_sn step
# ---------------------------------------------------------------------------


async def test_confirm_sn_duplicate_sn_aborts(hass):
    """confirm_sn step aborts when the confirmed uppercase SN is already configured."""
    # First: create an entry with TEST001
    with patch(_PATCH_MQTT, return_value=True):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data=_VALID_USER_INPUT,
        )
        await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY

    # Second: start new flow with lowercase SN that normalises to the same TEST001
    result2 = await _start_flow(hass)
    result3 = await hass.config_entries.flow.async_configure(
        result2["flow_id"],
        user_input={
            "device_sn": "test001",
            "token": "mytoken",
            "topic_prefix": "hb",
        },
    )
    assert result3["step_id"] == "confirm_sn"

    with patch(_PATCH_MQTT, return_value=True):
        result4 = await hass.config_entries.flow.async_configure(
            result3["flow_id"],
            user_input={"device_sn": "TEST001"},
        )

    assert result4["type"] == FlowResultType.ABORT
    assert result4["reason"] == "already_configured"


# ---------------------------------------------------------------------------
# Re-authentication: token is stripped; description_placeholders contains device_sn
# ---------------------------------------------------------------------------


async def test_reauth_token_is_stripped(hass):
    """Token submitted in re-auth form is stripped of whitespace before saving."""
    # Create initial entry
    with patch(_PATCH_MQTT, return_value=True):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data=_VALID_USER_INPUT,
        )
        await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY
    entry = result["result"]

    # Trigger re-auth
    result2 = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_REAUTH, "entry_id": entry.entry_id},
    )
    assert result2["type"] == FlowResultType.FORM
    assert result2["step_id"] == "reauth_confirm"

    # Submit token with surrounding whitespace
    result3 = await hass.config_entries.flow.async_configure(
        result2["flow_id"],
        user_input={"token": "  new-token  "},
    )
    await hass.async_block_till_done()

    assert result3["type"] == FlowResultType.ABORT
    assert result3["reason"] == "reauth_successful"
    assert entry.data["token"] == "new-token"


async def test_reauth_form_contains_device_sn_placeholder(hass):
    """The re-auth form exposes description_placeholders['device_sn'] for the template."""
    # Create initial entry
    with patch(_PATCH_MQTT, return_value=True):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data=_VALID_USER_INPUT,
        )
        await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY
    entry = result["result"]

    result2 = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_REAUTH, "entry_id": entry.entry_id},
    )
    assert result2["type"] == FlowResultType.FORM
    assert result2["step_id"] == "reauth_confirm"
    assert result2.get("description_placeholders", {}).get("device_sn") == "TEST001"
