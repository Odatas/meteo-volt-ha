# C1-C2 Standort-Stammdaten als Subentries — Umsetzungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fahrzeuge und Ladepunkte als zwei Config-Subentry-Typen unter dem bestehenden Meteo-Volt-Eintrag anlegen, ändern und löschen — statische Stammdaten, keine Entitäten.

**Architecture:** Die Abbildung von Formulardaten auf Kontrakt-Fragmente liegt in einem neuen, Home-Assistant-freien Modul `stammdaten.py` (Vorbild: `overrides.py`) und ist damit ohne HA prüfbar. `config_flow.py` bekommt nur die Formulare und die zwei `ConfigSubentryFlow`-Klassen. Die Subentries kommen additiv: ein bestehender Eintrag läuft unverändert weiter, die Config-Flow-`VERSION` bleibt 1.

**Tech Stack:** Python 3.12 (Venv `.venv`), voluptuous, Home Assistant 2026.4 (nur zur Laufzeit, nicht in den Testabhängigkeiten), pytest + jsonschema.

**Spec:** `meteo-volt-brain/docs/features/C1-C2-stammdaten-subentries/spec.md`, Branch `c1-c2-stammdaten-subentries`. Bei Widerspruch gilt die Spec, nicht dieser Plan.

## Global Constraints

- **Branch** ist `c1-c2-stammdaten-subentries`. Gemergt wird nach `beta`. **Niemals nach `master`.**
- **Python** ist `.venv/Scripts/python.exe`. Ein blankes `python` ist der Windows-Store-Alias und schlägt fehl.
- **`custom_components/` ist Endnutzer-Code.** HACS paketiert genau dieses Verzeichnis. `tests/` und `scripts/` erreichen keinen Nutzer.
- **`stammdaten.py` importiert nichts aus Home Assistant.** Kein `homeassistant`, kein `voluptuous`. Der Pfad-Import im Test ist die schärfste Fassung dieser Auflage: bekäme das Modul je einen HA-Import, scheitert schon der Import.
- **Die 35 Kontrakt-Artefakte werden nie von Hand geändert** — `tests/fixtures/contract/**` und `contract.lock.json`. Sie entstehen im Brain.
- **Das `unique_id`-Schema `meteo_volt_{entry_id}_{key}` bleibt unverändert.** Dieses Paket legt keine Entität und kein Gerät an (Bestandsschutz Auflage 5).
- **Config-Flow-`VERSION` bleibt 1, `async_migrate_entry` entsteht nicht** (Bestandsschutz Auflage 4).
- **HA-Untergrenze ist `2026.4.0`**, exakt der Kern der manuellen Abnahme.
- **Zeilenenden LF.** Der Arbeitsbaum trägt CRLF, das Repo LF. Prüf am gestagten Blob: `git show ":<datei>" | grep -q $'\r'` muss leer bleiben.
- **Commit-Nachrichten** englisch, Imperativ, mit abschliessender Zeile `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- **Die Testsuite ist vor jedem Commit grün:** `.venv/Scripts/python.exe -m pytest -q` — Ausgangsstand sind 55 bestandene Tests.

---

## Dateien

| Datei | Verantwortung |
|---|---|
| `custom_components/meteo_volt/stammdaten.py` | **neu.** Feldnamen, Vorbelegung, Abbildung auf Kontrakt-Fragmente, Auflösung der Ladepunkt-Zuordnung, Namensvergabe. HA-frei. |
| `custom_components/meteo_volt/config_flow.py` | **geändert.** `async_get_supported_subentry_types` und die zwei Flow-Klassen. Nur Formulare und Verdrahtung. |
| `custom_components/meteo_volt/translations/de.json` | **geändert.** Block `config_subentries`. |
| `custom_components/meteo_volt/translations/en.json` | **geändert.** derselbe Block, englisch. |
| `hacs.json` | **geändert.** `homeassistant` von `2024.1.0` auf `2026.4.0`. |
| `custom_components/meteo_volt/manifest.json` | **geändert.** Version auf `1.2.0-beta.1`. |
| `README.md` | **geändert.** Ein Absatz zur angehobenen Untergrenze. |
| `tests/test_stammdaten.py` | **neu.** Prüft die Abbildung gegen das vendorte `plan-request.schema.json`. |
| `tests/test_uebersetzungen.py` | **neu.** Prüft, dass jedes Feld in beiden Sprachen ein Label hat. |

**Was der automatische Gate nicht sieht:** das Formular, den Flow, das Rendern der Übersetzungen. Dafür ist die manuelle Abnahme am Ende dieses Plans da.

---

### Task 1: `stammdaten.py` — Modul und Ladepunkt-Abbildung

**Files:**
- Create: `custom_components/meteo_volt/stammdaten.py`
- Test: `tests/test_stammdaten.py`

**Interfaces:**
- Consumes: nichts.
- Produces: `TYP_LADEPUNKT = "station"`, `TYP_FAHRZEUG = "vehicle"`, die Feldkonstanten `FELD_*`, die Tupel `LADEPUNKT_FELDER`/`FAHRZEUG_FELDER`, die dicts `LADEPUNKT_DEFAULTS`/`FAHRZEUG_DEFAULTS`, `LADEPUNKT_WIRKUNGSGRAD = 1.0`, `VERBRAUCHSMODELL = {"type": "none"}` und `zu_ladepunkt(daten: dict, ladepunkt_id: str) -> dict`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_stammdaten.py`:

```python
"""Prueft die Abbildung Subentry -> Kontrakt-Fragment.

Die Abbildung ist die Stelle, an der ein Fehler wehtut: ein vertauschter
Faktor 100 beim Wirkungsgrad faellt in keinem Formular auf, wohl aber in der
Rechnung des Planers. Geprueft wird gegen die vendorten Schemas, nicht gegen
eine hier nochmal hingeschriebene Erwartung.

Was dieser Test NICHT sieht: das Formular, den Config-Flow und die
Uebersetzungen. Die brauchen Home Assistant und werden von Hand abgenommen.
"""

import importlib.util
import json
from pathlib import Path

import jsonschema
import pytest

WURZEL = Path(__file__).resolve().parents[1]
INTEGRATION = WURZEL / "custom_components" / "meteo_volt"
CONTRACT = WURZEL / "tests" / "fixtures" / "contract"

# Per Pfad geladen, NICHT als custom_components.meteo_volt.stammdaten: das
# Paket zu importieren zieht dessen __init__.py und damit homeassistant
# herein, das in den Testabhaengigkeiten nicht steckt. Der Ladeweg ist
# zugleich die schaerfste Fassung der Auflage "stammdaten.py hat keine
# HA-Importe" -- bekaeme das Modul je einen, scheitert schon dieser Import.
_SPEC = importlib.util.spec_from_file_location(
    "meteo_volt_stammdaten", INTEGRATION / "stammdaten.py")
stammdaten = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(stammdaten)


def _schema() -> dict:
    roh = json.loads((CONTRACT / "plan-request.schema.json").read_text(encoding="utf-8"))
    return {k: v for k, v in roh.items() if k != "x-meteo-volt-contract"}


REQUEST_SCHEMA = _schema()


def teilschema(name: str) -> dict:
    """Ein einzelnes Modell aus $defs, allein validierbar."""
    return {"$ref": f"#/$defs/{name}", "$defs": REQUEST_SCHEMA["$defs"]}


def test_das_teilschema_faengt_ueberhaupt_etwas():
    """Gegenprobe zuerst. Ein Validator, der alles durchwinkt, waere schlimmer
    als keiner -- und genau das passiert, wenn der $ref ins Leere zeigt."""
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"id": "x", "max_power_kw": 11.0, "phases": 2},
                            teilschema("Station"))


def test_ladepunkt_aus_vorbelegung_ist_kontraktkonform():
    fragment = stammdaten.zu_ladepunkt(dict(stammdaten.LADEPUNKT_DEFAULTS), "wb-1")
    jsonschema.validate(fragment, teilschema("Station"))
    assert fragment["id"] == "wb-1"


def test_ladepunkt_traegt_keinen_wirkungsgrad_des_kontrakt_defaults():
    """Abschnitt 3 der Spec: 1.0, nicht der Kontrakt-Default 0.99. Sonst wird
    das eine Prozent doppelt gezaehlt, weil der Fahrzeugwert es schon enthaelt
    -- und zwar still."""
    fragment = stammdaten.zu_ladepunkt(dict(stammdaten.LADEPUNKT_DEFAULTS), "wb-1")
    assert fragment["efficiency"] == 1.0


def test_weggelassene_optionale_felder_ergeben_die_vorbelegung():
    """Min. Leistung und Phasen stehen im eingeklappten Abschnitt. Wer ihn nie
    aufklappt, schickt sie nicht mit -- dann darf kein None ankommen."""
    fragment = stammdaten.zu_ladepunkt({stammdaten.FELD_MAX_LEISTUNG: 22.0}, "wb-2")
    assert fragment["min_power_kw"] == 1.4
    assert fragment["phases"] == 3
    assert fragment["available"] is True
    jsonschema.validate(fragment, teilschema("Station"))
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_stammdaten.py -v`

Expected: FAIL — `FileNotFoundError` beziehungsweise `ModuleNotFoundError`, weil `stammdaten.py` noch nicht existiert.

- [ ] **Step 3: Write the module**

Create `custom_components/meteo_volt/stammdaten.py`:

