# Power Flow Card Plus

[Power Flow Card Plus](https://github.com/flixlix/power-flow-card-plus) is an alternative to
Energy Flow Card Plus. Use it if `energy-flow-card-plus` shows Wh instead of W in your setup.

## Installation

Install via HACS: search for **Power Flow Card Plus**.

## Required Template Helper

Power Flow Card Plus requires a single **signed** battery power sensor
(positive = discharging, negative = charging).

Create a **Template sensor helper** in Home Assistant
(Settings → Devices & Services → Helpers → Add Helper → Template → Sensor):

```
{{ states('sensor.jackery_total_battery_discharge_power') | float(0)
 - states('sensor.jackery_total_battery_charge_power') | float(0) }}
```

Set unit to `W`, device class `power`, state class `measurement`.
Name it e.g. `jackery_battery_net_power_signed`.

## Example Configuration

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
    entity: sensor.jackery_battery_net_power_signed   # template sensor (see above)
    state_of_charge: sensor.jackery_bms_soc
    name: Battery
    icon: mdi:battery
  home:
    entity: sensor.jackery_home_power
    name: Home
    icon: mdi:home-lightning-bolt
```
