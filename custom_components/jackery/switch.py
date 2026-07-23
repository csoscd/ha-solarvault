"""Jackery Switch Platform."""
from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

from homeassistant.components import persistent_notification
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DOMAIN

if TYPE_CHECKING:
    from .sensor import JackeryDataCoordinator

_COMM_MODE_LOCAL = 1
_COMM_MODE_CLOUD = 2
_COMM_MODE_LABELS: dict[int, str] = {
    _COMM_MODE_LOCAL: "local",
    _COMM_MODE_CLOUD: "cloud",
}


def _plug_comm_mode(item: dict[str, Any]) -> int | None:
    """Read plug commMode (1=local, 2=cloud)."""
    val = item.get("commMode")
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _plug_mqtt_control_allowed(item: dict[str, Any]) -> tuple[bool, str]:
    """Return (allowed, reason) for MQTT control of a plug."""
    mode = _plug_comm_mode(item)
    if mode == _COMM_MODE_LOCAL:
        return True, ""
    if mode == _COMM_MODE_CLOUD:
        return (
            False,
            "Smart plug is cloud-connected (commMode=2) and cannot be controlled via MQTT. "
            "Please use the Jackery App.",
        )
    if mode is None:
        return (
            False,
            "Unknown commMode. MQTT control is only supported when commMode=1 (local).",
        )
    return (
        False,
        f"Smart plug commMode={mode} does not support MQTT control. Only commMode=1 (local) is supported.",
    )

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Jackery switches."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    if coordinator is None:
        _LOGGER.warning("Coordinator not ready for switches")
        return

    # Register callback for dynamic switch entities
    def add_switch_entities_callback(new_entities):
        async_add_entities(new_entities)
    coordinator.add_switch_entities_callback = add_switch_entities_callback

    entities = []

    # Main device switches
    entities.extend(
        [
            JackeryMainSwitch(
                key="isAutoStandby",
                translation_key="auto_standby_allowed",
                coordinator=coordinator,
                config_entry_id=config_entry.entry_id,
            ),
            JackeryMainSwitch(
                key="swEps",
                translation_key="eps_switch",
                coordinator=coordinator,
                config_entry_id=config_entry.entry_id,
            ),
            JackeryOptimisticSwitch(
                key="offGridDown",
                translation_key="off_grid_fallback",
                coordinator=coordinator,
                config_entry_id=config_entry.entry_id,
            ),
            JackeryFollowMeterSwitch(
                key="isFollowMeterPw",
                translation_key="follow_meter_power",
                coordinator=coordinator,
                config_entry_id=config_entry.entry_id,
            ),
        ]
    )

    # Add any existing sub-devices as switches (non-CT)
    for item in coordinator.get_subdevices():
        sn = item.get("deviceSn") or item.get("sn")
        dev_type = item.get("devType")
        if dev_type is None and item.get("subType") == 2:
            dev_type = 2
        if sn and dev_type != 2:
            entities.append(
                JackeryPlugSwitch(
                    plug_sn=sn,
                    dev_type=dev_type,
                    coordinator=coordinator,
                    config_entry_id=config_entry.entry_id,
                )
            )

    if entities:
        async_add_entities(entities)


