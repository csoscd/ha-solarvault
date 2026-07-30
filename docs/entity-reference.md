# Jackery SolarVault – Entity Reference

This document answers the most common question when setting up dashboards:
**which sensor should I use for what?**

## Entity ID naming convention

Entity IDs follow this pattern:

```
{domain}.jackery_{sn_lowercase}_{entity_display_name_slug}
```

Example: device SN `HS2C12600262HH4` → prefix `jackery_hs2c12600262hh4`

The slug is derived from the entity **display name** (not the internal `sensor_id`).
For example, `Battery Charge Power (Calc)` → `battery_charge_power_calc`.

Find all your entity IDs under **Developer Tools → States** (search for `jackery`),
or under **Settings → Devices & Services → Jackery → your device → entity list**.

---

## Quick start: sensors for a simple energy dashboard

### Real-time power (W)

| What you need | Entity name | entity_id | Notes |
|---|---|---|---|
| Solar production | Solar Power | `sensor.jackery_{sn}_solar_power` | Combined PV input |
| Grid draw | Grid Import Power | `sensor.jackery_{sn}_ct_3phase_import_total` | **SmartMeter** — preferred ¹ |
| Grid feed-in | Grid Export Power | `sensor.jackery_{sn}_ct_3phase_export_total` | **SmartMeter** — preferred ¹ |
| Battery charging | Battery Charge Power (Calc) | `sensor.jackery_{sn}_battery_charge_power_calc` | Covers all battery units |
| Battery discharging | Battery Discharge Power (Calc) | `sensor.jackery_{sn}_battery_discharge_power_calc` | Covers all battery units |
| Battery state of charge | BMS SOC | `sensor.jackery_{sn}_bms_soc` | Combined SOC across all units ² |
| Home consumption | Home Power | `sensor.jackery_{sn}_home_power` | Calculated |
| EPS output | EPS Output Power | `sensor.jackery_{sn}_eps_output_power` | Off-grid socket |

### Cumulative energy (kWh) — HA Energy Dashboard slots

| Dashboard slot | Entity name | entity_id | Notes |
|---|---|---|---|
| Solar production | Solar Energy | `sensor.jackery_{sn}_solar_energy` | — |
| Grid consumption | Grid Import Energy | `sensor.jackery_{sn}_ct_3phase_import_energy_total` | **SmartMeter** — preferred ¹ |
| Grid return | Grid Export Energy | `sensor.jackery_{sn}_ct_3phase_export_energy_total` | **SmartMeter** — preferred ¹ |
| Battery charge | Battery Charge Energy | `sensor.jackery_{sn}_battery_charge_energy` | — |
| Battery discharge | Battery Discharge Energy | `sensor.jackery_{sn}_battery_discharge_energy` | — |

> ¹ **Why prefer SmartMeter sensors for grid?**
> The SolarVault also exposes `Grid Import Power` / `Grid Export Power` (from `inOngridPw` / `outOngridPw`).
> These measure power flow at the SolarVault's own grid connection — **not** total house consumption.
> The SmartMeter 3P sits at the main meter point and measures everything, making it the correct
> source for grid billing-equivalent figures and the HA Energy Dashboard.
> If you don't have a SmartMeter, use the SolarVault sensors as a fallback
> (`sensor.jackery_{sn}_grid_import_power` / `sensor.jackery_{sn}_grid_export_power`).
>
> ² **Why BMS SOC, not Battery SOC?**
> `Battery SOC` (`batSoc`) reports the SOC of the main SolarVault unit only.
> `BMS SOC` (`soc`) reports the **weighted average** across all connected battery units
> (e.g. SolarVault 3 Pro Max + BP2500). Use BMS SOC in multi-unit setups.

---

## Sensor categories

| Category | Count | When useful |
|---|---|---|
| Core dashboard sensors (above) | ~12 | Always |
| Per-PV-string: PV1–PV4 power + energy | 8 | Monitoring individual strings |
| SmartMeter: per-phase L1/L2/L3 import + export (power + energy) | 12 | Phase-balance analysis |
| SmartMeter: diagnostics (commMode, commState, IP) | 3 | Diagnosing SmartMeter connection issues |
| Energy-flow breakdowns (PV→Battery, Battery→Grid, …) | ~15 | Sankey diagrams, detailed analytics |
| EPS (off-grid socket) power + energy | 4 | Off-grid monitoring |
| Expansion battery (BP2500): charge + discharge energy | 2 | Multi-battery setups |
| Inverter stack, grid AC side | 4 | Detailed inverter diagnostics |
| Diagnostics + configuration (WiFi, IP, limits, status) | ~60 | Troubleshooting, automations |

