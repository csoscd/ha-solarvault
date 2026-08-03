# Use Case: Late-Loading — Maximize Solar Self-Consumption via Forecast-Driven Charge Limit

## Goal

Delay battery charging so that the battery reaches 100 % as late as possible —
ideally just as solar generation ends for the day. This prevents the battery from
filling up early in the morning, then sitting full while excess PV power has nowhere
to go (grid export or curtailment). Instead the battery absorbs PV surplus throughout
the entire day.

## Strategy

1. **At sunrise**: fetch today's solar energy forecast. If the forecast exceeds the
   battery's remaining free capacity, lower `socChgLimit` so the battery cannot fill
   up immediately.
2. **Hourly during the day**: recalculate how much forecast energy is still to come
   vs. how much free capacity is left. Raise `socChgLimit` gradually so the battery
   arrives at 100 % at the latest possible moment.
3. **After sunset / no more generation expected**: set `socChgLimit` back to 100 %
   so the battery retains its full charge through the night.

### Critical constraint

`socChgLimit` only prevents further charging — the SolarVault does **not** actively
discharge the battery to reach a lower limit. The automation must act **before** the
battery reaches the intended ceiling. If the battery is already at 70 % and you set
`socChgLimit` to 60 %, charging simply stops at 70 % and PV energy is wasted.

Start the automation early (sunrise or earlier) and set an initial limit that is
below the current SOC or equal to it.

## Prerequisites

### Home Assistant integrations

| Integration | Purpose | Install |
|---|---|---|
| **Forecast.Solar** | Per-hour solar energy forecast (kWh) | HACS or built-in |
| **ha-solarvault** (this fork) | Read SOC, write `socChgLimit` | HACS |

Forecast.Solar requires your roof plane(s) configured (azimuth, tilt, kWp).
The forecast sensor provides `energy_production_today` and hourly breakdown.

### Entities used from this integration

| Entity | Description |
|---|---|
| `sensor.jackery_{sn}_bms_soc` | Combined SOC across all batteries (%) |
| `number.jackery_{sn}_soc_charge_limit` | Charge upper limit — **writable**, 50–100 % |
| `sensor.jackery_{sn}_battery_capacity` | Total usable capacity in kWh (if available) |

Replace `{sn}` with your device serial number (lowercase), e.g. `hq2c10000444hp3`.

If `battery_capacity` is not exposed, enter your system's usable kWh as a fixed value
in the automation (e.g. 3.0 kWh for SolarVault 3 Pro, 5.5 kWh for Pro Max + BP2500).

## Automation Logic

```
on_trigger:
  - at sunrise
  - every hour between sunrise and sunset

variables:
  soc_now          = sensor bms_soc (%)
  battery_kwh      = total usable battery capacity (kWh)
  energy_remaining = forecast kWh still expected today (from Forecast.Solar)
  free_capacity    = battery_kwh * (1 - soc_now / 100)   # kWh still empty

compute:
  if energy_remaining <= free_capacity:
    # Battery can absorb all remaining forecast → let it charge freely
    target_limit = 100

  else:
    # More solar coming than empty space → hold back some capacity
    # How full should the battery be NOW so it just reaches 100% at end of day?
    # = 100% minus the share of remaining forecast that fits in the battery
    headroom_pct = min(energy_remaining / battery_kwh * 100, 100)
    target_limit = round(100 - headroom_pct + soc_now)
    target_limit = clamp(target_limit, socDischgLimit + 5, 100)

action:
  set number.jackery_{sn}_soc_charge_limit to target_limit
```

### Example

- Battery: 3.0 kWh usable, currently at 30 % SOC (0.9 kWh stored, 2.1 kWh free)
- Forecast remaining: 4.5 kWh
- `headroom_pct = min(4.5 / 3.0 * 100, 100) = 100` → `target_limit = 100 - 100 + 30 = 30`
- Result: charge limit set to **30 %** — battery stays where it is, starts absorbing
  only once the formula raises the ceiling as the afternoon progresses.

Two hours later:
- SOC now 35 %, forecast remaining: 2.8 kWh
- `headroom_pct = min(2.8 / 3.0 * 100, 100) = 93` → `target_limit = 100 - 93 + 35 = 42`
- Limit raised to **42 %** — battery allowed to charge a bit more.

## Home Assistant Automation (YAML sketch)

```yaml
alias: "SolarVault – Late-loading charge limit"
description: "Adjusts socChgLimit hourly to delay full charge until end of solar day."

trigger:
  - platform: sun
    event: sunrise
  - platform: time_pattern
    hours: "/1"

condition:
  - condition: sun
    after: sunrise
    before: sunset

variables:
  soc: "{{ states('sensor.jackery_YOURDEVICESN_bms_soc') | float(0) }}"
  battery_kwh: 3.0   # ← adjust to your system
  forecast_remaining: >
    {{ states('sensor.energy_production_today_remaining') | float(0) }}
  free_kwh: "{{ battery_kwh * (1 - soc / 100) }}"

action:
  - variables:
      target: >
        {% if forecast_remaining <= free_kwh %}
          100
        {% else %}
          {% set headroom = [forecast_remaining / battery_kwh * 100, 100] | min %}
          {{ ([100 - headroom + soc, 25] | max) | round(0) | int }}
        {% endif %}
  - service: number.set_value
    target:
      entity_id: number.jackery_YOURDEVICESN_soc_charge_limit
    data:
      value: "{{ target }}"
  - service: notify.persistent_notification
    data:
      message: >
        Late-loading: SOC {{ soc }}%, forecast {{ forecast_remaining }} kWh,
        limit set to {{ target }}%

# Reset at sunset
- alias: "SolarVault – Reset charge limit at sunset"
  trigger:
    - platform: sun
      event: sunset
  action:
    - service: number.set_value
      target:
        entity_id: number.jackery_YOURDEVICESN_soc_charge_limit
      data:
        value: 100
```

## Known Limitations

- **Forecast accuracy**: on heavily cloudy days the forecast may significantly
  underestimate generation. Add a safety margin (e.g. always allow 10 % headroom)
  to avoid running out of charge on unexpectedly poor days.
- **No active discharge**: if the battery is already above the computed limit at
  sunrise (e.g. charged overnight from grid), the automation cannot reclaim that
  capacity. Consider not enabling grid charging on days with good forecast.
- **`socChgLimit` minimum**: the integration enforces a minimum of 50 %. Do not
  set targets below that value.
- **Multiple batteries**: `bms_soc` is the combined weighted SOC. Use the combined
  usable capacity of all units (SolarVault + BP2500) as `battery_kwh`.
- **Validation**: after setting `socChgLimit`, the SolarVault acknowledges the write
  via MQTT (cmd=107). The entity updates optimistically immediately; the device
  confirms within ~30 s.
