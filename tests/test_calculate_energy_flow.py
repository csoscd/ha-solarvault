"""Unit tests for JackeryDataCoordinator._calculate_energy_flow.

The method is pure (aside from logging) and has no HA dependency,
so all tests run without a hass fixture.
"""
from custom_components.jackery.sensor import JackeryDataCoordinator


def calc(data: dict) -> dict:
    """Helper: call _calculate_energy_flow as an unbound function."""
    return JackeryDataCoordinator._calculate_energy_flow(None, data)


# ---------------------------------------------------------------------------
# Battery charge / discharge split
# ---------------------------------------------------------------------------

def test_battery_charging_when_pv_exceeds_load():
    data = {
        "pvPw": 3000,
        "swEpsInPw": 0, "swEpsOutPw": 0,
        "inOngridPw": 0, "outOngridPw": 0,
    }
    result = calc(data)
    assert result["calc_batt_net_power"] == 3000.0
    assert result["total_battery_charge_power"] == 3000.0
    assert result["total_battery_discharge_power"] == 0.0


def test_battery_charging_when_grid_feeds_unit():
    data = {
        "pvPw": 0,
        "swEpsInPw": 0, "swEpsOutPw": 0,
        "inOngridPw": 500, "outOngridPw": 0,
    }
    result = calc(data)
    # inOngridPw=500 → grid charges the battery; total_batt_net = 0 + 500 - 0 = 500
    assert result["total_battery_charge_power"] == 500.0
    assert result["total_battery_discharge_power"] == 0.0


def test_battery_discharging_when_unit_feeds_grid():
    data = {
        "pvPw": 0,
        "swEpsInPw": 0, "swEpsOutPw": 0,
        "inOngridPw": 0, "outOngridPw": 2000,
    }
    result = calc(data)
    # p_ong = 0 - 2000 = -2000 → p_batt = -2000 → discharge
    assert result["total_battery_discharge_power"] == 2000.0
    assert result["total_battery_charge_power"] == 0.0


# ---------------------------------------------------------------------------
# CT available — basic grid net power
# ---------------------------------------------------------------------------

def test_grid_net_power_with_ct_import():
    data = {
        "pvPw": 0,
        "swEpsInPw": 0, "swEpsOutPw": 0,
        "inOngridPw": 0, "outOngridPw": 0,
        "cts": [{"tPhasePw": 800, "tnPhasePw": 0}],
    }
    result = calc(data)
    assert result["grid_available"] is True
    assert result["calc_grid_net_power"] == 800.0  # buy 800, sell 0


def test_grid_net_power_with_ct_export():
    data = {
        "pvPw": 5000,
        "swEpsInPw": 0, "swEpsOutPw": 0,
        "inOngridPw": 0, "outOngridPw": 3000,
        "cts": [{"tPhasePw": 0, "tnPhasePw": 500}],
    }
    result = calc(data)
    assert result["grid_available"] is True
    assert result["calc_grid_net_power"] == -500.0  # exporting


# ---------------------------------------------------------------------------
# CT available — home power calculation branches
# ---------------------------------------------------------------------------

def test_home_power_ct_available_normal():
    """Normal case: CT import, no ongrid anomaly."""
    data = {
        "pvPw": 2000,
        "swEpsInPw": 0, "swEpsOutPw": 0,
        "inOngridPw": 0, "outOngridPw": 0,
        "cts": [{"tPhasePw": 500, "tnPhasePw": 0}],
    }
    result = calc(data)
    # p_grid = 500, p_ong = 0 → p_home = 500 - 0 = 500
    assert result["calc_home_power"] == 500.0


def test_home_power_ct_feed_in_with_ongrid_supply():
    """CT export, system feeds grid: outOngridPw is total AC output (not net-to-grid).
    House load = outOngridPw - tnPhasePw when no grid import."""
    data = {
        "pvPw": 5000,
        "swEpsInPw": 0, "swEpsOutPw": 0,
        "inOngridPw": 0, "outOngridPw": 3000,
        "cts": [{"tPhasePw": 0, "tnPhasePw": 2000}],
    }
    result = calc(data)
    # p_grid = 0 - 2000 = -2000; p_ong = 0 - 3000 = -3000
    # p_home = -2000 - (-3000) = 1000 W house load
    assert result["calc_home_power"] == 1000.0