---

## Full main-device sensor list

### Battery

| Entity name | entity_id | MQTT field | Notes |
|---|---|---|---|
| Battery SOC | `sensor.jackery_{sn}_battery_soc` | `batSoc` | Main unit only |
| BMS SOC | `sensor.jackery_{sn}_bms_soc` | `soc` | All units combined |
| Battery Charge Power | `sensor.jackery_{sn}_battery_charge_power` | `batInPw` | Main unit |
| Battery Discharge Power | `sensor.jackery_{sn}_battery_discharge_power` | `batOutPw` | Main unit |
| Battery Charge Power (Calc) | `sensor.jackery_{sn}_battery_charge_power_calc` | calculated | All units |
| Battery Discharge Power (Calc) | `sensor.jackery_{sn}_battery_discharge_power_calc` | calculated | All units |
| Battery Net Power | `sensor.jackery_{sn}_battery_net_power` | calculated | Positive = charging |
| Battery Temperature | `sensor.jackery_{sn}_battery_temperature` | `cellTemp` | ×0.1 °C |
| Battery Count | `sensor.jackery_{sn}_battery_count` | `batNum` | Number of packs |
| Battery State | `sensor.jackery_{sn}_battery_state` | `batState` | 0/1/2 |
| Battery Charge Energy | `sensor.jackery_{sn}_battery_charge_energy` | `batChgEgy` | ×0.01 kWh |
| Battery Discharge Energy | `sensor.jackery_{sn}_battery_discharge_energy` | `batDisChgEgy` | ×0.01 kWh |

### Solar (PV)

| Entity name | entity_id | MQTT field |
|---|---|---|
| Solar Power | `sensor.jackery_{sn}_solar_power` | `pvPw` |
| Solar Power PV1–PV4 | `sensor.jackery_{sn}_solar_power_pv1` … | `pv1`…`pv4` |
| Solar Energy | `sensor.jackery_{sn}_solar_energy` | `pvEgy` |
| Solar Energy PV1–PV4 | `sensor.jackery_{sn}_solar_energy_pv1` … | `pv1Egy`…`pv4Egy` |

### Grid (SolarVault-side)

| Entity name | entity_id | MQTT field | Notes |
|---|---|---|---|
| Grid Import Power | `sensor.jackery_{sn}_grid_import_power` | `inOngridPw` | SolarVault port only |
| Grid Export Power | `sensor.jackery_{sn}_grid_export_power` | `outOngridPw` | SolarVault port only |
| Grid Net Power | `sensor.jackery_{sn}_grid_net_power` | calculated | Import − Export |
| Grid Import Energy | `sensor.jackery_{sn}_grid_import_energy` | `inOngridEgy` | |
| Grid Export Energy | `sensor.jackery_{sn}_grid_export_energy` | `outOngridEgy` | |
| Grid AC Input Power | `sensor.jackery_{sn}_grid_in_power` | `gridInPw` | Type-106 |
| Grid AC Output Power | `sensor.jackery_{sn}_grid_out_power` | `gridOutPw` | Type-106 |
| Max Output Power (OnGrid) | `sensor.jackery_{sn}_max_output_power_ongrid` | `maxOutPw` | → also a select entity |
| Max Feed Grid Power | `sensor.jackery_{sn}_max_feed_grid_power` | `maxFeedGrid` | Type-106, read-only |

### EPS (off-grid socket)

| Entity name | entity_id | MQTT field |
|---|---|---|
| EPS Output Power | `sensor.jackery_{sn}_eps_output_power` | `swEpsOutPw` |
| EPS Input Power | `sensor.jackery_{sn}_eps_input_power` | `swEpsInPw` |
| EPS Output Energy | `sensor.jackery_{sn}_eps_output_energy` | `outEpsEgy` |
| EPS Input Energy | `sensor.jackery_{sn}_eps_input_energy` | `inEpsEgy` |
| EPS State | `sensor.jackery_{sn}_eps_state` | `swEpsState` |
| EPS Switch Status | `sensor.jackery_{sn}_eps_switch_status` | `swEps` |

### Energy flow breakdowns (type-23, cumulative)

