"""Tests for startup logging, silence-warning, and repair-issue behaviour (Issue #23)."""
from __future__ import annotations

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.jackery.sensor import (
    DOMAIN,
    SILENCE_ISSUE_ID_PREFIX,
    SILENCE_WARNING_TIMEOUT,
    JackeryDataCoordinator,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_coordinator(*, device_sn: str = "TESTSN001", fork_version: str = "2.5.6") -> JackeryDataCoordinator:
    """Return a bare coordinator without MQTT subscription, for unit tests."""
    coord = JackeryDataCoordinator.__new__(JackeryDataCoordinator)
    coord.hass = MagicMock()
    coord.hass.data = {DOMAIN: {"test-entry-id": {"fork_version": fork_version}}}
    coord.hass.config_entries.async_get_entry.return_value = None
    coord._topic_prefix = "hb"
    coord._token = "testtoken"
    coord._mqtt_host = "localhost"
    coord._device_sn = device_sn
    coord._topic_root = "hb"
    coord._sensors = {}
    coord._data_task = None
    coord._subscribed = False
    coord._last_update_time = time.time()
    coord._known_plugs = set()
    coord._subdevice_missing_since = {}
    coord._subdevice_last_seen = {}
    coord._expansion_battery_sns = set()
    coord._start_time = time.time()
    coord._poll_105_counter = 0
    coord._device_type = None
    coord._soft_ver = None
    coord._reauth_started = False
    coord._ever_received = False
    coord._lifecycle_active = True
    coord._stop_requested = False
    coord._silence_warned = False
    coord._silence_issue_created = False
    coord._fork_version = fork_version
    coord.add_entities_callback = None
    coord.add_switch_entities_callback = None
    coord._data_cache = {}
    coord._type2_live_seen = {}
    coord._http_sm_sensor_sns_created = set()
    coord._smartmeter_http_task = None
    coord._mqtt_unsubscribers = []
    coord._topic_status_wildcard = "hb/device/+/status"
    coord._topic_event_wildcard = "hb/device/+/event"
    coord._topic_alert_wildcard = "hb/device/+/alert"
    coord.config_entry_id = "test-entry-id"
    return coord


def _unsub_mock() -> MagicMock:
    """Return a callable MagicMock that acts as an MQTT unsubscribe callback."""
    return MagicMock(return_value=None)


async def _run_one_poll_cycle(coord: JackeryDataCoordinator) -> None:
    """Run one full iteration of the _periodic_data_request while loop.

    Any sleep >= 10 s (REQUEST_INTERVAL) ends the loop via CancelledError.
    Shorter sleeps (initial 2 s, 0.5 s inter-poll, 5 s SN-discovery) pass through.
    """
    publish_mock = AsyncMock()

    async def _mock_sleep(seconds: float) -> None:
        if seconds >= 10:
            raise asyncio.CancelledError

    with (
        patch("custom_components.jackery.sensor.asyncio.sleep", side_effect=_mock_sleep),
        patch("custom_components.jackery.sensor.ha_mqtt.async_publish", publish_mock),
    ):
        try:
            await coord._periodic_data_request()
        except asyncio.CancelledError:
            pass


# ---------------------------------------------------------------------------
# Startup INFO log — calls real async_start (MQTT subscribe mocked)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_startup_log_contains_fork_tag(caplog):
    """async_start emits an INFO line identifying this fork and the device SN."""
    import logging

    coord = _make_coordinator(fork_version="2.5.6")
    unsub = _unsub_mock()

    with caplog.at_level(logging.INFO, logger="custom_components.jackery.sensor"):
        with (
            patch(
                "custom_components.jackery.sensor.ha_mqtt.async_subscribe",
                AsyncMock(return_value=unsub),
            ),
            patch.object(coord.hass, "async_create_task", return_value=MagicMock()),
            patch(
                "custom_components.jackery.sensor.ha_mqtt.async_wait_for_mqtt_client",
                return_value=True,
            ),
        ):
            # Patch create_task to prevent _periodic_data_request from actually running
            coord.hass.config_entries.async_get_entry.return_value = None
            await coord.async_start()

    assert any(
        "Jackery SolarVault (csoscd fork)" in r.message
        and "device_sn=TESTSN001" in r.message
        for r in caplog.records
        if r.levelno == logging.INFO
    ), f"Expected INFO with fork tag and SN. Records: {[r.message for r in caplog.records]}"


# ---------------------------------------------------------------------------
# Lowercase SN warning — calls real async_start
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lowercase_sn_emits_warning(caplog):
    """A device SN with lowercase letters triggers a WARNING during async_start."""
    import logging

    coord = _make_coordinator(device_sn="hr2c001abc")
    unsub = _unsub_mock()

    with caplog.at_level(logging.WARNING, logger="custom_components.jackery.sensor"):
        with (
            patch(
                "custom_components.jackery.sensor.ha_mqtt.async_subscribe",
                AsyncMock(return_value=unsub),
            ),
            patch.object(coord.hass, "async_create_task", return_value=MagicMock()),
        ):
            coord.hass.config_entries.async_get_entry.return_value = None
            await coord.async_start()

    assert any(
        "lowercase" in r.message for r in caplog.records if r.levelno == logging.WARNING
    ), f"Expected WARNING about lowercase SN. Records: {[r.message for r in caplog.records]}"
    assert any("hr2c001abc" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_uppercase_sn_no_lowercase_warning(caplog):
    """An uppercase SN does NOT trigger a lowercase warning during async_start."""
    import logging

    coord = _make_coordinator(device_sn="HR2C001ABC")
    unsub = _unsub_mock()

    with caplog.at_level(logging.WARNING, logger="custom_components.jackery.sensor"):
        with (
            patch(
                "custom_components.jackery.sensor.ha_mqtt.async_subscribe",
                AsyncMock(return_value=unsub),
            ),
            patch.object(coord.hass, "async_create_task", return_value=MagicMock()),
        ):
            coord.hass.config_entries.async_get_entry.return_value = None
            await coord.async_start()

    lowercase_warnings = [r for r in caplog.records if "lowercase" in r.message]
    assert lowercase_warnings == [], f"Unexpected lowercase warnings: {[r.message for r in lowercase_warnings]}"


# ---------------------------------------------------------------------------
# Silence warning (timeout without MQTT response)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_silence_timeout_emits_warning_not_reauth(caplog):
    """After SILENCE_WARNING_TIMEOUT with no MQTT reply, a WARNING is emitted — no re-auth flow.

    _trigger_reauth is wired up (non-None entry mock) so the assert is meaningful:
    if the silence path called _trigger_reauth, entry_mock.async_start_reauth would fire.
    """
    import logging

    coord = _make_coordinator()
    coord._start_time = time.time() - SILENCE_WARNING_TIMEOUT - 1

    # Provide a real entry mock so _trigger_reauth would actually proceed if called
    entry_mock = MagicMock()
    coord.hass.config_entries.async_get_entry.return_value = entry_mock

    with (
        caplog.at_level(logging.WARNING, logger="custom_components.jackery.sensor"),
        patch("custom_components.jackery.sensor.ir") as mock_ir,
    ):
        mock_ir.IssueSeverity = MagicMock()
        mock_ir.IssueSeverity.WARNING = "warning"
        await _run_one_poll_cycle(coord)

    assert coord._silence_warned is True
    assert coord._reauth_started is False
    entry_mock.async_start_reauth.assert_not_called()
    assert any("No MQTT response" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_silence_warning_only_once(caplog):
    """The silence WARNING is only emitted once even across multiple poll cycles."""
    import logging

    coord = _make_coordinator()
    coord._start_time = time.time() - SILENCE_WARNING_TIMEOUT - 1

    with (
        caplog.at_level(logging.WARNING, logger="custom_components.jackery.sensor"),
        patch("custom_components.jackery.sensor.ir") as mock_ir,
    ):
        mock_ir.IssueSeverity = MagicMock()
        mock_ir.IssueSeverity.WARNING = "warning"
        await _run_one_poll_cycle(coord)
        await _run_one_poll_cycle(coord)

    silence_warnings = [r for r in caplog.records if "No MQTT response" in r.message]
    assert len(silence_warnings) == 1


@pytest.mark.asyncio
async def test_silence_warning_suppressed_when_ever_received(caplog):
    """If _ever_received is True, the silence WARNING is NOT emitted."""
    import logging

    coord = _make_coordinator()
    coord._start_time = time.time() - SILENCE_WARNING_TIMEOUT - 1
    coord._ever_received = True

    with caplog.at_level(logging.WARNING, logger="custom_components.jackery.sensor"):
        with patch("custom_components.jackery.sensor.ir"):
            await _run_one_poll_cycle(coord)

    silence_warnings = [r for r in caplog.records if "No MQTT response" in r.message]
    assert silence_warnings == []


@pytest.mark.asyncio
async def test_silence_then_401_triggers_reauth():
    """After silence path fires, a type-123/401 message still triggers re-auth."""
    coord = _make_coordinator()
    coord._start_time = time.time() - SILENCE_WARNING_TIMEOUT - 1

    with patch("custom_components.jackery.sensor.ir") as mock_ir:
        mock_ir.IssueSeverity = MagicMock()
        mock_ir.IssueSeverity.WARNING = "warning"
        await _run_one_poll_cycle(coord)

    assert coord._silence_warned is True

    # Now send a type-123/401 message
    entry_mock = MagicMock()
    entry_mock.async_start_reauth = MagicMock()
    coord.hass.config_entries.async_get_entry.return_value = entry_mock

    msg = MagicMock()
    msg.topic = "hb/device/TESTSN001/status"
    msg.payload = json.dumps({"type": 123, "body": {"errorCode": 401}}).encode()
    coord._handle_message(msg)

    assert coord._reauth_started is True


# ---------------------------------------------------------------------------
# Repair Issue creation and deletion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_repair_issue_created_after_timeout():
    """After timeout, a HA Repair Issue is created via ir.async_create_issue."""
    coord = _make_coordinator()
    coord._start_time = time.time() - SILENCE_WARNING_TIMEOUT - 1

    with patch("custom_components.jackery.sensor.ir") as mock_ir:
        mock_ir.IssueSeverity = MagicMock()
        mock_ir.IssueSeverity.WARNING = "warning"
        await _run_one_poll_cycle(coord)

    mock_ir.async_create_issue.assert_called_once()
    call_args = mock_ir.async_create_issue.call_args
    assert call_args[0][0] is coord.hass
    assert call_args[0][1] == DOMAIN
    assert call_args[0][2] == f"{SILENCE_ISSUE_ID_PREFIX}test-entry-id"
    assert coord._silence_issue_created is True


@pytest.mark.asyncio
async def test_repair_issue_created_only_once():
    """The Repair Issue is created exactly once, not on every poll cycle."""
    coord = _make_coordinator()
    coord._start_time = time.time() - SILENCE_WARNING_TIMEOUT - 1

    with patch("custom_components.jackery.sensor.ir") as mock_ir:
        mock_ir.IssueSeverity = MagicMock()
        mock_ir.IssueSeverity.WARNING = "warning"
        await _run_one_poll_cycle(coord)
        await _run_one_poll_cycle(coord)

    assert mock_ir.async_create_issue.call_count == 1


def test_repair_issue_deleted_on_first_message():
    """When the first valid MQTT message arrives, the Repair Issue is deleted."""
    coord = _make_coordinator()
    coord._silence_issue_created = True

    with patch("custom_components.jackery.sensor.ir") as mock_ir:
        msg = MagicMock()
        msg.topic = "hb/device/TESTSN001/status"
        msg.payload = json.dumps({"type": 2, "body": {"soc": 50, "batSoc": 50}}).encode()
        coord._handle_message(msg)

    mock_ir.async_delete_issue.assert_called_once_with(
        coord.hass,
        DOMAIN,
        f"{SILENCE_ISSUE_ID_PREFIX}test-entry-id",
    )
    assert coord._silence_issue_created is False


@pytest.mark.asyncio
async def test_repair_issue_deleted_on_stop():
    """When the coordinator stops, an open Repair Issue is deleted."""
    coord = _make_coordinator()
    coord._silence_issue_created = True
    coord._data_task = None
    coord._smartmeter_http_task = None

    with patch("custom_components.jackery.sensor.ir") as mock_ir:
        await coord.async_stop()

    mock_ir.async_delete_issue.assert_called_once_with(
        coord.hass,
        DOMAIN,
        f"{SILENCE_ISSUE_ID_PREFIX}test-entry-id",
    )
    assert coord._silence_issue_created is False


# ---------------------------------------------------------------------------
# Poll DEBUG line contains fork tag
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_poll_debug_line_contains_fork_tag(caplog):
    """The _send_poll_requests debug line includes the fork identification tag."""
    import logging

    coord = _make_coordinator()

    with (
        caplog.at_level(logging.DEBUG, logger="custom_components.jackery.sensor"),
        patch("custom_components.jackery.sensor.ha_mqtt.async_publish", AsyncMock()),
    ):
        await coord._send_poll_requests()

    assert any(
        "Jackery SolarVault (csoscd fork)" in r.message
        for r in caplog.records
        if r.levelno == logging.DEBUG
    ), f"Expected DEBUG with fork tag. Records: {[r.message for r in caplog.records if r.levelno == logging.DEBUG]}"


# ---------------------------------------------------------------------------
# Re-auth WARNING contains fork tag
# ---------------------------------------------------------------------------


def test_reauth_warning_contains_fork_tag(caplog):
    """_trigger_reauth emits a WARNING that includes the fork identification tag."""
    import logging

    coord = _make_coordinator()
    entry_mock = MagicMock()
    entry_mock.async_start_reauth = MagicMock()
    coord.hass.config_entries.async_get_entry.return_value = entry_mock

    with caplog.at_level(logging.WARNING, logger="custom_components.jackery.sensor"):
        coord._trigger_reauth("test reason")

    assert any(
        "Jackery SolarVault (csoscd fork)" in r.message
        for r in caplog.records
        if r.levelno == logging.WARNING
    )
