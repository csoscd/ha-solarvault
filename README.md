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

#### New control entities (SolarVault 3 Pro Max)

| Entity | MQTT field | Range | Description |
|---|---|---|---|
| SOC Force Charge Target | `socForceChg` | 0–100 % | **⚠️ Purpose not fully determined.** Confirmed writable via MQTT (cmd=5, device acks with cmd=107). Hypothesis: manual force-charge to a target SOC, or backup-reserve threshold. Storm Warning in the Jackery app uses the cloud and does **not** set this field. Set to 0 to deactivate. |

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