| Entity name | entity_id | MQTT field |
|---|---|---|
| PV to Battery Energy | `sensor.jackery_{sn}_pv_to_battery_energy` | `pvOtBatEgy` |
| PV to AC Energy | `sensor.jackery_{sn}_pv_to_ac_energy` | `pvOtAcEgy` |
| PV to Grid Energy | `sensor.jackery_{sn}_pv_to_grid_energy` | `pvOtOngridEgy` |
| Battery to AC Energy | `sensor.jackery_{sn}_battery_to_ac_energy` | `batOtAcEgy` |
| Battery to Grid Energy | `sensor.jackery_{sn}_battery_to_grid_energy` | `batOtGridEgy` |
| Grid to Battery Energy | `sensor.jackery_{sn}_grid_to_battery_energy` | `ongridOtBatEgy` |
| Grid to AC Load Energy | `sensor.jackery_{sn}_grid_to_ac_load_energy` | `ongridOtAcLoadEgy` |
| AC to Battery Energy | `sensor.jackery_{sn}_ac_to_battery_energy` | `acOtBatEgy` |
| AC to Grid Energy | `sensor.jackery_{sn}_ac_to_grid_energy` | `acOtOngridEgy` |

### Status and diagnostics

| Entity name | entity_id | MQTT field | Notes |
|---|---|---|---|
| Device Status | `sensor.jackery_{sn}_device_status` | `stat` | ENUM |
| OnGrid Status | `sensor.jackery_{sn}_ongrid_status` | `ongridStat` | ENUM |
| CT Status | `sensor.jackery_{sn}_ct_status` | `ctStat` | ENUM |
| Grid Meter Link | `sensor.jackery_{sn}_grid_meter_link` | `gridSate` | ENUM |
| Home Power | `sensor.jackery_{sn}_home_power` | calculated | Estimated home load |
| Home Load Power (Estimated) | `sensor.jackery_{sn}_home_load_power_estimated` | `otherLoadPw` | Type-106 |
| CT Import Energy | `sensor.jackery_{sn}_ct_import_energy` | `inCtEgy` | Firmware post-2026-07 |
| CT Export Energy | `sensor.jackery_{sn}_ct_export_energy` | `outCtEgy` | Firmware post-2026-07 |
| WiFi Signal | `sensor.jackery_{sn}_wifi_signal` | `wsig` | dBm |
| WiFi SSID | `sensor.jackery_{sn}_wifi_ssid` | `wname` | |
| Ethernet Connected | `sensor.jackery_{sn}_ethernet_connected` | `ethPort` | |
| Ethernet IP | `sensor.jackery_{sn}_ethernet_ip` | `eip` | |
| Device Capability | `sensor.jackery_{sn}_device_capability` | `ability` | Bitmask |
| SOC Charge Limit | `sensor.jackery_{sn}_soc_charge_limit` | `socChgLimit` | Also writable |
| SOC Discharge Limit | `sensor.jackery_{sn}_soc_discharge_limit` | `socDischgLimit` | Also writable |
| SOC Force Charge Target | `sensor.jackery_{sn}_soc_force_charge_target` | `socForceChg` | Purpose unclear |
| Energy Plan Power | `sensor.jackery_{sn}_energy_plan_power` | `energyPlanPw` | |
| Standby Power Threshold | `sensor.jackery_{sn}_standby_power_threshold` | `standbyPw` | |
| PV Max Charge Power | `sensor.jackery_{sn}_pv_max_charge_power` | `pvMaxChgPower` | |
| Max System Output Power | `sensor.jackery_{sn}_max_system_output_power` | `maxSysOutPw` | |
| Max System Input Power | `sensor.jackery_{sn}_max_system_input_power` | `maxSysInPw` | |
| Off-Grid Switch Time | `sensor.jackery_{sn}_off_grid_switch_time` | `offGridTime` | Seconds |
| Max Inverter Standby Power | `sensor.jackery_{sn}_max_inverter_standby_power` | `maxInvStdPw` | |
| Max Grid Standby Power | `sensor.jackery_{sn}_max_grid_standby_power` | `maxGridStdPw` | |
| Inverter Stack Input Power | `sensor.jackery_{sn}_inverter_stack_input_power` | `stackInPw` | |
| Inverter Stack Output Power | `sensor.jackery_{sn}_inverter_stack_output_power` | `stackOutPw` | |
| Grid Side Input Power | `sensor.jackery_{sn}_grid_side_input_power` | `inGridSidePw` | |
| Grid Side Output Power | `sensor.jackery_{sn}_grid_side_output_power` | `outGridSidePw` | |

