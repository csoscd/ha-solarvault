"""Energy Monitor MQTT Integration for Home Assistant."""
import logging

from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

_LOGGER = logging.getLogger(__name__)

DOMAIN = "jackery"
PLATFORMS = [Platform.SENSOR, Platform.SWITCH, Platform.NUMBER, Platform.BUTTON, Platform.SELECT]


async def _migrate_unique_ids(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Migrate entity unique IDs from v1.x single-instance format to v2.0 multi-instance format.

    Old main-sensor format:   jackery_{sensor_id}
    New main-sensor format:   jackery_{device_sn}_{sensor_id}

    Old control-entity format: jackery_{config_entry_id}_{x}
    New control-entity format: jackery_{device_sn}_{x}

    Sub-device sensors already contain the sub-device SN and are left as-is.
    """
    device_sn = entry.data.get("device_sn", "").strip()
    if not device_sn:
        return

    entry_id = entry.entry_id
    new_prefix = f"jackery_{device_sn}_"

    @callback
    def _migrate(entity_entry: er.RegistryEntry) -> dict | None:
        uid = entity_entry.unique_id
        if not uid or not uid.startswith("jackery_"):
            return None
        # Already in new format
        if uid.startswith(new_prefix):
            return None
        suffix = uid[len("jackery_"):]
        # Sub-device sensors: contain sub-device SN, identified by device_name prefix
        for sub_prefix in ("smartmeter_", "battery_", "plug_", "ct_"):
            if suffix.startswith(sub_prefix):
                return None
        # Control entities: jackery_{config_entry_id}_{x} → jackery_{device_sn}_{x}
        if suffix.startswith(f"{entry_id}_"):
            new_suffix = suffix[len(f"{entry_id}_"):]
            new_uid = f"{new_prefix}{new_suffix}"
        else:
            # Main sensors: jackery_{sensor_id} → jackery_{device_sn}_{sensor_id}
            new_uid = f"{new_prefix}{suffix}"
        _LOGGER.info("Migrating unique_id: %s → %s", uid, new_uid)
        return {"new_unique_id": new_uid}

    await er.async_migrate_entries(hass, entry.entry_id, _migrate)

    # Migrate main device identifier in device registry from config_entry_id to device_sn
    device_reg = dr.async_get(hass)
    old_device = device_reg.async_get_device(identifiers={(DOMAIN, entry_id)})
    if old_device:
        device_reg.async_update_device(
            old_device.id,
            new_identifiers={(DOMAIN, device_sn)},
        )
        _LOGGER.info("Migrated device identifier: %s → %s", entry_id, device_sn)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Jackery from a config entry."""
    _LOGGER.info("Setting up Jackery integration")

    if not await mqtt.async_wait_for_mqtt_client(hass):
        _LOGGER.error(
            "MQTT integration is not available or not configured. "
            "Please set up the MQTT integration first: "
            "Settings -> Devices & Services -> Add Integration -> MQTT"
        )
        return False

    _LOGGER.info("MQTT integration is available and ready")

    # Migrate unique IDs from v1.x single-instance format (runs harmlessly if already migrated)
    await _migrate_unique_ids(hass, entry)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "config": entry.data,
        "coordinator": None,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading Jackery integration")

    entry_data = hass.data[DOMAIN].get(entry.entry_id, {})
    coordinator = entry_data.get("coordinator")
    if coordinator:
        await coordinator.async_stop()
        _LOGGER.info("Coordinator stopped")

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
