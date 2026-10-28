# Jackery SolarVault – Local MQTT Protocol Reference

This document describes the local MQTT protocol used by the Jackery SolarVault 3 series (tested on
SolarVault 3 Pro Max, firmware BEMS0002). All observations are from live MQTT captures unless
otherwise noted. Fields marked *APK* are from decompiled Jackery App v2.4.1 source.

---

## 1. Communication Basics

### 1.1 Broker & Topic Structure

Default topic prefix: `hb`

```
{prefix}/device/{DEVICE_SN}/status   ← device → broker  (status & energy data)
{prefix}/device/{DEVICE_SN}/event    ← device → broker  (sub-device data)
{prefix}/device/{DEVICE_SN}/alert    ← device → broker  (fault/alarm events)
{prefix}/device/{DEVICE_SN}/action   → broker → device  (commands & poll requests)
```

### 1.2 Message Envelope

Every message is a JSON object with the following wrapper:

```json
{
  "type": 2,
  "eventId": 0,
  "messageId": 4567,
  "ts": 1695347700,
  "token": "YOUR_TOKEN",
  "body": { ... },
  "deviceType": 3,
  "softver": 1001
}
```

| Field | Description |
|-------|-------------|
| `type` | Message type code (see §2) |
| `token` | Local auth token — must match the value stored on the device (obtained from Jackery app → device settings → MQTT). **Static** — does not rotate during normal operation. |
| `body` | Message payload |
| `deviceType` | Device class: `1`=Battery Pack, `2`=CT/Meter, `3`=DIY3 (SolarVault 3), `4`=Meter Collector |
| `softver` | Firmware version number |

**Token rejection:** The device does **not** send an error response when the token is wrong — it
simply ignores the command. Only a `type=123 / errorCode=401` message indicates a token mismatch,
and this is sent only occasionally (not on every rejected command).

---

## 2. Message Type Codes

| Type | Direction | Topic | Description | Cadence |
|------|-----------|-------|-------------|---------|
| 1 | HA → device | action | Control command (cmd 5) | on demand |
| 2 | device → HA | status | Full device status | ~11 s |
| 23 | device → HA | status/event | Cumulative energy statistics | ~10 min |
| 25 | HA → device | action | Poll request for type-2 status | ~11 s |
| 100 | HA → device | action | Poll request for sub-device list | ~11 s |
| 101 | device → HA | event | Sub-device full list (CTs, plugs) | ~11 s |
| 102 | device → HA | event | Sub-device incremental update | not observed on SV3 Pro Max |
| 103 | HA → device | action | Sub-device switch control | on demand |
| 105 | HA → device | action | Full system state poll | ~30 s |
| 106 | device → HA | status | Full system state response | on demand (reply to type-105) |
| 107 | device → HA | status | Incremental SOC/workMode update | not observed on SV3 Pro Max |
| 123 | device → HA | status | Auth error notification | on token mismatch |

---

## 3. Type 2 — Device Status

Sent approximately every **11 seconds** on the `/status` topic. Contains all real-time operational data.

### 3.1 Battery

| Field | Unit | Description |
|-------|------|-------------|
| `batSoc` | % | SOC of the main unit (SolarVault host) |
| `soc` | % | Combined BMS SOC across all battery units (main + expansion) |
| `batInPw` | W | Charge power — **main unit only** (does NOT include expansion batteries like BP2500) |
| `batOutPw` | W | Discharge power — **main unit only** |
| `cellTemp` | 0.1 °C | Cell temperature (raw value 250 = 25.0 °C) |
| `batNum` | – | Number of connected expansion battery packs |
| `batState` | – | Battery state: `0`=transitioning, `1`=charging (normal), `2`=active discharge |

> **Note on `batInPw`/`batOutPw`:** These reflect only the host unit's ADC measurement (BEMS0002 STM32H7).
> The BP2500's power is tracked by the BP2500's own Coulomb Counter and is **not** included in
> these fields — they can diverge by 200–300 W when the expansion pack is actively charging.