```python
"""Bildet die beiden Subentry-Typen auf Kontrakt-Fragmente ab.

Dieses Modul importiert bewusst NICHTS aus Home Assistant -- wie overrides.py.
Nur so laesst es sich in der Testsuite dieses Repos laden; homeassistant steckt
nicht in den Testabhaengigkeiten, und die HA-Abnahme laeuft von Hand auf einer
echten Instanz.

Der Schnitt hat einen zweiten Zweck. Die Abbildung ist die Stelle, an der ein
Fehler wehtut: ein vertauschter Faktor 100 beim Wirkungsgrad faellt in keinem
Formular auf, wohl aber in der Rechnung des Planers. Sie liegt deshalb hier und
nicht im Config-Flow, wo sie ohne Home Assistant nicht pruefbar waere.

Spec: meteo-volt-brain/docs/features/C1-C2-stammdaten-subentries/spec.md
"""

from __future__ import annotations

# --- Subentry-Typen ---------------------------------------------------------

TYP_LADEPUNKT = "station"
TYP_FAHRZEUG = "vehicle"

# --- Feldnamen --------------------------------------------------------------
# Zugleich die Schluessel im Formular und in den Uebersetzungen.
# tests/test_uebersetzungen.py prueft beide Sprachen gegen genau diese Listen.

FELD_NAME = "name"

FELD_MAX_LEISTUNG = "max_power_kw"
FELD_VERFUEGBAR = "available"
FELD_MIN_LEISTUNG = "min_power_kw"
FELD_PHASEN = "phases"

FELD_KAPAZITAET = "capacity_kwh"
FELD_SOC_MIN = "soc_min_pct"
FELD_SOC_MAX = "soc_max_pct"
FELD_MAX_LADELEISTUNG = "max_charge_kw"
FELD_VERBRAUCH = "consumption_kwh_per_100km"
FELD_SOC_ENTITAET = "soc_entity"
# Nicht "station": das ist schon der Wert von TYP_LADEPUNKT. Zwei Namensraeume,
# derselbe String -- beim Lesen einer Subentry-dict waere nicht mehr zu sehen,
# welcher von beiden gemeint ist.
FELD_LADEPUNKT = "station_id"
FELD_ANGESTECKT = "plugged_entity"
FELD_MIN_LADELEISTUNG = "min_charge_kw"
FELD_WIRKUNGSGRAD = "efficiency_pct"

LADEPUNKT_FELDER = (
    FELD_NAME,
    FELD_MAX_LEISTUNG,
    FELD_VERFUEGBAR,
    FELD_MIN_LEISTUNG,
    FELD_PHASEN,
)

FAHRZEUG_FELDER = (
    FELD_NAME,
    FELD_KAPAZITAET,
    FELD_SOC_MIN,
    FELD_SOC_MAX,
    FELD_MAX_LADELEISTUNG,
    FELD_VERBRAUCH,
    FELD_SOC_ENTITAET,
    FELD_LADEPUNKT,
    FELD_ANGESTECKT,
    FELD_MIN_LADELEISTUNG,
    FELD_WIRKUNGSGRAD,
)

# --- Vorbelegung ------------------------------------------------------------

LADEPUNKT_DEFAULTS = {
    FELD_MAX_LEISTUNG: 11.0,
    FELD_VERFUEGBAR: True,
    FELD_MIN_LEISTUNG: 1.4,
    FELD_PHASEN: 3,
}

FAHRZEUG_DEFAULTS = {
    FELD_KAPAZITAET: 58.0,
    FELD_SOC_MIN: 15.0,
    FELD_SOC_MAX: 80.0,
    FELD_MAX_LADELEISTUNG: 11.0,
    FELD_VERBRAUCH: 19.5,
    FELD_MIN_LADELEISTUNG: 1.4,
    FELD_WIRKUNGSGRAD: 92.0,
}

# Abschnitt 3 der Spec: der Ladepunkt traegt keinen Wirkungsgrad. Der
# Kontrakt-Default waere 0.99 -- ein Prozent, das der Fahrzeugwert bereits
# enthaelt. Neutral heisst hier 1.0, sonst wird still doppelt gezaehlt.
LADEPUNKT_WIRKUNGSGRAD = 1.0

# Abschnitt 4: die Strecke gehoert zum Fahrprofil und hat hier keinen Ort.
# "none" heisst, der Planer rechnet ohne Fahrverbrauch. Das ist entschieden,
# nicht vergessen -- siehe Abschnitt 11 der Spec.
VERBRAUCHSMODELL = {"type": "none"}


def zu_ladepunkt(daten: dict, ladepunkt_id: str) -> dict:
    """Ein Station-Fragment des Kontrakts.

    ladepunkt_id ist die subentry_id. Der Kontrakt verlangt eine ueber
    Requests stabile ID; ein Slug aus dem Titel waere es nicht, er aendert
    sich beim Umbenennen.
    """
    return {
        "id": ladepunkt_id,
        "max_power_kw": float(daten[FELD_MAX_LEISTUNG]),
        "min_power_kw": float(
            daten.get(FELD_MIN_LEISTUNG, LADEPUNKT_DEFAULTS[FELD_MIN_LEISTUNG])),
        "phases": int(daten.get(FELD_PHASEN, LADEPUNKT_DEFAULTS[FELD_PHASEN])),
        "efficiency": LADEPUNKT_WIRKUNGSGRAD,
        "available": bool(
            daten.get(FELD_VERFUEGBAR, LADEPUNKT_DEFAULTS[FELD_VERFUEGBAR])),
    }
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_stammdaten.py -v`

Expected: PASS — 4 passed.

- [ ] **Step 5: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest -q`

Expected: `59 passed`.

- [ ] **Step 6: Commit**

```bash
git add custom_components/meteo_volt/stammdaten.py tests/test_stammdaten.py
git commit -m "$(cat <<'EOF'
Map a charge point onto its contract fragment, without Home Assistant

The mapping lives in stammdaten.py with no homeassistant import, on the
model of overrides.py, so the test suite of this repo can load it by path.
That path import is also the sharpest form of the rule: give the module an
HA import and the test stops at the import line.

Station.efficiency is fixed at 1.0 rather than its contract default of
0.99. The vehicle figure already carries cable, meter and onboard charger,
so the default would charge one percent twice, silently.

The counter-check runs first: a phases value of 2 has to fail, or the
sub-schema validator is waving everything through.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: `stammdaten.py` — Fahrzeug-Abbildung

**Files:**
- Modify: `custom_components/meteo_volt/stammdaten.py` (anfügen)
- Modify: `tests/test_stammdaten.py` (anfügen)

**Interfaces:**
- Consumes: aus Task 1 `FAHRZEUG_DEFAULTS`, `FELD_*`, `VERBRAUCHSMODELL`.
- Produces: `zu_fahrzeug(daten: dict, fahrzeug_id: str, soc_pct: float, soc_measured_at: str | None = None, station_id: str | None = None) -> dict`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_stammdaten.py`:

```python
def test_fahrzeug_aus_vorbelegung_ist_kontraktkonform():
    fragment = stammdaten.zu_fahrzeug(
        dict(stammdaten.FAHRZEUG_DEFAULTS), "auto-1", soc_pct=47.0)
    jsonschema.validate(fragment, teilschema("VehicleProfile"))
    assert fragment["id"] == "auto-1"
    assert fragment["soc_pct"] == 47.0


def test_der_wirkungsgrad_wird_ein_stuetzpunkt_bei_voller_leistung():
    """92 Prozent werden zu eta 0.92, und der Punkt liegt bei max_charge_kw.
    Der Faktor 100 ist die Stelle, an der ein Fehler am teuersten waere: er
    faellt in keinem Formular auf."""
    fragment = stammdaten.zu_fahrzeug(
        dict(stammdaten.FAHRZEUG_DEFAULTS), "auto-1", soc_pct=50.0)
    assert fragment["efficiency_curve"] == [{"kw": 11.0, "eta": 0.92}]


def test_das_verbrauchsmodell_ist_none_und_nicht_geteilt():
    """type none, weil die Strecke zum Fahrprofil gehoert. Und je Aufruf ein
    eigenes dict -- ein geteiltes liesse einen Aufrufer die Werte aller
    anderen aendern."""
    a = stammdaten.zu_fahrzeug(dict(stammdaten.FAHRZEUG_DEFAULTS), "a", soc_pct=10.0)
    b = stammdaten.zu_fahrzeug(dict(stammdaten.FAHRZEUG_DEFAULTS), "b", soc_pct=10.0)
    assert a["consumption"] == {"type": "none"}
    assert a["consumption"] is not b["consumption"]
    assert a["consumption"] is not stammdaten.VERBRAUCHSMODELL


def test_ohne_ladepunkt_steht_station_id_auf_null():
    fragment = stammdaten.zu_fahrzeug(
        dict(stammdaten.FAHRZEUG_DEFAULTS), "auto-1", soc_pct=50.0)
    assert fragment["connection"] == {"station_id": None}
    jsonschema.validate(fragment, teilschema("VehicleProfile"))


def test_der_messzeitpunkt_faellt_weg_wenn_es_keinen_gibt():
    """soc_measured_at ist kein Pflichtfeld. Ein None mitzuschicken waere
    etwas anderes als es wegzulassen -- der Kontrakt erlaubt beides, aber ein
    fehlender Zeitpunkt soll fehlen und nicht als gemessen gelten."""
    ohne = stammdaten.zu_fahrzeug(
        dict(stammdaten.FAHRZEUG_DEFAULTS), "auto-1", soc_pct=50.0)
    assert "soc_measured_at" not in ohne

    mit = stammdaten.zu_fahrzeug(
        dict(stammdaten.FAHRZEUG_DEFAULTS), "auto-1", soc_pct=50.0,
        soc_measured_at="2026-09-12T08:00:00+02:00")
    assert mit["soc_measured_at"] == "2026-09-12T08:00:00+02:00"
    jsonschema.validate(mit, teilschema("VehicleProfile"))