def test_home_power_phase_balanced_feed_in():
    """Regression: phase-balanced CT causes jackery_home_power to go negative.

    Scenario: Jackery discharges 274 W + 27 W solar = 301 W total AC output.
    L1 draws 250 W from grid, L3 exports 279 W from Jackery.
    Combined-phase metering: tPhasePw=0, tnPhasePw=29 (net to public grid).
    Correct home load = 301 - 29 = 272 W (positive).
    Old Branch A produced 29 - 301 = -272 W (wrong sign).
    """
    data = {
        "pvPw": 27,
        "swEpsInPw": 0, "swEpsOutPw": 0,
        "inOngridPw": 0, "outOngridPw": 301,
        "cts": [{"tPhasePw": 0, "tnPhasePw": 29}],
    }
    result = calc(data)
    # p_grid = 0 - 29 = -29; p_ong = 0 - 301 = -301
    # p_home = -29 - (-301) = 272 W
    assert result["calc_home_power"] == 272.0


def test_home_power_anomaly_branch_small_difference():
    """Anomaly branch 1: grid_buy < ongrid_charge by ≤50 W → p_home = 0."""
    data = {
        "pvPw": 0,
        "swEpsInPw": 0, "swEpsOutPw": 0,
        "inOngridPw": 500, "outOngridPw": 0,
        "cts": [{"tPhasePw": 460, "tnPhasePw": 0}],
    }
    result = calc(data)
    # grid_buy=460 < ongrid_charge=500, diff=40 ≤50 → anomaly branch 1
    assert result["calc_home_power"] == 0.0


def test_home_power_anomaly_branch_large_difference():
    """Anomaly branch 2: grid_buy < ongrid_charge by >50 W → p_home = ongrid_charge - grid_buy."""
    data = {
        "pvPw": 0,
        "swEpsInPw": 0, "swEpsOutPw": 0,
        "inOngridPw": 500, "outOngridPw": 0,
        "cts": [{"tPhasePw": 400, "tnPhasePw": 0}],
    }
    result = calc(data)
    # diff = 100 > 50 → branch 2: p_home = 500 - 400 = 100
    assert result["calc_home_power"] == 100.0


# ---------------------------------------------------------------------------
# CT not available
# ---------------------------------------------------------------------------

def test_no_ct_grid_not_available():
    data = {
        "pvPw": 1000,
        "swEpsInPw": 0, "swEpsOutPw": 0,
        "inOngridPw": 0, "outOngridPw": 500,
    }
    result = calc(data)
    assert result["grid_available"] is False
    assert result["calc_grid_net_power"] is None


def test_no_ct_home_power_uses_ongrid_supply():
    data = {
        "pvPw": 0,
        "swEpsInPw": 0, "swEpsOutPw": 0,
        "inOngridPw": 0, "outOngridPw": 1200,
    }
    result = calc(data)
    assert result["calc_home_power"] == 1200.0


def test_no_ct_home_power_zero_when_no_supply():
    data = {
        "pvPw": 3000,
        "swEpsInPw": 0, "swEpsOutPw": 0,
        "inOngridPw": 0, "outOngridPw": 0,
    }
    result = calc(data)
    assert result["calc_home_power"] == 0.0


# ---------------------------------------------------------------------------
# Phase A/B/C fallback when tPhasePw missing
# ---------------------------------------------------------------------------

def test_ct_abc_phase_fallback_for_import():
    data = {
        "pvPw": 0,
        "swEpsInPw": 0, "swEpsOutPw": 0,
        "inOngridPw": 0, "outOngridPw": 0,
        "cts": [{"aPhasePw": 100, "bPhasePw": 200, "cPhasePw": 150, "tnPhasePw": 0}],
    }
    result = calc(data)
    assert result["grid_available"] is True
    assert result["calc_grid_net_power"] == 450.0  # 100+200+150


def test_ct_abc_phase_fallback_for_export():
    data = {
        "pvPw": 0,
        "swEpsInPw": 0, "swEpsOutPw": 0,
        "inOngridPw": 0, "outOngridPw": 0,
        "cts": [{"tPhasePw": 0, "anPhasePw": 50, "bnPhasePw": 80, "cnPhasePw": 70}],
    }
    result = calc(data)
    assert result["grid_available"] is True
    assert result["calc_grid_net_power"] == -(50 + 80 + 70)


