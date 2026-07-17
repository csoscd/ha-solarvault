## Jackery SolarVault – Home Assistant Integration (Fork)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/csoscd/ha-solarvault.svg)](https://github.com/csoscd/ha-solarvault/releases)
[![License](https://img.shields.io/github/license/csoscd/ha-solarvault.svg)](LICENSE)

> **⚠️ This is a fork of the original [Jackery-Official/jackery](https://github.com/Jackery-Official/jackery) integration.**
> 
> This fork adds fixes and additional sensors specifically tested with the **Jackery SolarVault 3 Pro Max** and the **Jackery SmartMeter 3P (HTO907A)**. All credits for the original implementation go to the original authors.
>
> Changes in this fork are tracked in the [commit history](https://github.com/csoscd/ha-solarvault/commits/main). Bug reports and improvements relating to this fork can be filed [here](https://github.com/csoscd/ha-solarvault/issues); for general Jackery integration issues please use the [original repository](https://github.com/Jackery-Official/jackery/issues).

---

## Support me

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/O5O21U13R9)

---

### Changes vs. the original

#### New sensors (SolarVault 3 Pro Max)

| Sensor | MQTT field | Description |
|---|---|---|
| Inverter Stack Input Power | `stackInPw` | AC power flowing into the inverter stack |
| Inverter Stack Output Power | `stackOutPw` | AC power flowing out of the inverter stack |
| BMS SOC | `soc` | Combined BMS state of charge across all battery units |
| Battery State | `batState` | Current battery operation state (0=transitioning, 1=normal, 2=active) |
| Ethernet Connected | `ethPort` | Whether the Ethernet port is connected |
| WiFi Signal | `wsig` | WiFi signal strength in dBm |
| Max Inverter Standby Power | `maxInvStdPw` | Configured inverter standby power limit |
| Max Grid Standby Power | `maxGridStdPw` | Configured grid standby power limit |
| AC to Grid Energy | `acOtOngridEgy` | Cumulative AC-to-grid energy |
| CT Import Energy | `inCtEgy` | Cumulative system-level CT import energy (added in firmware post-2026-07) |
| CT Export Energy | `outCtEgy` | Cumulative system-level CT export energy (added in firmware post-2026-07) |
| SOC Force Charge Target | `socForceChg` | See control entities below |
| WiFi SSID | `wname` | SSID of the connected WiFi network (empty when Ethernet is active) |
| Ethernet IP | `eip` | Ethernet IP address of the SolarVault |
| Device Capability | `ability` | Capability bitmask – changes value after firmware updates |
| Device Status | `stat` | Host operation status (normal / waiting / alarm / fault / standby / low_power) |
| OnGrid Status | `ongridStat` | Grid-tie status: on_grid / off_grid |
| CT Status | `ctStat` | CT meter connection status: online / offline |
| Grid Meter Link | `gridSate` | Grid meter link health: normal / abnormal |

#### New control entities (SolarVault 3 Pro Max)

| Entity type | Entity | MQTT field | Range / Options | Description |
|---|---|---|---|---|
| Number | SOC Charge Limit | `socChgLimit` | 0–100 % | Maximum SOC the battery charges to |
| Number | SOC Discharge Limit | `socDischgLimit` | 0–100 % | Minimum SOC the battery discharges to |
| Number | Max Feed-in Power (OnGrid) | `maxOutPw` | 0–10000 W | Maximum OnGrid feed-in power (Einspeiseleistung); app offers 800 W / 2500 W |
| Number | Default Output Power | `defaultPw` | 0–200 W (10 W steps) | Fallback output power for Benutzerdefiniert mode (workModel=4) when no schedule entry is active. App limit: 200 W. Schedule slots (configured in app, cloud-only) can be up to 800 W. |
| Number | SOC Force Charge Target | `socForceChg` | 0–100 % | **⚠️ Purpose not fully determined.** Confirmed writable via MQTT (cmd=5, device acks with cmd=107). Hypothesis: manual force-charge to a target SOC, or backup-reserve threshold. Storm Warning in the Jackery app uses the cloud and does **not** set this field. Set to 0 to deactivate. |
| Select | Auto Standby Mode | `autoStandby` | invalid / standby / on | Controls auto-standby behaviour |
| Select | Work Mode | `workModel` | Eigenverbrauch / Benutzerdefiniert / Tarifmodus / KI-Modus | Operating mode selector. Note: tariff/schedule configuration and KI strategy selection are cloud-only and not accessible via local MQTT. |
| Switch | Auto Standby Allowed | `isAutoStandby` | on / off | Whether auto-standby is permitted |
| Switch | EPS Switch | `swEps` | on / off | Enable/disable EPS (off-grid) output |
| Switch | Off-Grid Fallback | `offGridDown` | on / off | Enable off-grid fallback mode |
| Switch | Follow Meter Power (Zähler folgen) | `isFollowMeterPw` | on / off | Sub-mode within Benutzerdefiniert (workModel=4): device tracks the SmartMeter to achieve net-zero grid exchange. **Only available when Work Mode = Benutzerdefiniert.** |
| Button | Reboot | – | – | Sends a restart command to the SolarVault (type=1, cmd=5, reboot=1). Useful to restore SmartMeter LAN mode without touching the device or app. |

#### SmartMeter 3P fix (HTO907A, devType=3, subType=5)

The original integration incorrectly classified the Jackery SmartMeter 3P as a smart plug instead of a CT meter (see [issue #18](https://github.com/Jackery-Official/jackery/issues/18)). This caused the energy flow calculation to receive no CT data at all.

This fork fixes the classification and exposes **19 dedicated sensors** per SmartMeter:

| Sensor | MQTT field | Description |
|---|---|---|
| Grid Import Power | `tPhasePw` | Total net grid import power |
| Grid Export Power | `tnPhasePw` | Total net grid export power |
| L1/L2/L3 Import Power | `a/b/cPhasePw` | Per-phase grid import power |
| L1/L2/L3 Export Power | `an/bn/cnPhasePw` | Per-phase grid export power |
| Grid Import Energy | `tPhaseEgy` | Cumulative total grid import energy |
| Grid Export Energy | `tnPhaseEgy` | Cumulative total grid export energy |
| L1/L2/L3 Import Energy | `a/b/cPhaseEgy` | Cumulative per-phase import energy |
| L1/L2/L3 Export Energy | `an/bn/cnPhaseEgy` | Cumulative per-phase export energy |
| Communication Mode | `commMode` | 1 = LAN (local MQTT), 2 = Cloud relay – useful for diagnosing data loss |
| Communication State | `commState` | 1 = online, 0 = offline |
| IP Address | `wip` | IP address of the SmartMeter on the local network |

---

### Features

- **Custom Home Assistant integration** (no YAML entities required)
- **MQTT-based data flow** with a shared `JackeryDataCoordinator`
- Periodic data requests every **10 seconds**
- Real-time **power sensors** (W) and cumulative **energy sensors** (kWh)
- **Battery SoC** in percent with proper scaling
- Ready-to-use example configuration for **Energy Flow Card Plus**

### Prerequisites

Before the integration can receive data, **two things must be in place**:

1. **MQTT broker configured and reachable**
   - A running MQTT broker (e.g. Mosquitto) is required.
   - Home Assistant's built-in **MQTT integration** must be configured to connect to it.
   ![mqtt_config](./img/mqtt_config.png)
   ![mqtt_config](./img/mqtt_config_2.png)

2. **Device configured via Jackery app**
   - Use the Jackery mobile app (version **≥ 2.0.0**) to connect the device to your MQTT broker.
   - Go to: Device Details → Settings → MQTT
   ![jackery_config](./img/app_config_mqtt.png)

---

### Installation via HACS

1. Open HACS → **Integrations** → three dots → **Custom repositories**
2. Add URL: `https://github.com/csoscd/ha-solarvault`, Category: `Integration`
3. Search for **"Jackery SolarVault"** and install
4. Restart Home Assistant
5. Go to **Settings → Devices & Services → Add Integration** → search **"Jackery"**
6. Enter:
   - **Device SN**: your device serial number (visible in the Jackery app)
   - **Token**: your device token (visible in the Jackery app MQTT settings)
   - **Topic Prefix**: `hb` (default)

---

### Example: Energy Flow Card Plus

```yaml
type: custom:energy-flow-card-plus
entities:
  solar:
    entity: sensor.jackery_solar_power
    name: Solar
    icon: mdi:solar-power
  grid:
    entity:
      consumption: sensor.jackery_grid_import_power
      production: sensor.jackery_grid_export_power
    name: Grid
    icon: mdi:transmission-tower
  battery:
    entity:
      consumption: sensor.jackery_battery_charge_power_calc
      production: sensor.jackery_battery_discharge_power_calc
    state_of_charge: sensor.jackery_bms_soc
    name: Battery
    icon: mdi:battery
  home:
    entity: sensor.jackery_home_power
    name: Home
    icon: mdi:home-lightning-bolt
display_zero_lines:
  mode: show
  transparency: 50
  grey_color: [189, 189, 189]
w_decimals: 0
kw_decimals: 2
color_icons: true
animation_speed: 10
energy_date_selection: false
```

![demo](img/demo.png)

> **Note on battery sensors:**
> `sensor.jackery_battery_charge_power` reports the charge power of the main SolarVault unit only.
> `sensor.jackery_battery_charge_power_calc` sums the charge power across all connected battery units (e.g. SolarVault 3 Pro Max + BP2500) and is the correct sensor for multi-unit setups.
> `sensor.jackery_bms_soc` reports the combined BMS state of charge across the entire battery stack and should be preferred over `sensor.jackery_battery_soc` for multi-unit setups.

#### Alternative: power-flow-card-plus with a signed net sensor

If `energy-flow-card-plus` shows Wh instead of W in your setup, use [`power-flow-card-plus`](https://github.com/flixlix/power-flow-card-plus) instead.
It requires a single signed battery power sensor (positive = discharging, negative = charging).
Create a **Template sensor helper** in Home Assistant with this formula:

```
{{ states('sensor.jackery_battery_discharge_power_calc') | float(0) - states('sensor.jackery_battery_charge_power_calc') | float(0) }}
```

Then use it in your card config:

```yaml
type: custom:power-flow-card-plus
entities:
  solar:
    entity: sensor.jackery_solar_power
    name: Solar
    icon: mdi:solar-power
  grid:
    entity: sensor.jackery_grid_import_power
    entity_production: sensor.jackery_grid_export_power
    name: Grid
    icon: mdi:transmission-tower
  battery:
    entity: sensor.jackery_battery_net_power_signed   # your template sensor
    state_of_charge: sensor.jackery_bms_soc
    name: Battery
    icon: mdi:battery
  home:
    entity: sensor.jackery_home_power
    name: Home
    icon: mdi:home-lightning-bolt
```

---

### Troubleshooting

#### SmartMeter 3P: no measurement data (all sensors show 0 W / unavailable)

**Symptom:** SmartMeter power sensors (L1–L3 Import/Export, Grid Import/Export Power) suddenly stop delivering values or show 0 W permanently, even though the SmartMeter appears as available in Home Assistant.

**Root cause: commMode switch from LAN → Cloud**

The SmartMeter HTO907A can switch on its own from local MQTT mode ("LAN") to Jackery Cloud relay mode ("Cloud") — for example after repeated internet outages. In Cloud mode it still reports its device info to the SolarVault, but no measurement data.

**How to identify it:**

1. **HA sensor** `sensor.jackery_<name>_communication_mode` shows `2` instead of `1`
   - `1` = LAN (local MQTT path, measurement data flows normally)
   - `2` = Cloud (measurements are relayed via Jackery cloud, not available in HA)

2. **Jackery app:** The SmartMeter displays "Cloud" instead of "LAN" at the top.

3. **MQTT diagnosis:** The type-101 event contains `"commMode":2` and the measurement fields (`tPhasePw`, `aPhasePw`, etc.) are absent from the body entirely.

**Fix: restart the SolarVault**

Restarting the SolarVault (via the Jackery app or directly on the device) causes the SmartMeter to re-register with the SolarVault and automatically choose the LAN path. After the restart, `communication_mode` should return to `1` and measurement data should resume.

> **Note:** There is no MQTT command to set commMode directly — the mode is decided by the SmartMeter itself and cannot be overridden via MQTT.

---

### Links

- **Original integration**: https://github.com/Jackery-Official/jackery
- **Energy Flow Card Plus**: https://github.com/flixlix/energy-flow-card-plus
- **Home Assistant MQTT integration**: https://www.home-assistant.io/integrations/mqtt/

---

### Development

#### Running the tests

```bash
uv run pytest tests/ -v
```

Tests cover the energy-flow calculation logic, MQTT message routing (including regression tests for the CT-cache bug), and sensor value transformations. No real MQTT broker or Home Assistant installation is required.

---

### License

MIT License – see [LICENSE](LICENSE)