def test_weggelassene_erweiterte_fahrzeugfelder_ergeben_die_vorbelegung():
    daten = {
        stammdaten.FELD_KAPAZITAET: 77.0,
        stammdaten.FELD_SOC_MIN: 20.0,
        stammdaten.FELD_SOC_MAX: 90.0,
        stammdaten.FELD_MAX_LADELEISTUNG: 7.4,
        stammdaten.FELD_VERBRAUCH: 21.0,
    }
    fragment = stammdaten.zu_fahrzeug(daten, "auto-3", soc_pct=33.0)
    assert fragment["min_charge_kw"] == 1.4
    assert fragment["efficiency_curve"] == [{"kw": 7.4, "eta": 0.92}]
    jsonschema.validate(fragment, teilschema("VehicleProfile"))
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_stammdaten.py -v`

Expected: FAIL — `AttributeError: module 'meteo_volt_stammdaten' has no attribute 'zu_fahrzeug'`.

- [ ] **Step 3: Write the implementation**

Append to `custom_components/meteo_volt/stammdaten.py`:

```python
def zu_fahrzeug(
    daten: dict,
    fahrzeug_id: str,
    soc_pct: float,
    soc_measured_at: str | None = None,
    station_id: str | None = None,
) -> dict:
    """Ein VehicleProfile-Fragment des Kontrakts.

    soc_pct, soc_measured_at und station_id misst kein Formular. Sie kommen
    aus den Entitaeten des Nutzers und werden hereingereicht -- dieses Modul
    liest selbst nichts. Was bei einem unavailable-Zustand geschieht,
    entscheidet C5.
    """
    max_ladeleistung = float(daten[FELD_MAX_LADELEISTUNG])
    wirkungsgrad_pct = float(
        daten.get(FELD_WIRKUNGSGRAD, FAHRZEUG_DEFAULTS[FELD_WIRKUNGSGRAD]))

    fragment = {
        "id": fahrzeug_id,
        "capacity_kwh": float(daten[FELD_KAPAZITAET]),
        "soc_pct": float(soc_pct),
        "max_charge_kw": max_ladeleistung,
        "min_charge_kw": float(
            daten.get(FELD_MIN_LADELEISTUNG,
                      FAHRZEUG_DEFAULTS[FELD_MIN_LADELEISTUNG])),
        # Ein Stuetzpunkt heisst konstanter Wirkungsgrad ueber die ganze
        # Leistung: der Kontrakt klemmt ausserhalb auf den naechsten Punkt.
        "efficiency_curve": [
            {"kw": max_ladeleistung, "eta": wirkungsgrad_pct / 100},
        ],
        "soc_min_pct": float(daten[FELD_SOC_MIN]),
        "soc_max_pct": float(daten[FELD_SOC_MAX]),
        "consumption_kwh_per_100km": float(daten[FELD_VERBRAUCH]),
        "connection": {"station_id": station_id},
        # Eine Kopie, kein geteiltes dict: sonst aenderte ein Aufrufer die
        # Werte aller anderen mit.
        "consumption": dict(VERBRAUCHSMODELL),
    }

    # Weglassen ist etwas anderes als null: ein fehlender Zeitpunkt soll
    # fehlen und nicht als gemessen gelten.
    if soc_measured_at is not None:
        fragment["soc_measured_at"] = soc_measured_at

    return fragment
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_stammdaten.py -v`

Expected: PASS — 10 passed.

- [ ] **Step 5: Commit**

```bash
git add custom_components/meteo_volt/stammdaten.py tests/test_stammdaten.py
git commit -m "$(cat <<'EOF'
Map a vehicle onto its contract fragment

One percentage field becomes exactly one support point at max_charge_kw:
92 percent turns into eta 0.92. The contract clamps outside the points, so
one point reads cleanly as a constant efficiency, and the test pins the
factor of 100 -- the place where an error costs most and shows least.

consumption is fixed at type none because the distance belongs to the
driving profile, which has no home yet. The dict is copied per call rather
than shared, so one caller cannot edit every other caller's model.

soc_measured_at is omitted when there is none, rather than sent as null. A
missing measurement should be missing, not counted as taken.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: `stammdaten.py` — Auflösung, Namensvergabe, Abschnitte

**Files:**
- Modify: `custom_components/meteo_volt/stammdaten.py` (anfügen)
- Modify: `tests/test_stammdaten.py` (anfügen)

**Interfaces:**
- Consumes: aus Task 1 `TYP_LADEPUNKT`, `TYP_FAHRZEUG`.
- Produces:
  - `ladepunkt_aufloesen(gewaehlt: str | None, bekannte_ids, angesteckt: bool | None = None) -> str | None` — **in diesem Paket von niemandem aufgerufen.** Der Aufrufer ist `C5`, das die Entitäten liest. Die Funktion entsteht hier, weil hier die Abbildung liegt und weil sie hier prüfbar ist; ein Reviewer soll sie nicht als toten Code melden.
  - `naechster_name(vorhandene_titel, typ: str, sprache: str = "en") -> str`
  - `flach_aus_abschnitten(user_input: dict, abschnitte) -> dict`
  - `ABSCHNITTE_LADEPUNKT`, `ABSCHNITTE_FAHRZEUG` — die Abschnittsschlüssel des jeweiligen Formulars.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_stammdaten.py`:

```python
# --- Aufloesung der Ladepunkt-Zuordnung -------------------------------------
# Die fuenf Zeilen der Tabelle aus Abschnitt 5 der Spec, einzeln.

def test_ohne_gewaehlten_ladepunkt_keine_station():
    assert stammdaten.ladepunkt_aufloesen(None, {"wb-1"}) is None


def test_geloeschter_ladepunkt_wird_null_statt_haengender_verweis():
    """Es gibt keine Fehler-Fixture fuer eine unbekannte station_id -- der
    Server pinnt sein Verhalten dort nicht. Also darf der Client gar nicht
    erst eine erzeugen."""
    assert stammdaten.ladepunkt_aufloesen("wb-weg", {"wb-1"}) is None


def test_nicht_angesteckt_heisst_keine_station():
    assert stammdaten.ladepunkt_aufloesen("wb-1", {"wb-1"}, angesteckt=False) is None


def test_angesteckt_heisst_die_gewaehlte_station():
    assert stammdaten.ladepunkt_aufloesen("wb-1", {"wb-1"}, angesteckt=True) == "wb-1"


def test_ohne_angesteckt_sensor_gilt_das_fahrzeug_als_angesteckt():
    """Der dumme Fall ist die Grundeinstellung. Die Gegenannahme machte den
    Plan fuer jeden nutzlos, der keinen solchen Sensor hat."""
    assert stammdaten.ladepunkt_aufloesen("wb-1", {"wb-1"}, angesteckt=None) == "wb-1"


# --- Namensvergabe ----------------------------------------------------------

def test_erster_name_ohne_eingabe():
    assert stammdaten.naechster_name([], stammdaten.TYP_FAHRZEUG, "de") == "Fahrzeug 1"


def test_zweiter_name_zaehlt_hoch():
    assert stammdaten.naechster_name(
        ["Fahrzeug 1"], stammdaten.TYP_FAHRZEUG, "de") == "Fahrzeug 2"


def test_eine_geloeschte_nummer_wird_wiederverwendet():
    """Nicht len()+1: wer 'Fahrzeug 1' loescht und neu anlegt, bekaeme sonst
    eine Dublette zu 'Fahrzeug 2'."""
    assert stammdaten.naechster_name(
        ["Fahrzeug 2"], stammdaten.TYP_FAHRZEUG, "de") == "Fahrzeug 1"


def test_eigene_namen_stoeren_die_nummerierung_nicht():
    assert stammdaten.naechster_name(
        ["Papas Kombi"], stammdaten.TYP_FAHRZEUG, "de") == "Fahrzeug 1"


def test_ladepunkt_heisst_in_beiden_sprachen_wallbox():
    assert stammdaten.naechster_name([], stammdaten.TYP_LADEPUNKT, "de") == "Wallbox 1"
    assert stammdaten.naechster_name([], stammdaten.TYP_LADEPUNKT, "en") == "Wallbox 1"


def test_eine_unbekannte_sprache_faellt_auf_englisch_zurueck():
    assert stammdaten.naechster_name(
        [], stammdaten.TYP_FAHRZEUG, "fr") == "Vehicle 1"


# --- Abschnitte -------------------------------------------------------------

def test_abschnitte_werden_flachgezogen():
    """HA liefert section-Felder verschachtelt zurueck. Gespeichert wird flach,
    damit zu_fahrzeug nichts von Formularabschnitten wissen muss."""
    verschachtelt = {
        "name": "Kombi",
        "batterie": {"capacity_kwh": 58.0},
        "erweitert": {"min_charge_kw": 1.4, "efficiency_pct": 92.0},
    }
    flach = stammdaten.flach_aus_abschnitten(
        verschachtelt, ("batterie", "erweitert"))
    assert flach == {
        "name": "Kombi",
        "capacity_kwh": 58.0,
        "min_charge_kw": 1.4,
        "efficiency_pct": 92.0,
    }


def test_ein_unerwartetes_dict_bleibt_stehen():
    """Nur benannte Abschnitte werden aufgeloest. Alles andere durchzureichen
    hiesse raten -- und ein falsch aufgeloestes dict faellt spaeter still
    als fehlendes Feld auf."""
    flach = stammdaten.flach_aus_abschnitten(
        {"fremd": {"a": 1}}, ("batterie",))
    assert flach == {"fremd": {"a": 1}}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_stammdaten.py -v`

Expected: FAIL — `AttributeError: module 'meteo_volt_stammdaten' has no attribute 'ladepunkt_aufloesen'`.

- [ ] **Step 3: Write the implementation**

Append to `custom_components/meteo_volt/stammdaten.py`:

```python
# --- Formularabschnitte -----------------------------------------------------
# HA liefert section-Felder verschachtelt unter ihrem Schluessel zurueck.

