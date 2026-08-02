"""Tests for v2.3.0 changes: SOC bounds, dynamic min/max, plug helpers."""
from __future__ import annotations

from custom_components.jackery.number import NUMBERS
from custom_components.jackery.sensor import (
    COMM_MODE_CLOUD,
    COMM_MODE_LABELS,
    COMM_MODE_LOCAL,
    plug_comm_mode,
    plug_mqtt_control_allowed,
    should_create_plug_switch,
)

# ---------------------------------------------------------------------------
# SOC limit bounds
# ---------------------------------------------------------------------------

class TestSocBounds:
    def test_soc_charge_limit_min(self):
        assert NUMBERS["socChgLimit"]["min"] == 50

    def test_soc_charge_limit_max(self):
        assert NUMBERS["socChgLimit"]["max"] == 100

    def test_soc_discharge_limit_min(self):
        assert NUMBERS["socDischgLimit"]["min"] == 5

    def test_soc_discharge_limit_max(self):
        assert NUMBERS["socDischgLimit"]["max"] == 49

    def test_soc_charge_limit_has_min_key(self):
        assert NUMBERS["socChgLimit"].get("min_key") == "minSocChg"

    def test_soc_charge_limit_has_max_key(self):
        assert NUMBERS["socChgLimit"].get("max_key") == "maxSocChg"

    def test_soc_discharge_limit_has_min_key(self):
        assert NUMBERS["socDischgLimit"].get("min_key") == "minSocDischg"

    def test_soc_discharge_limit_has_max_key(self):
        assert NUMBERS["socDischgLimit"].get("max_key") == "maxSocDischg"

    def test_charge_min_always_greater_than_discharge_max(self):
        assert NUMBERS["socChgLimit"]["min"] > NUMBERS["socDischgLimit"]["max"]


# ---------------------------------------------------------------------------
# Dynamic min/max update in JackeryMainNumber
# ---------------------------------------------------------------------------

class TestDynamicBoundsUpdate:
    def _make_number(self, key: str):
        from unittest.mock import MagicMock

        from custom_components.jackery.number import JackeryMainNumber
        coord = MagicMock()
        coord._device_sn = "TESTSN"
        cfg = NUMBERS[key]
        entity = JackeryMainNumber(
            key=key,
            min_value=float(cfg["min"]),
            max_value=float(cfg["max"]),
            step=float(cfg["step"]),
            coordinator=coord,
            config_entry_id="test_entry",
            translation_key=cfg.get("translation_key"),
        )
        entity.async_write_ha_state = MagicMock()
        return entity

    def test_dynamic_min_updates_from_data(self):
        entity = self._make_number("socChgLimit")
        entity._update_from_coordinator({"minSocChg": 55, "socChgLimit": 80})
        assert entity._attr_native_min_value == 55.0

    def test_dynamic_max_updates_from_data(self):
        entity = self._make_number("socChgLimit")
        entity._update_from_coordinator({"maxSocChg": 95, "socChgLimit": 80})
        assert entity._attr_native_max_value == 95.0

    def test_dynamic_bounds_absent_leaves_defaults(self):
        entity = self._make_number("socDischgLimit")
        entity._update_from_coordinator({"socDischgLimit": 20})
        assert entity._attr_native_min_value == 5.0
        assert entity._attr_native_max_value == 49.0

    def test_value_updated_from_data(self):
        entity = self._make_number("socChgLimit")
        entity._update_from_coordinator({"socChgLimit": 75})
        assert entity._attr_native_value == 75.0


# ---------------------------------------------------------------------------
# plug_comm_mode
# ---------------------------------------------------------------------------

class TestPlugCommMode:
    def test_local_mode(self):
        assert plug_comm_mode({"commMode": 1}) == COMM_MODE_LOCAL

    def test_cloud_mode(self):
        assert plug_comm_mode({"commMode": 2}) == COMM_MODE_CLOUD

    def test_missing_returns_none(self):
        assert plug_comm_mode({}) is None

    def test_string_value_parsed(self):
        assert plug_comm_mode({"commMode": "1"}) == 1

    def test_invalid_value_returns_none(self):
        assert plug_comm_mode({"commMode": "bad"}) is None


# ---------------------------------------------------------------------------
# plug_mqtt_control_allowed
# ---------------------------------------------------------------------------

class TestPlugMqttControlAllowed:
    def test_local_mode_allowed(self):
        allowed, reason = plug_mqtt_control_allowed({"commMode": COMM_MODE_LOCAL})
        assert allowed is True
        assert reason == ""

    def test_cloud_mode_blocked(self):
        allowed, reason = plug_mqtt_control_allowed({"commMode": COMM_MODE_CLOUD})
        assert allowed is False
        assert "commMode=2" in reason or "cloud" in reason.lower()

    def test_unknown_mode_blocked(self):
        allowed, reason = plug_mqtt_control_allowed({})
        assert allowed is False
        assert reason != ""

    def test_unexpected_mode_blocked(self):
        allowed, reason = plug_mqtt_control_allowed({"commMode": 99})
        assert allowed is False
        assert "99" in reason


# ---------------------------------------------------------------------------
# should_create_plug_switch
# ---------------------------------------------------------------------------

class TestShouldCreatePlugSwitch:
    def test_devtype6_is_plug(self):
        assert should_create_plug_switch({"devType": 6}) is True

    def test_devtype2_is_not_plug(self):
        assert should_create_plug_switch({"devType": 2}) is False

    def test_devtype3_is_not_plug(self):
        assert should_create_plug_switch({"devType": 3}) is False

    def test_devtype4_is_not_plug(self):
        assert should_create_plug_switch({"devType": 4}) is False

    def test_missing_devtype_is_not_plug(self):
        assert should_create_plug_switch({}) is False


# ---------------------------------------------------------------------------
# COMM_MODE_LABELS
# ---------------------------------------------------------------------------

class TestCommModeLabels:
    def test_local_label(self):
        assert COMM_MODE_LABELS[COMM_MODE_LOCAL] == "local"

    def test_cloud_label(self):
        assert COMM_MODE_LABELS[COMM_MODE_CLOUD] == "cloud"
