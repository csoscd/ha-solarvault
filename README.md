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

## Entity Reference

With 100+ entities, finding the right sensor can be tricky.
**[→ docs/entity-reference.md](docs/entity-reference.md)** lists all sensors by category, explains which ones to use for energy dashboards, and explains why SmartMeter sensors are preferred over SolarVault-internal sensors for grid import/export.

Entity IDs follow the pattern:
```
{domain}.jackery_{sn_lowercase}_{entity_display_name_slug}
```
Example: SN `HS2C12600262HH4` → `sensor.jackery_hs2c12600262hh4_solar_power`

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
| WLAN IP | `wip` | IP address of the SolarVault on the WiFi network |
| Ethernet IP | `eip` | Ethernet IP address of the SolarVault |
| Device Capability | `ability` | Capability bitmask – changes value after firmware updates |
| Device Status | `stat` | Device operation status: normal / waiting / alarm / fault / standby / low_power |
| OnGrid Status | `ongridStat` | Grid-tie status: disconnected / connected |
| CT Status | `ctStat` | CT meter connection status: disconnected / connected |
| Grid Meter Link | `gridSate` | Grid meter link health: not_linked / linked |
| Max Feed Grid Power | `maxFeedGrid` | Maximum grid feed-in power reported by the device (from type-106 status) |

#### New control entities (SolarVault 3 Pro Max)