ABSCHNITT_ERWEITERT = "erweitert"
ABSCHNITT_BATTERIE = "batterie"
ABSCHNITT_GUARD = "guard"
ABSCHNITT_LADEN = "laden"
ABSCHNITT_FAHREN = "fahren"
ABSCHNITT_LAUFZEIT = "laufzeit"

ABSCHNITTE_LADEPUNKT = (ABSCHNITT_ERWEITERT,)
ABSCHNITTE_FAHRZEUG = (
    ABSCHNITT_BATTERIE,
    ABSCHNITT_GUARD,
    ABSCHNITT_LADEN,
    ABSCHNITT_FAHREN,
    ABSCHNITT_LAUFZEIT,
    ABSCHNITT_ERWEITERT,
)

# --- Namensvergabe ----------------------------------------------------------
# Der Titel wird erzeugt, nicht uebersetzt: HA hat fuer erzeugte Titel keinen
# Uebersetzungsschluessel. Deshalb hier eine kleine Tabelle statt einer
# deutschen Vorgabe in einer englischen Oberflaeche.

_NAMENSMUSTER = {
    "de": {TYP_LADEPUNKT: "Wallbox {}", TYP_FAHRZEUG: "Fahrzeug {}"},
    "en": {TYP_LADEPUNKT: "Wallbox {}", TYP_FAHRZEUG: "Vehicle {}"},
}


def naechster_name(vorhandene_titel, typ: str, sprache: str = "en") -> str:
    """Kleinste freie Nummer ab 1, etwa 'Fahrzeug 1', 'Fahrzeug 2'.

    Nicht len()+1: wer 'Fahrzeug 1' loescht und neu anlegt, bekaeme sonst eine
    Dublette zu 'Fahrzeug 2'.
    """
    muster = _NAMENSMUSTER.get(sprache, _NAMENSMUSTER["en"])[typ]
    belegt = set(vorhandene_titel)
    nummer = 1
    while muster.format(nummer) in belegt:
        nummer += 1
    return muster.format(nummer)


def ladepunkt_aufloesen(
    gewaehlt: str | None,
    bekannte_ids,
    angesteckt: bool | None = None,
) -> str | None:
    """connection.station_id aus Auswahl und Angesteckt-Sensor.

    angesteckt ist None, wenn der Nutzer keine Entitaet gewaehlt hat -- dann
    gilt das Fahrzeug als angesteckt. Wallboxen muessen nicht smart sein und
    Autos auch nicht; die Gegenannahme machte den Plan fuer jeden nutzlos, der
    keinen solchen Sensor hat.

    Ein Ladepunkt, den es nicht mehr gibt, wird null statt eines haengenden
    Verweises: es gibt keine Fehler-Fixture fuer eine unbekannte station_id,
    der Server pinnt sein Verhalten dort also nicht.
    """
    if not gewaehlt:
        return None
    if gewaehlt not in bekannte_ids:
        return None
    if angesteckt is False:
        return None
    return gewaehlt


def flach_aus_abschnitten(user_input: dict, abschnitte) -> dict:
    """Zieht die benannten Formularabschnitte flach.

    Nur die benannten. Jedes dict aufzuloesen hiesse raten, und ein falsch
    aufgeloestes faellt spaeter still als fehlendes Feld auf.
    """
    flach: dict = {}
    for schluessel, wert in user_input.items():
        if schluessel in abschnitte and isinstance(wert, dict):
            flach.update(wert)
        else:
            flach[schluessel] = wert
    return flach
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_stammdaten.py -v`

Expected: PASS — 23 passed.

- [ ] **Step 5: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest -q`

Expected: `78 passed`.

- [ ] **Step 6: Commit**

```bash
git add custom_components/meteo_volt/stammdaten.py tests/test_stammdaten.py
git commit -m "$(cat <<'EOF'
Resolve the charge point, name the subentry, flatten the sections

All five rows of the resolution table get their own test. The two that
matter: a charge point that no longer exists resolves to null rather than a
dangling reference, because no error fixture pins what the server does with
an unknown station_id; and a vehicle with no plugged-in sensor counts as
plugged in, because neither wallboxes nor cars have to be smart and the
opposite assumption makes the plan useless for anyone without one.

Generated titles take the lowest free number rather than count + 1, so
deleting Fahrzeug 1 frees that name instead of producing a second
Fahrzeug 2. The pattern comes from a small table keyed by language --
Home Assistant has no translation key for a title the flow invents, and a
German default in an English interface is a bug with a friendly face.

Sections come back nested from the frontend and are flattened by name only.
Resolving every dict would be guessing, and a wrongly resolved one shows up
later as a silently missing field.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Übersetzungen und ihr Gate

**Files:**
- Modify: `custom_components/meteo_volt/translations/de.json`
- Modify: `custom_components/meteo_volt/translations/en.json`
- Create: `tests/test_uebersetzungen.py`

**Interfaces:**
- Consumes: `LADEPUNKT_FELDER`, `FAHRZEUG_FELDER`, `TYP_LADEPUNKT`, `TYP_FAHRZEUG` aus Task 1.
- Produces: den Block `config_subentries` in beiden Sprachdateien.

**Warum zuerst die Übersetzungen und dann der Flow:** dieser Test ist der einzige automatische Halt, den die Formulare überhaupt bekommen können. Er prüft, dass jedes Feld aus `stammdaten.py` in beiden Sprachen eine Beschriftung hat — der klassische Fehler ist ein Feld, das im Formular auftaucht und als roher Schlüssel angezeigt wird.

- [ ] **Step 1: Write the failing test**

Create `tests/test_uebersetzungen.py`:

```python
"""Prueft, dass jedes Subentry-Feld in beiden Sprachen beschriftet ist.

Ohne Home Assistant laesst sich am Config-Flow fast nichts pruefen. Das hier
geht: die Feldnamen stehen in stammdaten.py, die Beschriftungen in den
Sprachdateien, und ein Feld ohne Beschriftung erscheint dem Nutzer als roher
Schluessel.

Was dieser Test NICHT sieht: ob HA die Datei ueberhaupt laedt, ob
data_description gerendert wird und ob eine Beschriftung inhaltlich passt.
"""

import importlib.util
import json
from pathlib import Path

import pytest

WURZEL = Path(__file__).resolve().parents[1]
INTEGRATION = WURZEL / "custom_components" / "meteo_volt"
UEBERSETZUNGEN = INTEGRATION / "translations"

_SPEC = importlib.util.spec_from_file_location(
    "meteo_volt_stammdaten", INTEGRATION / "stammdaten.py")
stammdaten = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(stammdaten)

SPRACHEN = ("de", "en")


def _laden(sprache: str) -> dict:
    return json.loads((UEBERSETZUNGEN / f"{sprache}.json").read_text(encoding="utf-8"))


def _schluesselbaum(knoten, praefix: str = "") -> set[str]:
    """Alle Blattpfade eines verschachtelten dict."""
    pfade = set()
    for schluessel, wert in knoten.items():
        pfad = f"{praefix}.{schluessel}" if praefix else schluessel
        if isinstance(wert, dict):
            pfade |= _schluesselbaum(wert, pfad)
        else:
            pfade.add(pfad)
    return pfade


def test_beide_sprachdateien_sind_da():
    """Eigene Existenzpruefung: die parametrisierten Tests unten wuerden bei
    einer fehlenden Datei mit einem Fehler abbrechen, der nach Tippfehler im
    Test aussieht statt nach fehlender Uebersetzung."""
    for sprache in SPRACHEN:
        assert (UEBERSETZUNGEN / f"{sprache}.json").is_file(), sprache


@pytest.mark.parametrize("sprache", SPRACHEN)
@pytest.mark.parametrize(
    ("typ", "felder"),
    [
        (stammdaten.TYP_LADEPUNKT, stammdaten.LADEPUNKT_FELDER),
        (stammdaten.TYP_FAHRZEUG, stammdaten.FAHRZEUG_FELDER),
    ],
)
@pytest.mark.parametrize("schritt", ["user", "reconfigure"])
def test_jedes_feld_hat_eine_beschriftung(sprache, typ, felder, schritt):
    daten = _laden(sprache)["config_subentries"][typ]["step"][schritt]["data"]
    fehlend = sorted(set(felder) - set(daten))
    assert not fehlend, f"{sprache}/{typ}/{schritt}: ohne Beschriftung: {fehlend}"


@pytest.mark.parametrize("sprache", SPRACHEN)
@pytest.mark.parametrize(
    ("typ", "felder"),
    [
        (stammdaten.TYP_LADEPUNKT, stammdaten.LADEPUNKT_FELDER),
        (stammdaten.TYP_FAHRZEUG, stammdaten.FAHRZEUG_FELDER),
    ],
)
@pytest.mark.parametrize("schritt", ["user", "reconfigure"])
def test_keine_beschriftung_ohne_feld(sprache, typ, felder, schritt):
    """Die Gegenrichtung, und die stillere von beiden: ein umbenanntes Feld
    laesst seine alte Beschriftung stehen, wo sie nie wieder jemand sieht."""
    daten = _laden(sprache)["config_subentries"][typ]["step"][schritt]["data"]
    verwaist = sorted(set(daten) - set(felder))
    assert not verwaist, f"{sprache}/{typ}/{schritt}: ohne Feld: {verwaist}"


def test_der_battery_guard_hat_seinen_hinweis():
    """Abschnitt 4 der Spec: die Rolle des Guards soll sichtbar sein, nicht
    aus dem Verhalten erschlossen werden muessen."""
    for sprache in SPRACHEN:
        schritte = _laden(sprache)["config_subentries"][
            stammdaten.TYP_FAHRZEUG]["step"]
        for schritt in ("user", "reconfigure"):
            hinweise = schritte[schritt]["data_description"]
            assert stammdaten.FELD_SOC_MIN in hinweise, f"{sprache}/{schritt}"
            assert stammdaten.FELD_SOC_MAX in hinweise, f"{sprache}/{schritt}"


