# Changelog

All notable changes to this project will be documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [2.0.0] – 2026-07-23

### Added

- **Multi-instance support**: Multiple Jackery devices can now be integrated simultaneously.
  Each config entry is identified by its device serial number. Existing single-device
  installations are migrated automatically on first startup — entity IDs and HA history
  are preserved via `_migrate_unique_ids()` (entity registry) and device registry migration.

- **Re-authentication flow**: If the device reports a token mismatch (MQTT type-123 /
  errorCode 401), Home Assistant now shows a persistent notification prompting the user to
  re-enter the token. Implemented via `async_step_reauth` / `async_step_reauth_confirm` in
  the config flow and `_trigger_reauth()` in the coordinator.

- **Device card: model and firmware version**: The HA device card now shows the device model
  (`DIY3` for SolarVault 3 Pro Max) and the firmware version, extracted from incoming MQTT
  messages via `_capture_device_meta()` / `_update_device_registry()`.

- **Human-readable ENUM status sensors**: `Device Status`, `OnGrid Status`, `CT Status`, and
  `Grid Meter Link` now use `SensorDeviceClass.ENUM` with translated labels (EN / DE / FR)
  instead of raw integers. Mapped via `DEVICE_STATUS_MAP`, `ONGRID_STATUS_MAP`,
  `CT_STATUS_MAP`, `GRID_METER_LINK_MAP`.

- **New sensor – Max Feed Grid Power** (`maxFeedGrid`, type-106): exposes the device-side
  feed-in limit for diagnostics. May differ from the writable `maxOutPw` setting.

- **Smart Plug commMode guard**: MQTT switch commands to smart plugs are now blocked when the
  plug is in cloud-relay mode (`commMode=2`). HA shows a persistent notification explaining
  the issue; `HomeAssistantError` is raised so automations can handle it. `async_toggle()` is
  also guarded. `extra_state_attributes` now includes `commMode`, `commMode_label`,
  `mqtt_controllable`, and `mqtt_control_block_reason`.

- **Initial poll before first sleep**: The coordinator now sends a type-25 poll 2 s after
  startup, making sensor data available faster after HA start or integration reload.

- **`_subdevice_sn()` helper**: Replaces inline `.get("deviceSn") or .get("sn")` calls
  throughout the coordinator.

### Fixed

- **`JackeryAutoStandbySelect` missing optimistic cache update**: Writing a new value via the
  Auto Standby select reverted to the old value on the next MQTT event (~10 s). Fixed by
  patching `coordinator._data_cache` after the write, consistent with the v1.3.1 pattern
  already applied to WorkMode and MaxFeedIn selects.

### Changed

- **Entry title**: Config entries are now titled `"Jackery {device_sn}"` instead of
  `"Jackery"`, making multiple instances distinguishable in the HA UI.

- **Unique ID format**: All entity unique IDs now include the device SN
  (`jackery_{sn}_{entity}` instead of `jackery_{entity}`). Migration runs automatically.

---

## [1.3.9] – 2026-07-17

### Fixed

- **Expansion battery sensors deleted every ~60 s (root cause fix)**: The sub-device deletion
  timer (step 1/2 in `_check_for_new_plugs`) checked whether each known SN was present in the
  current type-101 message. Expansion batteries appear exclusively in type-23 messages (~10 min
  cadence), never in type-101. So every incoming type-101 started the 60 s deletion countdown
  for the battery SN. After ~60 s, `entity.async_remove(force_remove=True)` was called — the
  entity disappeared from HA entirely ("Sensor nicht verfügbar"). The next type-23 recreated it,
  the next type-101 started the timer again — creating a continuous create/delete cycle.

  Fix: expansion battery SNs (tracked in `_expansion_battery_sns`) are now explicitly excluded
  from both the deletion-timer start (step 1) and the deletion execution (step 2).

  Note: v1.3.8 fixed a separate but related issue (null-value cache corruption) and is still
  included. This release contains both fixes.

---

## [1.3.8] – 2026-07-17

### Fixed

