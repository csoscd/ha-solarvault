"""Tests for JackerySensor._update_from_coordinator special-case transformations."""
from unittest.mock import MagicMock, patch

import pytest

from custom_components.jackery.sensor import JackeryDataCoordinator, JackerySensor, SENSORS


def make_sensor(sensor_id: str, coord: JackeryDataCoordinator) -> JackerySensor:
    """Create a JackerySensor without registering it in HA."""
    sensor = JackerySensor.__new__(JackerySensor)
    sensor._sensor_id = sensor_id
    sensor._coordinator = coord
    sensor._config = SENSORS[sensor_id]
    sensor._attr_native_value = None
    sensor._attr_available = False
    sensor.async_write_ha_state = MagicMock()
    return sensor


# ---------------------------------------------------------------------------
# battery_temperature: cellTemp × 0.1
# ---------------------------------------------------------------------------

def test_battery_temperature_scaling(coordinator):
    sensor = make_sensor("battery_temperature", coordinator)
    sensor._update_from_coordinator({"cellTemp": 293})
    assert sensor._attr_native_value == pytest.approx(29.3)
    assert sensor._attr_available is True


def test_battery_temperature_zero(coordinator):
    sensor = make_sensor("battery_temperature", coordinator)
    sensor._update_from_coordinator({"cellTemp": 0})
    assert sensor._attr_native_value == 0.0


# ---------------------------------------------------------------------------
# eps_output_power: swEpsOutPw − swEpsInPw
# ---------------------------------------------------------------------------

def test_eps_output_power_net_positive(coordinator):
    sensor = make_sensor("eps_output_power", coordinator)
    sensor._update_from_coordinator({"swEpsOutPw": 500, "swEpsInPw": 100})
    assert sensor._attr_native_value == pytest.approx(400.0)


def test_eps_output_power_net_negative(coordinator):
    sensor = make_sensor("eps_output_power", coordinator)
    sensor._update_from_coordinator({"swEpsOutPw": 50, "swEpsInPw": 200})
    assert sensor._attr_native_value == pytest.approx(-150.0)


def test_eps_output_power_defaults_to_zero_when_missing(coordinator):
    sensor = make_sensor("eps_output_power", coordinator)
    sensor._update_from_coordinator({})
    assert sensor._attr_native_value == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# solar_power_pv1: dict {"pvPw": ...} unpacking
# ---------------------------------------------------------------------------

def test_solar_pv1_dict_pvPw(coordinator):
    sensor = make_sensor("solar_power_pv1", coordinator)
    sensor._update_from_coordinator({"pv1": {"pvPw": 800, "commState": 1}})
    assert sensor._attr_native_value == 800


def test_solar_pv1_dict_w_key(coordinator):
    sensor = make_sensor("solar_power_pv1", coordinator)
    sensor._update_from_coordinator({"pv1": {"w": 600}})
    assert sensor._attr_native_value == 600


def test_solar_pv1_dict_power_key(coordinator):
    sensor = make_sensor("solar_power_pv1", coordinator)
    sensor._update_from_coordinator({"pv1": {"power": 400}})
    assert sensor._attr_native_value == 400


def test_solar_pv1_scalar_value(coordinator):
    """If pv1 is a plain number (unusual), scale × 1 applies."""
    sensor = make_sensor("solar_power_pv1", coordinator)
    sensor._update_from_coordinator({"pv1": 750})
    assert sensor._attr_native_value == pytest.approx(750.0)


# ---------------------------------------------------------------------------
# Energy sensors: scale = 0.01 (×0.01 for kWh)
# ---------------------------------------------------------------------------

def test_grid_import_energy_scale(coordinator):
    sensor = make_sensor("grid_import_energy", coordinator)
    sensor._update_from_coordinator({"inOngridEgy": 12345})
    assert sensor._attr_native_value == pytest.approx(123.45)


def test_battery_charge_energy_scale(coordinator):
    sensor = make_sensor("battery_charge_energy", coordinator)
    sensor._update_from_coordinator({"batChgEgy": 10000})
    assert sensor._attr_native_value == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# grid_net_power: keep last value when None (CT temporarily missing)
# ---------------------------------------------------------------------------

def test_grid_net_power_keeps_last_value_when_none(coordinator):
    sensor = make_sensor("grid_net_power", coordinator)
    sensor._attr_native_value = 350.0

    # CT missing → calc_grid_net_power is None
    sensor._update_from_coordinator({"calc_grid_net_power": None})

    # Value must be unchanged
    assert sensor._attr_native_value == 350.0


def test_grid_net_power_updates_when_value_present(coordinator):
    sensor = make_sensor("grid_net_power", coordinator)
    sensor._update_from_coordinator({"calc_grid_net_power": -500.0})
    assert sensor._attr_native_value == pytest.approx(-500.0)


# ---------------------------------------------------------------------------
# Missing key: sensor stays at previous value, stays unavailable
# ---------------------------------------------------------------------------

def test_missing_key_leaves_sensor_unchanged(coordinator):
    sensor = make_sensor("battery_soc", coordinator)
    sensor._attr_native_value = 42
    sensor._attr_available = True

    sensor._update_from_coordinator({})  # batSoc not in data

    assert sensor._attr_native_value == 42
    # async_write_ha_state must NOT be called (no state change)
    sensor.async_write_ha_state.assert_not_called()


# ---------------------------------------------------------------------------
# async_write_ha_state called on successful update
# ---------------------------------------------------------------------------

def test_state_written_after_update(coordinator):
    sensor = make_sensor("battery_soc", coordinator)
    sensor._update_from_coordinator({"batSoc": 80})
    sensor.async_write_ha_state.assert_called_once()