### 3.2 Solar (PV)

| Field | Unit | Description |
|-------|------|-------------|
| `pvPw` | W | Total combined PV input power |
| `pv1`–`pv4` | dict | Per-string: `{"pvPw": W, "commState": 0/1}`. `commState=1` = string active |

### 3.3 Grid (OnGrid)

| Field | Unit | Description |
|-------|------|-------------|
| `inOngridPw` | W | Power drawn from the grid |
| `outOngridPw` | W | Power output to the **house AC bus** via the OnGrid port (NOT net public-grid export) |
| `maxOutPw` | W | Configured max output to house AC bus (800 W / 1200 W / 2500 W); writable via cmd=5 |
| `maxFeedGrid` | W | Configured max export to the **public grid** (e.g. 800 W legal limit); distinct from `maxOutPw` |
| `maxInvStdPw` | W | Max inverter standby power |
| `maxGridStdPw` | W | Max grid standby power |

### 3.4 EPS (Off-grid / AC Socket)

| Field | Unit | Description |
|-------|------|-------------|
| `swEpsInPw` | W | EPS/AC Socket input power |
| `swEpsOutPw` | W | EPS/AC Socket output power |
| `swEpsState` | – | EPS state: `1`=normal, `0`=fault |
| `swEps` | – | EPS switch: `1`=on, `0`=off |

### 3.5 Inverter Stack

| Field | Unit | Description |
|-------|------|-------------|
| `stackInPw` | W | Power flowing into the inverter stack (AC side) |
| `stackOutPw` | W | Power flowing out of the inverter stack (AC side) |

### 3.6 Settings (readable; writable via type-1/cmd-5)

| Field | Unit | Description |
|-------|------|-------------|
| `socChgLimit` | % | SOC charge upper limit |
| `socDischgLimit` | % | SOC discharge lower limit |
| `autoStandby` | – | Auto-standby: `0`=invalid, `1`=standby/sleep, `2`=on |
| `isAutoStandby` | – | Auto-standby allowed: `1`=yes, `0`=no |
| `socForceChg` | – | Force Charge flag: **binary 0/1** (not a %). Sent together with SOC limits. (*APK*) |

### 3.7 Network / Diagnostics

| Field | Unit | Description |
|-------|------|-------------|
| `ethPort` | – | Ethernet connected: `1`=yes, `0`=no |
| `wsig` | dBm | WiFi signal strength |
| `wname` | str | WiFi SSID (empty when Ethernet active) |
| `eip` | str | Ethernet IP address |
| `emac` | str | Ethernet MAC address |
| `wip` | str | WiFi IP address of the SolarVault main unit |
| `ability` | – | Capability bitmask. Known bits (*APK*): Bit 8=chart feature, Bit 9=max output power visible, Bit 10=accessory panel, Bit 11=Force Charge feature (socForceChg toggle). Observed: `768`=bits 8+9, `3840`=bits 8+9+10+11 |
| `maxIotNum` | – | Maximum number of IoT sub-devices |

### 3.8 Status Fields (also present in type-106)

These fields can appear in both type-2 and type-106 responses. The full type-106 set is documented
in §5.1; they are listed here because they can arrive via the more frequent type-2 cycle as well.

| Field | Description |
|-------|-------------|
| `stat` | Device status: `0`=normal, `1`=waiting, `2`=alarm, `3`=fault, `4`=standby, `5`=low_power |
| `workMode` / `workModel` | Operating mode integer — see §9 for mapping |
| `ongridStat` | OnGrid status: `1`=connected, `0`=disconnected |
| `ctStat` | CT/SmartMeter status: `1`=online, `0`=offline |
| `gridSate` | Grid meter link: `1`=linked, `0`=not linked |
| `otherLoadPw` | W — Estimated home load (mirrors SmartMeter reading when CT available) |
| `maxFeedGrid` | W — Max export to public grid |

