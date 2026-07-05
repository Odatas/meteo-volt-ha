# Meteo-Volt for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

Home Assistant integration for the [Meteo-Volt](https://github.com/Odatas/meteo-volt-ha) electricity price prediction service. It polls the Meteo-Volt API once per hour and exposes the forecast as sensors, ready for charting and automations (e.g. charging an EV during the cheapest hours).

> **First release — rudimentary.** Expect rough edges. The forecast horizon and model you receive are determined entirely by your API key's tier; there is no model or horizon selector in Home Assistant yet.

## What it does

Meteo-Volt predicts German day-ahead electricity prices in 15-minute slots, each with three quantiles:

- `q10` — optimistic (low) estimate
- `q50` — median (the main forecast)
- `q90` — pessimistic (high) estimate

The integration fetches the current forecast hourly and makes the full slot series available as an entity attribute for charting.

## Requirements

- A Meteo-Volt API token. The token's tier decides how far ahead the forecast reaches (free / paid / admin). You cannot change model or horizon from within Home Assistant.
- Home Assistant with HACS installed (for the recommended install path).

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

The token is used as the config entry's unique ID, so the same token cannot be added twice.

## Entities

The integration creates one device (**Meteo-Volt Dienst**) with the following sensors:

| Sensor | State | Notes |
|---|---|---|
| **Q10** | number of slots | Forecast series in the `forecast` attribute. |
| **Q50** | number of slots | Forecast series in the `forecast` attribute. |
| **Q90** | number of slots | Forecast series in the `forecast` attribute. |
| **Model** | model name | Which model produced the forecast (server-decided). |
| **Snapshot Time** | timestamp | When the underlying weather snapshot was created. |
| **Computed At** | timestamp | When the prediction was computed. |

**Important:** the state of the Q10/Q50/Q90 sensors is the **number of slots** in the current forecast, not a price. The actual prices live in the `forecast` attribute:

```yaml
forecast:
  - target_timestamp: "2026-06-10T08:00:00+00:00"
    value: 0.0421   # q50 + grid_fees, in EUR/kWh
  - target_timestamp: "2026-06-10T08:15:00+00:00"
    value: 0.0398
  # ...
```

`value` already includes the configured grid fee.

## Usage examples

### Chart the forecast band with ApexCharts

Using [apexcharts-card](https://github.com/RomRider/apexcharts-card). Shows all three quantiles (Q10/Q50/Q90) in ct/kWh, with the outer bounds dimmed:

```yaml
type: custom:apexcharts-card
header:
  show: true
  title: Meteo-Volt Prognose
  show_states: false
graph_span: 7d
span:
  start: hour
all_series_config:
  unit: ct/kWh
  show:
    legend_value: false
apex_config:
  legend:
    show: true
  yaxis:
    decimalsInFloat: 0
series:
  - entity: sensor.meteo_volt_q10
    name: Q10
    type: line
    curve: smooth
    stroke_width: 2
    opacity: 0.4
    color: "#28a745"
    data_generator: |
      return entity.attributes.forecast.map((entry) => {
        return [new Date(entry.target_timestamp).getTime(), entry.value * 100];
      });
  - entity: sensor.meteo_volt_q50
    name: Q50
    type: line
    curve: smooth
    stroke_width: 3
    opacity: 1
    color: "#007bff"
    data_generator: |
      return entity.attributes.forecast.map((entry) => {
        return [new Date(entry.target_timestamp).getTime(), entry.value * 100];
      });
  - entity: sensor.meteo_volt_q90
    name: Q90
    type: line
    curve: smooth
    stroke_width: 2
    opacity: 0.4
    color: "#dc3545"
    data_generator: |
      return entity.attributes.forecast.map((entry) => {
        return [new Date(entry.target_timestamp).getTime(), entry.value * 100];
      });
```

> `graph_span: 7d` suits the paid tier. On the free tier the forecast is shorter (~2–3 days), so the axis will show empty space beyond the data — lower it to `3d` if you're on free.

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

Extend this to pick the cheapest N slots and trigger charging — the raw material (timestamp + value per slot) is all in the attribute.

## Troubleshooting

- **Setup fails with "invalid auth":** check the token. Note that in this early version a token error and an unreachable server both surface as an auth error.
- **Sensors show `unknown` / no data:** the hourly poll may not have completed yet, or the API returned no slots. Check the Home Assistant logs for the `meteo_volt` logger.
- **State shows a large number (e.g. 672):** that is expected — it's the slot count. Prices are in the `forecast` attribute (see above).

## Technical notes

- **Polling:** once per hour (`cloud_polling`). The server-side data itself refreshes independently; polling more often would not yield newer data.
- **Units:** all prices are EUR/kWh.
- **Timestamps:** slot timestamps are UTC (ISO 8601). Convert to local time in charts/templates as needed.

## Disclaimer

Meteo-Volt provides price *predictions*. They can be wrong, sometimes substantially, especially for extreme price events. Do not rely on them for decisions where an incorrect forecast would cause harm or significant cost. This integration is provided as-is, without warranty.
