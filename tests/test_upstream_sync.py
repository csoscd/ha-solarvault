"""Tests for the v2.0.0 upstream sync additions (helpers, type-102/107, flat body)."""
import json

from custom_components.jackery.sensor import (
    CT_SUBTYPE_MAP,
    FUNC_ENABLE_BITS,
    JackeryDataCoordinator,
    _effective_ongrid_net,
    _extract_flat_body,
    _field_present,
    _grid_net_from_system,
    _normalize_payload_fields,
    _pick_best_power_net,
    _safe_float,
)
from tests.conftest import FakeMqttMsg

TOPIC_STATUS = "hb/device/TESTSN001/status"
TOPIC_EVENT = "hb/device/TESTSN001/event"


def send(coord, topic: str, payload: dict) -> None:
    coord._handle_message(FakeMqttMsg(topic, json.dumps(payload)))


def calc(data: dict) -> dict:
    return JackeryDataCoordinator._calculate_energy_flow(None, data)


# ---------------------------------------------------------------------------
# _field_present / _safe_float / _pick_best_power_net
# ---------------------------------------------------------------------------

class TestFieldPresent:
    def test_zero_is_present(self):
        assert _field_present({"a": 0}, "a") is True

    def test_none_is_absent(self):
        assert _field_present({"a": None}, "a") is False

    def test_missing_key_is_absent(self):
        assert _field_present({}, "a") is False


class TestSafeFloat:
    def test_none_returns_default(self):
        assert _safe_float(None) == 0.0

    def test_custom_default(self):
        assert _safe_float(None, 5.0) == 5.0

    def test_string_number(self):
        assert _safe_float("12.5") == 12.5

    def test_garbage_returns_default(self):
        assert _safe_float("abc") == 0.0


class TestPickBestPowerNet:
    def test_empty_returns_zero(self):
        assert _pick_best_power_net([]) == 0.0

    def test_largest_magnitude_wins(self):
        assert _pick_best_power_net([100.0, -250.0, 10.0]) == -250.0

    def test_zero_does_not_mask_reading(self):
        assert _pick_best_power_net([0.0, 170.0]) == 170.0

    def test_all_zero_returns_last(self):
        assert _pick_best_power_net([0.0, 0.0]) == 0.0


# ---------------------------------------------------------------------------
# _effective_ongrid_net / _grid_net_from_system
# ---------------------------------------------------------------------------

class TestEffectiveOngridNet:
    def test_uses_ongrid_fields_when_only_source(self):
        data = {"inOngridPw": 0, "outOngridPw": 300}
        assert _effective_ongrid_net(data, 0, 0, 0, 300, 0, 0) == -300.0

    def test_type106_zero_does_not_mask_type2_reading(self):
        data = {"gridInPw": 0, "gridOutPw": 0, "inOngridPw": 0, "outOngridPw": 300}
        assert _effective_ongrid_net(data, 0, 0, 0, 300, 0, 0) == -300.0

    def test_no_source_returns_zero(self):
        assert _effective_ongrid_net({}, 0, 0, 0, 0, 0, 0) == 0.0


class TestGridNetFromSystem:
    def test_no_fields_not_available(self):
        net, available = _grid_net_from_system({}, 0, 0, 0, 0, 0, 0)
        assert available is False
        assert net == 0.0

    def test_grid_in_out_available(self):
        data = {"gridInPw": 300, "gridOutPw": 0}
        net, available = _grid_net_from_system(data, 300, 0, 0, 0, 0, 0)
        assert available is True
        assert net == 300.0

    def test_ongrid_excluded_when_requested(self):
        """include_ongrid=False must not treat the grid port as a meter reading."""
        data = {"inOngridPw": 0, "outOngridPw": 500}
        net, available = _grid_net_from_system(
            data, 0, 0, 0, 500, 0, 0, include_ongrid=False
        )
        assert available is False

    def test_ongrid_included_by_default(self):
        data = {"inOngridPw": 0, "outOngridPw": 500}
        net, available = _grid_net_from_system(data, 0, 0, 0, 500, 0, 0)
        assert available is True
        assert net == -500.0


# ---------------------------------------------------------------------------
# _normalize_payload_fields
# ---------------------------------------------------------------------------

class TestNormalizePayloadFields:
    def test_grid_buy_aliased_to_grid_in(self):
        assert _normalize_payload_fields({"gridBuyPw": 300})["gridInPw"] == 300

    def test_grid_sell_aliased_to_grid_out(self):
        assert _normalize_payload_fields({"gridSellPw": 120})["gridOutPw"] == 120

    def test_work_model_aliased_to_work_mode(self):
        assert _normalize_payload_fields({"workModel": 4})["workMode"] == 4

    def test_existing_value_wins_over_alias(self):
        result = _normalize_payload_fields({"workModel": 4, "workMode": 2})
        assert result["workMode"] == 2

    def test_zero_alias_is_kept(self):
        assert _normalize_payload_fields({"gridSellPw": 0})["gridOutPw"] == 0

    def test_input_not_mutated(self):
        payload = {"gridBuyPw": 10}
        _normalize_payload_fields(payload)
        assert "gridInPw" not in payload


