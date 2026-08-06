"""Energy Monitor MQTT Integration for Home Assistant."""
import logging

from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

_LOGGER = logging.getLogger(__name__)

DOMAIN = "jackery"
PLATFORMS = [Platform.SENSOR, Platform.SWITCH, Platform.NUMBER, Platform.BUTTON, Platform.SELECT]


async def _migrate_unique_ids(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Migrate entity unique IDs from v1.x single-instance format to v2.0 multi-instance format.

    Old main-sensor format:    jackery_{sensor_id}
    New main-sensor format:    jackery_{device_sn}_{sensor_id}

    Old switch/number format:  jackery_main_{mqtt_key}
    New switch format:         jackery_{device_sn}_switch_{mqtt_key}
    New number format:         jackery_{device_sn}_number_{mqtt_key}

    Old control-entity format: jackery_{config_entry_id}_{x}
    New control-entity format: jackery_{device_sn}_{x}

    Sub-device sensors (SmartMeter, expansion battery, plug) already contain the
    sub-device SN (uppercase) and are left as-is.

    v2.0.1 bug residue: entities with unique_id jackery_{device_sn}_main_{key} were
    created by the buggy v2.0.1 migration — they are removed here.
    """
    device_sn = entry.data.get("device_sn", "").strip()
    if not device_sn:
        return

    entry_id = entry.entry_id
    new_prefix = f"jackery_{device_sn}_"

    ent_reg = er.async_get(hass)
    all_entries = list(er.async_entries_for_config_entry(ent_reg, entry_id))
    existing_uids: set[str] = {e.unique_id for e in all_entries if e.unique_id}

    for entity_entry in all_entries:
        uid = entity_entry.unique_id
        if not uid or not uid.startswith("jackery_"):
            continue

        if uid.startswith(new_prefix):
            suffix_after_sn = uid[len(new_prefix):]
            # Remove wrongly-migrated jackery_{sn}_main_* entities from v2.0.1 bug 2
            if suffix_after_sn.startswith("main_"):
                _LOGGER.info(
                    "Removing v2.0.1 wrongly-migrated entity: %s (%s)",
                    uid, entity_entry.entity_id,
                )
                ent_reg.async_remove(entity_entry.entity_id)
            # Remove obsolete select entity replaced by number slider in v2.3.2
            elif suffix_after_sn == "max_feed_in_select":
                _LOGGER.info(
                    "Removing obsolete select entity (replaced by number slider): %s (%s)",
                    uid, entity_entry.entity_id,
                )
                ent_reg.async_remove(entity_entry.entity_id)
            continue

        suffix = uid[len("jackery_"):]

        # Sub-device sensors: identified by uppercase SN after device-name prefix.
        # v1.3.9 format: jackery_SmartMeter_{SN}_{key}, jackery_Battery_{SN}_{key}
        # The character after the prefix is uppercase for sub-device SNs.
        is_subdevice = False
        for sub_prefix in ("smartmeter_", "battery_", "plug_", "ct_"):
            if suffix.startswith(sub_prefix):
                rest = suffix[len(sub_prefix):]
                if rest and rest[0].isupper():
                    is_subdevice = True
                    break
        if is_subdevice:
            continue

        # Determine target unique_id
        if suffix.startswith(f"{entry_id}_"):
            # Control entities: jackery_{entry_id}_{x} → jackery_{device_sn}_{x}
            new_suffix = suffix[len(f"{entry_id}_"):]
            target_uid = f"{new_prefix}{new_suffix}"
        elif suffix.startswith("main_"):
            # Switches/numbers: use entity_id platform prefix to pick correct target
            mqtt_key = suffix[len("main_"):]
            if entity_entry.entity_id.startswith("switch."):
                target_uid = f"{new_prefix}switch_{mqtt_key}"
            elif entity_entry.entity_id.startswith("number."):
                target_uid = f"{new_prefix}number_{mqtt_key}"
            else:
                target_uid = f"{new_prefix}{suffix}"
        else:
            # Main sensors: jackery_{sensor_id} → jackery_{device_sn}_{sensor_id}
            target_uid = f"{new_prefix}{suffix}"

        if target_uid in existing_uids:
            # Target already exists (created fresh by v2.0.1) — delete old orphan to
            # eliminate duplicate "unavailable" entities in the UI.
            _LOGGER.info(
                "Removing orphaned entity: %s (%s) — target %s already present",
                uid, entity_entry.entity_id, target_uid,
            )
            ent_reg.async_remove(entity_entry.entity_id)
        else:
            _LOGGER.info("Migrating unique_id: %s → %s", uid, target_uid)
            ent_reg.async_update_entity(entity_entry.entity_id, new_unique_id=target_uid)
            existing_uids.discard(uid)
            existing_uids.add(target_uid)

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
