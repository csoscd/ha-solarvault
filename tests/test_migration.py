"""Tests for _migrate_unique_ids in custom_components/jackery/__init__.py.

Historical bug risk: this function was buggy in both v2.0.0 and v2.0.2.
A wrong migration destroys HA history permanently — must be thoroughly tested.
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.jackery import DOMAIN, _migrate_unique_ids

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")

_DEVICE_SN = "TESTSN001"
_PATCH_MQTT = "homeassistant.components.mqtt.async_wait_for_mqtt_client"

# SmartMeter HTO907A reports its serial in lowercase, the expansion battery in
# uppercase. The old migration only detected uppercase serials, so every SmartMeter
# entity was rewritten to the main-device unique_id format and duplicated.
_SM_SERIAL = "ac1518779cb4"


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


def _create_sub_device(hass, entry, serial=_SM_SERIAL):
    """Create a sub-device (SmartMeter) in the device registry and return it."""
    dev_reg = dr.async_get(hass)
    return dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, f"sub_{serial}")},
        name=f"Jackery SmartMeter {serial}",
    )


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


async def test_subdevice_uid_preserved_with_lowercase_serial(hass):
    """Sub-device entity with a LOWERCASE serial must not be migrated either.

    The SmartMeter HTO907A reports its serial in lowercase ("ac1518779cb4"). The old
    migration detected sub-devices by an uppercase character after the prefix, so it
    rewrote every SmartMeter unique_id to the main-device format - which made the
    integration create a duplicate entity with a "_2" suffix on every restart.
    """
    entry = await _create_entry(hass)
    ent_reg = er.async_get(hass)
    sub_device = _create_sub_device(hass, entry)

    uid = f"jackery_smartmeter_{_SM_SERIAL}_importl3"
    ent_reg.async_get_or_create(
        "sensor", "jackery", uid, config_entry=entry, device_id=sub_device.id
    )

    await _migrate_unique_ids(hass, entry)

    assert _find_by_uid(ent_reg, entry.entry_id, uid), \
        "Sub-device entity with lowercase serial must be preserved unchanged"
    assert not _find_by_uid(ent_reg, entry.entry_id, f"jackery_{_DEVICE_SN}_smartmeter_{_SM_SERIAL}_importl3"), \
        "Lowercase-serial sub-device entity must not be rewritten to the main-device format"


async def test_broken_subdevice_uid_repaired(hass):
    """A unique_id rewritten by the old buggy migration must be repaired."""
    entry = await _create_entry(hass)
    ent_reg = er.async_get(hass)
    sub_device = _create_sub_device(hass, entry)

    broken_uid = f"jackery_{_DEVICE_SN}_smartmeter_{_SM_SERIAL}_importl3"
    ent_reg.async_get_or_create(
        "sensor", "jackery", broken_uid, config_entry=entry, device_id=sub_device.id
    )

    await _migrate_unique_ids(hass, entry)

    assert _find_by_uid(ent_reg, entry.entry_id, f"jackery_smartmeter_{_SM_SERIAL}_importl3"), \
        "Broken unique_id must be repaired to the canonical sub-device format"
    assert not _find_by_uid(ent_reg, entry.entry_id, broken_uid), \
        "Broken unique_id must be gone after the repair"


async def test_duplicate_subdevice_entity_removed(hass):
    """The plain (older) entity keeps the canonical unique_id, the "_2" duplicate is removed."""
    entry = await _create_entry(hass)
    ent_reg = er.async_get(hass)
    sub_device = _create_sub_device(hass, entry)

    broken_uid = f"jackery_{_DEVICE_SN}_smartmeter_{_SM_SERIAL}_importl3"
    original = ent_reg.async_get_or_create(
        "sensor",
        "jackery",
        broken_uid,
        config_entry=entry,
        device_id=sub_device.id,
        suggested_object_id=f"jackery_smartmeter_{_SM_SERIAL}_l3_bezugsleistung",
    )
    await asyncio.sleep(0.02)
    duplicate = ent_reg.async_get_or_create(
        "sensor",
        "jackery",
        f"jackery_smartmeter_{_SM_SERIAL}_importl3",
        config_entry=entry,
        device_id=sub_device.id,
        suggested_object_id=f"jackery_smartmeter_{_SM_SERIAL}_l3_bezugsleistung",
    )
    assert duplicate.entity_id.endswith("_2"), \
        "The second entity with the same name must get the '_2' suffix"

    await _migrate_unique_ids(hass, entry)

    assert not _find_by_uid(ent_reg, entry.entry_id, broken_uid), \
        "Broken unique_id must be gone"
    holders = _find_by_uid(ent_reg, entry.entry_id, f"jackery_smartmeter_{_SM_SERIAL}_importl3")
    assert len(holders) == 1, \
        "Exactly one entity must hold the canonical unique_id"
    assert holders[0].entity_id == original.entity_id, \
        "The original entity must keep the canonical unique_id and its plain entity_id"


async def test_broken_duplicate_removed_when_holder_is_older(hass):
    """If the canonical unique_id is held by the older entity, the broken one is removed."""
    entry = await _create_entry(hass)
    ent_reg = er.async_get(hass)
    sub_device = _create_sub_device(hass, entry)

    canonical_uid = f"jackery_smartmeter_{_SM_SERIAL}_importl3"
    holder = ent_reg.async_get_or_create(
        "sensor", "jackery", canonical_uid, config_entry=entry, device_id=sub_device.id
    )
    await asyncio.sleep(0.02)
    broken_uid = f"jackery_{_DEVICE_SN}_smartmeter_{_SM_SERIAL}_importl3"
    ent_reg.async_get_or_create(
        "sensor", "jackery", broken_uid, config_entry=entry, device_id=sub_device.id
    )

    await _migrate_unique_ids(hass, entry)

    holders = _find_by_uid(ent_reg, entry.entry_id, canonical_uid)
    assert len(holders) == 1, \
        "Exactly one entity must hold the canonical unique_id"
    assert holders[0].entity_id == holder.entity_id, \
        "The older entity must keep the canonical unique_id"
    assert not _find_by_uid(ent_reg, entry.entry_id, broken_uid), \
        "The broken duplicate must be removed"


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