def test_beide_sprachen_haben_denselben_schluesselbaum():
    """Faengt den haeufigsten Fall: ein Schluessel wird in einer Sprache
    ergaenzt und in der anderen vergessen."""
    de = _schluesselbaum(_laden("de"))
    en = _schluesselbaum(_laden("en"))
    assert de == en, (
        f"nur de: {sorted(de - en)}; nur en: {sorted(en - de)}")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_uebersetzungen.py -v`

Expected: FAIL — `KeyError: 'config_subentries'`.

- [ ] **Step 3: Write the German translations**

Replace `custom_components/meteo_volt/translations/de.json` with:

```json
{
  "config": {
    "step": {
      "user": {
        "title": "Meteo-Volt Authentifizierung",
        "description": "Bitte gib dein API Token und optionale Netzkosten/Abgaben ein, um dich mit Meteo-Volt zu verbinden.",
        "data": {
          "api_token": "API Token",
          "grid_fees": "Netzkosten & Abgaben (EUR/kWh)"
        }
      }
    },
    "error": {
      "cannot_connect": "Verbindung zur API fehlgeschlagen.",
      "invalid_auth": "Ungültiges API Token.",
      "unknown": "Ein unbekannter Fehler ist aufgetreten."
    },
    "abort": {
      "already_configured": "Dieses API Token ist bereits konfiguriert."
    }
  },
  "config_subentries": {
    "station": {
      "title": "Ladepunkt",
      "entry_type": "Ladepunkt",
      "initiate_flow": {
        "user": "Ladepunkt hinzufügen",
        "reconfigure": "Ladepunkt bearbeiten"
      },
      "step": {
        "user": {
          "title": "Ladepunkt hinzufügen",
          "description": "Die Wallbox oder Steckdose, an der geladen wird. Sie muss nicht smart sein.",
          "data": {
            "name": "Name",
            "max_power_kw": "Max. Leistung (kW)",
            "available": "Verfügbar",
            "min_power_kw": "Min. Leistung (kW)",
            "phases": "Phasen"
          },
          "data_description": {
            "name": "Leer lassen vergibt automatisch einen Namen.",
            "available": "Aus heisst: an diesem Ladepunkt wird über den ganzen Zeitraum nicht geladen."
          },
          "sections": {
            "erweitert": {
              "name": "Erweitert",
              "description": "Werte, die selten geändert werden."
            }
          }
        },
        "reconfigure": {
          "title": "Ladepunkt bearbeiten",
          "description": "Die Wallbox oder Steckdose, an der geladen wird. Sie muss nicht smart sein.",
          "data": {
            "name": "Name",
            "max_power_kw": "Max. Leistung (kW)",
            "available": "Verfügbar",
            "min_power_kw": "Min. Leistung (kW)",
            "phases": "Phasen"
          },
          "data_description": {
            "name": "Leer lassen vergibt automatisch einen Namen.",
            "available": "Aus heisst: an diesem Ladepunkt wird über den ganzen Zeitraum nicht geladen."
          },
          "sections": {
            "erweitert": {
              "name": "Erweitert",
              "description": "Werte, die selten geändert werden."
            }
          }
        }
      },
      "abort": {
        "reconfigure_successful": "Der Ladepunkt wurde geändert."
      }
    },
    "vehicle": {
      "title": "Fahrzeug",
      "entry_type": "Fahrzeug",
      "initiate_flow": {
        "user": "Fahrzeug hinzufügen",
        "reconfigure": "Fahrzeug bearbeiten"
      },
      "step": {
        "user": {
          "title": "Fahrzeug hinzufügen",
          "description": "Das Fahrzeug und seine Batterie. Nur der Ladestand muss aus einer Entität kommen.",
          "data": {
            "name": "Name",
            "capacity_kwh": "Kapazität (kWh)",
            "soc_min_pct": "Ladestand min (%)",
            "soc_max_pct": "Ladestand max (%)",
            "max_charge_kw": "Max. Ladeleistung (kW)",
            "consumption_kwh_per_100km": "Verbrauch (kWh/100 km)",
            "soc_entity": "Ladestand",
            "station_id": "Ladepunkt",
            "plugged_entity": "Angesteckt",
            "min_charge_kw": "Min. Ladeleistung (kW)",
            "efficiency_pct": "Ladewirkungsgrad (%)"
          },
          "data_description": {
            "name": "Leer lassen vergibt automatisch einen Namen.",
            "soc_min_pct": "Untergrenze, die der Plan immer hält. Liegt das Fahrzeug darunter und ist angesteckt, wird sofort geladen — ohne auf einen günstigen Preis zu warten.",
            "soc_max_pct": "Obergrenze im Regelbetrieb. Darüber lädt der Plan nur für ein gesetztes Ziel.",
            "soc_entity": "Sensor oder Helfer mit dem Ladestand in Prozent. Ohne Ladestand lässt sich nicht planen — wer keinen Sensor hat, legt sich einen input_number-Helfer an.",
            "station_id": "Der Ladepunkt, an dem dieses Fahrzeug lädt.",
            "plugged_entity": "Optionaler binary_sensor: „an\" heisst angesteckt. Ohne ihn gilt das Fahrzeug als angesteckt.",
            "efficiency_pct": "Gesamter Ladewirkungsgrad — Kabel, Zähler und Bordlader zusammen."
          },
          "sections": {
            "batterie": {"name": "Batterie"},
            "guard": {
              "name": "Battery-Guard",
              "description": "Die Grenzen, die der Plan jederzeit hält."
            },
            "laden": {"name": "Laden"},
            "fahren": {"name": "Fahren"},
            "laufzeit": {
              "name": "Laufzeit",
              "description": "Woher der aktuelle Zustand kommt."
            },
            "erweitert": {
              "name": "Erweitert",
              "description": "Werte, die selten geändert werden."
            }
          }
        },
        "reconfigure": {
          "title": "Fahrzeug bearbeiten",
          "description": "Das Fahrzeug und seine Batterie. Nur der Ladestand muss aus einer Entität kommen.",
          "data": {
            "name": "Name",
            "capacity_kwh": "Kapazität (kWh)",
            "soc_min_pct": "Ladestand min (%)",
            "soc_max_pct": "Ladestand max (%)",
            "max_charge_kw": "Max. Ladeleistung (kW)",
            "consumption_kwh_per_100km": "Verbrauch (kWh/100 km)",
            "soc_entity": "Ladestand",
            "station_id": "Ladepunkt",
            "plugged_entity": "Angesteckt",
            "min_charge_kw": "Min. Ladeleistung (kW)",
            "efficiency_pct": "Ladewirkungsgrad (%)"
          },
          "data_description": {
            "name": "Leer lassen vergibt automatisch einen Namen.",
            "soc_min_pct": "Untergrenze, die der Plan immer hält. Liegt das Fahrzeug darunter und ist angesteckt, wird sofort geladen — ohne auf einen günstigen Preis zu warten.",
            "soc_max_pct": "Obergrenze im Regelbetrieb. Darüber lädt der Plan nur für ein gesetztes Ziel.",
            "soc_entity": "Sensor oder Helfer mit dem Ladestand in Prozent. Ohne Ladestand lässt sich nicht planen — wer keinen Sensor hat, legt sich einen input_number-Helfer an.",
            "station_id": "Der Ladepunkt, an dem dieses Fahrzeug lädt.",
            "plugged_entity": "Optionaler binary_sensor: „an\" heisst angesteckt. Ohne ihn gilt das Fahrzeug als angesteckt.",
            "efficiency_pct": "Gesamter Ladewirkungsgrad — Kabel, Zähler und Bordlader zusammen."
          },
          "sections": {
            "batterie": {"name": "Batterie"},
            "guard": {
              "name": "Battery-Guard",
              "description": "Die Grenzen, die der Plan jederzeit hält."
            },
            "laden": {"name": "Laden"},
            "fahren": {"name": "Fahren"},
            "laufzeit": {
              "name": "Laufzeit",
              "description": "Woher der aktuelle Zustand kommt."
            },
            "erweitert": {
              "name": "Erweitert",
              "description": "Werte, die selten geändert werden."
            }
          }
        }
      },
      "error": {
        "soc_range": "Ladestand min muss kleiner sein als Ladestand max."
      },
      "abort": {
        "reconfigure_successful": "Das Fahrzeug wurde geändert."
      }
    }
  }
}
```

- [ ] **Step 4: Write the English translations**

Replace `custom_components/meteo_volt/translations/en.json` with the same structure, English text. **The key tree must match `de.json` exactly** — `test_beide_sprachen_haben_denselben_schluesselbaum` compares them:

```json
{
  "config": {
    "step": {
      "user": {
        "title": "Meteo-Volt Authentication",
        "description": "Please enter your API token and optional grid fees to connect to Meteo-Volt.",
        "data": {
          "api_token": "API Token",
          "grid_fees": "Grid Fees (EUR/kWh)"
        }
      }
    },
    "error": {
      "cannot_connect": "Failed to connect to the API.",
      "invalid_auth": "Invalid API token.",
      "unknown": "An unknown error occurred."
    },
    "abort": {
      "already_configured": "This API token is already configured."
    }
  },
  "config_subentries": {
    "station": {
      "title": "Charge point",
      "entry_type": "Charge point",
      "initiate_flow": {
        "user": "Add charge point",
        "reconfigure": "Edit charge point"
      },
      "step": {
        "user": {
          "title": "Add charge point",
          "description": "The wallbox or socket you charge from. It does not have to be smart.",
          "data": {
            "name": "Name",
            "max_power_kw": "Max. power (kW)",
            "available": "Available",
            "min_power_kw": "Min. power (kW)",
            "phases": "Phases"
          },
          "data_description": {
            "name": "Leave empty to get a name assigned automatically.",
            "available": "Off means nothing charges here for the whole horizon."
          },
          "sections": {
            "erweitert": {
              "name": "Advanced",
              "description": "Values that are rarely changed."
            }
          }
        },
        "reconfigure": {
          "title": "Edit charge point",
          "description": "The wallbox or socket you charge from. It does not have to be smart.",
          "data": {
            "name": "Name",
            "max_power_kw": "Max. power (kW)",
            "available": "Available",
            "min_power_kw": "Min. power (kW)",
            "phases": "Phases"
          },
          "data_description": {
            "name": "Leave empty to get a name assigned automatically.",
            "available": "Off means nothing charges here for the whole horizon."
          },
          "sections": {
            "erweitert": {
              "name": "Advanced",
              "description": "Values that are rarely changed."
            }
          }
        }
      },
      "abort": {
        "reconfigure_successful": "The charge point was updated."
      }
    },
    "vehicle": {
      "title": "Vehicle",
      "entry_type": "Vehicle",
      "initiate_flow": {
        "user": "Add vehicle",
        "reconfigure": "Edit vehicle"
      },
      "step": {
        "user": {
          "title": "Add vehicle",
          "description": "The vehicle and its battery. Only the state of charge has to come from an entity.",
          "data": {
            "name": "Name",
            "capacity_kwh": "Capacity (kWh)",
            "soc_min_pct": "State of charge min (%)",
            "soc_max_pct": "State of charge max (%)",
            "max_charge_kw": "Max. charge power (kW)",
            "consumption_kwh_per_100km": "Consumption (kWh/100 km)",
            "soc_entity": "State of charge",
            "station_id": "Charge point",
            "plugged_entity": "Plugged in",
            "min_charge_kw": "Min. charge power (kW)",
            "efficiency_pct": "Charging efficiency (%)"
          },
          "data_description": {
            "name": "Leave empty to get a name assigned automatically.",
            "soc_min_pct": "Lower bound the plan always holds. Below it and plugged in, charging starts at once — without waiting for a good price.",
            "soc_max_pct": "Upper bound in normal operation. The plan only goes above it for a set target.",
            "soc_entity": "Sensor or helper carrying the state of charge in percent. Planning needs it — without a sensor, create an input_number helper.",
            "station_id": "The charge point this vehicle charges at.",
            "plugged_entity": "Optional binary_sensor: \"on\" means plugged in. Without it the vehicle counts as plugged in.",
            "efficiency_pct": "Total charging efficiency — cable, meter and onboard charger together."
          },
          "sections": {
            "batterie": {"name": "Battery"},
            "guard": {
              "name": "Battery guard",
              "description": "The bounds the plan holds at all times."
            },
            "laden": {"name": "Charging"},
            "fahren": {"name": "Driving"},
            "laufzeit": {
              "name": "Runtime",
              "description": "Where the current state comes from."
            },
            "erweitert": {
              "name": "Advanced",
              "description": "Values that are rarely changed."
            }
          }
        },
        "reconfigure": {
          "title": "Edit vehicle",
          "description": "The vehicle and its battery. Only the state of charge has to come from an entity.",
          "data": {
            "name": "Name",
            "capacity_kwh": "Capacity (kWh)",
            "soc_min_pct": "State of charge min (%)",
            "soc_max_pct": "State of charge max (%)",
            "max_charge_kw": "Max. charge power (kW)",
            "consumption_kwh_per_100km": "Consumption (kWh/100 km)",
            "soc_entity": "State of charge",
            "station_id": "Charge point",
            "plugged_entity": "Plugged in",
            "min_charge_kw": "Min. charge power (kW)",
            "efficiency_pct": "Charging efficiency (%)"
          },
          "data_description": {
            "name": "Leave empty to get a name assigned automatically.",
            "soc_min_pct": "Lower bound the plan always holds. Below it and plugged in, charging starts at once — without waiting for a good price.",
            "soc_max_pct": "Upper bound in normal operation. The plan only goes above it for a set target.",
            "soc_entity": "Sensor or helper carrying the state of charge in percent. Planning needs it — without a sensor, create an input_number helper.",
            "station_id": "The charge point this vehicle charges at.",
            "plugged_entity": "Optional binary_sensor: \"on\" means plugged in. Without it the vehicle counts as plugged in.",
            "efficiency_pct": "Total charging efficiency — cable, meter and onboard charger together."
          },
          "sections": {
            "batterie": {"name": "Battery"},
            "guard": {
              "name": "Battery guard",
              "description": "The bounds the plan holds at all times."
            },
            "laden": {"name": "Charging"},
            "fahren": {"name": "Driving"},
            "laufzeit": {
              "name": "Runtime",
              "description": "Where the current state comes from."
            },
            "erweitert": {
              "name": "Advanced",
              "description": "Values that are rarely changed."
            }
          }
        }
      },
      "error": {
        "soc_range": "State of charge min must be lower than state of charge max."
      },
      "abort": {
        "reconfigure_successful": "The vehicle was updated."
      }
    }
  }
}
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_uebersetzungen.py -v`

Expected: PASS — 19 passed.

- [ ] **Step 6: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest -q`

