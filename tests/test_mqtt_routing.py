"""Tests for JackeryDataCoordinator._handle_message MQTT routing and cache logic."""
import json

import pytest

from tests.conftest import FakeMqttMsg


TOPIC_STATUS = "hb/device/TESTSN001/status"
TOPIC_EVENT = "hb/device/TESTSN001/event"


def send(coord, topic: str, payload: dict) -> None:
    """Helper: inject a JSON MQTT message into the coordinator."""
    coord._handle_message(FakeMqttMsg(topic, json.dumps(payload)))


# ---------------------------------------------------------------------------
# Type 2 — main device status (flat merge)
# ---------------------------------------------------------------------------

def test_type2_merges_body_into_cache(coordinator):
    send(coordinator, TOPIC_STATUS, {
        "type": 2,
        "body": {"batSoc": 85, "pvPw": 1200, "cmd": 106},
    })
    assert coordinator._data_cache["batSoc"] == 85
    assert coordinator._data_cache["pvPw"] == 1200


def test_type2_accumulates_multiple_messages(coordinator):
    send(coordinator, TOPIC_STATUS, {"type": 2, "body": {"batSoc": 80}})
    send(coordinator, TOPIC_STATUS, {"type": 2, "body": {"pvPw": 500}})
    assert coordinator._data_cache["batSoc"] == 80
    assert coordinator._data_cache["pvPw"] == 500


# ---------------------------------------------------------------------------
# Type 23 — energy statistics
# ---------------------------------------------------------------------------

def test_type23_system_merges_into_main_cache(coordinator):
    send(coordinator, TOPIC_STATUS, {
        "type": 23,
        "body": {"deviceSn": "system", "pvEgy": 12345, "batChgEgy": 6789},
    })
    assert coordinator._data_cache["pvEgy"] == 12345
    assert coordinator._data_cache["batChgEgy"] == 6789


def test_type23_system_none_sn_also_merges(coordinator):
    send(coordinator, TOPIC_STATUS, {
        "type": 23,
        "body": {"pvEgy": 999},  # no deviceSn key
    })
    assert coordinator._data_cache["pvEgy"] == 999


def test_type23_expansion_battery_stored_separately(coordinator):
    bp_sn = "HQ2C10000444HP3"
    send(coordinator, TOPIC_STATUS, {
        "type": 23,
        "body": {"deviceSn": bp_sn, "devType": 1, "subType": 0, "inEgy": 196, "outEgy": 5},
    })
    exp = coordinator._data_cache.get("expansion_batteries", {})
    assert bp_sn in exp
    assert exp[bp_sn]["inEgy"] == 196
    assert exp[bp_sn]["outEgy"] == 5


# ---------------------------------------------------------------------------
# Type 101 — sub-device data (CT vs plug selective cache update)
# ---------------------------------------------------------------------------

def test_type101_ct_payload_sets_cts_cache(coordinator):
    send(coordinator, TOPIC_EVENT, {
        "type": 101,
        "body": {"cts": [{"deviceSn": "CT001", "tPhasePw": 300, "devType": 3, "subType": 5}]},
    })
    assert "cts" in coordinator._data_cache
    assert coordinator._data_cache["cts"][0]["tPhasePw"] == 300


def test_type101_plug_payload_sets_plugs_cache(coordinator):
    send(coordinator, TOPIC_EVENT, {
        "type": 101,
        "body": {"plugs": [{"deviceSn": "PLUG001", "sysSwitch": 1}]},
    })
    assert "plugs" in coordinator._data_cache
    assert coordinator._data_cache["plugs"][0]["deviceSn"] == "PLUG001"


def test_ct_cache_not_wiped_by_plug_response(coordinator):
    """Regression test for issue #16: plug poll must not overwrite CT cache."""
    # 1. CT data arrives
    send(coordinator, TOPIC_EVENT, {
        "type": 101,
        "body": {"cts": [{"deviceSn": "CT001", "tPhasePw": 300, "devType": 3, "subType": 5}]},
    })
    assert coordinator._data_cache["cts"][0]["tPhasePw"] == 300

    # 2. Plug poll response (no cts key in body)
    send(coordinator, TOPIC_EVENT, {
        "type": 101,
        "body": {"plugs": [{"deviceSn": "PLUG001", "sysSwitch": 1}]},
    })

    # CT data must still be present
    assert "cts" in coordinator._data_cache
    assert coordinator._data_cache["cts"][0]["tPhasePw"] == 300


def test_plug_cache_not_wiped_by_ct_response(coordinator):
    """Symmetric check: CT response must not overwrite plug cache."""
    send(coordinator, TOPIC_EVENT, {
        "type": 101,
        "body": {"plugs": [{"deviceSn": "PLUG001", "sysSwitch": 1}]},
    })
    assert coordinator._data_cache["plugs"][0]["deviceSn"] == "PLUG001"

    send(coordinator, TOPIC_EVENT, {
        "type": 101,
        "body": {"cts": [{"deviceSn": "CT001", "tPhasePw": 500, "devType": 3, "subType": 5}]},
    })

    assert coordinator._data_cache["plugs"][0]["deviceSn"] == "PLUG001"


def test_type101_smartmeter_devtype3_goes_to_cts(coordinator):
    """SmartMeter 3P (devType=3, subType=5) must be classified as CT, not plug."""
    send(coordinator, TOPIC_EVENT, {
        "type": 101,
        "body": {
            "cts": [{
                "deviceSn": "SM001", "devType": 3, "subType": 5,
                "tPhasePw": 400, "tnPhasePw": 0,
            }]
        },
    })
    cts = coordinator._data_cache.get("cts", [])
    plugs = coordinator._data_cache.get("plugs", [])
    assert any(d.get("deviceSn") == "SM001" for d in cts), "SmartMeter must be in cts"
    assert not any(d.get("deviceSn") == "SM001" for d in plugs), "SmartMeter must not be in plugs"


def test_type101_standard_ct_devtype2_goes_to_cts(coordinator):
    """Standard CT (devType=2) must also be classified as CT."""
    send(coordinator, TOPIC_EVENT, {
        "type": 101,
        "body": {"cts": [{"deviceSn": "CT002", "devType": 2}]},
    })
    cts = coordinator._data_cache.get("cts", [])
    assert any(d.get("deviceSn") == "CT002" for d in cts)


def test_type101_plug_devtype6_goes_to_plugs(coordinator):
    send(coordinator, TOPIC_EVENT, {
        "type": 101,
        "body": {"plugs": [{"deviceSn": "PLUG002", "devType": 6}]},
    })
    plugs = coordinator._data_cache.get("plugs", [])
    cts = coordinator._data_cache.get("cts", [])
    assert any(d.get("deviceSn") == "PLUG002" for d in plugs)
    # should not also be in cts
    assert not any(d.get("deviceSn") == "PLUG002" for d in cts)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_invalid_json_does_not_crash(coordinator):
    coordinator._handle_message(FakeMqttMsg(TOPIC_STATUS, b"not-json"))
    # Should not raise, cache stays empty
    assert coordinator._data_cache == {}


def test_unknown_message_type_falls_back_to_flat_merge(coordinator):
    send(coordinator, TOPIC_STATUS, {
        "type": 99,
        "body": {"someKey": "someValue"},
    })
    assert coordinator._data_cache.get("someKey") == "someValue"


def test_type101_body_none_returns_early(coordinator):
    """Type 101 with null body must not crash or modify cache."""
    send(coordinator, TOPIC_STATUS, {"type": 101, "body": None})
    assert coordinator._data_cache == {}
