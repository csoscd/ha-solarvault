"""Tests for async_setup_entry: fork_version storage and fallback."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from custom_components.jackery import DOMAIN, async_setup_entry

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")

_PATCH_MQTT = "homeassistant.components.mqtt.async_wait_for_mqtt_client"
_PATCH_MIGRATE = "custom_components.jackery._migrate_unique_ids"
_PATCH_FORWARD = "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups"
_PATCH_INTEGRATION = "custom_components.jackery.async_get_loaded_integration"
_PATCH_NOT_LOADED = "custom_components.jackery.IntegrationNotLoaded"


def _make_entry(hass, device_sn: str = "TESTSN001") -> MagicMock:
    entry = MagicMock()
    entry.entry_id = "test-entry-id"
    entry.data = {"device_sn": device_sn, "token": "tok", "topic_prefix": "hb"}
    entry.options = {}
    return entry


@pytest.mark.asyncio
async def test_fork_version_stored_in_hass_data(hass):
    """async_setup_entry reads the manifest version and stores it in hass.data."""
    entry = _make_entry(hass)

    mock_integration = MagicMock()
    mock_integration.manifest = {"version": "2.5.6"}

    with (
        patch(_PATCH_MQTT, return_value=True),
        patch(_PATCH_MIGRATE),
        patch(_PATCH_FORWARD, return_value=True),
        patch(_PATCH_INTEGRATION, return_value=mock_integration),
    ):
        result = await async_setup_entry(hass, entry)

    assert result is True
    stored = hass.data[DOMAIN][entry.entry_id]
    assert stored["fork_version"] == "2.5.6"


@pytest.mark.asyncio
async def test_fork_version_fallback_on_integration_not_loaded(hass):
    """When IntegrationNotLoaded is raised, fork_version falls back to 'unknown'."""
    entry = _make_entry(hass)

    from homeassistant.loader import IntegrationNotLoaded

    with (
        patch(_PATCH_MQTT, return_value=True),
        patch(_PATCH_MIGRATE),
        patch(_PATCH_FORWARD, return_value=True),
        patch(_PATCH_INTEGRATION, side_effect=IntegrationNotLoaded(DOMAIN)),
    ):
        result = await async_setup_entry(hass, entry)

    assert result is True
    stored = hass.data[DOMAIN][entry.entry_id]
    assert stored["fork_version"] == "unknown"