Expected: `97 passed`.

- [ ] **Step 7: Commit**

```bash
git add custom_components/meteo_volt/translations/de.json custom_components/meteo_volt/translations/en.json tests/test_uebersetzungen.py
git commit -m "$(cat <<'EOF'
Label every subentry field in both languages, and check that it is

Without Home Assistant in the test dependencies there is almost nothing to
assert about a config flow. This much works: the field names live in
stammdaten.py, the labels live in the translation files, and a field
without a label reaches the user as a raw key.

The check runs in both directions. A label with no field is the quieter
failure of the two -- a renamed field leaves its old label sitting where
nobody will ever see it again. The key trees of both languages are
compared as well, which catches a key added to one and forgotten in the
other.

The battery guard's two hints are asserted by name. Section 4 of the spec
wants its role visible rather than inferred from behaviour, and a hint that
quietly disappears takes the reason with it.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Der Ladepunkt-Subentry-Flow

**Files:**
- Modify: `custom_components/meteo_volt/config_flow.py`

**Interfaces:**
- Consumes: `stammdaten.TYP_LADEPUNKT`, `LADEPUNKT_DEFAULTS`, `LADEPUNKT_FELDER`, `ABSCHNITTE_LADEPUNKT`, `flach_aus_abschnitten`, `naechster_name`, `FELD_*`.
- Produces: `LadepunktSubentryFlow` und die Klassenmethode `ConfigFlow.async_get_supported_subentry_types`.

**Dieser Task hat keinen automatischen Test.** `config_flow.py` importiert Home Assistant, das nicht in den Testabhängigkeiten steckt. Die Abnahme steht am Ende dieses Plans und läuft auf der echten Instanz.

- [ ] **Step 1: Extend the imports**

In `custom_components/meteo_volt/config_flow.py`, replace the import block (lines 1–18) with:

```python
"""Config flow for Meteo-Volt integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries, data_entry_flow
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector

from . import stammdaten
from .const import DOMAIN, CONF_API_TOKEN, CONF_GRID_FEES, API_URL
from .overrides import load_overrides
from .api import MeteoVoltApiClient

_LOGGER = logging.getLogger(__name__)
```

- [ ] **Step 2: Register the subentry types**

In the existing `class ConfigFlow`, directly below `VERSION = 1`, insert:

```python
    # VERSION bleibt 1. Subentries kommen additiv: ein bestehender Eintrag
    # ohne sie ist gueltig, entry.subentries ist dann leer. Eine Migration
    # ohne Datenaenderung waere Risiko ohne Gegenwert -- Bestandsschutz
    # Auflage 4.

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Die zwei Stammdaten-Typen unter dem bestehenden Eintrag."""
        return {
            stammdaten.TYP_LADEPUNKT: LadepunktSubentryFlow,
            stammdaten.TYP_FAHRZEUG: FahrzeugSubentryFlow,
        }
```

- [ ] **Step 3: Add the charge point flow**

Append to `custom_components/meteo_volt/config_flow.py`, **above** the `CannotConnect`/`InvalidAuth` classes:

```python
def _vorhandene_titel(entry: ConfigEntry, typ: str) -> list[str]:
    """Die Titel aller Subentries eines Typs, fuer die Namensvergabe."""
    return [
        subentry.title
        for subentry in entry.subentries.values()
        if subentry.subentry_type == typ
    ]


def _titel_bestimmen(
    flow: ConfigSubentryFlow,
    typ: str,
    daten: dict[str, Any],
    bisher: str | None = None,
) -> str:
    """Der eingetippte Name, sonst der bisherige, sonst eine Nummer.

    Nimmt den Namen aus daten HERAUS: er ist der Titel des Subentries und
    nicht eines seiner Felder. Stuenden beide da, gingen sie beim naechsten
    Umbenennen auseinander.

    Beide Flows teilen sich diese Funktion. _get_entry ist die dokumentierte
    API von ConfigSubentryFlow, auch wenn der Unterstrich anderes nahelegt.
    """
    name = str(daten.pop(stammdaten.FELD_NAME, "") or "").strip()
    if name:
        return name
    if bisher:
        return bisher
    return stammdaten.naechster_name(
        _vorhandene_titel(flow._get_entry(), typ),
        typ,
        flow.hass.config.language,
    )