# ---------------------------------------------------------------------------
# PV dict format (pv1–pv4 come as dicts in some firmware)
# ---------------------------------------------------------------------------

def test_pv_as_dict():
    data = {
        "pvPw": {"pvPw": 2500, "commState": 1},
        "swEpsInPw": 0, "swEpsOutPw": 0,
        "inOngridPw": 0, "outOngridPw": 0,
    }
    result = calc(data)
    assert result["calc_batt_net_power"] == 2500.0


# ---------------------------------------------------------------------------
# Fallback to gridBuyPw / gridSellPw when no CT
# ---------------------------------------------------------------------------

def test_fallback_to_grid_buy_sell_fields():
    data = {
        "pvPw": 0,
        "swEpsInPw": 0, "swEpsOutPw": 0,
        "inOngridPw": 0, "outOngridPw": 0,
        "gridBuyPw": 300, "gridSellPw": 0,
    }
    result = calc(data)
    assert result["grid_available"] is True
    assert result["calc_grid_net_power"] == 300.0


# ---------------------------------------------------------------------------
# Missing/zero fields should not crash
# ---------------------------------------------------------------------------

def test_empty_data_does_not_crash():
    result = calc({})
    assert "calc_batt_net_power" in result
    assert "calc_home_power" in result
    assert result["total_battery_charge_power"] == 0.0
    assert result["total_battery_discharge_power"] == 0.0


def test_ct_with_empty_cts_list():
    data = {"pvPw": 0, "swEpsInPw": 0, "swEpsOutPw": 0,
            "inOngridPw": 0, "outOngridPw": 0, "cts": []}
    result = calc(data)
    assert result["grid_available"] is False


# ---------------------------------------------------------------------------
# p_home clamp: negative values from sensor timing artefacts → 0 (v2.0.1)
# ---------------------------------------------------------------------------

def test_home_power_clamped_to_zero_on_sensor_timing_artefact():
    """Regression v2.0.1: asynchronous sampling can briefly yield negative p_home.

    Scenario: outOngridPw=50 W (unit AC output), but SmartMeter reports tnPhasePw=100 W
    (net export). Both values are momentarily inconsistent due to different update cadences.
    Without the clamp: p_ong = -50, p_grid = -100, p_home = -100 - (-50) = -50 W (impossible).
    With the clamp: p_home = max(0.0, -50) = 0.0 W.
    """
    data = {
        "pvPw": 0,
        "swEpsInPw": 0, "swEpsOutPw": 0,
        "inOngridPw": 0, "outOngridPw": 50,
        "cts": [{"deviceSn": "SM", "tPhasePw": 0, "tnPhasePw": 100, "devType": 3, "subType": 5}],
    }
    result = calc(data)
    assert result["calc_home_power"] == 0.0, \
        "Negative home power from sensor timing artefact must be clamped to 0"


# ---------------------------------------------------------------------------
# gridSellPw=0 explicit presence — grid_available must be True (v1.1.68 fix)
# ---------------------------------------------------------------------------

def test_grid_available_true_when_grid_sell_is_explicitly_zero():
    """Regression v1.1.68: gridSellPw=0 was treated as falsy and grid_available stayed False.

    Both gridBuyPw and gridSellPw present, both zero → net grid = 0 but grid IS available.
    The explicit is-None check (not 'or') must correctly classify this.
    """
    data = {
        "pvPw": 0,
        "swEpsInPw": 0, "swEpsOutPw": 0,
        "inOngridPw": 0, "outOngridPw": 0,
        "gridBuyPw": 0, "gridSellPw": 0,
    }
    result = calc(data)
    assert result["grid_available"] is True, \
        "grid_available must be True when gridBuyPw and gridSellPw are both explicitly 0"
    assert result["calc_grid_net_power"] == 0.0


def test_grid_available_true_when_only_sell_is_present_and_zero():
    """gridBuyPw=100, gridSellPw=0 — net=100 W, grid_available=True."""
    data = {
        "pvPw": 0,
        "swEpsInPw": 0, "swEpsOutPw": 0,
        "inOngridPw": 0, "outOngridPw": 0,
        "gridBuyPw": 100, "gridSellPw": 0,
    }
    result = calc(data)
    assert result["grid_available"] is True
    assert result["calc_grid_net_power"] == 100.0
