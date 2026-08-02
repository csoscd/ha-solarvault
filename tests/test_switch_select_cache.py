"""Tests for the optimistic-state cache-patch pattern in switch.py and select.py.

The pattern (documented in v1.3.1): after a control write, coordinator._data_cache
must be patched immediately so _distribute_data calls don't revert the UI state
before the next type-106 poll confirms the write.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.jackery.select import JackeryMaxFeedInSelect, JackeryWorkModeSelect
from custom_components.jackery.switch import JackeryFollowMeterSwitch, JackeryOptimisticSwitch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeCoordinator:
    def __init__(self):
        self._data_cache: dict = {}
        self._device_sn = "TESTSN001"
        self.last_cmd: dict = {}

    async def async_control_main_device(self, params: dict) -> None:
        self.last_cmd = params

    async def send_command(self, *args, **kwargs) -> None:
        pass


def _make_switch(key: str) -> JackeryOptimisticSwitch:
    s = JackeryOptimisticSwitch.__new__(JackeryOptimisticSwitch)
    s._key = key
    s._coordinator = _FakeCoordinator()
    s._attr_is_on = False
    s._attr_available = True
    s.async_write_ha_state = MagicMock()
    return s


def _make_follow_meter_switch() -> JackeryFollowMeterSwitch:
    s = JackeryFollowMeterSwitch.__new__(JackeryFollowMeterSwitch)
    s._key = "isFollowMeterPw"
    s._coordinator = _FakeCoordinator()
    s._attr_is_on = False
    s._attr_available = True
    s.async_write_ha_state = MagicMock()
    return s


def _make_workmode_select() -> JackeryWorkModeSelect:
    sel = JackeryWorkModeSelect.__new__(JackeryWorkModeSelect)
    sel._coordinator = _FakeCoordinator()
    sel._attr_current_option = None
    sel.async_write_ha_state = MagicMock()
    return sel


def _make_max_feed_in_select() -> JackeryMaxFeedInSelect:
    sel = JackeryMaxFeedInSelect.__new__(JackeryMaxFeedInSelect)
    sel._coordinator = _FakeCoordinator()
    sel._attr_current_option = None
    sel.async_write_ha_state = MagicMock()
    return sel


# ---------------------------------------------------------------------------
# JackeryOptimisticSwitch — cache-patch on turn_on / turn_off
# ---------------------------------------------------------------------------

async def test_optimistic_switch_turn_on_patches_cache():
    """turn_on must patch cache to 1 before sending MQTT command."""
    s = _make_switch("swEps")
    await s.async_turn_on()

    assert s._attr_is_on is True
    assert s._coordinator._data_cache["swEps"] == 1
    assert s._coordinator.last_cmd == {"swEps": 1}
    s.async_write_ha_state.assert_called()


async def test_optimistic_switch_turn_off_patches_cache():
    """turn_off must patch cache to 0 before sending MQTT command."""
    s = _make_switch("swEps")
    s._attr_is_on = True
    await s.async_turn_off()

    assert s._attr_is_on is False
    assert s._coordinator._data_cache["swEps"] == 0
    assert s._coordinator.last_cmd == {"swEps": 0}


# ---------------------------------------------------------------------------
# JackeryWorkModeSelect — both workMode and workModel must be patched
# ---------------------------------------------------------------------------

async def test_work_mode_select_patches_both_cache_keys():
    """async_select_option must patch both workMode and workModel to prevent state revert."""
    sel = _make_workmode_select()
    await sel.async_select_option("self_consumption")

    assert sel._attr_current_option == "self_consumption"
    assert sel._coordinator._data_cache.get("workMode") == 2
    assert sel._coordinator._data_cache.get("workModel") == 2
    assert sel._coordinator.last_cmd == {"workModel": 2}


async def test_work_mode_select_custom_mode():
    """Benutzerdefiniert (custom) maps to workModel=4."""
    sel = _make_workmode_select()
    await sel.async_select_option("custom")

    assert sel._coordinator._data_cache["workMode"] == 4
    assert sel._coordinator._data_cache["workModel"] == 4


# ---------------------------------------------------------------------------
# JackeryMaxFeedInSelect — maxOutPw must be patched
# ---------------------------------------------------------------------------

async def test_max_feed_in_select_patches_cache():
    """async_select_option must patch maxOutPw in coordinator cache."""
    sel = _make_max_feed_in_select()
    await sel.async_select_option("w800")

    assert sel._attr_current_option == "w800"
    assert sel._coordinator._data_cache.get("maxOutPw") == 800
    assert sel._coordinator.last_cmd == {"maxOutPw": 800}


async def test_max_feed_in_select_w2500():
    """2500 W option must be correctly mapped and patched."""
    sel = _make_max_feed_in_select()
    await sel.async_select_option("w2500")

    assert sel._coordinator._data_cache["maxOutPw"] == 2500


# ---------------------------------------------------------------------------
# JackeryFollowMeterSwitch — availability tied to workMode
# ---------------------------------------------------------------------------

def test_follow_meter_switch_unavailable_when_work_mode_not_4():
    """When workMode != 4, FollowMeterSwitch must become unavailable."""
    s = _make_follow_meter_switch()
    s._attr_available = True

    s._update_from_coordinator({"workMode": 2, "isFollowMeterPw": 1})

    assert s._attr_available is False
    s.async_write_ha_state.assert_called()


def test_follow_meter_switch_available_and_on_when_work_mode_4():
    """When workMode == 4 and isFollowMeterPw == 1, switch is available and on."""
    s = _make_follow_meter_switch()
    s._attr_available = False

    s._update_from_coordinator({"workMode": 4, "isFollowMeterPw": 1})

    assert s._attr_available is True
    assert s._attr_is_on is True