# ---------------------------------------------------------------------------
# _extract_flat_body
# ---------------------------------------------------------------------------

class TestExtractFlatBody:
    def test_non_status_payload_returns_empty(self):
        assert _extract_flat_body({"type": 25, "messageId": 1234}) == {}

    def test_status_fields_extracted(self):
        raw = {"type": 2, "ts": 1, "messageId": 9, "token": "x", "batSoc": 88, "pvPw": 120}
        assert _extract_flat_body(raw) == {"batSoc": 88, "pvPw": 120}

    def test_meta_keys_stripped(self):
        raw = {"type": 2, "deviceType": 3, "softver": "1.0", "soc": 50}
        assert _extract_flat_body(raw) == {"soc": 50}


def test_flat_status_message_merged_into_cache(coordinator):
    """A payload without a `body` wrapper must still populate the cache."""
    send(coordinator, TOPIC_STATUS, {"type": 2, "ts": 1, "batSoc": 77, "pvPw": 450})
    assert coordinator._data_cache["batSoc"] == 77
    assert coordinator._data_cache["pvPw"] == 450


def test_flat_message_without_status_fields_ignored(coordinator):
    send(coordinator, TOPIC_STATUS, {"type": 25, "messageId": 1234})
    assert "messageId" not in coordinator._data_cache


# ---------------------------------------------------------------------------
# Type 102 — sub-device point updates
# ---------------------------------------------------------------------------

def test_type102_patches_known_subdevice(coordinator):
    send(coordinator, TOPIC_EVENT, {
        "type": 101,
        "body": {"cts": [{"deviceSn": "SM001", "devType": 3, "subType": 5,
                          "tPhasePw": 300, "commMode": 1}]},
    })
    send(coordinator, TOPIC_EVENT, {
        "type": 102,
        "body": {"deviceSn": "SM001", "devType": 3, "tPhasePw": 900},
    })
    ct = next(c for c in coordinator._data_cache["cts"] if c["deviceSn"] == "SM001")
    assert ct["tPhasePw"] == 900
    assert ct["commMode"] == 1  # untouched field preserved


def test_type102_creates_new_ct_from_devtype(coordinator):
    send(coordinator, TOPIC_EVENT, {
        "type": 102,
        "body": {"deviceSn": "SM002", "devType": 3, "tPhasePw": 120},
    })
    assert any(c["deviceSn"] == "SM002" for c in coordinator._data_cache.get("cts", []))


def test_type102_creates_new_plug_from_devtype(coordinator):
    send(coordinator, TOPIC_EVENT, {
        "type": 102,
        "body": {"deviceSn": "PLUG9", "devType": 6, "outPw": 40},
    })
    assert any(p["deviceSn"] == "PLUG9" for p in coordinator._data_cache.get("plugs", []))
    assert not any(c["deviceSn"] == "PLUG9" for c in coordinator._data_cache.get("cts", []))


def test_type102_infers_plug_devtype_from_fields(coordinator):
    send(coordinator, TOPIC_EVENT, {
        "type": 102,
        "body": {"deviceSn": "PLUG8", "switchSta": 1, "totalEgy": 55},
    })
    plugs = coordinator._data_cache.get("plugs", [])
    assert any(p["deviceSn"] == "PLUG8" and p["devType"] == 6 for p in plugs)


def test_type102_with_arrays_uses_array_merge(coordinator):
    send(coordinator, TOPIC_EVENT, {
        "type": 102,
        "body": {"cts": [{"deviceSn": "SM003", "devType": 3, "tPhasePw": 77}]},
    })
    assert any(c["deviceSn"] == "SM003" for c in coordinator._data_cache.get("cts", []))


def test_type102_records_last_seen(coordinator):
    send(coordinator, TOPIC_EVENT, {
        "type": 102,
        "body": {"deviceSn": "SM004", "devType": 3, "tPhasePw": 5},
    })
    assert "SM004" in coordinator._subdevice_last_seen


def test_type102_ignores_main_device_sn(coordinator):
    send(coordinator, TOPIC_EVENT, {
        "type": 102,
        "body": {"deviceSn": "TESTSN001", "devType": 3, "tPhasePw": 5},
    })
    assert coordinator._data_cache.get("cts") is None


# ---------------------------------------------------------------------------
# Type 107 — incremental system updates
# ---------------------------------------------------------------------------

def test_type107_merges_soc(coordinator):
    send(coordinator, TOPIC_STATUS, {"type": 107, "body": {"soc": 64}})
    assert coordinator._data_cache["soc"] == 64


