"""Jackery Button Platform."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DOMAIN

if TYPE_CHECKING:
    from .sensor import JackeryDataCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Jackery button entities."""
    coordinator: JackeryDataCoordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    if coordinator is None:
        _LOGGER.warning("Coordinator not ready for buttons")
        return

    async_add_entities([
        JackeryRebootButton(coordinator=coordinator, config_entry_id=config_entry.entry_id)
    ])


class JackeryRebootButton(ButtonEntity):
    """Restart the SolarVault main unit (type=1, cmd=5, reboot=1)."""

    def __init__(self, coordinator: JackeryDataCoordinator, config_entry_id: str) -> None:
        self._coordinator = coordinator
        self._attr_name = "Reboot"
        self._attr_icon = "mdi:restart"
        self._attr_device_class = ButtonDeviceClass.RESTART
        self._attr_has_entity_name = True
        self._attr_unique_id = f"jackery_{config_entry_id}_reboot"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, config_entry_id)},
            "name": "Jackery",
            "manufacturer": "Jackery",
            "model": "Energy Monitor",
        }

    async def async_press(self) -> None:
        """Send reboot command to the SolarVault."""
        await self._coordinator.async_control_main_device({"reboot": 1})
        _LOGGER.info("Reboot command sent to SolarVault")