---

## Control entities

| Type | Entity name | entity_id | MQTT field | Notes |
|---|---|---|---|---|
| Select | Work Mode | `select.jackery_{sn}_work_mode` | `workModel` | Eigenverbrauch / Benutzerdefiniert / Tarifmodus / KI-Modus |
| Select | Auto Standby Mode | `select.jackery_{sn}_auto_standby_mode` | `autoStandby` | invalid / standby / on |
| Select | Max Feed-in Power (OnGrid) | `select.jackery_{sn}_max_feed_in_power_ongrid` | `maxOutPw` | 800 / 1200 / 2500 W |
| Number | SOC Charge Limit | `number.jackery_{sn}_soc_charge_limit` | `socChgLimit` | 50–100 % (device-enforced) |
| Number | SOC Discharge Limit | `number.jackery_{sn}_soc_discharge_limit` | `socDischgLimit` | 5–49 % (device-enforced) |
| Number | SOC Force Charge Target | `number.jackery_{sn}_soc_force_charge_target` | `socForceChg` | 0–100 % |
| Number | Default Output Power | `number.jackery_{sn}_default_output_power` | `defaultPw` | 0–200 W, Benutzerdefiniert mode |
| Switch | Auto Standby Allowed | `switch.jackery_{sn}_auto_standby_allowed` | `isAutoStandby` | |
| Switch | EPS Switch | `switch.jackery_{sn}_eps_switch` | `swEps` | |
| Switch | Off-Grid Fallback | `switch.jackery_{sn}_off_grid_fallback` | `offGridDown` | |
| Switch | Follow Meter Power | `switch.jackery_{sn}_follow_meter_power` | `isFollowMeterPw` | Only available in Benutzerdefiniert mode |
| Button | Reboot | `button.jackery_{sn}_reboot` | `reboot=1` | Useful to restore SmartMeter LAN mode |

---

## SmartMeter 3P sensors (HTO907A, devType=3, subType=5)

These sensors belong to the SmartMeter sub-device. Their entity IDs include the SmartMeter's serial number.

### Power (real-time, type-101)

| Entity name | entity_id | MQTT field |
|---|---|---|
| Grid Import Power | `sensor.jackery_{smartmeter_sn}_grid_import_power` | `tPhasePw` |
| Grid Export Power | `sensor.jackery_{smartmeter_sn}_grid_export_power` | `tnPhasePw` |
| L1 Import Power | `sensor.jackery_{smartmeter_sn}_l1_import_power` | `aPhasePw` |
| L2 Import Power | `sensor.jackery_{smartmeter_sn}_l2_import_power` | `bPhasePw` |
| L3 Import Power | `sensor.jackery_{smartmeter_sn}_l3_import_power` | `cPhasePw` |
| L1 Export Power | `sensor.jackery_{smartmeter_sn}_l1_export_power` | `anPhasePw` |
| L2 Export Power | `sensor.jackery_{smartmeter_sn}_l2_export_power` | `bnPhasePw` |
| L3 Export Power | `sensor.jackery_{smartmeter_sn}_l3_export_power` | `cnPhasePw` |

### Energy (cumulative, type-23)

> ⚠️ **Note: these energy sensors are NOT phase-saldated.**
> `Grid Import Energy` and `Grid Export Energy` accumulate per-phase gross values independently.
> If L1 imports 200 W while L3 exports 180 W simultaneously, both counters increase — the net
> grid exchange of 20 W is not what is counted. This differs from a traditional Ferraris meter,
> which nets all phases.
>
> For phase-saldated energy values (matching a Ferraris meter), use HA's **Riemann Sum Integration**
> helper on `Grid Import Power` (`tPhasePw`) and `Grid Export Power` (`tnPhasePw`) — these power
> sensors are already phase-saldated (net across all phases).

