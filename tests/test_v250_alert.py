"""Tests for v2.5.0 – Alert-Topic subscription and jackery_alert HA bus event."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

from tests.conftest import FakeMqttMsg

TOPIC_ALERT = "hb/device/TESTSN001/alert"
TOPIC_ALERT_OTHER_SN = "hb/device/OTHERSN999/alert"


def fire_alert(coordinator, topic: str, payload: dict) -> None:
    """Inject an alert MQTT message directly into the coordinator."""
    coordinator._handle_alert_message(FakeMqttMsg(topic, json.dumps(payload)))


# ---------------------------------------------------------------------------
# Topic-wildcard attribute
# ---------------------------------------------------------------------------


def test_alert_wildcard_attribute_set(coordinator):
    """_topic_alert_wildcard must follow the hb/device/+/alert pattern."""
    assert coordinator._topic_alert_wildcard == "hb/device/+/alert"


# ---------------------------------------------------------------------------
# Alert event firing — happy paths
# ---------------------------------------------------------------------------


def test_alert_fires_ha_event_basic(coordinator):
    """A well-formed alert payload must fire a jackery_alert event on the HA bus."""
    mock_hass = MagicMock()
    coordinator.hass = mock_hass

    fire_alert(coordinator, TOPIC_ALERT, {
        "alertId": 42,
        "recordTs": 1700000000,
    })

    mock_hass.bus.async_fire.assert_called_once()
    event_type, event_data = mock_hass.bus.async_fire.call_args[0]
    assert event_type == "jackery_alert"
    assert event_data["device_sn"] == "TESTSN001"
    assert event_data["alert_id"] == 42
    assert event_data["record_ts"] == 1700000000


def test_alert_includes_optional_storm_warning_fields(coordinator):
    """Storm Warning fields (status, startTs, endTs, manual) must be included when present."""
    mock_hass = MagicMock()
    coordinator.hass = mock_hass

    fire_alert(coordinator, TOPIC_ALERT, {
        "alertId": 7,
        "recordTs": 1700001000,
        "status": 1,
        "startTs": 1700001000,
        "endTs": 1700010000,
        "manual": 0,
    })

    _, event_data = mock_hass.bus.async_fire.call_args[0]
    assert event_data["status"] == 1
    assert event_data["startTs"] == 1700001000
    assert event_data["endTs"] == 1700010000
    assert event_data["manual"] == 0


def test_alert_works_with_wrapped_body(coordinator):
    """Payloads wrapped in a {'body': {...}} envelope must be handled."""
    mock_hass = MagicMock()
    coordinator.hass = mock_hass

    fire_alert(coordinator, TOPIC_ALERT, {
        "type": 99,
        "body": {
            "alertId": 5,
            "recordTs": 1700002000,
        },
    })

    _, event_data = mock_hass.bus.async_fire.call_args[0]
    assert event_data["alert_id"] == 5
    assert event_data["record_ts"] == 1700002000


def test_alert_omits_missing_optional_fields(coordinator):
    """Optional fields (status, startTs, etc.) must not appear when absent from payload."""
    mock_hass = MagicMock()
    coordinator.hass = mock_hass

    fire_alert(coordinator, TOPIC_ALERT, {"alertId": 1, "recordTs": 1700003000})

    _, event_data = mock_hass.bus.async_fire.call_args[0]
    assert "status" not in event_data
    assert "startTs" not in event_data
    assert "endTs" not in event_data
    assert "manual" not in event_data


# ---------------------------------------------------------------------------
# SN filtering
# ---------------------------------------------------------------------------


def test_alert_ignored_for_different_sn(coordinator):
    """Alert from a different device SN must be silently discarded."""
    mock_hass = MagicMock()
    coordinator.hass = mock_hass

    fire_alert(coordinator, TOPIC_ALERT_OTHER_SN, {"alertId": 99, "recordTs": 0})

    mock_hass.bus.async_fire.assert_not_called()


def test_alert_accepted_when_device_sn_not_configured(coordinator):
    """Without a configured device SN, alerts from any SN are accepted."""
    mock_hass = MagicMock()
    coordinator.hass = mock_hass
    coordinator._device_sn = ""  # empty string — no SN filter active

    fire_alert(coordinator, TOPIC_ALERT_OTHER_SN, {"alertId": 3, "recordTs": 1700004000})

    mock_hass.bus.async_fire.assert_called_once()


# ---------------------------------------------------------------------------
# Topic matching
# ---------------------------------------------------------------------------


def test_alert_not_fired_for_status_topic(coordinator):
    """Messages on hb/device/{sn}/status must not trigger the alert handler."""
    mock_hass = MagicMock()
    coordinator.hass = mock_hass

    # Using the status topic — _handle_alert_message does a fullmatch, so /status ≠ /alert
    msg = FakeMqttMsg("hb/device/TESTSN001/status", json.dumps({"alertId": 1, "recordTs": 0}))
    coordinator._handle_alert_message(msg)

    mock_hass.bus.async_fire.assert_not_called()


# ---------------------------------------------------------------------------
# Robustness: malformed payloads must not raise
# ---------------------------------------------------------------------------


def test_alert_invalid_json_does_not_raise(coordinator):
    """Malformed JSON on the alert topic must be silently swallowed."""
    mock_hass = MagicMock()
    coordinator.hass = mock_hass

    msg = FakeMqttMsg(TOPIC_ALERT, b"this is not json{{{{")
    coordinator._handle_alert_message(msg)  # must not raise

    mock_hass.bus.async_fire.assert_not_called()


def test_alert_non_dict_payload_does_not_raise(coordinator):
    """A JSON array payload must be silently ignored."""
    mock_hass = MagicMock()
    coordinator.hass = mock_hass

    msg = FakeMqttMsg(TOPIC_ALERT, json.dumps([1, 2, 3]))
    coordinator._handle_alert_message(msg)

    mock_hass.bus.async_fire.assert_not_called()


def test_alert_bytes_payload_decoded_correctly(coordinator):
    """Payload arriving as bytes must be decoded to UTF-8 before JSON parsing."""
    mock_hass = MagicMock()
    coordinator.hass = mock_hass

    payload = json.dumps({"alertId": 9, "recordTs": 1700005000}).encode("utf-8")
    msg = FakeMqttMsg(TOPIC_ALERT, payload)
    coordinator._handle_alert_message(msg)

    mock_hass.bus.async_fire.assert_called_once()
    _, event_data = mock_hass.bus.async_fire.call_args[0]
    assert event_data["alert_id"] == 9