### 3.9 Additional Fields (post-firmware 2026-07)

| Field | Unit | Description |
|-------|------|-------------|
| `inCtEgy` | ×0.01 kWh | Cumulative system-level CT import energy |
| `outCtEgy` | ×0.01 kWh | Cumulative system-level CT export energy |

---

## 4. Type 23 — Energy Statistics

Sent approximately every **10 minutes** on the `/status` or `/event` topic. Values require a scale
factor of **×0.01** to convert to kWh.

> **TOTAL_INCREASING:** HA's `TOTAL_INCREASING` state class handles these correctly — it only tracks
> increases from first observation. Non-zero values at commissioning (from factory testing) are safe.
>
> **Observation (2026-09-17):** Each ~10-min cycle sends two consecutive packets for the main device —
> first without `deviceSn`, then with `deviceSn="system"`. Both contain identical fields. The
> no-`deviceSn` packet is handled via the existing fallback path.

### 4.1 Main Device (`deviceSn="system"`)

| Field | kWh (×0.01) | Description |
|-------|-------------|-------------|
| `pvEgy` | kWh | Total solar energy |
| `pv1Egy`–`pv4Egy` | kWh | Per-string solar energy |
| `batChgEgy` | kWh | Battery charge energy |
| `batDisChgEgy` | kWh | Battery discharge energy |
| `inOngridEgy` | kWh | Grid import energy |
| `outOngridEgy` | kWh | Grid export energy |
| `inEpsEgy` | kWh | EPS input energy |
| `outEpsEgy` | kWh | EPS output energy |
| `pvOtBatEgy` | kWh | PV → Battery |
| `pvOtAcEgy` | kWh | PV → AC load |
| `pvOtOngridEgy` | kWh | PV → Grid |
| `ongridOtAcLoadEgy` | kWh | Grid → AC load |
| `batOtAcEgy` | kWh | Battery → AC |
| `batOtGridEgy` | kWh | Battery → Grid |
| `ongridOtBatEgy` | kWh | Grid → Battery |
| `acOtBatEgy` | kWh | AC → Battery |
| `acOtOngridEgy` | kWh | AC → Grid |

### 4.2 SmartMeter 3P HTO907A (`devType=3`, `subType=5`)

| Field | kWh (×0.01) | Description |
|-------|-------------|-------------|
| `tPhaseEgy` | kWh | Total import energy |
| `tnPhaseEgy` | kWh | Total export energy |
| `aPhaseEgy`–`cPhaseEgy` | kWh | L1–L3 import energy |
| `anPhaseEgy`–`cnPhaseEgy` | kWh | L1–L3 export energy |

### 4.3 BP2500 Expansion Battery (`devType=1`, `subType=0`)

| Field | kWh (×0.01) | Description |
|-------|-------------|-------------|
| `inEgy` | kWh | Cumulative energy charged into BP2500 |
| `outEgy` | kWh | Cumulative energy discharged from BP2500 |

Both values come directly from the BP2500's on-board Coulomb Counter — fully reliable. Individual
BP2500 SOC (`tSoc`) is transmitted internally to the main unit via CAN1/NORTH bus and merged into
the combined `soc` field; it is **never published separately via MQTT** (architectural firmware
decision, not a missing feature).

---

## 5. Type 106 — Full System State

Response to a type-105 poll request. Contains additional fields not in type-2.

### 5.1 Status Fields

| Field | Description |
|-------|-------------|
| `stat` | Device status: `0`=normal, `1`=waiting, `2`=alarm, `3`=fault, `4`=standby, `5`=low_power |
| `ongridStat` | OnGrid status: `1`=connected, `0`=disconnected |
| `ctStat` | CT/SmartMeter status: `1`=online, `0`=offline |
| `gridSate` | Grid meter link: `1`=linked, `0`=not linked |

