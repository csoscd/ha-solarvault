"""Jackery Number Platform."""
import logging
from typing import TYPE_CHECKING

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DOMAIN

if TYPE_CHECKING:
    from .sensor import JackeryDataCoordinator

_LOGGER = logging.getLogger(__name__)


NUMBERS = {
    "socChgLimit": {
        "translation_key": "soc_charge_limit",
        "min": 50, "max": 100, "step": 1,
        "min_key": "minSocChg", "max_key": "maxSocChg",
        "unit": PERCENTAGE,
    },
    "socDischgLimit": {
        "translation_key": "soc_discharge_limit",
        "min": 5, "max": 49, "step": 1,
        "min_key": "minSocDischg", "max_key": "maxSocDischg",
        "unit": PERCENTAGE,
    },
    # maxOutPw moved to select.py (only 800 W / 2500 W are valid app values)
    # socForceChg: confirmed writable via MQTT (cmd=5), device acknowledges with cmd=107.
    # Exact purpose not fully determined: Storm Warning uses cloud, not this field.
    # Hypothesis: manual force-charge to a target SOC, or backup-reserve threshold.
    # Set to 0 to deactivate.
    "socForceChg": {
        "translation_key": "soc_force_charge",
        "min": 0, "max": 100, "step": 1,
        "unit": PERCENTAGE,
    },
    # defaultPw: fallback output power for Benutzerdefiniert mode (workModel=4).
    # Active when no time-based schedule entry is in effect.
    # App caps at 200 W with 10 W steps. Schedule slots (cloud-only) can reach 800 W.
    "defaultPw": {
        "translation_key": "default_output_power",
        "min": 0, "max": 200, "step": 10,
        "unit": UnitOfPower.WATT, "optimistic": True,
    },
    # maxFeedGrid: public grid export cap — limits how much power the SolarVault
    # may export to the PUBLIC electricity grid (not the house AC bus).
    # App "Einspeiseleistungsgrenze", 0–2500 W in 10 W steps.
    # Confirmed writable via cmd=5 (device acks with cmd=107).
    # Distinct from maxOutPw (house AC bus limit, 800/2500 W select).
    # Effect only visible when the device is actually exporting to the public grid;
    # in Eigenverbrauch mode with near-zero net export the limit appears inactive.
    "maxFeedGrid": {
        "translation_key": "max_feed_grid_power",
        "min": 0, "max": 2500, "step": 10,
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
                min_value=float(cfg["min"]),
                max_value=float(cfg["max"]),
                step=float(cfg["step"]),
                coordinator=coordinator,
                config_entry_id=config_entry.entry_id,
                translation_key=str(cfg["translation_key"]) if cfg.get("translation_key") else None,
                unit=str(cfg["unit"]) if cfg.get("unit") else None,
                optimistic=bool(cfg.get("optimistic", False)),
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
        self._attr_available: bool = False
        self._attr_native_value: float | None = None
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
        cfg = NUMBERS.get(self._key, {})
        changed = False

        min_key = cfg.get("min_key")
        if min_key and min_key in data:
            new_min = float(data[min_key])
            if new_min != self._attr_native_min_value:
                self._attr_native_min_value = new_min
                changed = True

        max_key = cfg.get("max_key")
        if max_key and max_key in data:
            new_max = float(data[max_key])
            if new_max != self._attr_native_max_value:
                self._attr_native_max_value = new_max
                changed = True

        if self._key in data:
            val = data.get(self._key)
            if val is not None:
                try:
                    new_val = float(val)
                    if not self._attr_available or new_val != self._attr_native_value:
                        self._attr_native_value = new_val
                        self._attr_available = True
                        changed = True
                except (TypeError, ValueError):
                    pass

        if changed:
            self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        if self._optimistic:
            self._attr_native_value = value
            self.async_write_ha_state()
            self._coordinator._data_cache[self._key] = int(value)
        await self._coordinator.async_control_main_device({self._key: int(value)})