def test_type107_normalizes_workmodel(coordinator):
    send(coordinator, TOPIC_STATUS, {"type": 107, "body": {"workModel": 8}})
    assert coordinator._data_cache["workMode"] == 8


def test_type107_preserves_other_cached_fields(coordinator):
    send(coordinator, TOPIC_STATUS, {"type": 2, "body": {"batSoc": 90, "pvPw": 300}})
    send(coordinator, TOPIC_STATUS, {"type": 107, "body": {"soc": 88}})
    assert coordinator._data_cache["batSoc"] == 90
    assert coordinator._data_cache["soc"] == 88


# ---------------------------------------------------------------------------
# Alias normalization on ingest
# ---------------------------------------------------------------------------

def test_type2_grid_buy_alias_normalized(coordinator):
    send(coordinator, TOPIC_STATUS, {"type": 2, "body": {"gridBuyPw": 250, "gridSellPw": 0}})
    assert coordinator._data_cache["gridInPw"] == 250
    assert coordinator._data_cache["gridOutPw"] == 0


def test_type23_system_alias_normalized(coordinator):
    send(coordinator, TOPIC_STATUS, {
        "type": 23, "body": {"deviceSn": "system", "workModel": 7, "pvEgy": 10},
    })
    assert coordinator._data_cache["workMode"] == 7


# ---------------------------------------------------------------------------
# Battery power via energy balance (total stack incl. expansion batteries)
# ---------------------------------------------------------------------------

def test_total_battery_charge_uses_energy_balance():
    # batInPw is main-unit-only and is ignored for total battery power.
    # Energy balance: pv=1000, inOngridPw=0, outOngridPw=0 → total_batt_net=1000
    result = calc({"pvPw": 1000, "batInPw": 820, "batOutPw": 0,
                   "inOngridPw": 0, "outOngridPw": 0})
    assert result["total_battery_charge_power"] == 1000.0
    assert result["total_battery_discharge_power"] == 0.0
    assert result["calc_batt_net_power"] == 1000.0


def test_total_battery_discharge_uses_energy_balance():
    # pv=0, outOngridPw=400 → total_batt_net = 0 - 400 = -400 → discharge 400 W
    result = calc({"pvPw": 0, "batInPw": 0, "batOutPw": 430,
                   "inOngridPw": 0, "outOngridPw": 400})
    assert result["total_battery_discharge_power"] == 400.0
    assert result["total_battery_charge_power"] == 0.0
    assert result["calc_batt_net_power"] == -400.0


def test_total_battery_charge_without_bat_fields():
    # Energy balance works even without batInPw/batOutPw in the payload.
    result = calc({"pvPw": 1500, "inOngridPw": 0, "outOngridPw": 0})
    assert result["total_battery_charge_power"] == 1500.0


def test_total_battery_charge_with_eps_output():
    # EPS output reduces the energy available for battery charging.
    # pvPw=500, swEpsOutPw=100, outOngridPw=50 → total_batt_net=350
    result = calc({"pvPw": 500, "swEpsOutPw": 100, "swEpsInPw": 0,
                   "inOngridPw": 0, "outOngridPw": 50})
    assert result["total_battery_charge_power"] == 350.0


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestConstants:
    def test_func_enable_bits_are_contiguous(self):
        assert sorted(FUNC_ENABLE_BITS) == list(range(12))

    def test_func_enable_names_unique(self):
        assert len(set(FUNC_ENABLE_BITS.values())) == len(FUNC_ENABLE_BITS)

    def test_ct_subtype_map_has_jackery_3p(self):
        assert CT_SUBTYPE_MAP[7] == "Jackery Smart Meter 3P (UK 4008)"


def test_func_enable_attributes_decode_bits(coordinator):
    from unittest.mock import MagicMock

    from custom_components.jackery.sensor import SENSORS, JackerySensor

    sensor = JackerySensor.__new__(JackerySensor)
    sensor._sensor_id = "func_enable"
    sensor._coordinator = coordinator
    sensor._config = SENSORS["func_enable"]
    sensor.async_write_ha_state = MagicMock()

    coordinator._data_cache["funcEnable"] = 0b101  # bit0 + bit2
    attrs = sensor.extra_state_attributes
    assert attrs["func_enable_raw"] == 5
    assert attrs["func_enable_flags"]["aerosol"] is True
    assert attrs["func_enable_flags"]["low_power"] is True
    assert attrs["func_enable_flags"]["soc_calibration"] is False


def test_func_enable_attributes_without_value(coordinator):
    from unittest.mock import MagicMock

    from custom_components.jackery.sensor import SENSORS, JackerySensor

    sensor = JackerySensor.__new__(JackerySensor)
    sensor._sensor_id = "func_enable"
    sensor._coordinator = coordinator
    sensor._config = SENSORS["func_enable"]
    sensor.async_write_ha_state = MagicMock()

    attrs = sensor.extra_state_attributes
    assert "func_enable_flags" not in attrs
