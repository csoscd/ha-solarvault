# ha-solarvault – Project Documentation

## Overview

Fork of [Jackery-Official/jackery](https://github.com/Jackery-Official/jackery) – a Home Assistant custom integration for Jackery energy storage systems via MQTT.

Tested hardware:
- **Jackery SolarVault 3 Pro Max** (main unit, `deviceType: 3`)
- **Jackery BP2500** (expansion battery, `devType: 1`, `subType: 0` – cumulative energy only via type 23)
- **Jackery SmartMeter 3P / HTO907A** (CT meter, `devType: 3`, `subType: 5`)

---

## MQTT Protocol

### Topic structure

```
hb/device/{DEVICE_SN}/status   ← device → broker (status data)
hb/device/{DEVICE_SN}/event    ← device → broker (sub-device data)
hb/device/{DEVICE_SN}/action   → broker → device (commands/polls)
```

Default topic prefix: `hb`

### Message types

| Type | Direction | Description | Interval |
|------|-----------|-------------|----------|
| 2    | device→HA | Main device status (cmd 106) | ~11 s |
| 23   | device→HA | Energy statistics (cumulative kWh counters) | ~10 min |
| 25   | HA→device | Poll request for device status | ~11 s |
| 100  | HA→device | Poll request for sub-device data | ~11 s |
| 101  | device→HA | Sub-device response (CTs, plugs) | ~11 s |
| 1    | HA→device | Control command (cmd 5) | on demand |
| 103  | HA→device | Sub-device switch control | on demand |
| 105  | HA→device | Poll request for full system state | ~30 s (integration, 3 cycles × 10 s) |
| 106  | device→HA | Full system state response (only on demand) | on demand only |
| 102  | device→HA | Sub-device real-time updates? | **Not observed on this hardware** |
| 107  | device→HA | Incremental soc/workMode update? | **Not observed on this hardware** |

---

## Type 2 – Main Device Status

Full body fields observed on SolarVault 3 Pro Max:

### Battery
| Field | Unit | Description |
|-------|------|-------------|
| `batSoc` | % | Display SOC of main unit |
| `soc` | % | Combined BMS SOC across all battery units (main + expansion) |
| `batInPw` | W | Battery charge power (**main unit only** — does NOT include expansion batteries such as BP2500) |
| `batOutPw` | W | Battery discharge power (**main unit only** — does NOT include expansion batteries such as BP2500) |
| `cellTemp` | 0.1 °C | Cell temperature (divide by 10 for °C) |
| `batNum` | – | Number of expansion battery packs |
| `batState` | – | Battery operation state: 0=transitioning, 1=normal, 2=active charging |

**Note:** `batSoc` = SOC of the SolarVault 3 Pro Max main unit. `soc` = weighted average across all connected batteries (e.g. main unit 92% + BP2500 88% → soc ≈ 90%).

### Solar (PV)
| Field | Unit | Description |
|-------|------|-------------|
| `pvPw` | W | Total combined solar power |
| `pv1` | dict | `{"pvPw": W, "commState": 0/1}` – PV string 1 |
| `pv2` | dict | `{"pvPw": W, "commState": 0/1}` – PV string 2 |
| `pv3` | dict | `{"pvPw": W, "commState": 0/1}` – PV string 3 |
| `pv4` | dict | `{"pvPw": W, "commState": 0/1}` – PV string 4 |

`commState: 0` = string not connected/active, `commState: 1` = active.

### Grid (OnGrid)
| Field | Unit | Description |
|-------|------|-------------|
| `inOngridPw` | W | Power drawn from grid |
| `outOngridPw` | W | Power exported to grid |
| `maxOutPw` | W | Max OnGrid feed-in power (Einspeiseleistung); selectable 800 W / 2500 W in app; writable via cmd=5; confirmed by live test 2026-07-16 |
| `maxInvStdPw` | W | Max inverter standby power |
| `maxGridStdPw` | W | Max grid standby power |

### EPS (off-grid output)
| Field | Unit | Description |
|-------|------|-------------|
| `swEpsInPw` | W | EPS input power |
| `swEpsOutPw` | W | EPS output power |
| `swEpsState` | – | EPS state: 1=normal, 0=fault |
| `swEps` | – | EPS switch: 1=on, 0=off |

### Inverter Stack
| Field | Unit | Description |
|-------|------|-------------|
| `stackInPw` | W | Power flowing into the inverter stack (AC side) |
| `stackOutPw` | W | Power flowing out of the inverter stack (AC side) |

### Settings (read/write)
| Field | Unit | Description |
|-------|------|-------------|
| `socChgLimit` | % | SOC charge upper limit |
| `socDischgLimit` | % | SOC discharge lower limit |
| `autoStandby` | – | Auto-standby mode: 0=invalid, 1=off/sleep, 2=on |
| `isAutoStandby` | – | Auto-standby allowed: 1=yes, 0=no |
| `socForceChg` | % | SOC force-charge target (range 0–100, cmd=5, ack=107). Purpose not fully determined; hypothesis: manual force-charge target or backup-reserve threshold. Set 0 to deactivate. |

### Network / Diagnostics
| Field | Unit | Description |
|-------|------|-------------|
| `ethPort` | – | Ethernet connected: 1=yes, 0=no |
| `wsig` | dBm | WiFi signal strength |
| `wname` | str | WiFi SSID (empty when Ethernet is active) |
| `eip` | str | Ethernet IP address |
| `emac` | str | Ethernet MAC address |
| `ability` | – | Capability bitmask (768 observed; changes after firmware updates) |
| `maxIotNum` | – | Maximum number of IoT sub-devices |

### Additional sensors (post-firmware 2026-07)
| Field | Unit | Description |
|-------|------|-------------|
| `inCtEgy` | ×0.01 kWh | Cumulative system-level CT import energy |
| `outCtEgy` | ×0.01 kWh | Cumulative system-level CT export energy |

---

## Type 23 – Energy Statistics

Sent approximately every **10 minutes**. Contains cumulative energy counters since last device reset. Values use scale factor **×0.01** to get kWh.

**Important:** Devices may have non-zero values at commissioning due to factory testing. Home Assistant handles this correctly via `TOTAL_INCREASING` state class (only tracks increases from first observation).

### Main device (type 23, deviceSn="system")
| Field | ×0.01 kWh | Description |
|-------|-----------|-------------|
| `pvEgy` | kWh | Total solar energy |
| `pv1Egy`–`pv4Egy` | kWh | Per-string solar energy |
| `batChgEgy` | kWh | Battery charge energy |
| `batDisChgEgy` | kWh | Battery discharge energy |
| `inOngridEgy` | kWh | Grid import energy |
| `outOngridEgy` | kWh | Grid export energy |
| `inEpsEgy` | kWh | EPS input energy |
| `outEpsEgy` | kWh | EPS output energy |
| `pvOtBatEgy` | kWh | PV → Battery energy |
| `pvOtAcEgy` | kWh | PV → AC load energy |
| `pvOtOngridEgy` | kWh | PV → Grid energy |
| `ongridOtAcLoadEgy` | kWh | Grid → AC load energy |
| `batOtAcEgy` | kWh | Battery → AC energy |
| `batOtGridEgy` | kWh | Battery → Grid energy |
| `ongridOtBatEgy` | kWh | Grid → Battery energy |
| `acOtBatEgy` | kWh | AC → Battery energy |
| `acOtOngridEgy` | kWh | AC → Grid energy |

### SmartMeter 3P (type 23, per-device, devType=3, subType=5)
| Field | ×0.01 kWh | Description |
|-------|-----------|-------------|
| `tPhaseEgy` | kWh | Total import energy |
| `tnPhaseEgy` | kWh | Total export energy |
| `aPhaseEgy` | kWh | L1 import energy |
| `bPhaseEgy` | kWh | L2 import energy |
| `cPhaseEgy` | kWh | L3 import energy |
| `anPhaseEgy` | kWh | L1 export energy |
| `bnPhaseEgy` | kWh | L2 export energy |
| `cnPhaseEgy` | kWh | L3 export energy |

### BP2500 Expansion Battery (type 23, per-device, devType=1, subType=0)

The BP2500 appears in type-23 messages under its own serial number with two cumulative energy counters.
No real-time power data is available via MQTT for the BP2500.

| Field | ×0.01 kWh | Description |
|-------|-----------|-------------|
| `outEgy` | kWh | Cumulative energy discharged from BP2500 |
| `inEgy` | kWh | Cumulative energy charged into BP2500 |

Example observed: `{"deviceSn":"HQ2C10000444HP3","devType":1,"subType":0,"outEgy":5,"inEgy":196}`

---

## Type 101 – Sub-device Event Data

### SmartMeter 3P / HTO907A (devType=3, subType=5)

**Critical bug in original integration:** `devType=3` was routed to `plugs` instead of `cts`, breaking the energy flow calculation entirely. Fixed in this fork.

Field semantics (from [issue #18](https://github.com/Jackery-Official/jackery/issues/18)):

| Field | Description |
|-------|-------------|
| `aPhasePw` | L1 consumption / grid import (W) |
| `bPhasePw` | L2 consumption / grid import (W) |
| `cPhasePw` | L3 consumption / grid import (W) |
| `tPhasePw` | Total consumption / net grid import (W) |
| `anPhasePw` | L1 production / grid export (W) |
| `bnPhasePw` | L2 production / grid export (W) |
| `cnPhasePw` | L3 production / grid export (W) |
| `tnPhasePw` | Total production / net grid export (W) |
| `commState` | Communication state: 1=online (connected to SolarVault), 0=offline |
| `commMode` | Communication path: 1=LAN (local MQTT, measurements flow), 2=Cloud relay (measurements go to Jackery cloud, NOT available in HA) |
| `wip` | IP address of the SmartMeter on the local network |
| `bindKey` | Static binding key (metadata only, no sensor value) |
| `schePhase` | Phase scheme (4 = dual-circuit wiring) |
| `funForm` | Function form (5 observed) |

**Important – commMode LAN→Cloud switching:** Internet outages can cause the SmartMeter to switch from LAN (commMode=1) to Cloud relay (commMode=2) mode autonomously. In Cloud mode, `commState` remains 1 (device still connected to SolarVault) but all measurement fields (`tPhasePw`, `aPhasePw`, etc.) are absent from type-101 messages. This is invisible unless the `commMode` sensor is tracked.

**commMode cannot be controlled via MQTT.** Four different command variants were tested (type-103 with/without sysSwitch, type-1 cmd=5 with device SN, speculative type-104) — none had any effect. The SmartMeter decides its own mode. The only known fix is a **SolarVault restart** (via the Jackery app or directly on the device), which causes the SmartMeter to re-register via the LAN path.

---

## Control Commands

### Main device (type 1, cmd 5)

```json
{
  "type": 1,
  "eventId": 3,
  "messageId": <random 1000-9999>,
  "ts": <unix timestamp>,
  "token": "<device token>",
  "body": {
    "cmd": 5,
    "rc": 1,
    "<param>": <value>
  }
}
```

Writable parameters (all confirmed with cmd=107 acknowledgement):

| Parameter | Type | Notes |
|-----------|------|-------|
| `socChgLimit` | % 0–100 | SOC charge upper limit |
| `socDischgLimit` | % 0–100 | SOC discharge lower limit |
| `maxOutPw` | W | Max OnGrid output power |
| `autoStandby` | 0/1/2 | Auto-standby: 0=invalid, 1=standby, 2=on |
| `isAutoStandby` | 0/1 | Allow auto-standby |
| `swEps` | 0/1 | EPS switch |
| `socForceChg` | % 0–100 | Force-charge target; set 0 to deactivate. Exact behavior undetermined. |
| `reboot` | 1 | Triggers device reboot. Useful to restore SmartMeter from Cloud to LAN mode. |
| `workModel` | int | Operating mode (see table below) |
| `defaultPw` | W | Default output power in Benutzerdefiniert mode (fallback when no schedule entry active) |
| `isFollowMeterPw` | 0/1 | Follow-meter sub-mode within workModel=4 |
| `offGridDown` | 0/1 | Off-grid fallback enable |

Device acknowledges writes with cmd=107 response.

### Sub-device switch (type 103)

```json
{
  "type": 103,
  "eventId": 0,
  "messageId": <random>,
  "ts": <unix timestamp>,
  "token": "<device token>",
  "body": {
    "deviceSn": "<sub-device SN>",
    "devType": <devType>,
    "sysSwitch": 1
  }
}
```

### Poll requests

**Device status (type 25):**
```json
{"type": 25, "eventId": 0, "messageId": <random>, "ts": <ts>, "token": "<token>", "body": null}
```

**Sub-device data (type 100):**
```json
{"type": 100, "eventId": 0, "messageId": <random>, "ts": <ts>, "token": "<token>", "body": {"devType": 2}}
```
- `devType: 2` → Standard CTs (discovery only; returns SmartMeter config metadata but NO measurement fields)
- `devType: 3` → SmartMeter 3P (HTO907A) real-time measurement data (`tPhasePw`, `aPhasePw`, etc.)
- `devType: 6` → Smart plugs

**Important:** The SmartMeter (devType=3, subType=5) appears in the `devType:2` poll response (`cts` key) but only with configuration metadata — no power fields. The integration additionally polls `devType:3`; whether this actively triggers real-time type-101 responses or the SmartMeter sends them autonomously is not definitively confirmed.

**Full system state (type 105):**
```json
{"type": 105, "eventId": 0, "messageId": <random>, "ts": <ts>, "token": "<token>", "body": null}
```
Device responds with a **type-106** message containing the full system state (30+ fields not present in regular type-2). Integration polls this every ~30 s (3 cycles × 10 s, changed in v1.3.2). The counter (`_poll_105_counter`) starts at 2, threshold 3 — so the first poll fires within the first 10 s cycle.

---

## Expansion Battery (BP2500)

The BP2500 is connected to the SolarVault 3 Pro Max via an internal bus. Real-time power data for the BP2500 is **not exposed via MQTT**. Available data:

**Aggregated (in main device type-2 messages):**
- `soc` = combined BMS SOC across all battery units (main + BP2500)
- `batInPw` = charge power of the **main unit only** (confirmed 2026-08-04; does NOT include BP2500 — diverges by 200–300 W when BP2500 is actively charging)
- `batNum` = number of expansion packs connected

**Per-device cumulative energy (in type-23 messages, devType=1, subType=0):**
- `inEgy` = cumulative energy charged into the BP2500 (×0.01 kWh)
- `outEgy` = cumulative energy discharged from the BP2500 (×0.01 kWh)

Individual BP2500 real-time data (per-unit SOC, current input power, firmware version) is only accessible via the Jackery app (cloud) or Bluetooth.

---

## Known Limitations / Open Questions

- **`batState` semantics** (verified from 90-min live capture):
  - `1` = Normal charging (batInPw > 0, soc < 100%)
  - `0` = Transitioning: appears when battery just reached 100% (charge stops), and also during balancing/settling after a discharge event
  - `2` = Active high-power discharge (battery supplying loads, soc=100%, loads > solar)
  - Note: `0` is a transient state on both sides – charge completion AND post-discharge settling.
- **`ability` bitmask**: Value 768 (= 0b1100000000) observed. Meaning of individual bits unknown; value changes after firmware updates.
- **`workMode` / energy mode**: Fully mapped via live MQTT capture (2026-07-16). See Operating Modes table below. `workModel` is writable via type-1/cmd=5 (confirmed by community, cmd=107 ack). Mode-switching via MQTT is supported locally.
- **Energy counters reset behavior**: Unknown when/if the device resets cumulative energy counters (daily, on power cycle, never).
- **Type-23 forward spikes / counter corruption (observed 2026-07-23)**: The device occasionally sends unrealistically large forward jumps in cumulative energy fields (e.g. `pvEgy` +8.88 kWh in a single ~10 min interval, `inOngridEgy` +3.96 kWh). These are not counter resets (values don't drop) — they are forward spikes that HA's `TOTAL_INCREASING` cannot filter. Result: corrupted long-term statistics and stuck sensors (if the internal counter subsequently restarted from a lower value, `TOTAL_INCREASING` ignores all subsequent readings below the spike). The trigger was NOT a user-initiated restart. Possible causes: cloud-triggered firmware update, internal watchdog restart, micro power outage, or firmware counter arithmetic bug. **No uptime or boot-count field exists in the MQTT protocol** — a device restart cannot be detected directly. Only a *decreasing* counter value in type-23 would hint at a reset, but forward spikes give no such signal. Workaround: manually correct corrupted statistics entries in HA under Settings → Statistics. Potential integration fix: plausibility check in type-23 handler (reject delta > configurable threshold per interval), but threshold is hard to set without knowing the installation size.
- **`collectors` field**: Always `[]` in observed data. May be used for future device types.
- **`isAutoStandby` field**: Never observed in type-2 messages, despite being listed as writable. Likely only sent when auto-standby feature is actively relevant (not in our configuration with autoStandby=2).
- **SmartMeter `bindKey`**: Static metadata, no sensor value.
- **SmartMeter `commMode`**: Dynamic, NOT static. Switches between 1 (LAN) and 2 (Cloud relay) — notably after internet outages. Now tracked as sensor `communication_mode`. See Type-101 section for details.
- **`socForceChg` purpose**: Confirmed writable (cmd=5, ack=107), but exact behavior undetermined. Storm Warning feature in the Jackery app uses cloud and does NOT set this field via MQTT.
- **`wps` / `wpc` fields**: Always `0` in all captures regardless of mode or schedule. Meaning unknown; do NOT assume these represent schedule count or schedule presence.
- **`defaultPw` semantics**: Confirmed as the user-configured default output power for Benutzerdefiniert mode (workModel=4). Active when no time-based schedule entry applies. `energyPlanPw` mirrors `defaultPw` when no schedule is active. Writable via cmd=5 (confirmed by community).
- **Time-based schedules (Benutzerdefiniert/Tarifmodus)**: Managed exclusively in the Jackery cloud. Not readable or writable via local MQTT. `wps`/`wpc`/`chargePlanPw` remain 0 locally even when schedules are configured in the app.
- **KI-Modus strategy selection** (Ausgewogener Modus, Arbitrage-Modus, etc.): Cloud-only. All strategies report identical `workModel: 8` locally — no distinguishing field visible via MQTT.

## Operating Modes (`workModel`)

Fully mapped via live MQTT capture (2026-07-16) by switching modes in the Jackery app and polling type-105 after each change.

| `workModel` | App-Modus (DE) | Notes |
|-------------|----------------|-------|
| `2` | Eigenverbrauch | — |
| `4` | Benutzerdefiniert | `isFollowMeterPw: 0`; output power fixed at `defaultPw` when no schedule active |
| `4` | Zähler folgen | `isFollowMeterPw: 1`; device tracks SmartMeter to achieve net-zero grid exchange |
| `7` | Tarifmodus | Tariff periods/prices cloud-only; no local MQTT fields |
| `8` | KI-Modus | Strategy (Ausgewogen, Arbitrage, …) cloud-only; all strategies report `workModel: 8` locally |

**What is controllable locally:**
- Switch between modes: write `workModel` via type-1/cmd=5
- Benutzerdefiniert output power: write `defaultPw` (W)
- Toggle Zähler-folgen within Benutzerdefiniert: write `isFollowMeterPw` (0/1)

**What is cloud-only (not reachable via local MQTT):**
- Time-based schedules (Benutzerdefiniert, Tarifmodus)
- KI strategy selection
- Tariff price configuration

---

## Fixed Bugs (this fork)

- **SmartMeter misclassified as plug (issue #18, v1.1.63)**: The original integration routed `devType=3` to the plug handler, causing the energy flow calculation to receive no CT data. Fixed by adding a dedicated `ct_3phase` sensor group.

- **CT sub-device flapping (issue #16, v1.1.65 → improved v1.2.0)**: The original integration overwrites `data_cache["cts"]` unconditionally on every Type 101 message. Since the integration polls `devType=2` (CTs) and `devType=6` (plugs) in separate requests, the plug response (which contains no `cts` key) wiped the CT cache, causing the SmartMeter to appear "missing" every ~11 s. Initially fixed (v1.1.65) by checking `has_ct_payload`/`has_plug_payload` flags. Replaced in v1.2.0 with **SN-based merging** (`_merge_subdevice_list`): each section (cts/plugs) is merged by `deviceSn`, so only the section present in the payload is updated and partial updates preserve all previously received fields.

- **`gridSellPw=0` treated as falsy (v1.1.68)**: The fallback path for `gridBuyPw`/`gridSellPw` used `or` to check presence, so a value of `0` (no export) left `grid_available=False` even when both fields were present. Fixed with explicit `is not None` checks.

- **String sensor values silently discarded in `ct_3phase` update path (v1.1.69)**: The `except (TypeError, ValueError): pass` block in `_update_from_coordinator` dropped string values (e.g. IP addresses from `wip`) without setting `_attr_native_value`. Fixed by catching the exception and setting the value as string directly (string fallback).

- **`jackery_home_power` negative during phase-balanced feed-in (v1.1.70)**: A special-case branch (Branch A) computed `grid_sell - ongrid_supply` with inverted sign, overriding the correct base formula `p_grid - p_ong`. Example: 301 W AC output, 29 W net to grid → result was −272 W instead of +272 W. Branch A and Branch B were removed; the base formula handles all scenarios correctly.

---

## Changes in v1.2.x (v1.2.0 + v1.2.1)

### What was adopted (v1.2.0 + v1.2.1)

| Feature | Version | Implementation | Notes |
|---------|---------|---------------|-------|
| **Reboot button** | 1.2.0 | `button.py` | Sends `reboot=1` via type=1/cmd=5. Useful to restore SmartMeter LAN mode without touching device or app. |
| **Auto Standby select** | 1.2.0 | `select.py` | `autoStandby` as dropdown (invalid/standby/on) instead of numeric sensor. |
| **Sub-device offline detection** | 1.2.0 | `sensor.py` `_subdevice_last_seen` | Per-SN `last_seen` timestamps; sensors marked `unavailable` after 60 s without data. Grace period: first 60 s after HA start. |
| **SN-based cache merge** | 1.2.0 | `_merge_subdevice_list()` | Partial type-101 updates preserve existing fields. Items identified by `deviceSn` or `sn`. |
| **CT_DEV_TYPES** | 1.2.0 | `frozenset({2, 3, 4})` | devType=4 (Meter Collector) now classified as CT, not plug. |
| **5 status sensors** | 1.2.0 | `SENSOR_TYPES` | `stat`, `workMode`, `ongridStat`, `ctStat`, `gridSate` — appear automatically when device first reports the field. |
| **Type-105 poll + type-106 handler** | 1.2.1 | `_periodic_data_request` | type-105 sent every 30 cycles (~5 min); fires on first startup. Device responds with type-106 full system state. |
| **13 new sensors from type-106** | 1.2.1 | `SENSOR_TYPES` | `otherLoadPw`, `gridInPw`/`gridOutPw`, `inGridSidePw`/`outGridSidePw`, `energyPlanPw`, `standbyPw`, `pvMaxChgPower`, `maxSysOutPw`/`maxSysInPw`, `isFollowMeterPw`, `offGridDown`, `offGridTime` |
| **`workModel`→`workMode` alias** | 1.2.1 | type-106 handler | type-106 sends `workModel` (not `workMode`); normalized on ingest so the `work_mode` sensor is populated. |

### Type-106 observed fields (live capture 2026-07-15)

```json
{
  "cmd": 120, "stat": 0, "ongridStat": 1, "ctStat": 1, "gridSate": 1,
  "gridInPw": 0, "gridOutPw": 167, "otherLoadPw": 167,
  "soc": 81, "batNum": 1,
  "inGridSidePw": 0, "outGridSidePw": 0,
  "batInPw": 0, "batOutPw": 211,
  "workModel": 2,
  "batState": 2, "maxFeedGrid": 800,
  "pvMaxChgPower": 0, "maxSysOutPw": 800, "maxSysInPw": 2500,
  "swEpsInPw": 0, "swEpsOutPw": 0,
  "energyPlanPw": 150, "chargePlanPw": 0, "defaultPw": 150,
  "isFollowMeterPw": 0, "wps": 0, "wpc": 0,
  "isAutoStandby": 1, "standbyPw": 25,
  "offGridDown": 1, "offGridTime": 120,
  "tempUnit": 0, "funcEnable": 2147483648,
  "pvPw": 0, "pv1": {"pvPw": 0}, "pv2": {"pvPw": 0}, "pv3": {"pvPw": 0}, "pv4": {"pvPw": 0}
}
```

Key findings:
- `workModel: 2` = energy work mode (was previously thought invisible in MQTT — it IS present, but only in type-106)
- `otherLoadPw` matches SmartMeter reading — SolarVault estimates home load internally
- `gridInPw`/`gridOutPw` are equivalent to `inOngridPw`/`outOngridPw` (same values observed)
- `inGridSidePw`/`outGridSidePw` = 0 in our capture — third measurement point, purpose unclear
- `funcEnable: 2147483648` = only bit 31 set (unknown function)
- `defaultPw` — user-configured fallback output power for Benutzerdefiniert mode (workModel=4); writable via cmd=5
- `wps`, `wpc` — always `0` regardless of mode or schedule; meaning unknown
- `tempUnit`, `chargePlanPw` — not yet mapped to sensors (unclear semantics)

### What was NOT adopted (and why)

| Feature | Reason |
|---------|--------|
| **Type 102 handler** | Not observed spontaneously on our hardware (live capture 20+ min). Likely requires newer firmware. |
| **Type 107 handler** | Not observed at all. Incremental soc/workMode updates — possibly cloud-only or firmware-gated. |
| **commMode validation for plug switches** | Prevents MQTT switch commands to cloud-connected plugs. No smart plugs in our setup, but worth adding if plugs are ever used. |
| **Field alias normalization (`_normalize_payload_fields`)** | `workModel`→`workMode` handled directly in type-106 handler. `gridBuyPw`→`gridInPw` covered by existing fallback logic. |
| **REQUEST_INTERVAL = 5 s** | Upstream went to 5 s; we stay at 10 s — sufficient for homelab use, less MQTT traffic. |
| **Branch A/B in energy flow** | Upstream v2.0-beta still has these buggy branches. We removed them in v1.1.70. Do **not** re-introduce. |

### v2.0-beta analysis notes
- **SmartMeter bug (issue #18)**: also fixed upstream via `CT_ITEM_DEV_TYPES = frozenset({2, 3, 4})` — equivalent to our fix.
- **Branch A** (`grid_sell − ongrid_supply`): still present in v2.0-beta → negative `jackery_home_power` in phase-balanced feed-in. We fixed this; they did not. Do not adopt their `_calculate_energy_flow`.
- **`workModel` alias**: v2.0-beta normalizes via `_normalize_payload_fields`; we handle it directly in the type-106 handler — same effect, simpler scope.

---

## `jackery_home_power` – Energy Flow Formula

Implemented in `_calculate_energy_flow` in `sensor.py`.

### Variables
| Variable | Source | Sign convention |
|----------|--------|-----------------|
| `pv` | `pvPw` | positive = generating |
| `p_ac` | `swEpsOutPw - swEpsInPw` | positive = EPS delivering to loads |
| `ongrid_charge` | `inOngridPw` | positive = grid charging unit |
| `ongrid_supply` | `outOngridPw` | positive = unit supplying AC bus |
| `p_ong` | `ongrid_charge - ongrid_supply` | positive = net grid→unit, negative = net unit→grid |
| `grid_buy` | `tPhasePw` (CT) | grid import power (W, always ≥ 0) |
| `grid_sell` | `tnPhasePw` (CT) | grid export power (W, always ≥ 0) |
| `p_grid` | `grid_buy - grid_sell` | net grid power (positive = import, negative = export) |

### SmartMeter field semantics
`tPhasePw` and `tnPhasePw` are combined net values: `tPhasePw = max(0, net_total)`, `tnPhasePw = max(0, -net_total)`. Mathematically equivalent to `∑(per-phase imports) - ∑(per-phase exports)`, so using either approach gives the same `p_grid`. Phase-balanced scenarios (e.g. L1 imports 250 W, L3 exports 279 W) result in `tPhasePw=0`, `tnPhasePw=29` — the correct net export of 29 W.

**Note:** `outOngridPw` is the **total AC output** from the SolarVault to the house AC bus — NOT the net export to the public grid. The SmartMeter's `tnPhasePw` is the actual net-to-grid value.

### Base formula (correct for all scenarios)
```
p_home = p_grid - p_ong
       = (grid_buy - grid_sell) - (ongrid_charge - ongrid_supply)
```

This holds regardless of phase balance. Example with L3 house load:
- L1: 158 W load → `aPhasePw=158`, `anPhasePw=0`
- L3: 100 W load + Jackery 270 W → net L3 export 170 W → `cPhasePw=0`, `cnPhasePw=170`
- `p_grid = 158 - 170 = -12 W` (net export)
- `p_ong = 0 - 270 = -270 W`
- `p_home = -12 - (-270) = 258 W` ✓ (158 + 100 = 258 W)

### Anomaly branches (still present)
- **Branch 1** (`grid_buy < ongrid_charge` by ≤ 50 W): measurement noise, set `p_home = 0`
- **Branch 2** (`grid_buy < ongrid_charge` by > 50 W): `p_home = ongrid_charge - grid_buy`

### CT not available fallback
Without CT data: `p_home = ongrid_supply` (SolarVault AC output, rough estimate only).

---

---

## Changes in v1.3.0 – Control Entities from type-106 fields

**Status:** Implemented 2026-07-17.

All fields below are confirmed writable via type-1/cmd=5 with cmd=107 acknowledgement (confirmed by pyrots via community research and live MQTT capture 2026-07-16).

### New HA entities

| Entity type | Field | File | Details |
|-------------|-------|------|---------|
| Select | `workModel` | `select.py` | `JackeryWorkModeSelect`. Options: Eigenverbrauch (2), Benutzerdefiniert (4), Tarifmodus (7), KI-Modus (8). Reads `workMode` from cache (type-106 handler aliases `workModel`→`workMode`). Writes `workModel`. Optimistic. Replaces `work_mode` sensor. Note: value `5` referenced in Jackery cloud code as possible legacy Tarifmodus alias — not tested locally, not included. |
| Switch | `isFollowMeterPw` | `switch.py` | `JackeryFollowMeterSwitch`. "Zähler folgen" sub-mode within workModel=4. Entity becomes **unavailable** automatically when workMode ≠ 4. Optimistic. Replaces `is_follow_meter_power` sensor. |
| Switch | `offGridDown` | `switch.py` | `JackeryOptimisticSwitch`. Off-grid fallback enable. Optimistic. Replaces `off_grid_fallback` sensor. |
| Number | `defaultPw` | `number.py` | 0–200 W, step 10 W. Fallback output power for Benutzerdefiniert mode. App caps at 200 W; schedule slots (cloud-only) reach 800 W. Optimistic. Previously not implemented at all. |

### Removed entities

- `work_mode` sensor (`workMode`) → replaced by Work Mode select
- `is_follow_meter_power` sensor (`isFollowMeterPw`) → replaced by Follow Meter Power switch
- `off_grid_fallback` sensor (`offGridDown`) → replaced by Off-Grid Fallback switch
- `autoStandby` number (slider 0–2) → removed; Auto Standby Mode select covers this field

### Fields that remain read-only

- `offGridTime` — pyrots tested cmd=5, no cmd=107 ack received. Read-only sensor (value: 120 s). Unit fixed to `UnitOfTime.SECONDS`.
- `energyPlanPw` — mirrors `defaultPw` when no schedule active; computed, read-only sensor.

### Switch implementation details

- `JackeryOptimisticSwitch(JackeryMainSwitch)` — overrides `turn_on/off` to update state before MQTT send
- `JackeryFollowMeterSwitch(JackeryOptimisticSwitch)` — overrides `_update_from_coordinator` to check `workMode`; sets `_attr_available = False` when workMode is known and ≠ 4

### Community collaboration

**pyrots** (GitHub user) reverse-engineered the same protocol on a SolarVault 3 Pro and confirmed writability of `workModel`, `defaultPw`, `isFollowMeterPw`, `offGridDown` independently. See [issue #5](https://github.com/Jackery-Official/jackery/issues/5).

---

## Changes in v1.3.1 – Optimistic State Revert Fix

**Problem:** After writing a new value (e.g. Work Mode select), the coordinator's `_data_cache` still held the old value. Every incoming type-2 message (~10 s) triggered `_distribute_data`, which pushed the stale cached value back to the entity — reverting the optimistic UI state before the next type-106 poll could confirm the write.

**Fix:** On every control write (`turn_on`, `turn_off`, `async_select_option`, `async_set_native_value`), `coordinator._data_cache` is updated alongside the optimistic UI state (`_attr_is_on` / `_attr_current_option` / `_attr_native_value` + `async_write_ha_state()`). The cache update uses the same key as the inbound MQTT field so `_distribute_data` reads back the optimistic value instead of overwriting it.

**Pattern (must be followed for all future writable entities):**
```python
# 1. Update optimistic UI state
self._attr_current_option = option   # or _attr_is_on, _attr_native_value
self.async_write_ha_state()
# 2. Patch the coordinator cache to prevent _distribute_data reverting the state
self.coordinator._data_cache["workMode"] = new_raw_value
# 3. Send MQTT command
await self.coordinator.send_command(...)
```

---

## Changes in v1.3.2 – Type-105 Poll Interval Reduction

Changed `_poll_105_counter` logic to poll type-105 every **30 s** (3 cycles × 10 s) instead of ~5 min (30 cycles × 10 s from v1.2.1).

**Why:** App-initiated mode changes (Jackery cloud) are now visible in HA within ~30 s instead of up to 5 min. The SolarVault 3 Pro Max responds instantly to type-105 with full type-106 state. Additional traffic is negligible (~75 KB/h).

**Implementation:** `_poll_105_counter` starts at `2`, threshold `3`. First poll fires within the first 10 s cycle (counter immediately reaches 3 on startup).

---

## Changes in v1.3.3 – Internationalization for Control Entities

### Translation system introduction

Created the three required HA translation files, replacing the original Chinese-only `strings.json`:

| File | Purpose |
|------|---------|
| `custom_components/jackery/strings.json` | English base (HA tooling reads this) |
| `custom_components/jackery/translations/en.json` | Explicit English overrides (identical to strings.json) |
| `custom_components/jackery/translations/de.json` | German translations |

**Control entities translated (v1.3.3):** 12 entities — 2 selects, 4 switches, 5 numbers, 1 button.

### Work Mode option key change (breaking)

Option values for the Work Mode select were changed from German literal strings to neutral snake_case keys:

| Old value (v1.3.0–v1.3.2) | New key (v1.3.3+) | EN label | DE label |
|---------------------------|-------------------|----------|----------|
| `"Eigenverbrauch"` | `"self_consumption"` | Self-Consumption | Eigenverbrauch |
| `"Benutzerdefiniert"` | `"custom"` | Custom | Benutzerdefiniert |
| `"Tarifmodus"` | `"tariff"` | Tariff Mode | Tarifmodus |
| `"KI-Modus"` | `"ai"` | AI Mode | KI-Modus |

**Automations referencing old German option values must be updated to the new keys.**

### HA restart requirement

After updating to a version that changes translation files, an **HA restart** is required (not just integration reload). A browser hard-refresh (Ctrl+Shift+R) may additionally be needed if cached translations show in the wrong language.

---

## Changes in v1.3.4 – Complete Sensor Internationalization

### Root cause of untranslated sensors

`JackerySensor.__init__` used `self._attr_name = self._config["name"]` — a hardcoded string that bypasses the HA translation system entirely. Same for `JackerySubDeviceSensor`. Both classes were fixed to use `_attr_translation_key` instead.

### Translation key conventions

**Main device sensors (`JackerySensor`):**
```python
# Before (hardcoded English, not translatable):
self._attr_name = self._config["name"]

# After (translation-key driven):
self._attr_translation_key = sensor_id   # sensor_id is already snake_case, e.g. "battery_soc"
# _attr_name must NOT be set
```

**Sub-device sensors (`JackerySubDeviceSensor`):**
```python
# sensor_group parameter added to __init__
translation_key = f"{sensor_group}_{sensor_key}" if sensor_group else sensor_key
self._attr_translation_key = translation_key
# Examples: "ct_3phase_import_total", "ct_3phase_comm_mode", "expansion_battery_charge_energy"
```

`sensor_group` values:
| Condition | `sensor_group` |
|-----------|----------------|
| `devType=3, subType=5` (SmartMeter 3P) | `"ct_3phase"` |
| `devType=2/4` (standard CT) | `"ct"` |
| Non-CT plug | `"plug"` |
| Expansion battery (type-23, devType=1) | `"expansion_battery"` |

### Integer fix for unitless sensors

Previously all numeric values were stored as `float(value) * scale`, resulting in `1.0` instead of `1` for integer-valued fields without a unit.

**Fix in `JackerySensor._update_from_coordinator` and `JackerySubDeviceSensor._update_from_coordinator`:**
```python
scale = self._config.get("scale", 1)
try:
    raw = float(value) * scale
    if self._config.get("unit") is None and scale == 1:
        self._attr_native_value = int(raw) if raw == int(raw) else raw
    else:
        self._attr_native_value = raw
except (TypeError, ValueError):
    self._attr_native_value = value
```

Affected sensors that now display as integers: Battery Count, Battery State, Device Status, OnGrid Status, CT Status, Grid Meter Link, EPS State, EPS Switch Status, Ethernet Connected, and all other unitless numeric fields.

### ENUM sensors for commMode / commState

`commMode` and `commState` from the SmartMeter 3P (devType=3, subType=5) are now `SensorDeviceClass.ENUM` sensors with human-readable state labels.

**MQTT value → options index mapping:**
| Field | MQTT value | `options` index | Displayed label |
|-------|-----------|----------------|----------------|
| `commMode` | `1` | `options[1]` = `"cloud"` | Cloud (Relay) |
| `commMode` | `2` | `options[2]` = *(out-of-range, shows raw)* | — |
| `commState` | `0` | `options[0]` = `"offline"` | Offline |
| `commState` | `1` | `options[1]` = `"online"` | Online |

**commMode mapping:** Protocol values are 1-based (1=LAN, 2=Cloud). The sensor config uses `"options_offset": 1` so `idx = int(float(val)) - 1` → commMode=1 → `options[0]` = `"lan"`, commMode=2 → `options[1]` = `"cloud"`. Fixed in v1.3.5 (v1.3.4 had an off-by-one: commMode=1 showed "Cloud (Relay)" instead of "LAN").

**SUBDEVICE_SENSORS entry:**
```python
"comm_mode": {
    "key": "commMode",
    "device_class": SensorDeviceClass.ENUM,
    "options": ["lan", "cloud"],
    "unit": None, "icon": "mdi:lan"
},
"comm_state": {
    "key": "commState",
    "device_class": SensorDeviceClass.ENUM,
    "options": ["offline", "online"],
    "unit": None, "icon": "mdi:connection"
},
```

**ENUM handling in `_update_from_coordinator`:**
```python
options = self._sensor_config.get("options")
if options is not None:
    try:
        idx = int(float(val))
        self._attr_native_value = options[idx] if idx < len(options) else str(idx)
    except (TypeError, ValueError, IndexError):
        self._attr_native_value = str(val)
else:
    # numeric path with int-fix ...
```

### Entity count after v1.3.4

| Platform | Count | Translated since |
|----------|-------|-----------------|
| sensor (main device) | 70 | v1.3.4 |
| sensor (sub-device) | 25 | v1.3.4 |
| select | 2 | v1.3.3 |
| switch | 4 | v1.3.3 |
| number | 5 | v1.3.3 |
| button | 1 | v1.3.3 |
| **Total** | **107** | |

---

## Changes in v1.3.5 – commMode ENUM Mapping Fix

`commMode` is 1-based (1=LAN, 2=Cloud), but the ENUM options list `["lan", "cloud"]` is 0-indexed. The previous implementation did `options[int(val)]`, so commMode=1 mapped to `options[1]` = `"cloud"` (wrong — showed "Cloud (Relay)" even in LAN mode).

**Fix:** Added `"options_offset": 1` to the `comm_mode` sensor config. The update handler now does `idx = int(float(val)) - offset` before indexing. `commState` is unaffected (0-based, default offset=0).

```python
"comm_mode": {
    "key": "commMode",
    "device_class": SensorDeviceClass.ENUM,
    "options": ["lan", "cloud"],
    "options_offset": 1,  # commMode is 1-based: 1=LAN, 2=Cloud
    ...
}
```

ENUM handler:
```python
offset = self._sensor_config.get("options_offset", 0)
idx = int(float(val)) - offset
self._attr_native_value = options[idx] if 0 <= idx < len(options) else str(val)
```

---

## Changes in v1.3.6 – Expansion Battery Availability Fix (Part 1)

**Problem:** Expansion battery (BP2500) sensors were marked `unavailable` ~60 s after data arrived. Two root causes:

1. `_subdevice_last_seen[sn]` was never set in the type-23 handler — only in the type-101 handler (CTs/plugs).
2. Even if set, the 60 s offline timeout was too short for type-23's ~10 min cadence.

**Fix:**
1. Set `_subdevice_last_seen[device_sn] = time.time()` in the type-23 handler whenever a devType=1 message is processed.
2. Added `_expansion_battery_sns: set[str]` — populated in `_check_for_new_expansion_batteries`. Offline timeout for these SNs was raised from 60 s to 900 s.

This was still insufficient (see v1.3.7 for the complete fix).

---

## Changes in v1.3.7 – Max Feed-in Select, Expansion Battery Availability (Part 2), FR Translation

### Max Feed-in Power: number → select

`maxOutPw` was a free-range number slider (0–10000 W). The Jackery app only allows 800 W or 2500 W; arbitrary values are not supported and may violate local grid regulations.

Replaced with `JackeryMaxFeedInSelect` in `select.py`:

```python
_MAX_FEED_IN_OPTIONS: dict[str, int] = {"w800": 800, "w2500": 2500}
_MAX_FEED_IN_VALUE_TO_OPTION: dict[int, str] = {v: k for k, v in _MAX_FEED_IN_OPTIONS.items()}
```

- Translation key: `"max_feed_in_power"` under `entity.select` (was under `entity.number`)
- Optimistic updates + coordinator cache patch (same pattern as WorkMode select)
- Translations updated in `strings.json`, `en.json`, `de.json`, `fr.json`

### Expansion battery availability fix (Part 2)

The 900 s timeout from v1.3.6 still caused flapping if type-23 was delayed or a few messages were missed. Since expansion battery sensors report cumulative energy (not real-time power), the value remains valid between updates.

**Fix:** Once `last_seen > 0` (first data received), expansion battery SNs are kept available indefinitely — no timeout:

```python
if sn in self._expansion_battery_sns:
    is_available = last_seen > 0   # available forever once first data arrives
else:
    is_available = last_seen > 0 and (now - last_seen) <= 60
```

### French translation

`translations/fr.json` contributed by pyrots via PR #1 — full coverage of all 107 entities.

---

## Changes in v1.3.8 – Null-value fix for expansion battery sensors

### Root cause

Devices occasionally send `null` for `inEgy`/`outEgy` in type-23 messages (e.g. during a restart or transient error). Two issues resulted:

1. **Cache corruption**: `exp_bats[sn].update(body)` overwrote real cached values with `None`. While `_update_from_coordinator` guarded against writing `None` to `_attr_native_value` (early return on `val is None`), the corrupted cache meant the entity showed its old value — but after a reload/restart, the cached null was the only available value.

2. **Entity initial state**: Newly created expansion battery entities started with `_attr_native_value = None` (HA state: "unknown"). Before this fix, the entity only got its value on the first subsequent MQTT cycle — briefly showing "null kWh" in charts.

### Fix 1: Null-value filter in type-23 handler (`sensor.py` ~line 1077)

```python
# Before:
exp_bats[device_sn_in_body].update(body)

# After: only update with non-null values
for k, v in body.items():
    if v is not None:
        exp_bats[device_sn_in_body][k] = v
```

### Fix 2: Pre-initialization in `_check_for_new_expansion_batteries`

Before calling `add_entities_callback`, each new entity gets its initial value pre-set from the current cache:

```python
exp_data = exp_bats.get(sn, {})
pre_val = exp_data.get(sensor_cfg.get("key"))
if pre_val is not None:
    try:
        entity._attr_native_value = float(pre_val) * sensor_cfg.get("scale", 1)
    except (TypeError, ValueError):
        entity._attr_available = False
else:
    entity._attr_available = False  # shows as gap, not null, in charts
```

If no real value is available at creation time, the entity starts as "unavailable" (chart gap) rather than "unknown" (null data point).

---

## Changes in v1.3.9 – Expansion battery deletion timer fix (root cause)

### Root cause

`_check_for_new_plugs` step 1/2 betreibt einen 60-Sekunden-Lösch-Timer: Jede SN in `_known_plugs`, die in den aktuellen type-101-Daten (`current_sns`) fehlt, bekommt einen Timer. Nach 60 s wird `entity.async_remove(force_remove=True)` aufgerufen.

Expansionsbatterien (BP2500) erscheinen **ausschließlich in type-23-Nachrichten** (~10 min). Sie tauchen nie in type-101 auf. Folge: Jede type-101-Nachricht (~11 s) brachte den Timer näher an 60 s. Nach ~60 s wurden die Battery-Entities komplett gelöscht. Die nächste type-23 erstellte sie neu → nächste type-101 startete den Timer erneut → dauerhafter Create/Delete-Kreislauf. Beobachtetes Symptom: „Sensor nicht verfügbar" ca. 56–63 Sekunden nach dem Erscheinen der Werte.

### Fix

In Step 1 und Step 2 von `_check_for_new_plugs` werden SNs aus `_expansion_battery_sns` explizit übersprungen:

```python
# Step 1 – Timer starten
for sn in self._known_plugs:
    if sn in self._expansion_battery_sns:
        continue  # expansion batteries appear in type-23, not type-101
    if sn not in current_sns:
        ...

# Step 2 – Löschung ausführen
for sn in list(self._subdevice_missing_since.keys()):
    ...
    if sn in self._expansion_battery_sns:
        del self._subdevice_missing_since[sn]
        continue
    ...
```

---

## Internationalization (i18n) Architecture

### Translation files

Three files must be kept in sync when adding new entities:

```
custom_components/jackery/
├── strings.json                  # English base — HA tooling reads this
└── translations/
    ├── en.json                   # Explicit English (identical to strings.json)
    └── de.json                   # German translations
```

**`strings.json`** serves as the English base and is used by HA tooling (translation validators, frontend build). **`translations/en.json`** must be identical to it. **`translations/de.json`** contains the German labels.

### JSON structure

```json
{
    "entity": {
        "sensor": {
            "<translation_key>": {"name": "English Name"},
            "<translation_key_with_states>": {
                "name": "Sensor Name",
                "state": {
                    "<option_key>": "Displayed Label"
                }
            }
        },
        "select": { ... },
        "switch": { ... },
        "number": { ... },
        "button": { ... }
    }
}
```

### Entity class requirements

For the translation system to work, every entity class must set:

```python
_attr_has_entity_name = True   # inherited from JackeryMainSensor / JackerySubDeviceSensor base
_attr_translation_key = "my_sensor_id"   # set in __init__; do NOT also set _attr_name
```

For ENUM sensors:
```python
_attr_device_class = SensorDeviceClass.ENUM
_attr_options = ["option_a", "option_b"]   # string keys matching the "state" block in translations
_attr_native_value = "option_a"            # must be one of the options
```

### Adding a new entity

1. Add `_attr_translation_key` in the entity's `__init__` (snake_case, no spaces)
2. Add the key to `strings.json` under `entity.<platform>.<key>`
3. Add it identically to `translations/en.json`
4. Add the German translation to `translations/de.json`
5. After HACS update: HA restart required (not just reload)

### HA restart requirement

Custom integration translation files are loaded once at startup. After any change to `strings.json` or `translations/*.json` (including HACS updates), an **HA restart** is required. Integration reload is not sufficient. Browser hard-refresh (Ctrl+Shift+R) may also be needed if the browser cached stale translations.

---

## Changes in v2.0.3 – WLAN IP sensor, entity reference doc, translation fix

### Added

- **`wlan_ip` sensor** (`sensor.py`): Maps `wip` field from type-2 body — WiFi IP of the SolarVault main unit.
  Not to be confused with `ct_3phase_ip_address` (SmartMeter's `wip` from type-101).
- **`docs/entity-reference.md`**: Full entity guide — dashboard recommendations, SmartMeter vs. SolarVault for grid,
  entity_id naming convention `{domain}.jackery_{sn_lowercase}_{display_name_slug}`, complete sensor tables.

### Fixed

- **German translation `low_power`**: "Schwachstrom" → "Energiesparmodus" in `translations/de.json`.

### Open issues (tracked in GitHub)

- **Issue #11** (`maxFeedGrid` writable): User tested cmd=5 with `maxFeedGrid=140` — it works. Not yet implemented.
  Currently `max_feed_grid_power` is read-only. Discuss with user whether Number (free value 0–800 W) or
  keep Select approach.

---

## Changes in v2.0.2 – Migration fix, sub-device entity creation fix, 1200 W option

### Fixed

- **Bug 3** (`sensor.py`): `coordinator.config_entry_id` was changed to `coordinator._config_entry_id`
  (private) in v2.0.0, but `hasattr(self, "config_entry_id")` guards in `_check_for_new_plugs()`
  and `_check_for_new_expansion_batteries()` still checked the public name → always `False` →
  SmartMeter, BP2500, smart plug entities never created after HA restart. Fixed by restoring
  the public attribute (`coordinator.config_entry_id`) and updating the corresponding
  `__init__` declaration in `JackeryDataCoordinator.__init__`.

- **Bug 1 + Bug 2** (`__init__.py`): `_migrate_unique_ids()` completely rewritten to use direct
  entity registry manipulation (instead of `async_migrate_entries` callback). Changes:
  - Sub-prefix check now requires uppercase character after prefix to distinguish main-device
    sensors (`battery_soc`) from sub-device sensors (`SmartMeter_{SN}_{key}`).
  - `jackery_main_{key}` entities now correctly migrate to `jackery_{sn}_switch_{key}` (switches)
    or `jackery_{sn}_number_{key}` (numbers) by inspecting the `entity_id` platform prefix.
  - Conflict handling: if target unique_id already exists (created fresh by v2.0.1), the old
    orphaned entity is deleted. `jackery_{sn}_main_*` entities (v2.0.1 migration residue) deleted.

### Added

- **Max Feed-in Power select: 1200 W option** for SV3 Pro (non-Max) — resolves Issue #5.
  New option key `w1200` added to `_MAX_FEED_IN_OPTIONS` and all translation files
  (`strings.json`, `en.json`, `de.json`, `fr.json`).

---

## Changes in v2.0.1 – jackery_home_power negative values fix

### Fixed

- **`jackery_home_power` could show negative values**: The base formula
  `p_home = p_grid - p_ong` can temporarily yield a negative result when the SmartMeter
  (type-101) and SolarVault (type-2) are sampled at different moments — e.g. when
  `grid_sell` momentarily exceeds `ongrid_supply` due to asynchronous sensor updates.
  House loads are physically never negative; any negative result is a measurement artefact.
  Added `p_home = max(0.0, p_home)` clamp after all formula branches in
  `_calculate_energy_flow`. Grid charging (`inOngridPw > 0`) is correctly handled by the
  formula itself and does not produce negative values.

---

## Changes in v2.0.0 – Upstream Merge (based on Jackery-Official/jackery v2.0.0)

**Branch:** `feature/v2.0.0-upstream-merge`  
**Analysis source:** `DIFF_ORG_FORK_2.0.0.md` (in repo root, not committed to git)

---

### Implemented (ÜBERNEHMEN)

| # | Change | Files | Notes |
|---|---|---|---|
| Ü1 | Device-SN isolation: early `return` in `_handle_message` when SN doesn't match | `sensor.py` | Harmless in single-device setups, required for multi-device |
| Ü2 | `_capture_device_meta()`: extracts `deviceType` + `softver` from MQTT body | `sensor.py` | Triggers `_update_device_registry()` via `asyncio.create_task` |
| Ü3 | `_update_device_registry()`: writes model (`DIY3`) + firmware version to HA device card | `sensor.py` | Uses `DEVICE_TYPE_MODEL_MAP = {3: "DIY3"}` |
| Ü4 | Constants: `DEVICE_TYPE_MODEL_MAP`, `DEFAULT_MODEL`, `DEVICE_STATUS_MAP`, `ONGRID_STATUS_MAP`, `CT_STATUS_MAP`, `GRID_METER_LINK_MAP` | `sensor.py` | Status maps used by value_map ENUM sensors |
| Ü5 | ENUM `device_class` for `device_status`, `ongrid_status`, `ct_status`, `grid_meter_link` | `sensor.py` | Added `options` + `value_map` to SENSOR_TYPES; update path uses `value_map` branch |
| Ü6 | `_subdevice_sn(item)` helper function | `sensor.py` | Replaces inline `.get("deviceSn") or .get("sn")` calls |
| Ü7 | Initial poll before first sleep in `_periodic_data_request` | `sensor.py` | 2 s delay, then poll; accelerates data availability after HA start/reload |
| Ü8 | Multi-Instance: `async_set_unique_id(device_sn)` + `_abort_if_unique_id_configured()` | `config_flow.py` | Entry title: `f"Jackery {device_sn}"` |
| — | Unique-ID migration: `_migrate_unique_ids()` in `__init__.py` | `__init__.py` | Migrates `jackery_{sensor_id}` → `jackery_{device_sn}_{sensor_id}` on upgrade; preserves HA history |
| — | Device-registry migration: `DOMAIN, entry_id` identifier → `DOMAIN, device_sn` | `__init__.py` | Runs in same `_migrate_unique_ids()` function |
| — | Unique-IDs updated everywhere to `jackery_{device_sn}_*` | `sensor.py`, `select.py`, `switch.py`, `number.py`, `button.py` | Via `coordinator._device_sn` |
| — | Re-Auth flow: `async_step_reauth` + `async_step_reauth_confirm` | `config_flow.py` | Triggered by type-123/401 MQTT message |
| — | `_trigger_reauth()` + `_reauth_started` flag in coordinator | `sensor.py` | Fires `hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_REAUTH}, ...)` |
| — | Type-123 handler in `_handle_message` | `sensor.py` | `errorCode == 401` → `_trigger_reauth()` |
| — | `reauth_confirm` strings in all translation files | `strings.json`, `en.json`, `de.json`, `fr.json` | Also removed `single_instance_allowed` |
| — | New sensor `max_feed_grid_power` (json_key: `maxFeedGrid`) | `sensor.py`, translations | Read-only, from type-106; confirmed distinct from `maxOutPw` via live MQTT capture |
| B1 | Fix `JackeryAutoStandbySelect.async_select_option`: added optimistic cache update | `select.py` | Missing since v1.3.0; now follows the v1.3.1 pattern like WorkMode/MaxFeedIn selects |

### PRÜFEN items — deferred or rejected after investigation

| # | Change | Decision | Reason |
|---|---|---|---|
| P1 | Re-Auth flow | **Implemented** (see above) | — |
| P2 | `maxFeedGrid` sensor | **Implemented** (see above) | Live MQTT confirmed `maxFeedGrid`=800 ≠ `maxOutPw`=2500 |
| P3 | Dynamic SOC limits (`minSocChg`/`maxSocChg`) | **Not implemented** | Fields not observed in any MQTT capture on our hardware |
| P4 | `_effective_ongrid_net()` multi-source prioritization | **Not implemented** | `gridSidePw` always 0 on our hardware; no benefit without the Branch A/B bugs we fixed in v1.1.70 |
| P5 | Type-2 poll request in addition to type-25 | **Not implemented** | Could not verify if it delivers additional data (no device token available for testing); type-25 sufficient in practice |
| P6 | PascalCase aliases in CT parsing (`AphasePw` etc.) | **Not implemented** | SmartMeter HTO907A sends camelCase only (confirmed by live MQTT capture); not needed for `ct_3phase` group |
| P7 | `_entity_keys_for_subdevice()` / `_set_subdevice_available()` helper methods | **Not implemented** | Code-quality improvement only; our existing availability logic is correct and well-tested |
| P8 | SN-specific MQTT topic subscription | **Not implemented** | No difference in single-device setup; wildcard subscription works correctly |
| P9 | Re-Auth strings | **Implemented** (part of P1) | — |

### ABLEHNEN items — intentionally not adopted

| Change | Reason |
|---|---|
| `REQUEST_INTERVAL = 5 s` | Documented: we use 10 s. Sufficient for homelab, less MQTT traffic. |
| `_normalize_payload_fields()` | Our type-106 handler already aliases `workModel`→`workMode` directly. |
| Type-102 handler | Not observed on our hardware (SolarVault 3 Pro Max). |
| Type-107 handler | Not observed on our hardware. |
| commMode validation for plug switches | No smart plugs in our setup. |
| `_calculate_energy_flow` (Branch A + Branch B) | **Bugs in upstream** — we removed these in v1.1.70 with the correct base formula `p_home = p_grid - p_ong`. Do **not** re-introduce. |
| `grid_import_power` → `gridInPw` (type-106) | Our mapping to `inOngridPw` (type-2, ~11 s cadence) gives better real-time data. The type-106 fields are already exposed as `grid_in_power`/`grid_out_power`. |
| `_attr_name` instead of `_attr_translation_key` | Upstream uses hardcoded strings (not translatable). Our translation-key approach is correct. |
| Switches/numbers without optimistic cache update | **Revert bug in upstream** — state reverts to old value after next MQTT event. Our v1.3.1 fix must stay. |
| `maxOutPw` as free-range Number slider (0–2500 W) | Our Select approach (800/2500 W only) prevents invalid values and matches app behavior. |
| `average_soc` rename | Upstream calls `soc` → `average_soc`; we call it `bms_soc`. No functional difference; keeping our name avoids breaking entity IDs. |
| `CT_SUBTYPE_MAP` / `FUNC_ENABLE_BITS` / `COMM_MODE_*` constants | Metadata/debug constants not needed for functional sensor logic. |
| devType-based replace for sub-device cache (vs. our SN-based merge) | Our merge approach correctly handles expansion batteries (type-23) and prevents the cache-clear flapping fixed in v1.2.0. |
| Re-Auth timeout heuristic (`_ever_received`) | Too aggressive for our setup; type-25 poll response is reliable. Only the explicit type-123/401 trigger is implemented. |

---

## CI / Development Tooling

### Dependency management

`uv` with `pyproject.toml` dependency groups:

```bash
uv sync --group test   # pytest, pytest-asyncio, pytest-homeassistant-custom-component, pytest-cov
uv sync --group lint   # ruff, mypy
```

### Running checks locally

```bash
uv run pytest tests/ -v                         # tests + coverage (threshold 30 %)
uv run ruff check custom_components/jackery/    # linter (E, F, I, W, UP; line-length 120)
uv run mypy custom_components/jackery/          # type checker
python tools/check_translations.py             # translation completeness
```

### GitHub Actions jobs (`.github/workflows/validate.yml`)

| Job | Steps |
|-----|-------|
| `lint` | Ruff check, mypy, `tools/check_translations.py` |
| `tests` | `pytest tests/ -v` with coverage (fail-under=30) |
| `validate` | HACS validation, Hassfest validation |

### Ruff configuration

Rules: E, F, I, W, UP — ignoring E501 (line length), UP007, UP035.
`known-first-party = ["custom_components.jackery"]` for import sorting.

### mypy configuration

`ignore_missing_imports = true` — HA's dynamic typing causes false positives otherwise.
`warn_return_any = false`, `warn_unused_ignores = false`.

### Translation check (`tools/check_translations.py`)

Compares each `translations/*.json` against `strings.json` (base). Reports MISSING keys as
errors (exit 1) and EXTRA keys as warnings. `translations/zh-Hans.json` was removed —
the upstream original had 143 missing keys (all new entities) and would confuse Chinese-locale users.

### Integration tests (`tests/test_config_flow.py`)

Uses `pytest-homeassistant-custom-component` (provides `hass` fixture, `enable_custom_integrations`).
Patches `homeassistant.components.mqtt.async_wait_for_mqtt_client` — no real MQTT broker needed.
4 tests: form display, successful entry creation, duplicate-SN abort, MQTT-not-configured error.

### Dependabot (`.github/dependabot.yml`)

Weekly Monday updates for GitHub Actions (`package-ecosystem: "github-actions"`).

---

## Repository

- **This fork**: https://github.com/csoscd/ha-solarvault
- **Original**: https://github.com/Jackery-Official/jackery
- **HACS install**: Add `https://github.com/csoscd/ha-solarvault` as custom repository
