# Meteo-Volt for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

Home Assistant integration for the [Meteo-Volt](https://github.com/Odatas/meteo-volt-ha) electricity price prediction service. It polls the Meteo-Volt API once per hour and exposes the forecast as sensors, ready for charting and automations (e.g. charging an EV during the cheapest hours). Currently the API is in beta and there is no open way of reciving an api key.

> **First release — rudimentary.** Expect rough edges. There is no prediction model selector in Home Assistant yet.

## What it does

Meteo-Volt predicts German day-ahead electricity prices in 15-minute slots, each with three quantiles:

- `q10` — optimistic (low) estimate
- `q50` — median (the main forecast)
- `q90` — pessimistic (high) estimate

The integration fetches the current forecast hourly and makes the full slot series available as an entity attribute for charting.

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

## Charge planning

Optional. Under the integration entry, add a charge point and a vehicle (**Add charge point**,
**Add vehicle**). Every vehicle then gets its own device with eight entities. Without a vehicle,
nothing changes: the six forecast sensors stay exactly as they are.

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

### Automation: let the wallbox follow Charge now

Replace the entity IDs with yours. Their names follow the language of your Home Assistant.

```yaml
automation:
  - alias: "Wallbox follows Meteo-Volt"
    triggers:
      - trigger: state
        entity_id: binary_sensor.my_car_charge_now
        to: "on"
        id: "an"
      - trigger: state
        entity_id: binary_sensor.my_car_charge_now
        to: "off"
        id: "aus"
    actions:
      - choose:
          - conditions:
              - condition: trigger
                id: "an"
            sequence:
              - action: switch.turn_on
                target:
                  entity_id: switch.wallbox_charging
          - conditions:
              - condition: trigger
                id: "aus"
            sequence:
              - action: switch.turn_off
                target:
                  entity_id: switch.wallbox_charging
```

If your wallbox takes a power or current setpoint, set it from **Planned charging power** in the
same automation.

> **Two vehicles on one wallbox:** until vehicles are assigned to charge points, both can report
> Charge now at the same time. Your automation has to decide which one charges.

### Chart the charge plan with ApexCharts

Charging power per slot as columns, the planned state of charge as a line:

```yaml
type: custom:apexcharts-card
header:
  show: true
  title: Charge plan
graph_span: 2d
span:
  start: hour
yaxis:
  - id: kw
    min: 0
  - id: soc
    min: 0
    max: 100
    opposite: true
series:
  - entity: sensor.my_car_charge_plan
    name: Charging power
    type: column
    yaxis_id: kw
    unit: kW
    data_generator: |
      return (entity.attributes.slots || []).map((slot) => {
        return [new Date(slot.t).getTime(), slot.kw || 0];
      });
  - entity: sensor.my_car_charge_plan
    name: State of charge
    type: line
    yaxis_id: soc
    unit: "%"
    data_generator: |
      return (entity.attributes.slots || []).map((slot) => {
        return [new Date(slot.t).getTime() + 15 * 60 * 1000, slot.soc_end_pct];
      });
```

`soc_end_pct` is the state of charge at the *end* of a slot, hence the 15 minutes.

## Troubleshooting

- **Setup fails with "invalid auth":** check the token. Note that in this early version a token error and an unreachable server both surface as an auth error.
- **Sensors show `unknown` / no data:** the hourly poll may not have completed yet, or the API returned no slots. Check the Home Assistant logs for the `meteo_volt` logger.
- **State shows a large number (e.g. 672):** that is expected — it's the slot count. Prices are in the `forecast` attribute (see above).

## Technical notes

- **Polling:** once per hour (`cloud_polling`). The server-side data itself refreshes independently; polling more often would not yield newer data.
- **Units:** all prices are EUR/kWh.
- **Timestamps:** slot timestamps are UTC (ISO 8601). Convert to local time in charts/templates as needed.

## Generated contract fixtures

Everything under `tests/fixtures/contract/` is **generated and must never be edited by
hand**, together with `contract.lock.json` in the repository root:

| File | What it is |
| --- | --- |
| `tests/fixtures/contract/plan-*.schema.json` | JSON Schema for a plan request, response and error |
| `tests/fixtures/contract/*.request.json` / `*.response.json` | Paired example exchanges, one pair per scenario |
| `tests/fixtures/contract/errors/*.request.json` / `*.problem.json` | The same for each documented error case |
| `contract.lock.json` | The content hash of every file above |

They come from `meteo-volt-brain`, which owns the charge-planning contract, and are
produced by:

```bash
# in the meteo-volt-brain checkout, with its own virtualenv active
source meteovolt_plan/.venv/Scripts/activate   # Scripts/ on Windows, bin/ elsewhere
python scripts/export_contract.py --to-ha ../meteo-volt-ha
```

Nothing under `custom_components/` is touched by that command. Fixtures you write
yourself belong somewhere else — `tests/fixtures/contract/` holds generated files only,
and the check below rejects anything there that has no lock entry.

### Verifying the copies

The check runs as part of the normal test suite, so you cannot forget it:

```bash
python -m pytest tests/
```

It is also available on its own, which is the form to use in a pre-commit hook or
whenever you want a single answer without the rest of the suite:

```bash
python scripts/check_contract.py
# Kontrakt in sync (35 Dateien geprueft)
```

Both run the same code (`scripts/check_contract.py`); the test file only calls it.
Neither needs a `meteo-volt-brain` checkout.

The check compares the **content hash** of each file, not the `brain_commit` stamp it
carries. The stamp names the commit the file was generated *from*, so it necessarily
lags one commit behind the commit that contains the file — comparing stamps would
report drift on every unrelated commit in the brain repository.

The hash is taken over the **parsed** document, not the bytes on disk, and the parsed
document is canonicalised per [RFC 8785][jcs] first. That is why reformatting a fixture
— reindenting it, or writing `58` where the file says `58.0` — does not register as a
change, while any change to an actual value does. The canonicaliser is the `rfc8785`
package (a test-only dependency, see `tests/requirements-test.txt`); this repository
deliberately does not carry its own copy of that algorithm.

Checks performed, per file and in both directions:

- every lock entry has a file, and it hashes to the recorded value;
- every file under `tests/fixtures/contract/` has a lock entry;
- the lock itself is present, carries `do_not_edit`, and lists at least one file;
- where a file carries an `x-meteo-volt-contract` stamp, the stamp agrees with the
  content — the lock hash is taken with the stamp removed, so this is the only thing
  that looks at the stamp at all.

[jcs]: https://www.rfc-editor.org/rfc/rfc8785

### When the check fails

The message names the file and the reason. There are three cases, and they want
opposite responses:

| Message | What happened | What to do |
| --- | --- | --- |
| `sha256 weicht vom Lock-Eintrag ab` | A generated file was edited by hand | Undo the edit. `git checkout -- <file>` if it is committed, otherwise re-run the export above |
| `Datei fehlt` / `kein Lock-Eintrag` | A file was deleted, or one was added that the brain did not generate | Re-run the export. If you added the file yourself, move it out of `tests/fixtures/contract/` |
| `Stempel …` | The stamp inside a schema file was edited | Undo the edit or re-run the export |

Do **not** fix a failure by editing `contract.lock.json` — the lock is generated too,
and the brain-side checker (`meteo-volt-brain/scripts/check_contract_drift.py`, which
needs all three checkouts side by side) compares it against what the brain produces
today. Editing the lock to match a hand-edited fixture turns a loud local failure into
a silent inconsistency between the repositories.

If the fixtures are current but the *contract itself* changed in the brain, that is not
something this check can see — it has no brain checkout to compare against. Run the
export again and commit the result; `check_contract_drift.py` on the brain side is what
catches a stale-but-self-consistent copy.

## Disclaimer

Meteo-Volt provides price *predictions*. They can be wrong, sometimes substantially, especially for extreme price events. Do not rely on them for decisions where an incorrect forecast would cause harm or significant cost. This integration is provided as-is, without warranty.