- **Expansion battery sensors showing "null kWh" in HA history charts**: Two-part fix:
  1. **Null-value filter in type-23 cache**: Devices occasionally send `null` for `inEgy`/`outEgy`
     fields (e.g. during a restart or transient error). Previously these overwrote real cached
     values with `None`. `_update_from_coordinator` already guarded against writing `None` to
     `_attr_native_value`, but the corrupted cache meant the entity showed its value correctly
     until HA re-evaluated the state. The type-23 handler now only updates cached fields that
     have non-`null` values, preserving previously received real data.
  2. **Pre-initialization of entity values on creation**: When an expansion battery entity is
     created for the first time (on discovery via type-23), it now reads the current cache and
     pre-sets `_attr_native_value` before being added to HA. Previously, the entity started with
     `_attr_native_value = None` (HA state: "unknown") and only got its value on the next MQTT
     update cycle — briefly showing "null kWh" in charts. If no real cached value is available
     at creation time, the entity starts as "unavailable" (chart gap) rather than "unknown"
     (null data point).

---

## [1.3.7] – 2026-07-17

### Changed
- **Max Feed-in Power converted from number to select**: `maxOutPw` is now a dropdown
  restricted to the two values the Jackery app allows — **800 W** and **2500 W**. The previous
  free-range slider (0–10000 W) accepted arbitrary values the device does not support.
  Translations updated for DE, EN and FR.

### Fixed
- **Expansion battery sensors flapping unavailable**: After the v1.3.6 fix, sensors still went
  unavailable ~15 min after each type-23 message (900 s timeout). Since expansion batteries
  report cumulative energy only every ~10 min, the timeout was too aggressive. Once a battery
  has reported data for the first time, its sensors now stay available indefinitely (until
  integration restart), matching the nature of slowly-changing cumulative energy values.

### Added
- **French translation** (`fr.json`) contributed by pyrots — merci!

---

## [1.3.6] – 2026-07-17

### Fixed
- **Expansion battery sensors permanently unavailable after ~60 s**: Energy data for BP2500 units
  arrives via type-23 messages (~every 10 min), but the offline detection marked sub-devices
  unavailable after 60 s without a type-101 update. Two-part fix:
  1. `_subdevice_last_seen[sn]` is now updated in the type-23 handler whenever an expansion
     battery reports data.
  2. Offline timeout for expansion battery SNs raised from 60 s to 900 s (15 min), matching
     the ~10 min type-23 cadence with a safety margin.

---

## [1.3.5] – 2026-07-17

### Fixed
- **`commMode` sensor showed "Cloud (Relay)" even when SmartMeter was in LAN mode**: The MQTT
  field `commMode` is 1-based (1=LAN, 2=Cloud), but the ENUM options list was 0-indexed, so
  `commMode=1` mapped to `options[1]` = `"cloud"` instead of `options[0]` = `"lan"`. Fixed by
  adding `options_offset: 1` to the sensor config; the update handler now subtracts the offset
  before indexing. `commState` is unaffected (0-based, offset=0).

---

## [1.3.4] – 2026-07-17

### Added
- **Complete sensor translations** (EN + DE) for all 95 sensor entities via HA translation system:
  - 70 main device sensors (battery, solar, grid, EPS, energy flow, diagnostics, type-106 fields)
  - 25 sub-device sensors (SmartMeter 3P phases/energy, CT, plug, expansion battery)
  - `JackerySensor` and `JackerySubDeviceSensor` now use `_attr_translation_key` instead of hardcoded `_attr_name`
- **`commMode` / `commState` as ENUM sensors** with human-readable state labels:
  - `commMode`: `1` → "LAN", `2` → "Cloud (Relay)" (with DE/EN translations)
  - `commState`: `0` → "Offline", `1` → "Online" (with DE/EN translations)

### Fixed
- **Integer status sensors showed float values** (e.g. `1.0` instead of `1`): All sensors without
  unit and without scale factor now store integer values. Affected: Battery Count, Battery State,
  Device Status, OnGrid Status, CT Status, Grid Meter Link, EPS State, EPS Switch Status,
  Ethernet Connected, and all other unitless numeric fields.

