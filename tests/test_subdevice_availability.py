"""Tests for sub-device availability and deletion-timer logic.

Covers _check_for_new_plugs phases 0–2:
- Expansion battery ∞-availability (once seen → always available, never deleted)
- Regular plug offline after OFFLINE_TIMEOUT
- Deletion timer skipped for expansion batteries
- Startup grace period
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

from custom_components.jackery.sensor import OFFLINE_TIMEOUT, JackeryDataCoordinator

PLUG_SN = "PLUG001"
EXP_SN = "EXP001"
DUMMY_SN = "DUMMY001"   # always-present device to keep all_devices non-empty


def make_coordinator() -> JackeryDataCoordinator:
    """Minimal coordinator for availability/deletion tests (no HA / MQTT required)."""
    coord = JackeryDataCoordinator.__new__(JackeryDataCoordinator)
    coord.hass = None
    coord._known_plugs = set()
    coord._expansion_battery_sns = set()
    coord._subdevice_missing_since = {}
    coord._subdevice_last_seen = {}
    coord._start_time = time.time() - 200   # well past the 60s grace period
    coord._sensors = {}
    coord._data_cache = {}
    coord.add_entities_callback = None
    coord.add_switch_entities_callback = None
    return coord


def payload_with(*sns):
    """Build a minimal type-101-style payload containing the given device SNs."""
    return {"plugs": [{"deviceSn": sn} for sn in sns]}


# ---------------------------------------------------------------------------
# Expansion battery: deletion timer must be skipped (Phase 1+2)
# ---------------------------------------------------------------------------

def test_expansion_battery_not_added_to_deletion_timer(coordinator):
    """Expansion battery SN must never enter _subdevice_missing_since (Phase 1)."""
    coord = make_coordinator()
    coord._known_plugs.add(EXP_SN)
    coord._known_plugs.add(DUMMY_SN)
    coord._expansion_battery_sns.add(EXP_SN)

    # DUMMY is present, EXP_SN is absent — expansion batteries never appear in type-101
    coord._check_for_new_plugs(payload_with(DUMMY_SN))

    assert EXP_SN not in coord._subdevice_missing_since, \
        "Expansion battery must never be added to deletion timer"


def test_expansion_battery_not_deleted_even_if_timer_set(coordinator):
    """Even if somehow _subdevice_missing_since[EXP_SN] is populated, Phase 2 clears it."""
    coord = make_coordinator()
    coord._known_plugs.add(EXP_SN)
    coord._known_plugs.add(DUMMY_SN)
    coord._expansion_battery_sns.add(EXP_SN)
    # Simulate stale timer entry (e.g. from before the v1.3.9 fix)
    coord._subdevice_missing_since[EXP_SN] = time.time() - 200

    with patch.object(coord, "_remove_subdevice_from_ha") as mock_remove:
        coord._check_for_new_plugs(payload_with(DUMMY_SN))
        mock_remove.assert_not_called()

    assert EXP_SN not in coord._subdevice_missing_since, \
        "Stale timer for expansion battery must be cleared without deleting the entity"


# ---------------------------------------------------------------------------
# Expansion battery: ∞-availability (Phase 0)
# ---------------------------------------------------------------------------

def test_expansion_battery_stays_available_after_long_gap():
    """After first data, expansion battery remains available even with 600s gap."""
    coord = make_coordinator()
    coord._known_plugs.add(EXP_SN)
    coord._known_plugs.add(DUMMY_SN)
    coord._expansion_battery_sns.add(EXP_SN)
    coord._subdevice_last_seen[EXP_SN] = time.time() - 600  # seen long ago

    fake_entity = MagicMock()
    fake_entity.available = False  # currently offline
    coord._sensors[f"jackery_battery_{EXP_SN}_foo"] = fake_entity

    coord._check_for_new_plugs(payload_with(DUMMY_SN))

    assert fake_entity._attr_available is True, \
        "Expansion battery must remain available once first data was received"
    fake_entity.async_write_ha_state.assert_called()


def test_expansion_battery_unavailable_if_never_seen():
    """Expansion battery stays unavailable if last_seen == 0 after grace period."""
    coord = make_coordinator()
    coord._known_plugs.add(EXP_SN)
    coord._known_plugs.add(DUMMY_SN)
    coord._expansion_battery_sns.add(EXP_SN)
    # last_seen = 0 (never seen), start_time is in the past (past grace period)

    fake_entity = MagicMock()
    fake_entity.available = True  # currently falsely marked online
    coord._sensors[f"jackery_battery_{EXP_SN}_foo"] = fake_entity

    coord._check_for_new_plugs(payload_with(DUMMY_SN))

    assert fake_entity._attr_available is False, \
        "Expansion battery must be unavailable if no data was ever received"


# ---------------------------------------------------------------------------
# Regular plug: deleted after OFFLINE_TIMEOUT (Phase 2)
# ---------------------------------------------------------------------------

def test_plug_deleted_after_offline_timeout():
    """Regular plug missing from type-101 for >OFFLINE_TIMEOUT s → _remove_subdevice_from_ha."""
    coord = make_coordinator()
    coord._known_plugs.add(PLUG_SN)
    coord._known_plugs.add(DUMMY_SN)
    # Not an expansion battery
    coord._subdevice_missing_since[PLUG_SN] = time.time() - OFFLINE_TIMEOUT - 10

    with patch.object(coord, "_remove_subdevice_from_ha") as mock_remove:
        # PLUG_SN absent from payload → timer threshold exceeded → delete
        coord._check_for_new_plugs(payload_with(DUMMY_SN))
        mock_remove.assert_called_once_with(PLUG_SN)


# ---------------------------------------------------------------------------
# Startup grace period (Phase 0)
# ---------------------------------------------------------------------------

def test_startup_grace_period_suppresses_offline():
    """Within first OFFLINE_TIMEOUT seconds, never-seen devices are not marked offline."""
    coord = make_coordinator()
    coord._start_time = time.time() - 30   # only 30s since start, within grace period
    coord._known_plugs.add(PLUG_SN)
    coord._known_plugs.add(DUMMY_SN)
    # last_seen = 0 (never seen)

    fake_entity = MagicMock()
    fake_entity.available = True
    coord._sensors[f"jackery_plug_{PLUG_SN}_foo"] = fake_entity

    coord._check_for_new_plugs(payload_with(DUMMY_SN))

    # Phase 0 should have skipped PLUG_SN due to grace period → availability unchanged
    fake_entity.async_write_ha_state.assert_not_called()