### 5.2 Power Fields (additional to type-2)

| Field | Unit | Description |
|-------|------|-------------|
| `gridInPw` / `gridBuyPw` | W | Grid import power (mirrors `inOngridPw` in type-2) |
| `gridOutPw` / `gridSellPw` | W | Grid export power (mirrors `outOngridPw`) |
| `otherLoadPw` | W | Estimated home load (mirrors SmartMeter reading when CT available) |
| `inGridSidePw` | W | Grid-side input power (third measurement point; always 0 on SV3 Pro Max) |
| `outGridSidePw` | W | Grid-side output power (same) |

### 5.3 Settings Fields (additional to type-2)

| Field | Description |
|-------|-------------|
| `workModel` | Operating mode (normalized to `workMode` in integration); see §9 |
| `defaultPw` | Fallback output power for Custom mode (W); writable |
| `energyPlanPw` | Active schedule output power (mirrors `defaultPw` when no schedule active; read-only) |
| `isFollowMeterPw` | Follow-meter sub-mode within workModel=4: `1`=on, `0`=off; writable |
| `offGridDown` | Off-grid fallback enable: `1`=on, `0`=off; writable |
| `offGridTime` | Off-grid fallback delay in seconds (read-only, `120` on SV3 Pro Max) |
| `standbyPw` | Standby power consumption (W) |
| `pvMaxChgPower` | Max PV charge power (dynamic: 0 when no PV active, 4000 W with 4 strings) |
| `maxSysOutPw` | Max system output power — mirrors `maxOutPw` setting |
| `maxSysInPw` | Max system input power — fixed hardware spec (2500 W on SV3 Pro Max) |
| `isAutoStandby` | Auto-standby allowed: `1`=yes |
| `maxFeedGrid` | Max export to public grid (W); writable |
| `chargePlanPw` | Scheduled charge power (cloud-only; always `0` locally) |
| `wps` | Storm Warning switch (cloud-only; always `0` locally) |
| `wpc` | Storm Warning plan count (cloud-only; always `0` locally) |
| `funcEnable` | Feature enable bitmask (see §6) |

---

## 6. `funcEnable` Bitmask

The `funcEnable` field in type-106 responses is a 32-bit bitmask. Bits 0–11 are documented below
(source: upstream LOCAL_PROTOCOL.md + APK decompile). Bit 31 is always set on the SV3 Pro Max
(value `2147483648`) and its meaning is unknown.

| Bit | Name | Description |
|-----|------|-------------|
| 0 | `aerosol` | Aerosol function |
| 1 | `soc_calibration` | SOC calibration in progress |
| 2 | `low_power` | Low power mode active |
| 3 | `soh_calibration` | SOH calibration in progress |
| 4 | `pcs_comm_diag` | PCS communication diagnostic |
| 5 | `shutdown_2h` | 2-hour shutdown scheduled |
| 6 | `fault_shutdown` | Fault shutdown active |
| 7 | `epo` | Emergency Power Off active |
| 8 | `func_48v` | 48 V function enabled |
| 9 | `ethernet_debug` | Ethernet debug mode |
| 10 | `energy_flow_fill` | Energy flow data backfill active |
| 11 | `smart_plug_first` | Smart plug priority mode |
| 31 | *(unknown)* | Always set on SV3 Pro Max |

The integration exposes `funcEnable` as the `func_enable` sensor and decodes all 12 known bits as
entity attributes (`func_enable_flags`). Access via HA template:

```yaml
{{ state_attr('sensor.jackery_YOURDEVICE_func_enable', 'func_enable_flags').fault_shutdown }}
```

---

## 7. Type 101 — Sub-device Event Data

### 7.1 CT Sub-device Types (`subType`)

