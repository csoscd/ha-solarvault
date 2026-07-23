"""Jackery Number Platform."""
import logging
from typing import Any, TYPE_CHECKING

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DOMAIN

if TYPE_CHECKING:
    from .sensor import JackeryDataCoordinator

_LOGGER = logging.getLogger(__name__)


NUMBERS = {
    "socChgLimit": {
        "translation_key": "soc_charge_limit",
        "min": 0, "max": 100, "step": 1,
    },
    "socDischgLimit": {
        "translation_key": "soc_discharge_limit",
        "min": 0, "max": 100, "step": 1,
    },
    # maxOutPw moved to select.py (only 800 W / 2500 W are valid app values)
    # socForceChg: confirmed writable via MQTT (cmd=5), device acknowledges with cmd=107.
    # Exact purpose not fully determined: Storm Warning uses cloud, not this field.
    # Hypothesis: manual force-charge to a target SOC, or backup-reserve threshold.
    # Set to 0 to deactivate.
    "socForceChg": {
        "translation_key": "soc_force_charge",
        "min": 0, "max": 100, "step": 1,
    },
    # defaultPw: fallback output power for Benutzerdefiniert mode (workModel=4).
    # Active when no time-based schedule entry is in effect.
    # App caps at 200 W with 10 W steps. Schedule slots (cloud-only) can reach 800 W.
    "defaultPw": {
        "translation_key": "default_output_power",
        "min": 0, "max": 200, "step": 10,
        "unit": UnitOfPower.WATT, "optimistic": True,
    },
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Jackery number entities."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    if coordinator is None:
        _LOGGER.warning("Coordinator not ready for numbers")
        return

    entities = []
    for key, cfg in NUMBERS.items():
        entities.append(
            JackeryMainNumber(
                key=key,
                min_value=cfg["min"],
                max_value=cfg["max"],
                step=cfg["step"],
                coordinator=coordinator,
                config_entry_id=config_entry.entry_id,
                translation_key=cfg.get("translation_key"),
                unit=cfg.get("unit"),
                optimistic=cfg.get("optimistic", False),
            )
        )

    if entities:
        async_add_entities(entities)


class JackeryMainNumber(NumberEntity):
    """Main device number (cmd=5)."""

    def __init__(
        self,
        key: str,
        min_value: float,
        max_value: float,
        step: float,
        coordinator: "JackeryDataCoordinator",
        config_entry_id: str,
        translation_key: str | None = None,
        unit: str | None = None,
        optimistic: bool = False,
    ) -> None:
        self._key = key
        self._coordinator = coordinator
        self._optimistic = optimistic
        device_sn = coordinator._device_sn or config_entry_id
        self._attr_unique_id = f"jackery_{device_sn}_number_{key}"
        self._attr_has_entity_name = True
        self._attr_mode = NumberMode.SLIDER
        self._attr_native_min_value = min_value
        self._attr_native_max_value = max_value
        self._attr_native_step = step
        if translation_key:
            self._attr_translation_key = translation_key
        if unit is not None:
            self._attr_native_unit_of_measurement = unit
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
        self._coordinator.register_sensor(f"main_number_{self._key}", self)

    async def async_will_remove_from_hass(self) -> None:
        self._coordinator.unregister_sensor(f"main_number_{self._key}")
        await super().async_will_remove_from_hass()

    def _update_from_coordinator(self, data: dict) -> None:
        if self._key not in data:
            return
        val = data.get(self._key)
        if val is None:
            return
        try:
            self._attr_native_value = float(val)
            self._attr_available = True
            self.async_write_ha_state()
        except (TypeError, ValueError):
            pass

    async def async_set_native_value(self, value: float) -> None:
        if self._optimistic:
            self._attr_native_value = value
            self.async_write_ha_state()
            self._coordinator._data_cache[self._key] = int(value)
        await self._coordinator.async_control_main_device({self._key: int(value)})
