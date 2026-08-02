"""Tests for _migrate_unique_ids in custom_components/jackery/__init__.py.

Historical bug risk: this function was buggy in both v2.0.0 and v2.0.2.
A wrong migration destroys HA history permanently — must be thoroughly tested.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.jackery import DOMAIN, _migrate_unique_ids

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")

_DEVICE_SN = "TESTSN001"
_PATCH_MQTT = "homeassistant.components.mqtt.async_wait_for_mqtt_client"


async def _create_entry(hass):
    """Create a real config entry and return it."""
    with patch(_PATCH_MQTT, return_value=True):
        await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={"device_sn": _DEVICE_SN, "token": "tok", "topic_prefix": "hb"},
        )
        await hass.async_block_till_done()
    return hass.config_entries.async_entries(DOMAIN)[0]


def _find_by_uid(ent_reg, entry_id, uid):
    return [
        e for e in er.async_entries_for_config_entry(ent_reg, entry_id)
        if e.unique_id == uid
    ]


# ---------------------------------------------------------------------------
# Main sensor migration
# ---------------------------------------------------------------------------

async def test_main_sensor_gets_sn_prefix(hass):
    """jackery_{sensor_id} → jackery_{sn}_{sensor_id}."""
    entry = await _create_entry(hass)
    ent_reg = er.async_get(hass)

    ent_reg.async_get_or_create("sensor", "jackery", "jackery_battery_soc", config_entry=entry)

    await _migrate_unique_ids(hass, entry)

    new_uid = f"jackery_{_DEVICE_SN}_battery_soc"
    assert _find_by_uid(ent_reg, entry.entry_id, new_uid), \
        f"Expected entity with uid={new_uid}"
    # Old uid must be gone
    assert not _find_by_uid(ent_reg, entry.entry_id, "jackery_battery_soc"), \
        "Old uid must be removed"


# ---------------------------------------------------------------------------
# Sub-device entities must be left unchanged
# ---------------------------------------------------------------------------

async def test_subdevice_uid_preserved(hass):
    """Sub-device entity (uppercase char after prefix) must not be migrated."""
    entry = await _create_entry(hass)
    ent_reg = er.async_get(hass)

    old_uid = "jackery_smartmeter_HQ123_comm_mode"
    ent_reg.async_get_or_create("sensor", "jackery", old_uid, config_entry=entry)

    await _migrate_unique_ids(hass, entry)

    assert _find_by_uid(ent_reg, entry.entry_id, old_uid), \
        "Sub-device entity must be preserved unchanged"


# ---------------------------------------------------------------------------
# v2.0.1 residue removal
# ---------------------------------------------------------------------------

async def test_main_infix_artifact_deleted(hass):
    """jackery_{sn}_main_{key} (v2.0.1 bug) must be deleted."""
    entry = await _create_entry(hass)
    ent_reg = er.async_get(hass)

    bad_uid = f"jackery_{_DEVICE_SN}_main_battery_soc"
    ent_reg.async_get_or_create("sensor", "jackery", bad_uid, config_entry=entry)

    await _migrate_unique_ids(hass, entry)

    assert not _find_by_uid(ent_reg, entry.entry_id, bad_uid), \
        "v2.0.1 artifact entity must be deleted"


# ---------------------------------------------------------------------------
# Conflict: target already exists — delete orphan
# ---------------------------------------------------------------------------

async def test_conflict_orphan_deleted(hass):
    """Old uid cannot migrate when target already exists — orphan is deleted."""
    entry = await _create_entry(hass)
    ent_reg = er.async_get(hass)

    new_uid = f"jackery_{_DEVICE_SN}_battery_soc"
    ent_reg.async_get_or_create("sensor", "jackery", new_uid, config_entry=entry)

    old_uid = "jackery_battery_soc"
    ent_reg.async_get_or_create("sensor", "jackery", old_uid, config_entry=entry)

    await _migrate_unique_ids(hass, entry)

    assert not _find_by_uid(ent_reg, entry.entry_id, old_uid), \
        "Orphan must be deleted when target already exists"
    assert _find_by_uid(ent_reg, entry.entry_id, new_uid), \
        "New-format entity must be preserved"


# ---------------------------------------------------------------------------
# Device registry migration
# ---------------------------------------------------------------------------

async def test_device_has_sn_identifier_after_setup(hass):
    """After fresh setup, device must have SN-based identifier (not entry_id-based).

    In a fresh v2.0+ install, the migration is a no-op for the device registry
    because the platform setup creates the device with the SN identifier directly.
    This test verifies the expected state and that migration does not break it.
    """
    entry = await _create_entry(hass)
    dev_reg = dr.async_get(hass)

    new_device = dev_reg.async_get_device(identifiers={(DOMAIN, _DEVICE_SN)})
    assert new_device is not None, "Device must have SN-based identifier after setup"

    old_device = dev_reg.async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    assert old_device is None, "Old entry_id-based identifier must not exist"

    # Running migration on an already-migrated setup must be a no-op (idempotent)
    await _migrate_unique_ids(hass, entry)

    assert dev_reg.async_get_device(identifiers={(DOMAIN, _DEVICE_SN)}) is not None, \
        "SN-based device must still exist after migration no-op"


# ---------------------------------------------------------------------------
# Empty SN → no-op
# ---------------------------------------------------------------------------

async def test_empty_sn_skips_migration(hass):
    """Empty device_sn must not modify the entity registry."""
    entry = await _create_entry(hass)
    ent_reg = er.async_get(hass)

    old_uid = "jackery_battery_soc"
    ent_reg.async_get_or_create("sensor", "jackery", old_uid, config_entry=entry)

    fake_entry = MagicMock()
    fake_entry.data = {"device_sn": "   "}
    fake_entry.entry_id = entry.entry_id

    await _migrate_unique_ids(hass, fake_entry)

    assert _find_by_uid(ent_reg, entry.entry_id, old_uid), \
        "Entity must not be migrated when device_sn is empty/whitespace"
