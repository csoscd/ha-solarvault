"""Jackery Select Platform."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DOMAIN

if TYPE_CHECKING:
    from .sensor import JackeryDataCoordinator

_LOGGER = logging.getLogger(__name__)

# autoStandby: 0=Invalid, 1=Standby, 2=On
_AUTO_STANDBY_OPTIONS: dict[str, int] = {
    "invalid": 0,
    "standby": 1,
    "on": 2,
}
_AUTO_STANDBY_VALUE_TO_OPTION: dict[int, str] = {v: k for k, v in _AUTO_STANDBY_OPTIONS.items()}

# workModel: operating mode
_WORK_MODE_OPTIONS: dict[int, str] = {
    2: "Eigenverbrauch",
    4: "Benutzerdefiniert",
    7: "Tarifmodus",
    8: "KI-Modus",
}
_WORK_MODE_OPTION_TO_VALUE: dict[str, int] = {v: k for k, v in _WORK_MODE_OPTIONS.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Jackery select entities."""
    coordinator: JackeryDataCoordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    if coordinator is None:
        _LOGGER.warning("Coordinator not ready for selects")
        return

    async_add_entities([
        JackeryAutoStandbySelect(coordinator=coordinator, config_entry_id=config_entry.entry_id),
        JackeryWorkModeSelect(coordinator=coordinator, config_entry_id=config_entry.entry_id),
    ])


class JackeryAutoStandbySelect(SelectEntity):
    """Auto Standby mode selector (autoStandby field, cmd=5)."""

    def __init__(self, coordinator: JackeryDataCoordinator, config_entry_id: str) -> None:
        self._coordinator = coordinator
        self._config_entry_id = config_entry_id
        self._attr_name = "Auto Standby Mode"
        self._attr_icon = "mdi:power-sleep"
        self._attr_options = list(_AUTO_STANDBY_OPTIONS.keys())
        self._attr_has_entity_name = True
        self._attr_unique_id = f"jackery_{config_entry_id}_auto_standby_select"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, config_entry_id)},
            "name": "Jackery",
            "manufacturer": "Jackery",
            "model": "Energy Monitor",
        }

    @property
    def should_poll(self) -> bool:
        return False

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._coordinator.register_sensor("main_select_autoStandby", self)

    async def async_will_remove_from_hass(self) -> None:
        self._coordinator.unregister_sensor("main_select_autoStandby")
        await super().async_will_remove_from_hass()

    def _update_from_coordinator(self, data: dict) -> None:
        val = data.get("autoStandby")
        if val is None:
            return
        try:
            option = _AUTO_STANDBY_VALUE_TO_OPTION.get(int(val))
            if option is not None:
                self._attr_current_option = option
                self._attr_available = True
                self.async_write_ha_state()
        except (TypeError, ValueError):
            pass

    async def async_select_option(self, option: str) -> None:
        value = _AUTO_STANDBY_OPTIONS.get(option)
        if value is None:
            return
        await self._coordinator.async_control_main_device({"autoStandby": value})


class JackeryWorkModeSelect(SelectEntity):
    """Operating mode selector (workModel field, cmd=5).

    Type-106 reports this as `workModel`; the coordinator aliases it to `workMode`.
    Writes use `workModel` as the device field name.
    """

    def __init__(self, coordinator: JackeryDataCoordinator, config_entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_name = "Work Mode"
        self._attr_icon = "mdi:cog-outline"
        self._attr_options = list(_WORK_MODE_OPTIONS.values())
        self._attr_has_entity_name = True
        self._attr_unique_id = f"jackery_{config_entry_id}_work_mode_select"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, config_entry_id)},
            "name": "Jackery",
            "manufacturer": "Jackery",
            "model": "Energy Monitor",
        }

    @property
    def should_poll(self) -> bool:
        return False

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._coordinator.register_sensor("main_select_workModel", self)

    async def async_will_remove_from_hass(self) -> None:
        self._coordinator.unregister_sensor("main_select_workModel")
        await super().async_will_remove_from_hass()

    def _update_from_coordinator(self, data: dict) -> None:
        val = data.get("workMode")
        if val is None:
            return
        try:
            option = _WORK_MODE_OPTIONS.get(int(val))
            if option is not None:
                self._attr_current_option = option
                self._attr_available = True
                self.async_write_ha_state()
        except (TypeError, ValueError):
            pass

    async def async_select_option(self, option: str) -> None:
        value = _WORK_MODE_OPTION_TO_VALUE.get(option)
        if value is None:
            return
        # Optimistic: update UI and coordinator cache immediately so periodic
        # _distribute_data calls don't revert the state before type-106 confirms.
        self._attr_current_option = option
        self.async_write_ha_state()
        self._coordinator._data_cache["workMode"] = value
        self._coordinator._data_cache["workModel"] = value
        await self._coordinator.async_control_main_device({"workModel": value})
