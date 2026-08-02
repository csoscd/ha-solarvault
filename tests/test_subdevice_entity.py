"""Tests for JackerySubDeviceSensor._update_from_coordinator.

Covers the ENUM/options_offset path, null-guard, string-fallback,
and int-fix — all critical for commMode/commState correctness (v1.3.5 fix).
Uses the __new__ bypass pattern: no HA fixture needed.
"""
from __future__ import annotations

from custom_components.jackery.sensor import JackerySubDeviceSensor

SN = "SM001"


def make_ct_sensor(sensor_config: dict) -> JackerySubDeviceSensor:
    """Build a minimal SmartMeter 3P sensor (data_key=cts, dev_type=3 → is_direct_access)."""
    s = JackerySubDeviceSensor.__new__(JackerySubDeviceSensor)
    s._plug_sn = SN
    s._dev_type = 3      # SmartMeter 3P → is_direct_access = True
    s._data_key = "cts"
    s._use_expansion = False
    s._sensor_config = sensor_config
    s._attr_native_value = None
    s._attr_available = False
    s.async_write_ha_state = lambda: None
    return s


def ct_data(payload: dict) -> dict:
    return {"cts": [{"deviceSn": SN, **payload}]}


# ---------------------------------------------------------------------------
# commMode ENUM — options_offset=1 (1-based MQTT values)
# ---------------------------------------------------------------------------

def test_commmode_1_maps_to_lan():
    """commMode=1 → 'lan' (options_offset corrects 1-based → 0-based index)."""
    s = make_ct_sensor({
        "key": "commMode",
        "options": ["lan", "cloud"],
        "options_offset": 1,
    })
    s._update_from_coordinator(ct_data({"commMode": 1}))
    assert s._attr_native_value == "lan"


def test_commmode_2_maps_to_cloud():
    """commMode=2 → 'cloud'."""
    s = make_ct_sensor({
        "key": "commMode",
        "options": ["lan", "cloud"],
        "options_offset": 1,
    })
    s._update_from_coordinator(ct_data({"commMode": 2}))
    assert s._attr_native_value == "cloud"


def test_commmode_invalid_value_uses_str_fallback():
    """Out-of-range value → str representation, no crash."""
    s = make_ct_sensor({
        "key": "commMode",
        "options": ["lan", "cloud"],
        "options_offset": 1,
    })
    s._update_from_coordinator(ct_data({"commMode": 99}))
    assert s._attr_native_value == "99"


# ---------------------------------------------------------------------------
# commState ENUM — no offset (0-based MQTT values)
# ---------------------------------------------------------------------------

def test_commstate_0_maps_to_offline():
    """commState=0 → 'offline' (no offset)."""
    s = make_ct_sensor({
        "key": "commState",
        "options": ["offline", "online"],
    })
    s._update_from_coordinator(ct_data({"commState": 0}))
    assert s._attr_native_value == "offline"


def test_commstate_1_maps_to_online():
    """commState=1 → 'online'."""
    s = make_ct_sensor({
        "key": "commState",
        "options": ["offline", "online"],
    })
    s._update_from_coordinator(ct_data({"commState": 1}))
    assert s._attr_native_value == "online"


# ---------------------------------------------------------------------------
# Null guard — existing value must be preserved
# ---------------------------------------------------------------------------

def test_null_guard_preserves_existing_value():
    """val=None in update must not overwrite a previously set value."""
    s = make_ct_sensor({
        "key": "commMode",
        "options": ["lan", "cloud"],
        "options_offset": 1,
    })
    s._attr_native_value = "lan"

    s._update_from_coordinator(ct_data({"commMode": None}))

    assert s._attr_native_value == "lan", "Null value must not overwrite cached state"


def test_key_absent_does_not_change_value():
    """If the key is entirely missing from the payload, existing value is kept."""
    s = make_ct_sensor({
        "key": "commMode",
        "options": ["lan", "cloud"],
        "options_offset": 1,
    })
    s._attr_native_value = "cloud"

    s._update_from_coordinator(ct_data({"tPhasePw": 300}))  # commMode absent

    assert s._attr_native_value == "cloud"


# ---------------------------------------------------------------------------
# String field (e.g. wip IP address)
# ---------------------------------------------------------------------------

def test_string_ip_field_stored_as_string():
    """String fields (no 'options' in config) must be stored via the numeric
    path's TypeError fallback and end up as-is in _attr_native_value."""
    s = make_ct_sensor({"key": "wip"})
    s._update_from_coordinator(ct_data({"wip": "192.168.1.100"}))
    assert s._attr_native_value == "192.168.1.100"


# ---------------------------------------------------------------------------
# Integer fix: unitless, scale=1 numeric sensor
# ---------------------------------------------------------------------------

def test_unitless_integer_no_float_suffix():
    """Unitless numeric field with scale=1 must be stored as int, not float."""
    s = make_ct_sensor({"key": "commState", "scale": 1})
    # no 'options' → goes through numeric path
    s._update_from_coordinator(ct_data({"commState": 3}))
    assert s._attr_native_value == 3
    assert isinstance(s._attr_native_value, int), "Should be int, not 3.0"