| `devType` | `subType` | Device |
|-----------|-----------|--------|
| 3 | 1 | Shelly 1P |
| 3 | 2 | Shelly 3P |
| 3 | 5 | Jackery SmartMeter 3P / HTO907A |
| 3 | 6 | Jackery US |

Only `subType=5` (HTO907A) is confirmed by live observation. Others are from upstream documentation.

### 7.2 SmartMeter 3P / HTO907A (`devType=3`, `subType=5`)

All power fields are in **Watts** and are non-negative. The meter decomposes net phase power into
separate import/export values.

| Field | Description |
|-------|-------------|
| `aPhasePw` / `bPhasePw` / `cPhasePw` | L1–L3 import power (W) |
| `tPhasePw` | Total net import power (W) — `max(0, net_total)` |
| `anPhasePw` / `bnPhasePw` / `cnPhasePw` | L1–L3 export power (W) |
| `tnPhasePw` | Total net export power (W) — `max(0, -net_total)` |
| `commState` | Communication state: `1`=online, `0`=offline |
| `commMode` | Communication path: `1`=LAN (measurements available), `2`=Cloud relay (measurements absent) |
| `wip` | SmartMeter IP address on the local network |
| `bindKey` | Static binding key (metadata only) |
| `schePhase` | Phase scheme (`4`=dual-circuit) |

> **`commMode` switching:** After internet outages the SmartMeter may switch autonomously from
> LAN (1) to Cloud relay (2). In Cloud mode all power fields are absent; `commState` stays 1.
> Only a SolarVault reboot restores LAN mode. `commMode` cannot be changed via MQTT.

> **PascalCase aliases:** Some firmware versions send `TphasePw` / `AphasePw` etc. (PascalCase)
> instead of the camelCase variants above. Both are semantically equivalent.

### 7.3 Smart Plug (`devType=6`)

| Field | Description |
|-------|-------------|
| `deviceSn` / `sn` | Sub-device serial number |
| `outPw` / `power` | Current power (W) |
| `totalEgy` | Cumulative energy (×0.01 kWh) |
| `switchSta` / `sysSwitch` | Switch state: `1`=on, `0`=off |
| `commState` | Communication state: `1`=online |
| `commMode` | `1`=LAN (switch commands work), `2`=Cloud (commands ignored) |

---

## 8. Control Commands

### 8.1 Main Device Settings (type 1, cmd 5)

```json
{
  "type": 1,
  "eventId": 3,
  "messageId": 4567,
  "ts": 1695347700,
  "token": "YOUR_TOKEN",
  "body": {
    "cmd": 5,
    "rc": 1,
    "<parameter>": <value>
  }
}
```

Device acknowledges successful writes with a `cmd=107` response.

**Writable parameters (all confirmed with cmd=107 ack):**

| Parameter | Type | Notes |
|-----------|------|-------|
| `socChgLimit` | 0–100 % | SOC charge upper limit |
| `socDischgLimit` | 0–100 % | SOC discharge lower limit |
| `maxOutPw` | W | Max output to house AC bus: `800`, `1200`, or `2500` |
| `maxFeedGrid` | W | Max export to public grid |
| `autoStandby` | 0/1/2 | `0`=invalid, `1`=standby, `2`=on |
| `isAutoStandby` | 0/1 | Allow auto-standby |
| `swEps` | 0/1 | EPS/AC Socket switch |
| `socForceChg` | 0/1 | Force Charge: binary flag, sent together with SOC limits |
| `reboot` | 1 | Trigger device reboot |
| `workModel` | int | Operating mode (see §9) |
| `defaultPw` | W | Default output power for Custom mode |
| `isFollowMeterPw` | 0/1 | Follow-meter sub-mode within workModel=4 |
| `offGridDown` | 0/1 | Off-grid fallback enable |

### 8.2 Sub-device Switch (type 103)

