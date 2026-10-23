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


def _repair_subdevice_unique_id(
    ent_reg: er.EntityRegistry,
    entity_entry: er.RegistryEntry,
    uid_owner: dict[str, er.RegistryEntry],
    new_prefix: str,
) -> None:
    """Restore the canonical unique_id of a sub-device entity.

    A buggy earlier run of the v2.x migration rewrote the unique_id of sub-device
    entities from the canonical jackery_{subtype}_{sn}_{key} to the main-device
    format jackery_{device_sn}_{subtype}_{sn}_{key}. The integration then no longer
    matched the entity and created a second one with a "_2" suffix, while the
    original stayed "unavailable" forever.

    If the canonical unique_id is already held by a second entity (the "_2"
    duplicate), the OLDER entity wins - it keeps the plain entity_id without the
    ugly "_2" suffix - and the newer duplicate is removed.

    See issue #25 for the full analysis.
    """
    uid = entity_entry.unique_id
    if not uid.startswith(new_prefix):
        # Already canonical (jackery_{subtype}_{sn}_{key}) or unknown format.
        return

    canonical = f"jackery_{uid[len(new_prefix) :]}"
    holder = uid_owner.get(canonical)
    if holder is not None and holder.entity_id != entity_entry.entity_id:
        # Which entry keeps the canonical unique_id? The OLDER one: the buggy
        # migration rewrote the original entity's unique_id first and created the
        # duplicate afterwards, so the older entry is the original and keeps the
        # plain entity_id (without the "_2" suffix). Tie-break for entities created
        # within the same clock tick: the shorter entity_id wins.
        holder_wins = (holder.created_at, len(holder.entity_id)) < (
            entity_entry.created_at,
            len(entity_entry.entity_id),
        )
        if not holder_wins:
            # The holder is the NEWER entry (the duplicate the bug created) ->
            # remove it, this (older) entity takes the canonical unique_id and
            # keeps its plain entity_id without the "_2" suffix.
            _LOGGER.info(
                "Removing duplicate sub-device entity: %s (%s) - canonical unique_id %s goes to the older entity",
                holder.unique_id,
                holder.entity_id,
                canonical,
            )
            try:
                ent_reg.async_remove(holder.entity_id)
            except KeyError:
                pass
        else:
            _LOGGER.info(
                "Removing broken sub-device entity: %s (%s) - canonical unique_id %s is held by the older entity",
                uid,
                entity_entry.entity_id,
                canonical,
            )
            try:
                ent_reg.async_remove(entity_entry.entity_id)
            except KeyError:
                pass
            return

    _LOGGER.info(
        "Repairing sub-device unique_id: %s -> %s (%s)",
        uid,
        canonical,
        entity_entry.entity_id,
    )
    try:
        ent_reg.async_update_entity(entity_entry.entity_id, new_unique_id=canonical)
    except ValueError as err:
        _LOGGER.warning("Could not repair unique_id of %s: %s", entity_entry.entity_id, err)
        return
    uid_owner[canonical] = entity_entry


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
    uid_owner: dict[str, er.RegistryEntry] = {e.unique_id: e for e in all_entries if e.unique_id}

    # Sub-device entities (SmartMeter, expansion battery, plug, CT) live on their own
    # device in the device registry (identifiers: (jackery, sub_{sn})). They are
    # detected here via that device instead of via the unique_id string, because the
    # sub-device SN is NOT always uppercase: the SmartMeter HTO907A reports it in
    # lowercase ("ac1518779cb4"). The former isupper() check therefore misclassified
    # the SmartMeter entities as main-device sensors and rewrote their unique_id to
    # jackery_{device_sn}_smartmeter_{sn}_{key}. The integration no longer matched
    # them afterwards and created a second set of entities with a "_2" suffix, while
    # the originals stayed "unavailable" forever. See issue #25.
    device_reg = dr.async_get(hass)
    subdevice_device_ids: set[str] = {
        device.id
        for device in device_reg.devices.values()
        for domain, identifier in device.identifiers
        if domain == DOMAIN and identifier.startswith("sub_")
    }

    for entity_entry in all_entries:
        uid = entity_entry.unique_id
        if not uid or not uid.startswith("jackery_"):
            continue

        # Sub-device entity -> repair its unique_id (see _repair_subdevice_unique_id)
        if entity_entry.device_id and entity_entry.device_id in subdevice_device_ids:
            _repair_subdevice_unique_id(ent_reg, entity_entry, uid_owner, new_prefix)
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

        # NOTE: sub-device entities are already handled above via the device registry.
        # The string-based check below is only a fallback for legacy entities without
        # a device assignment.
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