### Notes
- After updating via HACS, an **HA restart** is required (not just integration reload) for all
  new translation files to be loaded. A browser hard-refresh (Ctrl+Shift+R) may additionally
  be needed if cached translations show in the wrong language.
- Total translated entities: 107 (70 main sensors + 25 sub-device sensors + 12 control entities)

---

## [1.3.3] – 2026-07-17

### Added
- **Internationalization (i18n)** for all control entities via HA translation system:
  - `translations/de.json` — German
  - `translations/en.json` — English
  - `strings.json` updated to English base (was Chinese from original integration)
  - Config flow UI now available in English and German
- Entities translated: Work Mode select, Auto Standby select, all 5 numbers, all 4 switches, reboot button

### Changed
- **Work Mode select option keys** changed from German strings (`"Eigenverbrauch"`, …) to neutral translation keys (`"self_consumption"`, `"custom"`, `"tariff"`, `"ai"`). HA displays them in the user's language via translations. **Breaking:** automations referencing the old German option values need to be updated to the new keys.

---

## [1.3.2] – 2026-07-17

### Changed
- **Type-105 poll interval reduced from 5 min to 30 s** (3 cycles × 10 s). App-initiated mode changes (via Jackery cloud) now appear in HA within ~30 s instead of up to 5 min. Additional traffic: ~75 KB/h — negligible for homelab use.

---

## [1.3.1] – 2026-07-17

### Fixed
- **Optimistic state updates reverting after ~10 s**: After writing a new value via the Work Mode select, Off-Grid Fallback switch, Follow Meter Power switch, or Default Output Power number, the coordinator's `_data_cache` still held the old value. Every incoming type-2 message (~10 s) triggered `_distribute_data`, which pushed the stale cached value back to the entity — reverting the optimistic UI state before the next type-106 poll (~5 min) could confirm the write. Fix: `_data_cache` is now updated alongside the optimistic UI state on every write.

---

## [1.3.0] – 2026-07-17

### Added
- **Work Mode select** (`workModel`): dropdown to switch between Eigenverbrauch (2), Benutzerdefiniert (4), Tarifmodus (7), KI-Modus (8). State populated from type-106 poll. Writes use `workModel` field via type-1/cmd=5. Replaces the former read-only `work_mode` sensor.
- **Default Output Power number** (`defaultPw`): slider 0–200 W, 10 W steps. Fallback power for Benutzerdefiniert mode when no schedule entry is active. Optimistic updates (state reflects write immediately). App limit: 200 W; schedule slots (cloud-only) can reach 800 W.
- **Off-Grid Fallback switch** (`offGridDown`): enables off-grid fallback mode. Optimistic updates.
- **Follow Meter Power switch** (`isFollowMeterPw`, "Zähler folgen"): sub-mode within Benutzerdefiniert (workModel=4). When on, the SolarVault tracks the SmartMeter to achieve net-zero grid exchange. Entity becomes **unavailable** automatically when Work Mode ≠ Benutzerdefiniert.

### Changed
- `maxOutPw` number renamed from "Max Output Power (OnGrid)" to "Max Feed-in Power (OnGrid)" — confirmed as Einspeiseleistung (grid feed-in power limit), not EPS socket output.
- `off_grid_time` sensor unit fixed from raw string `"s"` to `UnitOfTime.SECONDS`.

### Removed
- Read-only `work_mode` sensor (`workMode`) → replaced by Work Mode select.
- Read-only `is_follow_meter_power` sensor (`isFollowMeterPw`) → replaced by Follow Meter Power switch.
- Read-only `off_grid_fallback` sensor (`offGridDown`) → replaced by Off-Grid Fallback switch.
- `autoStandby` number entity (slider 0–2) → removed; the Auto Standby Mode select (added in v1.2.0) already covers this field. Users with automations referencing `number.jackery_main_autostandby` should migrate to `select.jackery_*_auto_standby_select`.