```json
{
  "type": 103,
  "eventId": 0,
  "messageId": 4567,
  "ts": 1695347700,
  "token": "YOUR_TOKEN",
  "body": {
    "deviceSn": "<plug_sn>",
    "devType": 6,
    "sysSwitch": 1
  }
}
```

**Only effective when the plug's `commMode == 1` (LAN).** If `commMode == 2`, the command is ignored.

### 8.3 Poll Requests

**Device status (type 25):**
```json
{"type": 25, "eventId": 0, "messageId": 4567, "ts": <ts>, "token": "<token>", "body": null}
```

**Sub-device list (type 100):**
```json
{"type": 100, "eventId": 0, "messageId": 4567, "ts": <ts>, "token": "<token>", "body": {"devType": 3}}
```
`devType`: `2`=CT discovery (metadata only, no power fields), `3`=SmartMeter real-time data, `6`=smart plugs.

**Full system state (type 105):**
```json
{"type": 105, "eventId": 0, "messageId": 4567, "ts": <ts>, "token": "<token>", "body": null}
```
Device responds with type-106.

### 8.4 Third-Party MQTT Config (type 1, cmd 113/114) — *APK*

| cmd | Purpose |
|-----|---------|
| 113 | Set third-party local MQTT broker config |
| 114 | Query third-party local MQTT broker config |

### 8.5 Commands That Do NOT Work Locally

| Command | Reason |
|---------|--------|
| Storm Warning (`wps`, `SendWeatherAlert`) | Cloud/BLE only (`bleMsgType=0`); MQTT ignored |
| Time-based schedules | Cloud-managed exclusively |
| KI strategy selection | Cloud-managed exclusively |
| SmartMeter `commMode` switch | Device decides autonomously; no MQTT interface |

---

## 9. Operating Modes (`workModel`)

Fully mapped via live MQTT capture (2026-07-16).

| `workModel` | App Name | Notes |
|-------------|----------|-------|
| 2 | Self-Consumption | Solar-first; battery covers loads; grid export when full. With SmartMeter: adapts to actual consumption. |
| 4 | Custom | Fixed `defaultPw` or schedule (cloud). `isFollowMeterPw=1` = follow-meter mode. |
| 7 | Tariff | Tariff periods/prices are cloud-only |
| 8 | AI Mode | All sub-strategies (balanced, arbitrage, …) report `workModel=8` locally |

**`workModel=4` with `isFollowMeterPw=1` (Follow-meter):** Output power = SmartMeter import reading
1:1 at every moment. Purely reactive; no battery strategy or solar-first logic.

---

## 10. SmartMeter HTO907A — Local HTTP API