class LadepunktSubentryFlow(ConfigSubentryFlow):
    """Anlegen und Aendern eines Ladepunkts."""

    @property
    def _neu(self) -> bool:
        return self.source == "user"

    def _schema(self, vorgabe: dict[str, Any]) -> vol.Schema:
        """Das Formular, vorbelegt aus vorgabe.

        Min. Leistung und Phasen haben einen Kontrakt-Default, den kaum
        jemand aendert. Sie stehen deshalb eingeklappt -- der Wizard fragt
        sonst nach Werten, zu denen ein Erstnutzer nichts sagen kann.
        """
        standard = stammdaten.LADEPUNKT_DEFAULTS
        return vol.Schema(
            {
                vol.Optional(
                    stammdaten.FELD_NAME,
                    default=vorgabe.get(stammdaten.FELD_NAME, ""),
                ): str,
                vol.Required(
                    stammdaten.FELD_MAX_LEISTUNG,
                    default=vorgabe.get(
                        stammdaten.FELD_MAX_LEISTUNG,
                        standard[stammdaten.FELD_MAX_LEISTUNG]),
                ): vol.All(vol.Coerce(float), vol.Range(min=0, min_included=False)),
                vol.Required(
                    stammdaten.FELD_VERFUEGBAR,
                    default=vorgabe.get(
                        stammdaten.FELD_VERFUEGBAR,
                        standard[stammdaten.FELD_VERFUEGBAR]),
                ): bool,
                vol.Required(stammdaten.ABSCHNITT_ERWEITERT): data_entry_flow.section(
                    vol.Schema(
                        {
                            vol.Optional(
                                stammdaten.FELD_MIN_LEISTUNG,
                                default=vorgabe.get(
                                    stammdaten.FELD_MIN_LEISTUNG,
                                    standard[stammdaten.FELD_MIN_LEISTUNG]),
                            ): vol.All(
                                vol.Coerce(float),
                                vol.Range(min=0, min_included=False),
                            ),
                            vol.Optional(
                                stammdaten.FELD_PHASEN,
                                default=vorgabe.get(
                                    stammdaten.FELD_PHASEN,
                                    standard[stammdaten.FELD_PHASEN]),
                            ): vol.In([1, 3]),
                        }
                    ),
                    {"collapsed": True},
                ),
            }
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Neuen Ladepunkt anlegen."""
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=self._schema({}))

        daten = stammdaten.flach_aus_abschnitten(
            user_input, stammdaten.ABSCHNITTE_LADEPUNKT)
        titel = _titel_bestimmen(self, stammdaten.TYP_LADEPUNKT, daten)
        return self.async_create_entry(title=titel, data=daten)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Bestehenden Ladepunkt aendern."""
        subentry = self._get_reconfigure_subentry()

        if user_input is None:
            # Der Name kommt mit dem bestehenden Titel vorbelegt zurueck,
            # nicht leer: sonst verloere "Wallbox Garage" seinen Namen,
            # sobald jemand nur die Leistung korrigiert.
            vorgabe = dict(subentry.data)
            vorgabe[stammdaten.FELD_NAME] = subentry.title
            return self.async_show_form(
                step_id="reconfigure", data_schema=self._schema(vorgabe))

        daten = stammdaten.flach_aus_abschnitten(
            user_input, stammdaten.ABSCHNITTE_LADEPUNKT)
        titel = _titel_bestimmen(
            self, stammdaten.TYP_LADEPUNKT, daten, bisher=subentry.title)
        return self.async_update_and_abort(
            self._get_entry(), subentry, title=titel, data=daten)
```

- [ ] **Step 4: Verify the module still parses**

`config_flow.py` importiert Home Assistant und lässt sich hier nicht ausführen. Prüfbar ist die Syntax:

Run: `.venv/Scripts/python.exe -m py_compile custom_components/meteo_volt/config_flow.py`

Expected: keine Ausgabe, Exit-Code 0.

- [ ] **Step 5: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest -q`

Expected: `97 passed` — unverändert. Dieser Task fügt keinen automatischen Test hinzu; das ist bekannt und steht im Plan.

- [ ] **Step 6: Commit**

```bash
git add custom_components/meteo_volt/config_flow.py
git commit -m "$(cat <<'EOF'
Add the charge point as a config subentry

VERSION stays at 1 and no migration is written. Subentries are additive: an
entry without them is valid and entry.subentries is simply empty, so a
migration that changes no data would be risk without return.

Minimum power and phases carry a contract default that almost nobody
changes, so they sit in a collapsed section. The wizard then asks for two
values instead of four, and a first-time user is not asked about phases
before they have seen a plan.

Reconfigure returns the name field filled with the current title rather
than empty, or correcting a power rating would silently rename the charge
point. The title is cosmetic either way -- the contract id is the
subentry_id.

This task has no automated test. config_flow.py imports Home Assistant,
which is not in the test dependencies; py_compile is the only machine check
and the form is taken manually on 2026.4.1.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Der Fahrzeug-Subentry-Flow

**Files:**
- Modify: `custom_components/meteo_volt/config_flow.py`

**Interfaces:**
- Consumes: alles aus Task 5 plus `stammdaten.FAHRZEUG_DEFAULTS`, `ABSCHNITTE_FAHRZEUG`, `TYP_FAHRZEUG`.
- Produces: `FahrzeugSubentryFlow` — bereits in `async_get_supported_subentry_types` aus Task 5 referenziert.

**Auch dieser Task hat keinen automatischen Test.**

- [ ] **Step 1: Add the vehicle flow**

Append to `custom_components/meteo_volt/config_flow.py`, **above** the `CannotConnect`/`InvalidAuth` classes:

```python
class FahrzeugSubentryFlow(ConfigSubentryFlow):
    """Anlegen und Aendern eines Fahrzeugs."""

    @property
    def _neu(self) -> bool:
        return self.source == "user"

    def _ladepunkt_auswahl(self) -> list[selector.SelectOptionDict]:
        """Die angelegten Ladepunkte, Wert ist die subentry_id.

        Der Titel ist nur die Beschriftung: umbenennen darf die Zuordnung
        nicht verlieren, und die Kontrakt-ID ist ohnehin die subentry_id.
        """
        return [
            selector.SelectOptionDict(value=subentry.subentry_id, label=subentry.title)
            for subentry in self._get_entry().subentries.values()
            if subentry.subentry_type == stammdaten.TYP_LADEPUNKT
        ]

    def _schema(self, vorgabe: dict[str, Any]) -> vol.Schema:
        """Das Formular, vorbelegt aus vorgabe."""
        standard = stammdaten.FAHRZEUG_DEFAULTS
        prozent = vol.All(vol.Coerce(float), vol.Range(min=0, max=100))
        positiv = vol.All(vol.Coerce(float), vol.Range(min=0, min_included=False))

        def vor(feld: str):
            return vorgabe.get(feld, standard.get(feld))

        laufzeit = {
            vol.Required(
                stammdaten.FELD_SOC_ENTITAET,
                description={"suggested_value": vor(stammdaten.FELD_SOC_ENTITAET)},
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["sensor", "input_number"])
            ),
        }
        auswahl = self._ladepunkt_auswahl()
        if auswahl:
            laufzeit[
                vol.Optional(
                    stammdaten.FELD_LADEPUNKT,
                    description={"suggested_value": vor(stammdaten.FELD_LADEPUNKT)},
                )
            ] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=auswahl, mode=selector.SelectSelectorMode.DROPDOWN)
            )
        laufzeit[
            vol.Optional(
                stammdaten.FELD_ANGESTECKT,
                description={"suggested_value": vor(stammdaten.FELD_ANGESTECKT)},
            )
        ] = selector.EntitySelector(
            selector.EntitySelectorConfig(domain="binary_sensor")
        )

        return vol.Schema(
            {
                vol.Optional(
                    stammdaten.FELD_NAME,
                    default=vorgabe.get(stammdaten.FELD_NAME, ""),
                ): str,
                vol.Required(stammdaten.ABSCHNITT_BATTERIE): data_entry_flow.section(
                    vol.Schema(
                        {
                            vol.Required(
                                stammdaten.FELD_KAPAZITAET,
                                default=vor(stammdaten.FELD_KAPAZITAET),
                            ): positiv,
                        }
                    ),
                    {"collapsed": False},
                ),
                vol.Required(stammdaten.ABSCHNITT_GUARD): data_entry_flow.section(
                    vol.Schema(
                        {
                            vol.Required(
                                stammdaten.FELD_SOC_MIN,
                                default=vor(stammdaten.FELD_SOC_MIN),
                            ): prozent,
                            vol.Required(
                                stammdaten.FELD_SOC_MAX,
                                default=vor(stammdaten.FELD_SOC_MAX),
                            ): prozent,
                        }
                    ),
                    {"collapsed": False},
                ),
                vol.Required(stammdaten.ABSCHNITT_LADEN): data_entry_flow.section(
                    vol.Schema(
                        {
                            vol.Required(
                                stammdaten.FELD_MAX_LADELEISTUNG,
                                default=vor(stammdaten.FELD_MAX_LADELEISTUNG),
                            ): positiv,
                        }
                    ),
                    {"collapsed": False},
                ),
                vol.Required(stammdaten.ABSCHNITT_FAHREN): data_entry_flow.section(
                    vol.Schema(
                        {
                            vol.Required(
                                stammdaten.FELD_VERBRAUCH,
                                default=vor(stammdaten.FELD_VERBRAUCH),
                            ): positiv,
                        }
                    ),
                    {"collapsed": False},
                ),
                vol.Required(stammdaten.ABSCHNITT_LAUFZEIT): data_entry_flow.section(
                    vol.Schema(laufzeit), {"collapsed": False},
                ),
                vol.Required(stammdaten.ABSCHNITT_ERWEITERT): data_entry_flow.section(
                    vol.Schema(
                        {
                            vol.Optional(
                                stammdaten.FELD_MIN_LADELEISTUNG,
                                default=vor(stammdaten.FELD_MIN_LADELEISTUNG),
                            ): positiv,
                            vol.Optional(
                                stammdaten.FELD_WIRKUNGSGRAD,
                                default=vor(stammdaten.FELD_WIRKUNGSGRAD),
                            ): vol.All(
                                vol.Coerce(float),
                                vol.Range(min=0, max=100, min_included=False),
                            ),
                        }
                    ),
                    {"collapsed": True},
                ),
            }
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Neues Fahrzeug anlegen."""
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=self._schema({}))

        daten = stammdaten.flach_aus_abschnitten(
            user_input, stammdaten.ABSCHNITTE_FAHRZEUG)
        if (fehler := self._pruefen(daten)) is not None:
            return self.async_show_form(
                step_id="user", data_schema=self._schema(daten), errors=fehler)

        titel = _titel_bestimmen(self, stammdaten.TYP_FAHRZEUG, daten)
        return self.async_create_entry(title=titel, data=daten)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Bestehendes Fahrzeug aendern."""
        subentry = self._get_reconfigure_subentry()

        if user_input is None:
            vorgabe = dict(subentry.data)
            vorgabe[stammdaten.FELD_NAME] = subentry.title
            return self.async_show_form(
                step_id="reconfigure", data_schema=self._schema(vorgabe))

        daten = stammdaten.flach_aus_abschnitten(
            user_input, stammdaten.ABSCHNITTE_FAHRZEUG)
        if (fehler := self._pruefen(daten)) is not None:
            vorgabe = dict(daten)
            # Nur einsetzen, wenn nichts getippt wurde. Den eingegebenen Namen
            # im Fehlerfall durch den alten zu ersetzen hiesse, dem Nutzer
            # seine Eingabe wegzunehmen, waehrend er einen Fehler korrigiert.
            if not vorgabe.get(stammdaten.FELD_NAME):
                vorgabe[stammdaten.FELD_NAME] = subentry.title
            return self.async_show_form(
                step_id="reconfigure",
                data_schema=self._schema(vorgabe),
                errors=fehler,
            )

        titel = _titel_bestimmen(
            self, stammdaten.TYP_FAHRZEUG, daten, bisher=subentry.title)
        return self.async_update_and_abort(
            self._get_entry(), subentry, title=titel, data=daten)

    @staticmethod
    def _pruefen(daten: dict[str, Any]) -> dict[str, str] | None:
        """Die eine Bedingung ueber zwei Felder hinweg.

        Voluptuous prueft jedes Feld fuer sich; dass der Boden unter der
        Decke liegt, sieht es nicht.
        """
        if daten[stammdaten.FELD_SOC_MIN] >= daten[stammdaten.FELD_SOC_MAX]:
            return {"base": "soc_range"}
        return None
```

- [ ] **Step 2: Verify the module parses**

Run: `.venv/Scripts/python.exe -m py_compile custom_components/meteo_volt/config_flow.py`

Expected: keine Ausgabe, Exit-Code 0.

- [ ] **Step 3: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest -q`

Expected: `97 passed`.

- [ ] **Step 4: Commit**

```bash
git add custom_components/meteo_volt/config_flow.py
git commit -m "$(cat <<'EOF'
Add the vehicle as a config subentry

The state of charge is the one required entity. Planning cannot happen
without it, and not every car supplies one -- so the selector accepts
input_number beside sensor, and whoever has no source keeps a helper by
hand. Failing here, at creation, beats failing later in a plan.

The charge point field only appears once a charge point exists. An empty
dropdown asks a question with no answers.

soc_min against soc_max is checked by hand after the form returns.
Voluptuous validates each field on its own and cannot see that the floor
has to sit below the ceiling.

Sections come back nested and are flattened through stammdaten, so the
stored data stays flat and the mapping never learns about form layout.

Like the charge point flow, this has no automated test: py_compile is the
only machine check, the rest is the manual acceptance.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Die Untergrenze, die Version und der Satz im README

**Files:**
- Modify: `hacs.json`
- Modify: `custom_components/meteo_volt/manifest.json`
- Modify: `README.md`

**Interfaces:**
- Consumes: nichts.
- Produces: nichts für spätere Tasks. Dies ist Punkt `C12V` aus der Spec, Abschnitt 7.

- [ ] **Step 1: Raise the floor**

In `hacs.json`, change one line:

```diff
-  "homeassistant": "2024.1.0",
+  "homeassistant": "2026.4.0",
```

- [ ] **Step 2: Bump the version**

In `custom_components/meteo_volt/manifest.json`, change one line:

```diff
-  "version": "1.1.0-beta.2"
+  "version": "1.2.0-beta.1"
```

- [ ] **Step 3: Say it in the README**

**Der README ist englisch.** Der Absatz ist es deshalb auch. Er kommt in die bestehende Sektion `## Requirements`, `README.md:19`. Ersetze diese drei Zeilen:

```markdown
- A Meteo-Volt API token.
- Home Assistant with HACS installed (for the recommended install path).
```

durch:

```markdown
- A Meteo-Volt API token.
- **Home Assistant 2026.4 or newer.**
- HACS installed (for the recommended install path).

Version 1.2.0 stores vehicles and charge points as config subentries, which
older cores do not have. That raises the floor from 2024.1 to 2026.4.

If you run an older core, nothing breaks: HACS will not offer 1.2.0 there, you
keep the version you have, and the price forecast goes on working. What stops
arriving is new features.
```

- [ ] **Step 4: Verify the JSON files are still valid**

Run:

```bash
.venv/Scripts/python.exe -c "import json,pathlib; [json.loads(pathlib.Path(p).read_text(encoding='utf-8')) for p in ['hacs.json','custom_components/meteo_volt/manifest.json']]; print('beide gueltig')"
```

Expected: `beide gueltig`

- [ ] **Step 5: Confirm the contract is untouched**

Run: `.venv/Scripts/python.exe scripts/check_contract.py`

Expected: `Kontrakt in sync (35 Dateien geprueft)`

- [ ] **Step 6: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest -q`

Expected: `97 passed`.

- [ ] **Step 7: Commit**

```bash
git add hacs.json custom_components/meteo_volt/manifest.json README.md
git commit -m "$(cat <<'EOF'
Raise the Home Assistant floor to 2026.4 and say so

Config subentries do not exist in older cores, so C1-C2 raises the floor
whether or not anyone wants it to. 2026.4.0 is the core the manual
acceptance runs on, which makes the floor the one version actually
measured rather than a figure nobody looked up.

Users below it keep the version they have. HACS will not offer 1.2.0 there
and the price prediction goes on working; what stops is new features. The
README says that in its own paragraph, so the outcome is a decision the
reader can see rather than an update that silently never arrives.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Manuelle Abnahme

Der automatische Gate sieht das Formular nicht, den Flow nicht und das Rendern der Übersetzungen nicht. Diese Liste ist der Rest. Sie läuft auf **Home Assistant 2026.4.1**, dem Kern, der in `hacs.json` als Untergrenze steht.

**Vorher:** die Integration aus diesem Branch nach `config/custom_components/meteo_volt/` kopieren und Home Assistant neu starten.

- [ ] **Auflage 4 des Bestandsschutzes zuerst.** Eine Instanz mit ausschliesslich der alten Konfiguration — kein Fahrzeug, kein Ladepunkt — startet sauber und zeigt **alle sechs Sensoren**. Das ist der Test, der als einziger einen Merge verhindern darf.
- [ ] Unter dem bestehenden Eintrag stehen zwei Schaltflächen: „Ladepunkt hinzufügen" und „Fahrzeug hinzufügen".
- [ ] Einen Ladepunkt anlegen, ohne Namen einzutippen → er heisst `Wallbox 1`. Der Abschnitt **Erweitert** kommt eingeklappt.
- [ ] Einen zweiten anlegen → `Wallbox 2`. Den ersten löschen, einen dritten anlegen → wieder `Wallbox 1`, nicht `Wallbox 3`.
- [ ] Ein Fahrzeug anlegen. Das Feld **Ladestand** listet Sensoren **und** `input_number`-Helfer und lässt sich nicht leer absenden.
- [ ] Die Auswahl **Ladepunkt** zeigt die angelegten Wallboxen mit ihrem Titel.
- [ ] `Ladestand min` auf 80 und `Ladestand max` auf 15 setzen → die Meldung aus `soc_range` erscheint, in der eingestellten Sprache lesbar.
- [ ] Unter `Ladestand min` steht der Hinweistext. **Erscheint er nicht, ist `data_description` in Subentry-Flows nicht wirksam** — dann wandert der Satz in die Beschriftung des Feldes, und dieser Plan hat seine Annahme gemessen statt sie zu glauben.
- [ ] Ein Fahrzeug anlegen, **ohne** Ladepunkt und **ohne** Angesteckt-Entität. Es lässt sich speichern. Das ist der Normalfall für nicht-smarte Hardware.
- [ ] Ein Fahrzeug umbenennen zu „Papas Kombi", speichern, danach **nur die Kapazität** ändern → der Name bleibt „Papas Kombi".
- [ ] Den Ladepunkt löschen, den ein Fahrzeug referenziert → das Fahrzeug lässt sich weiter öffnen und speichern.
- [ ] Die Oberfläche auf Englisch stellen und beide Formulare erneut öffnen → keine rohen Schlüssel, keine deutschen Reste. Ein neu angelegtes Fahrzeug heisst dort `Vehicle 1`.

**Erst wenn diese Liste durch ist**, geht der Branch nach `beta`. Den Merge nach `master` macht ausschliesslich der Mensch.

---

## Was dieser Plan nicht baut

| Nicht hier | Wo |
|---|---|
| Lesen der Subentries, Aufruf von `POST /v1/plan` | `C5`, `C7` |
| Das Fahrprofil — Wochenraster, Ausnahmen, Termine | `Z3` |
| `soc_min_pct`/`soc_max_pct` als Entitäten | `C3` |
| `site.max_power_kw` — Punkt `C5S` | `C5` |
| Geräte, Entitäten, Attribute | `C6` |
