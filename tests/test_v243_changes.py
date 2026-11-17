"""Tests for v2.4.3 changes: ability-gated entities and storm_warning_active sensor."""
from __future__ import annotations

import pytest

from custom_components.jackery.number import NUMBERS
from custom_components.jackery.sensor import SENSORS, STORM_WARNING_MAP


class TestStormWarningMap:
    def test_map_keys_are_ints(self) -> None:
        for k in STORM_WARNING_MAP:
            assert isinstance(k, int)

    def test_map_values_are_strings(self) -> None:
        for v in STORM_WARNING_MAP.values():
            assert isinstance(v, str)

    def test_inactive_is_zero(self) -> None:
        assert STORM_WARNING_MAP[0] == "inactive"

    def test_active_is_one(self) -> None:
        assert STORM_WARNING_MAP[1] == "active"


class TestStormWarningActiveSensorConfig:
    def test_sensor_exists(self) -> None:
        assert "storm_warning_active" in SENSORS

    def test_json_key_is_wps(self) -> None:
        assert SENSORS["storm_warning_active"]["json_key"] == "wps"

    def test_has_value_map(self) -> None:
        cfg = SENSORS["storm_warning_active"]
        assert "value_map" in cfg
        assert cfg["value_map"] == STORM_WARNING_MAP

    def test_options_match_map_values(self) -> None:
        cfg = SENSORS["storm_warning_active"]
        assert list(cfg["options"]) == list(STORM_WARNING_MAP.values())

    def test_no_unit(self) -> None:
        assert SENSORS["storm_warning_active"].get("unit") is None

    def test_no_state_class(self) -> None:
        assert SENSORS["storm_warning_active"].get("state_class") is None


class TestMaxOutPwAbilityBitConfig:
    def test_ability_bit_9_in_numbers(self) -> None:
        assert "ability_bit" in NUMBERS["maxOutPw"]
        assert NUMBERS["maxOutPw"]["ability_bit"] == 9

    def test_max_out_pw_optimistic(self) -> None:
        assert NUMBERS["maxOutPw"].get("optimistic") is True

    def test_max_out_pw_translation_key(self) -> None:
        assert NUMBERS["maxOutPw"]["translation_key"] == "max_feed_in_power"


class TestAbilityBitLogic:
    """Unit tests for the ability-bit masking logic used in ForceCharge / MaxOutPw."""

    @pytest.mark.parametrize("ability,bit,expected_set", [
        # bit 11 (Force Charge)
        (0, 11, False),
        (768, 11, False),    # bits 8+9 only — no Force Charge
        (2048, 11, True),    # only bit 11
        (3840, 11, True),    # bits 8+9+10+11 — Force Charge available
        (4095, 11, True),    # all lower 12 bits
        # bit 9 (Max Output Power select)
        (0, 9, False),
        (512, 9, True),      # only bit 9
        (768, 9, True),      # bits 8+9
        (256, 9, False),     # only bit 8
        (3840, 9, True),     # bits 8+9+10+11
    ])
    def test_bit_extraction(self, ability: int, bit: int, expected_set: bool) -> None:
        result = bool((int(ability) >> bit) & 1)
        assert result is expected_set, (
            f"ability={ability:#010b}, bit={bit}: expected {expected_set}, got {result}"
        )

    def test_ability_768_bit9_set_bit11_not(self) -> None:
        ability = 768  # observed value on hardware without Force Charge
        assert bool((ability >> 9) & 1) is True   # Max Output Power: visible
        assert bool((ability >> 11) & 1) is False  # Force Charge: hidden

    def test_ability_3840_both_bits_set(self) -> None:
        ability = 3840  # observed value on hardware with Force Charge
        assert bool((ability >> 9) & 1) is True
        assert bool((ability >> 11) & 1) is True