class JackeryPlugSwitch(SwitchEntity):
    """Jackery Smart Plug Switch."""

    def __init__(
        self,
        plug_sn: str,
        dev_type: int,
        coordinator: "JackeryDataCoordinator",
        config_entry_id: str,
    ) -> None:
        """Initialize."""
        self._plug_sn = plug_sn
        self._dev_type = dev_type
        self._coordinator = coordinator
        self._raw_data: dict[str, Any] = {}

        self._attr_name = "Switch"
        self._attr_unique_id = f"jackery_plug_{plug_sn}_switch"
        self._attr_has_entity_name = True

        main_device_id = coordinator._device_sn or config_entry_id
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"sub_{plug_sn}")},
            "via_device": (DOMAIN, main_device_id),
            "name": f"Jackery Plug {plug_sn}",
            "manufacturer": "Jackery",
            "model": f"Sub-device Type {dev_type}",
        }

    @property
    def should_poll(self) -> bool:
        return False

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._coordinator.register_sensor(f"plug_switch_{self._plug_sn}", self)

    async def async_will_remove_from_hass(self) -> None:
        self._coordinator.unregister_sensor(f"plug_switch_{self._plug_sn}")
        await super().async_will_remove_from_hass()

    def _plug_item(self) -> dict[str, Any]:
        """Return plug data, merging entity snapshot with coordinator cache (cache wins)."""
        cached = self._coordinator.get_plug_item(self._plug_sn)
        if cached:
            return {**self._raw_data, **cached}
        return dict(self._raw_data)

    def _update_from_coordinator(self, data: dict) -> None:
        my_plug = self._coordinator.get_plug_item(self._plug_sn)
        if not my_plug:
            plugs = data.get("plugs") or data.get("plug")
            if plugs and isinstance(plugs, list):
                my_plug = next(
                    (p for p in plugs if isinstance(p, dict)
                     and (p.get("sn") == self._plug_sn or p.get("deviceSn") == self._plug_sn)),
                    None,
                )
        if not my_plug:
            return

        self._raw_data = dict(my_plug)
        val = my_plug.get("sysSwitch")
        if val is None:
            val = my_plug.get("switchSta")
        if val is not None:
            self._attr_is_on = bool(int(val))
        self._attr_available = True
        self.async_write_ha_state()

    async def _ensure_mqtt_controllable(self) -> None:
        """Block control when plug is cloud-connected (commMode=2); show persistent notification."""
        allowed, reason = _plug_mqtt_control_allowed(self._plug_item())
        if not allowed:
            persistent_notification.async_create(
                self.hass,
                message=reason,
                title="Jackery Smart Plug",
                notification_id=f"jackery_plug_{self._plug_sn}_mqtt_blocked",
            )
            raise HomeAssistantError(reason)

    async def async_toggle(self, **kwargs: Any) -> None:
        await self._ensure_mqtt_controllable()
        await self._coordinator.async_control_subdevice_switch(
            plug_sn=self._plug_sn,
            dev_type=self._dev_type,
            is_on=not self.is_on,
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._ensure_mqtt_controllable()
        await self._coordinator.async_control_subdevice_switch(
            plug_sn=self._plug_sn,
            dev_type=self._dev_type,
            is_on=True,
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._ensure_mqtt_controllable()
        await self._coordinator.async_control_subdevice_switch(
            plug_sn=self._plug_sn,
            dev_type=self._dev_type,
            is_on=False,
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        raw = self._plug_item()
        mode = _plug_comm_mode(raw)
        mqtt_ok, mqtt_block_reason = _plug_mqtt_control_allowed(raw)
        switchval = raw.get("switchSta") if raw.get("switchSta") is not None else raw.get("sysSwitch")
        return {
            "plug_sn": self._plug_sn,
            "dev_type": self._dev_type,
            "commState": raw.get("commState"),
            "commMode": mode,
            "commMode_label": _COMM_MODE_LABELS.get(mode) if mode is not None else None,
            "mqtt_controllable": mqtt_ok,
            "mqtt_control_block_reason": mqtt_block_reason or None,
            "scanName": raw.get("scanName") or raw.get("name"),
            "switchSta": switchval,
            "outPw": raw.get("outPw"),
            "inPw": raw.get("inPw"),
            "raw_data": raw,
        }


class JackeryMainSwitch(SwitchEntity):
    """Main device switch (cmd=5)."""

    def __init__(
        self,
        key: str,
        coordinator: "JackeryDataCoordinator",
        config_entry_id: str,
        translation_key: str | None = None,
        name: str | None = None,
    ) -> None:
        self._key = key
        self._coordinator = coordinator
        device_sn = coordinator._device_sn or config_entry_id
        self._attr_unique_id = f"jackery_{device_sn}_switch_{key}"
        self._attr_has_entity_name = True
        if translation_key:
            self._attr_translation_key = translation_key
        elif name:
            self._attr_name = name
        self._attr_device_info = {
            "identifiers": {(DOMAIN, device_sn)},
            "name": "Jackery",
            "manufacturer": "Jackery",
            "model": "Energy Monitor",
        }

    @property
    def should_poll(self) -> bool:
        return False

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._coordinator.register_sensor(f"main_switch_{self._key}", self)

    async def async_will_remove_from_hass(self) -> None:
        self._coordinator.unregister_sensor(f"main_switch_{self._key}")
        await super().async_will_remove_from_hass()

    def _update_from_coordinator(self, data: dict) -> None:
        if self._key not in data:
            return
        val = data.get(self._key)
        if val is None:
            return
        self._attr_is_on = bool(int(val))
        self._attr_available = True
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._coordinator.async_control_main_device({self._key: 1})

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._coordinator.async_control_main_device({self._key: 0})


class JackeryOptimisticSwitch(JackeryMainSwitch):
    """Main device switch with optimistic state updates (cmd=5)."""

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._attr_is_on = True
        self.async_write_ha_state()
        self._coordinator._data_cache[self._key] = 1
        await self._coordinator.async_control_main_device({self._key: 1})

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._attr_is_on = False
        self.async_write_ha_state()
        self._coordinator._data_cache[self._key] = 0
        await self._coordinator.async_control_main_device({self._key: 0})


class JackeryFollowMeterSwitch(JackeryOptimisticSwitch):
    """'Zähler folgen' switch — only available when workModel=4 (Benutzerdefiniert).

    Writing isFollowMeterPw=1 activates Follow-Meter mode within workModel=4.
    This entity becomes unavailable when workMode != 4 to signal that the setting
    has no effect in other operating modes.
    """

    def _update_from_coordinator(self, data: dict) -> None:
        work_mode = data.get("workMode")
        if work_mode is not None:
            try:
                if int(work_mode) != 4:
                    self._attr_available = False
                    self.async_write_ha_state()
                    return
                self._attr_available = True
            except (TypeError, ValueError):
                pass

        if self._key not in data:
            return
        val = data.get(self._key)
        if val is None:
            return
        self._attr_is_on = bool(int(val))
        self._attr_available = True
        self.async_write_ha_state()