### Notes
- `workModel` writability confirmed independently by community member pyrots ([issue #5](https://github.com/Jackery-Official/jackery/issues/5)).
- `offGridTime` is NOT writable via cmd=5 (no cmd=107 ack received in testing); remains read-only sensor.
- Time-based schedules (Benutzerdefiniert, Tarifmodus) and KI-Modus strategy selection are cloud-only — not accessible via local MQTT.

---

## [1.2.1] – 2026-07-15

### Added
- **Type-105 poll** every 5 minutes (30 cycles × 10 s); fires immediately on first startup cycle.
  The SolarVault responds with a **type-106 full system state** message.
- **Type-106 message handler**: merges the response body into the data cache.
  `workModel` (type-106 alias) is automatically normalized to `workMode`.
- **13 new sensors** from type-106 data — all appear automatically once reported:
  - `Home Load Power (Estimated)` (`otherLoadPw`) — house consumption as seen by the SolarVault
  - `Grid AC Input Power` (`gridInPw`) / `Grid AC Output Power` (`gridOutPw`) — alternative to `inOngridPw`/`outOngridPw`
  - `Grid Side Input Power` (`inGridSidePw`) / `Grid Side Output Power` (`outGridSidePw`)
  - `Energy Plan Power` (`energyPlanPw`) — planned output target
  - `Standby Power Threshold` (`standbyPw`)
  - `PV Max Charge Power` (`pvMaxChgPower`)
  - `Max System Output Power` (`maxSysOutPw`) / `Max System Input Power` (`maxSysInPw`)
  - `Follow Meter Power` (`isFollowMeterPw`)
  - `Off-Grid Fallback` (`offGridDown`) / `Off-Grid Switch Time` (`offGridTime`)

### Notes
- Confirmed via live MQTT capture: our SolarVault does **not** send types 102/106/107 spontaneously.
  Type 106 is only delivered as a response to a type-105 poll.
  Types 102 and 107 were not observed at all — likely require newer firmware or different hardware.

---

## [1.2.0] – 2026-07-15

### Added
- **Reboot button** – new `button` entity sends a restart command (type=1, cmd=5, reboot=1) to the
  SolarVault directly from Home Assistant. Useful to restore SmartMeter LAN mode without touching
  the device or app.
- **Auto Standby Mode select** – `autoStandby` is now exposed as a `select` entity with human-readable
  options (invalid / standby / on) instead of a raw numeric sensor.
- **5 new device status sensors**: `Device Status` (stat), `Work Mode` (workMode),
  `OnGrid Status` (ongridStat), `CT Status` (ctStat), `Grid Meter Link` (gridSate).
  These fields are sent in type-2 / type-106 / type-107 messages; sensors appear automatically
  once the device reports the field at least once.
- **Sub-device offline detection** – each CT/plug is now marked `unavailable` in HA if it has not
  reported data for 60 seconds, instead of holding the last known value indefinitely.
- **devType=4 (Meter Collector) support** – classified as CT rather than plug; sensor group
  follows the same `ct` path as devType=2.

### Changed
- Sub-device cache now uses **SN-based merging** (`_merge_subdevice_list`): partial updates
  preserve fields not present in the current message, rather than replacing the entire list.
  Adopted from upstream v2.0-beta.
- `CT_DEV_TYPES = frozenset({2, 3, 4})` replaces inline `devType` checks throughout the
  discovery and sensor-creation path.

---

## [1.1.70] – 2026-07-15

### Fixed
- `jackery_home_power` was calculated as a negative value during phase-balanced feed-in.
  When the SmartMeter operates in combined-phase mode, `outOngridPw` (total SolarVault AC
  output) is much larger than `tnPhasePw` (net to public grid). A special-case branch used
  `grid_sell − ongrid_supply` (inverted sign) and overrode the correct base formula
  `p_grid − p_ong`. The branch has been removed; the base formula handles all scenarios correctly.
  Example: 301 W AC output, 29 W net to grid → home load now correctly shows 272 W instead of −272 W.

### Tests
- Added regression test `test_home_power_phase_balanced_feed_in` covering the above scenario.
- Fixed `test_home_power_ct_feed_in_with_ongrid_supply` to use a physically realistic scenario.

---

## [1.1.69] – 2026-07-15

### Added
- **6 new diagnostic sensors** to aid troubleshooting:
  - SolarVault: `WiFi SSID` (`wname`), `Ethernet IP` (`eip`), `Device Capability` (`ability`)
  - SmartMeter 3P: `Communication Mode` (`commMode`), `Communication State` (`commState`), `IP Address` (`wip`)
- `commMode` sensor makes the LAN→Cloud switch immediately visible in HA history.
- String sensor support in `ct_3phase` update path (previously string values were silently discarded).

### Documentation
- Added Troubleshooting section to README documenting the SmartMeter `commMode` LAN→Cloud issue:
  internet outages can cause the SmartMeter to switch to Cloud mode, stopping MQTT measurement data.
  A SolarVault restart (via app or on the device) restores LAN mode.

---

## [1.1.68] – 2026-07-15

### Added
- Automated test suite (49 tests) covering `_calculate_energy_flow`, MQTT message routing,
  and sensor value transforms. No real MQTT broker or HA installation required.
- CI workflow (`.github/workflows/validate.yml`) runs tests on every push.

### Fixed
- `gridSellPw=0` (no export) was treated as falsy by `or`, causing the
  `gridBuyPw`/`gridSellPw` fallback path to leave `grid_available=False` even when both
  fields were present. Fixed with explicit `is not None` checks.

---

## [1.1.67] – 2026-07-14

### Added
- `SOC Force Charge Target` (`socForceChg`) as a writable `number` entity (range 0–100 %).
  Confirmed writable via MQTT (cmd=5, device acks with cmd=107). Exact purpose undetermined —
  documented uncertainty in README and code.

---

## [1.1.66] – 2026-07-14

### Added
- 3 new sensors confirmed via live MQTT capture after firmware update:
  - `SOC Force Charge Target` (`socForceChg`) — read-only sensor (writable entity added in 1.1.67)
  - `CT Import Energy` (`inCtEgy`) — cumulative system-level CT import energy
  - `CT Export Energy` (`outCtEgy`) — cumulative system-level CT export energy

---

## [1.1.65] – 2026-07-10

### Fixed
- **CT/SmartMeter sub-device flapping (issue #16):** A `devType=6` (plug) poll response
  overwrote the CT cache with an empty list, causing the SmartMeter to appear as missing every
  ~11 s. Fixed by only updating the relevant cache section (CT or plug) when the payload
  contains the corresponding keys (`has_ct_payload` / `has_plug_payload`).

### Added
- **BP2500 expansion battery energy sensors** — the BP2500 appears in type-23 energy statistics
  messages (~every 10 min). Two sensors are created automatically when detected:
  `Charge Energy` (`inEgy`) and `Discharge Energy` (`outEgy`), both in kWh (scale × 0.01).

---

## [1.1.64] – 2026-07-10

### Added
- 8 CT energy sensors for SmartMeter 3P from type-23 messages:
  `tPhaseEgy`, `tnPhaseEgy`, per-phase import/export energy (L1–L3).
- Missing `AC to Grid Energy` sensor (`acOtOngridEgy`).

### Fixed
- Scale factor for `ct_3phase` energy sensors corrected to × 0.01 (→ kWh).

---

## [1.1.63] – 2026-07-10

### Added (initial fork release)
- Fork of [Jackery-Official/jackery](https://github.com/Jackery-Official/jackery) with fixes
  and new sensors for the **Jackery SolarVault 3 Pro Max**.
- New sensors from live MQTT data: `stackInPw`, `stackOutPw`, `soc` (BMS SOC), `batState`,
  `ethPort`, `wsig`, `maxInvStdPw`, `maxGridStdPw`.

### Fixed
- **SmartMeter 3P (HTO907A, devType=3, subType=5) misclassified as plug (issue #18):**
  The original integration routed `devType=3` to the plug handler, causing the energy flow
  calculation to receive no CT data. Fixed by adding a dedicated `ct_3phase` sensor group
  with 8 sensors (L1/L2/L3 import + export + totals).
