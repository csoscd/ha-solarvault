"""Shared test fixtures."""
import time
from unittest.mock import MagicMock

import pytest

from custom_components.jackery.sensor import JackeryDataCoordinator


@pytest.fixture
def coordinator():
    """Minimal JackeryDataCoordinator without MQTT subscription, for unit tests."""
    coord = JackeryDataCoordinator.__new__(JackeryDataCoordinator)
    coord.hass = None
    coord._topic_prefix = "hb"
    coord._token = "testtoken"
    coord._mqtt_host = "localhost"
    coord._device_sn = "TESTSN001"
    coord._topic_root = "hb"
    coord._sensors = {}
    coord._data_task = None
    coord._subscribed = False
    coord._last_update_time = time.time()
    coord._known_plugs = set()
    coord._subdevice_missing_since = {}
    coord._subdevice_last_seen = {}
    coord._start_time = time.time()
    coord.add_entities_callback = None
    coord.add_switch_entities_callback = None
    coord._data_cache = {}
    coord._topic_status_wildcard = "hb/device/+/status"
    coord._topic_event_wildcard = "hb/device/+/event"
    return coord


class FakeMqttMsg:
    """Minimal MQTT message stub."""

    def __init__(self, topic: str, payload: str | bytes) -> None:
        self.topic = topic
        self.payload = payload.encode() if isinstance(payload, str) else payload
