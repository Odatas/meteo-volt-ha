# Meteo-Volt for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

Home Assistant integration for the [Meteo-Volt](https://github.com/Odatas/meteo-volt-ha) electricity price prediction service. It is made for dynamic electricity tariffs and, above all, for charging electric vehicles when power is cheap: it polls the Meteo-Volt API once per hour, exposes the price forecast as sensors and, once you add a vehicle, plans its charging into the cheapest hours. The integration brings its own panel to the sidebar: forecast, charge plan and the trips the plan is built around. Currently the API is in beta and there is no open way of receiving an API key.

> **Beta.** Expect rough edges. There is no prediction model selector in Home Assistant yet.

## What it does

Meteo-Volt predicts German day-ahead electricity prices in 15-minute slots, each with three quantiles:

- `q10` — optimistic (low) estimate
- `q50` — median (the main forecast)
- `q90` — pessimistic (high) estimate

The integration fetches the current forecast hourly. On top of that it plans the charging of your
electric vehicles: you describe the vehicle and the charge point, enter your trips in the panel,
and Meteo-Volt puts the charging into the cheapest slots that still get every trip done. The plan
comes back as entities your wallbox automation can follow.

## Requirements

- A Meteo-Volt API token.
- **Home Assistant 2026.4 or newer.**
- HACS installed (for the recommended install path).

Version 1.1.0 stores vehicles and charge points as config subentries, which
older cores do not have. That raises the floor from 2024.1 to 2026.4.

If you run an older core, nothing breaks: HACS will not offer 1.1.0 there, you
keep the version you have, and the price forecast goes on working. What stops
arriving is new features.

## Installation

### HACS (recommended)

1. In HACS, go to **Integrations → ⋮ → Custom repositories**.
2. Add `https://github.com/Odatas/meteo-volt-ha` with category **Integration**.
3. Search for **Meteo-Volt** and install it.
4. Restart Home Assistant.

### Manual

1. Copy the `meteo_volt` folder into `<config>/custom_components/`.
2. Restart Home Assistant.

## Configuration

Add the integration via **Settings → Devices & Services → Add Integration → Meteo-Volt**. You will be asked for:

| Field | Required | Description |
|---|---|---|
| **API Token** | yes | Your Meteo-Volt API key. Validated against the API during setup. |
| **Grid Fees** | no | A flat surcharge in EUR/kWh added to every forecast value (e.g. grid charges, taxes), so the forecast reflects your end price instead of the raw exchange price. Default `0.0`. |
| **Grid connection** | no | The limit of your grid connection in kW. Only taken into account once several vehicles are planned together. |

The token is used as the config entry's unique ID, so the same token cannot be added twice.

**Charge planning is optional.** Under the integration entry, add a charge point and a vehicle
(**Add charge point**, **Add vehicle**). The charge point is the wallbox or socket you charge from;
it does not have to be smart. The vehicle needs its capacity, minimum and maximum state of charge,
charging power, efficiency, consumption and the entity that reports its state of charge. Without a
vehicle, nothing changes: the six forecast sensors stay exactly as they are.

## Entities

### Price forecast

One device (**Meteo-Volt Dienst**) with six sensors:

| Sensor | State | Notes |
|---|---|---|
| **Q10** | number of slots | Forecast series in the `forecast` attribute. |
| **Q50** | number of slots | Forecast series in the `forecast` attribute. |
| **Q90** | number of slots | Forecast series in the `forecast` attribute. |
| **Model** | model name | Which model produced the forecast (server-decided). |
| **Snapshot Time** | timestamp | When the underlying weather snapshot was created. |
| **Computed At** | timestamp | When the prediction was computed. |

**Important:** the state of the Q10/Q50/Q90 sensors is the **number of slots** in the current forecast, not a price. The actual prices live in the `forecast` attribute, for templates and automations:

```yaml
forecast:
  - target_timestamp: "2026-06-10T08:00:00+00:00"
    value: 0.0421   # q50 + grid_fees, in EUR/kWh
  - target_timestamp: "2026-06-10T08:15:00+00:00"
    value: 0.0398
  # ...
```

`value` already includes the configured grid fee.

### Vehicle

Every vehicle gets its own device with eight entities:

| Entity | State | Notes |
|---|---|---|
| **Charge now** | on / off | Whether to charge now. Attributes `quelle` (`plan` or `default`) and `ziel_erreicht` |
| **Planned charging power** | kW | The power that goes with Charge now, `0` when it is off |
| **Next charge start** | timestamp | Start of the next charging block after the current one |
| **Planned energy** | kWh | Energy drawn from the grid over the whole plan |
| **Planned cost** | EUR | Including grid fees when you configured them |
| **State of charge at plan end** | % | |
| **Plan feasible** | on / off | Attribute `violations` says why not |
| **Charge plan** | `aktuell`, `kein_plan`, or why the vehicle has no plan | Attributes `slots`, `intervals`, `warnings`, `fehler` |

Energy, cost, state of charge at plan end and Plan feasible show `unknown` while there is no
usable plan. Charge now then falls back to a safe default: it charges only below the vehicle's
minimum state of charge.

**The integration does not switch anything.** Charge now is a signal. The automation that
switches your wallbox is yours, and so is any fine-tuning your hardware allows.

**Charge now follows the measured state of charge, not only the clock.** It switches off as soon
as the vehicle reaches the target of the current charging block and stays off until that block
ends. It never charges longer than the plan. How precisely it stops depends on how often your
state-of-charge entity reports: one that reports every 15 minutes can stop up to 15 minutes late.

**Deviation warning.** After two hours of charging, the integration compares how fast the vehicle
actually charged with what the plan assumed. More than 5 % off raises a repair issue that names
the likely cause, usually the charging efficiency, the capacity or the charging power in the
vehicle settings.

The plan attributes are never written to the database. A plan needs no history, and the full
slot grid would exceed the recorder's attribute limit.

## The panel

The integration adds **Meteo-Volt** to the sidebar. Every user sees it, admin rights are not
needed. Without a vehicle it shows only the prices.

| Tab | What you see |
|---|---|
| **Overview** | The risk setting — Economical, Balanced or Safe, for all vehicles. The charging plan of every vehicle on one time axis under the electricity price: state of charge, charging, away, a mark at every departure. The trips of all vehicles for the coming days, filterable by driver. |
| **Prices** | Price now, the cheapest window today and tomorrow, the last day with exchange prices. The chart from now to the end of the horizon: exchange prices solid, the Q50 forecast dashed inside the Q10–Q90 band. Per day the cheapest window of 1 to 4 hours, low, high, daily average and the forecast spread. |
| **One tab per vehicle** | State of charge now, planned kWh, cost and state of charge at plan end. The status: "Away until 17:30", "Charging now, 11 kW", "Charging from 22:00" or "No charging planned". The chart of state of charge, charging blocks, trips and price over the horizon. The charging blocks with their reason, and the vehicle's trips with what the plan says about each: "Departure at 80 %", or a warning when a target is out of reach or the trip pulls the car below its minimum. A trip under way has a **Back home** button: the trip is then ignored and charging is planned right away; **Restore** takes it back. |

The toolbar shows when the plan was made and has a **Replan** button. Where grid fees are
configured, the switch **Exchange | With grid fees** applies to every price and cost in the panel.

### Trips

A trip is the one kind of entry: the car is away from departure to return. The **Trip** button
opens the form.

| Field | What it means for the plan |
|---|---|
| Departure, return | The car is unavailable in between |
| Repeat | Once, daily, every weekday, weekly, monthly or annually — on the weekday or date of the departure |
| Round-trip distance (km) | Booked as consumption at the departure |
| Vehicle, driver | Which car; the driver is shown, warns when one person is on the road with two cars at once, and ends the trip early when they come home (see below) |
| State of charge at departure (%) | Optional. A charging target for the departure |
| Keep minimum SoC | Ticked by default. The car leaves with its minimum state of charge plus what the trip consumes, so it never comes back below the minimum. Untick it only if you can charge on the way |

The form checks the input as you type and names the field. A recurring trip can be changed or
deleted for this trip only, for this and all following, or for all. Every save, delete and cancel
shows a message with **Undo** at the bottom. After every change the plan is recomputed.

**Back home early.** A trip under way stops blocking charging as soon as the car or its driver
comes home in the last 30 % of the trip — for a three-hour trip, the last hour. The car counts if
its vehicle has a **Location** (a `device_tracker`), the driver if the trip has one; whichever
arrives first wins. The trip is then ignored, exactly as with the **Back home** button, and the
event `meteo_volt_trip_ignored` fires with `entry`, `date`, `vehicle` and `source`, for a
notification of your own.

**Plugged in at home.** If the charge point has a **Plugged in** entity, plugging the car into it
ends a running trip at any time. The car's own plug entity and the charge point's must both switch
on within 10 minutes; a car without its own plug entity counts on the charge point alone, as long
as it is the only vehicle at that charge point. A public charger does not count.

**Late back.** If a trip reaches its return while its car and driver are still away, it extends
itself by 15 minutes at a time and shows "Away until 18:30 (extended)". It needs the same sources
as above, at least one reporting a real state other than `home`; a tracker that is `unavailable`
extends nothing. It never runs into the vehicle's next trip and never more than 12 hours past the
planned return. Coming home or plugging in ends it.

Without trips, Meteo-Volt plans without driving.

## Using it

1. Add the integration with your token. The six forecast sensors and the **Prices** tab work from
   here.
2. Add a charge point and a vehicle under the integration entry. The vehicle gets its device with
   the eight entities above and its own tab in the panel.
3. Enter your trips in the panel and pick the risk you are comfortable with.
4. Let your wallbox follow **Charge now** and **Planned charging power** with an automation like
   the one below.

### Automation: let the wallbox follow Charge now

Replace the entity IDs with yours. Their names follow the language of your Home Assistant.
`number.wallbox_charging_power` stands for the power setpoint of your wallbox, in kW.

```yaml
automation:
  - alias: "Wallbox follows Meteo-Volt"
    mode: queued
    triggers:
      - trigger: state
        entity_id: binary_sensor.my_car_charge_now
        to: "on"
        id: "start"
      - trigger: state
        entity_id: binary_sensor.my_car_charge_now
        to: "off"
        id: "stop"
      - trigger: state
        entity_id: sensor.my_car_planned_charging_power
        not_to:
          - "unavailable"
          - "unknown"
        id: "power"
    actions:
      - choose:
          - conditions:
              - condition: trigger
                id:
                  - "start"
                  - "power"
              - condition: state
                entity_id: binary_sensor.my_car_charge_now
                state: "on"
            sequence:
              - action: number.set_value
                target:
                  entity_id: number.wallbox_charging_power
                data:
                  value: "{{ states('sensor.my_car_planned_charging_power') }}"
              - action: switch.turn_on
                target:
                  entity_id: switch.wallbox_charging
          - conditions:
              - condition: trigger
                id: "stop"
              - condition: state
                entity_id: binary_sensor.my_car_charge_now
                state: "off"
            sequence:
              - action: switch.turn_off
                target:
                  entity_id: switch.wallbox_charging
```

The setpoint is set before the wallbox switches on and follows **Planned charging power** while
charging. `mode: queued` keeps the runs in order, and every branch checks Charge now again, so a
late run never undoes a newer one. For a current setpoint instead of power: amperes = kW × 1000 ÷
(230 V × phases).

> **Two vehicles on one wallbox:** until vehicles are assigned to charge points, both can report
> Charge now at the same time. Your automation has to decide which one charges.

### Actions

Everything the panel writes goes through actions that automations can call as well:
`meteo_volt.create_appointment`, `update_appointment`, `delete_appointment`,
`cancel_appointments`, `undo`, `ignore_appointment`, `set_risk` and `replan`. Their fields are described in the action
picker under **Developer tools → Actions**.

### Template: cheapest upcoming slot

A template sensor exposing the lowest-priced future slot from the median forecast:

```yaml
template:
  - sensor:
      - name: "Cheapest price today"
        unit_of_measurement: "EUR/kWh"
        state: >
          {% set slots = state_attr('sensor.meteo_volt_q50', 'forecast') %}
          {% if slots %}
            {{ slots | map(attribute='value') | min }}
          {% else %}
            unknown
          {% endif %}
```

Extend this to pick the cheapest N slots and trigger something — the raw material (timestamp + value per slot) is all in the attribute.

## Troubleshooting

- **Setup fails with "invalid auth":** check the token. Note that in this early version a token error and an unreachable server both surface as an auth error.
- **Sensors show `unknown` / no data:** the hourly poll may not have completed yet, or the API returned no slots. Check the Home Assistant logs for the `meteo_volt` logger.
- **State shows a large number (e.g. 672):** that is expected — it's the slot count. Prices are in the `forecast` attribute (see above).
- **Meteo-Volt is missing from the sidebar:** the panel registers when the first config entry loads. Reload the browser page; if it stays missing, check the logs for the `meteo_volt` logger.

## Technical notes

- **Polling:** once per hour (`cloud_polling`). The server-side data itself refreshes independently; polling more often would not yield newer data.
- **Units:** all prices are EUR/kWh.
- **Timestamps:** slot timestamps are UTC (ISO 8601). Convert to local time in templates as needed. The panel shows everything in Home Assistant's time zone.
- **Panel:** plain JavaScript, served by Home Assistant from `custom_components/meteo_volt/frontend/`. Nothing is loaded from the internet. It speaks German when Home Assistant does, English otherwise, and works in the Companion app.

## Disclaimer

Meteo-Volt provides price *predictions*. They can be wrong, sometimes substantially, especially for extreme price events. Do not rely on them for decisions where an incorrect forecast would cause harm or significant cost. This integration is provided as-is, without warranty.