| Entity type | Entity | MQTT field | Range / Options | Description |
|---|---|---|---|---|
| Number | SOC Charge Limit | `socChgLimit` | 0–100 % | Maximum SOC the battery charges to |
| Number | SOC Discharge Limit | `socDischgLimit` | 0–100 % | Minimum SOC the battery discharges to |
| Select | Max Feed-in Power (OnGrid) | `maxOutPw` | 800 W / 1200 W / 2500 W | Maximum OnGrid feed-in power (Einspeiseleistung). SV3 Pro: 800/1200 W. SV3 Pro Max: 800/2500 W. Only app-supported values are offered to prevent invalid configurations. |
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
uv sync --group test
uv run pytest tests/ -v
```

Tests cover energy-flow calculation logic, MQTT message routing (regression tests for the CT-cache bug), sensor value transforms, and config flow integration tests (using the real HA test framework). Coverage is reported after every run; the minimum threshold is 30 %.

#### Linting & type checking

```bash
uv sync --group lint
uv run ruff check custom_components/jackery/   # linter + import order
uv run mypy custom_components/jackery/         # type checker
python tools/check_translations.py            # translation completeness
```

#### CI pipeline

Every push and pull request runs three GitHub Actions jobs automatically:

| Job | Checks |
|-----|--------|
| **Lint** | Ruff, mypy, translation completeness (`tools/check_translations.py`) |
| **Tests** | pytest with coverage (`--cov-fail-under=30`) |
| **Validate** | HACS validation, Hassfest validation |

[Dependabot](https://docs.github.com/en/code-security/dependabot) is configured to keep GitHub Actions versions up to date (weekly, Mondays).

---

### What's new in v2.0.3

#### WLAN IP sensor

New sensor `WLAN IP` (`wip`) shows the SolarVault's IP address on the WiFi network.
Useful for network diagnostics alongside the existing `Ethernet IP` sensor.

#### Entity reference documentation

New file [`docs/entity-reference.md`](docs/entity-reference.md) explains which sensors
to use for energy dashboards, why SmartMeter sensors are preferred for grid import/export,
and lists all 100+ entities by category with their entity_id patterns.

#### German translation: `low_power` renamed

The German label for the `low_power` device status state was changed from "Schwachstrom"
to "Energiesparmodus" (more natural phrasing).

---

### What's new in v2.0.2

#### SmartMeter and expansion battery sensors no longer disappear after HA restart

A regression in v2.0.0 caused SmartMeter 3P, BP2500, and smart plug entities to never
be created (or recreated) after a Home Assistant restart or integration reload. All values
were absent; reverting to v2.0.0 was the only workaround (see Issue #7).

**Root cause:** The coordinator attribute `config_entry_id` was accidentally renamed to
`_config_entry_id` (private) in v2.0.0, while the `hasattr(self, "config_entry_id")`
guards in the sub-device discovery code still checked the old public name.
The guards always evaluated to `False`, so sub-device entities were never instantiated.

This is fixed in v2.0.2 by restoring the public attribute name.

#### Duplicate "unavailable" entities cleaned up on upgrade

The v2.0.0 entity migration contained two bugs that left orphaned entities in the HA UI
(showing "unavailable" or "unknown" alongside working duplicates):

1. Main-device sensors with `battery_*` or `ct_*` in their name (e.g. `Battery SoC`,
   `CT Status`) were skipped by the migration and kept their old unique ID — causing them
   to be re-created as orphaned entities.
2. Switch and number entities were migrated to the wrong unique-ID format
   (`…_main_swEps` instead of `…_switch_swEps`), leaving both the wrongly-renamed entity
   and a fresh duplicate.

v2.0.2 detects and removes these orphaned/wrongly-migrated entities on startup. No manual
cleanup needed.

> **Note for users upgrading from v1.x**: After updating and restarting Home Assistant,
> duplicate "unavailable" entities are removed automatically. A browser hard-refresh
> (Ctrl+Shift+R) may be needed if the UI still shows stale entries.

#### Max Feed-in Power: 1200 W option for SV3 Pro

The `Max Feed-in Power` select entity now includes `1200 W (SV3 Pro)` as an option,
alongside `800 W` and `2500 W (SV3 Pro Max)`. Previously, SV3 Pro users with 1200 W set
in the app saw "unknown" in the select entity (Issue #5).

---

### What's new in v2.0.1

#### `jackery_home_power` negative values clamped to 0

The home power formula can temporarily yield a negative result due to asynchronous
sensor updates between the SmartMeter and the SolarVault. Since house loads cannot be
negative, any negative result is now clamped to 0.

---

### What's new in v2.0.0

#### Multi-Instance support

Multiple Jackery devices can now be integrated simultaneously. Each integration entry is identified by its device serial number, so two SolarVaults or other Jackery MQTT devices can coexist in one Home Assistant instance without conflict.

Existing single-device installations are migrated automatically on first startup — entity IDs and HA history are preserved.

#### Re-Authentication flow

If the device reports a token mismatch (MQTT type-123 / error 401), Home Assistant will now show a persistent notification prompting you to re-enter the token. This avoids having to remove and re-add the integration when the token changes.

#### Device card: model and firmware version

The HA device card now shows the device model (`DIY3` for SolarVault 3 Pro Max) and the firmware version, extracted from incoming MQTT messages. Previously, the device card always showed the generic label "Energy Monitor".

#### Human-readable status labels

The status sensors `Device Status`, `OnGrid Status`, `CT Status`, and `Grid Meter Link` now use `SensorDeviceClass.ENUM` and display human-readable labels (e.g. "Normal", "Connected") instead of raw integers. All labels are translated into English, German, and French.

#### New sensor: Max Feed Grid Power

`max_feed_grid_power` reads `maxFeedGrid` from type-106 messages. On some hardware configurations this differs from `maxOutPw` (the writable max feed-in setting). The new sensor exposes the raw device-side limit for diagnostics.

#### Smart Plug commMode guard

If a smart plug switches to cloud-relay mode (`commMode=2`) — which can happen autonomously after internet outages — MQTT switch commands are now blocked. Home Assistant shows a persistent notification explaining that the plug must be controlled via the Jackery App until it returns to LAN mode. The plug's `extra_state_attributes` expose `commMode`, `commMode_label`, and `mqtt_controllable` for diagnostics and automations.

---

### License

MIT License – see [LICENSE](LICENSE)