| Entity name | entity_id | MQTT field |
|---|---|---|
| Grid Import Energy | `sensor.jackery_{smartmeter_sn}_grid_import_energy` | `tPhaseEgy` |
| Grid Export Energy | `sensor.jackery_{smartmeter_sn}_grid_export_energy` | `tnPhaseEgy` |
| L1 Import Energy | `sensor.jackery_{smartmeter_sn}_l1_import_energy` | `aPhaseEgy` |
| L2 Import Energy | `sensor.jackery_{smartmeter_sn}_l2_import_energy` | `bPhaseEgy` |
| L3 Import Energy | `sensor.jackery_{smartmeter_sn}_l3_import_energy` | `cPhaseEgy` |
| L1 Export Energy | `sensor.jackery_{smartmeter_sn}_l1_export_energy` | `anPhaseEgy` |
| L2 Export Energy | `sensor.jackery_{smartmeter_sn}_l2_export_energy` | `bnPhaseEgy` |
| L3 Export Energy | `sensor.jackery_{smartmeter_sn}_l3_export_energy` | `cnPhaseEgy` |

### Diagnostics

| Entity name | entity_id | MQTT field | Notes |
|---|---|---|---|
| Communication Mode | `sensor.jackery_{smartmeter_sn}_communication_mode` | `commMode` | `lan` / `cloud` — see below |
| Communication State | `sensor.jackery_{smartmeter_sn}_communication_state` | `commState` | `online` / `offline` |
| IP Address | `sensor.jackery_{smartmeter_sn}_ip_address` | `wip` | |

> **commMode: `cloud` means no measurement data**
> The SmartMeter can switch autonomously from LAN (local MQTT) to Cloud relay mode after
> internet outages. In Cloud mode `commState` stays `online`, but all measurement fields
> (`tPhasePw`, `aPhasePw`, etc.) are absent — all power sensors show the last known value.
> **Fix:** Restart the SolarVault (via the Jackery app or the `Reboot` button entity) to
> force the SmartMeter back to LAN mode.

---

## Expansion battery sensors (BP2500, devType=1, subType=0)

Entity IDs include the BP2500's serial number. Only cumulative energy is available via MQTT.

| Entity name | entity_id | MQTT field |
|---|---|---|
| Charge Energy | `sensor.jackery_{bp2500_sn}_charge_energy` | `inEgy` (×0.01 kWh) |
| Discharge Energy | `sensor.jackery_{bp2500_sn}_discharge_energy` | `outEgy` (×0.01 kWh) |

---

## Smart Meter D0 Reader sensors (HTO910A, devType=4, subType=7)

The **Jackery Smart Meter D0 Reader** reads the optical D0 infrared interface (IEC 62056-21 / SML) of German electricity meters. It reports the totals that the meter itself measures — no per-phase breakdown. The underlying household connection can still be 3-phase.

Entity IDs include the HTO910A's serial number.

| Entity name | entity_id | MQTT field | Notes |
|---|---|---|---|
| Grid Import Power | `sensor.jackery_{hto910a_sn}_grid_import_power` | `inPw` | Total grid import (W) |
| Grid Export Power | `sensor.jackery_{hto910a_sn}_grid_export_power` | `outPw` | Total grid export (W) |
| Communication State | `sensor.jackery_{hto910a_sn}_communication_state` | `commState` | Online / Offline |
| Communication Mode | `sensor.jackery_{hto910a_sn}_communication_mode` | `commMode` | LAN / Cloud (Relay) |
| IP Address | `sensor.jackery_{hto910a_sn}_ip_address` | `wip` | HTO910A IP |

> **For Energy Dashboard:** Use `Grid Import Power` and `Grid Export Power` from the D0 Reader — they reflect exactly what the electricity meter measures. The same `jackery_home_power` formula applies as with the HTO907A.

---

## Energy Flow Card Plus configuration

```yaml
type: custom:energy-flow-card-plus
entities:
  solar:
    entity: sensor.jackery_{sn}_solar_power
  grid:
    entity:
      consumption: sensor.jackery_{sn}_ct_3phase_import_total   # SmartMeter preferred
      production: sensor.jackery_{sn}_ct_3phase_export_total    # SmartMeter preferred
  battery:
    entity:
      consumption: sensor.jackery_{sn}_battery_charge_power_calc
      production: sensor.jackery_{sn}_battery_discharge_power_calc
    state_of_charge: sensor.jackery_{sn}_bms_soc
  home:
    entity: sensor.jackery_{sn}_home_power
```

If you don't have a SmartMeter, replace the grid sensors with:
```yaml
  grid:
    entity:
      consumption: sensor.jackery_{sn}_grid_import_power
      production: sensor.jackery_{sn}_grid_export_power
```