The SolarVault **polls** the SmartMeter over HTTP (Pull model — confirmed via packet capture
2026-08-13). The SmartMeter does **not** push data.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/device_info` | GET | Device metadata: `name` (`"JA-IOT3PA"`), `type` (4003), `sn`, `version`, `ssid`, `rssi`, `mac`, `ip` |
| `/api/measurement` | GET | Full 3-phase real-time data (polled every ~2 s by SolarVault) |

**`/api/measurement` fields:**

| Field | Unit | Description |
|-------|------|-------------|
| `volt1/2/3` | V | Per-phase voltage |
| `curr1/2/3` | A | Per-phase current |
| `power1/2/3` | W | Per-phase active power (**negative = export**) |
| `power` | W | Total active power |
| `rep1/2/3` | VAr | Per-phase reactive power |
| `ap1/2/3` | VA | Per-phase apparent power |
| `fact1/2/3` | ×0.001 | Per-phase power factor |
| `freq` | Hz | Grid frequency |
| `engy1/2/3` / `engy` | kWh | Cumulative import energy |
| `engyo1/2/3` / `engyo` | kWh | Cumulative export energy |
| `sc` | – | Status code |
| `ts` | Unix | Timestamp |

Port 80, no authentication, HTTP only.

---

## 11. Energy Flow Calculation

### 11.1 Variables

| Variable | Source | Sign convention |
|----------|--------|-----------------|
| `pv` | `pvPw` | positive = generating |
| `ongrid_charge` | `inOngridPw` | positive = grid charging unit |
| `ongrid_supply` | `outOngridPw` | positive = unit supplying AC bus |
| `p_ong` | `ongrid_charge − ongrid_supply` | positive = net grid→unit |
| `grid_buy` | `tPhasePw` (CT) | net import (W, ≥ 0) |
| `grid_sell` | `tnPhasePw` (CT) | net export (W, ≥ 0) |
| `p_grid` | `grid_buy − grid_sell` | positive = import |

### 11.2 Grid Net Power (`p_grid`) — Source Priority

Three sources are tried in order:

| Priority | Condition | Formula |
|----------|-----------|---------|
| 1 | CT online and data available | `p_grid = tPhasePw − tnPhasePw` |
| 2 | `inGridSidePw` or `outGridSidePw` non-zero | `p_grid = inGridSidePw − outGridSidePw` |
| 3 | Fallback | `p_grid = gridInPw − gridOutPw`  or  `inOngridPw − outOngridPw` |

The CT-based value (priority 1) is preferred because it measures actual public-grid flow.
`outOngridPw` is the SolarVault's AC output to the **house bus**, not the net public-grid export.

### 11.3 Home Power Formula

```
p_home = p_grid − p_ong
       = (grid_buy − grid_sell) − (ongrid_charge − ongrid_supply)
```

This holds for all scenarios including phase-balanced export. Example:
- L1: 158 W load → `tPhasePw=158`, `tnPhasePw=0`
- L3: 100 W load + 270 W SolarVault output → net L3 export 170 W
- `p_grid = (158+0) − (0+170) = −12 W`  (net export)
- `p_ong = 0 − 270 = −270 W`
- `p_home = −12 − (−270) = 258 W` ✓

Without CT data: `p_home = ongrid_supply` (rough estimate only).

### 11.4 Battery Net Power (`p_batt`)

```
# Direct (preferred):
p_batt = batInPw − batOutPw

# Fallback when direct fields unavailable:
p_batt = pvPw + (swEpsInPw − swEpsOutPw) + (gridInPw − gridOutPw)
```

Positive = net charging, negative = net discharging. Note that `batInPw`/`batOutPw` cover the
**main unit only** — the BP2500 expansion battery's contribution is not included (see §12).

---

## 12. Known Limitations & Observations

| Topic | Observation |
|-------|-------------|
| **BP2500 real-time power** | Not exposed via MQTT. Only cumulative `inEgy`/`outEgy` (type-23) are available. |
| **BP2500 individual SOC** | Merged into combined `soc` by the BEMS controller. Never published separately — firmware design decision. |
| **`batInPw` scope** | Main unit only (BEMS0002 ADC path). Diverges from total battery power by BP2500 contribution. |
| **Type-23 forward spikes** | Device occasionally sends unrealistically large jumps (e.g. +8.88 kWh in 10 min). These are not counter resets. HA's `TOTAL_INCREASING` cannot filter them. Correct manually in HA Statistics. |
| **`batState` semantics** | `0`=transitioning (appears at 100% charge completion AND post-discharge settling), `1`=normal charging, `2`=active discharge |
| **Type 102 / 107** | Not observed on SV3 Pro Max. May require different firmware. |
| **`funcEnable` bit 31** | Always set on SV3 Pro Max (value `2147483648`). Meaning unknown. |
| **SmartMeter `commMode`** | Switches from LAN→Cloud autonomously after internet outages. Only SolarVault reboot restores LAN mode. Cannot be forced via MQTT. |
| **Time-based schedules** | `wps`, `wpc`, `chargePlanPw` always `0` locally; schedules are cloud-managed. |
| **KI mode sub-strategies** | All sub-strategies (Balanced, Arbitrage, …) report identical `workModel=8` locally. |
