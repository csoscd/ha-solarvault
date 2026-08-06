# Energy Flow Card Plus

[Energy Flow Card Plus](https://github.com/flixlix/energy-flow-card-plus) is a popular Home Assistant
custom card that visualizes solar, grid, battery and home consumption in a circular flow diagram.

## Installation

Install via HACS: search for **Energy Flow Card Plus**.

## Example Configuration

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
      consumption: sensor.jackery_total_battery_charge_power
      production: sensor.jackery_total_battery_discharge_power
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

## Battery Sensor Notes

`sensor.jackery_battery_charge_power` ("Main Unit Charge Power") reports the charge power of the
SolarVault main unit **only** — expansion batteries like the BP2500 are not included.

`sensor.jackery_total_battery_charge_power` derives the full-stack battery power via energy balance
(PV + grid import − AC output − EPS output) and covers all connected battery units.
**Use this one for dashboards in multi-unit setups.**

`sensor.jackery_bms_soc` reports the combined BMS state of charge across the entire battery stack
and should be preferred over `sensor.jackery_battery_soc` in multi-unit setups.

> **Note:** If this card shows Wh instead of W in your setup, use
> [power-flow-card-plus](card-power-flow-plus.md) instead.
