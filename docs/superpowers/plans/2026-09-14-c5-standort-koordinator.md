# C5 Standort-Koordinator — Umsetzungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ein Koordinator je Eintrag sammelt Fahrzeuge und Ladepunkte ein, baut den Request, holt über den Plan-Client aus C7 einen Plan und hält das Ergebnis — mit Auslösern, Nachholen, sicherem Default und 12-h-Regel, dazu das Hausanschluss-Feld, das erst mit E1 wirkt.

**Architecture:** Alles, was C5 entscheidet — Ladepunkt, Auslassen, Request, nächster Versuch, was gerade gilt, wann das Repair-Issue fällig ist — liegt im neuen Modul `standort.py`, ohne Import aus Home Assistant, und ist gegen die vendorten Fixtures geprüft. `plankoordinator.py` verdrahtet es: ein `DataUpdateCoordinator` mit eigener Bündelung, eigenem Grundtakt-Timer, Listenern und dem Repair-Issue. Der Haupteintrag bekommt ein optionales Feld, und die Dev-Action holt den Plan über den Koordinator.

**Tech Stack:** Python 3.12 (Venv `.venv`), pytest + jsonschema. Zur Laufzeit Home Assistant 2026.4.1 — nicht in den Testabhängigkeiten.

**Spec:** `meteo-volt-brain/docs/features/C5-standort-koordinator/spec.md`, Branch `c5-standort-koordinator`. Bei Widerspruch gilt die Spec, nicht dieser Plan.

## Global Constraints

- **Branch** ist `c5-standort-koordinator`, im ha-Repo und im Brain. Gemergt wird nach `beta`. **Niemals nach `master` oder `main`.**
- **Die Abnahme macht Patrick** auf seiner Instanz (Abschnitt „Abnahme"). Vorher ist C5 nicht fertig: kein Status `fertig`, kein Merge nach `beta`.
- **Python** ist `.venv/Scripts/python.exe`. Ein blankes `python` ist der Windows-Store-Alias. **Kein Venv-Update**, keine neue Testabhängigkeit.
- **`custom_components/` ist Endnutzer-Code.** HACS paketiert genau dieses Verzeichnis.
- **`standort.py` importiert nichts aus Home Assistant und nichts aus aiohttp**, ebenso wenig die drei Module, die es lädt: `stammdaten.py`, `planabruf.py`, `const.py`. Der Test lädt es über ein Paket, dessen `__init__.py` nicht läuft — die schärfste Fassung dieser Auflage.
- **Bestandsschutz:** `sensor.py`, `coordinator.py`, `async_get_predictions` und `hass.data[DOMAIN]` bleiben unberührt, ebenso das `unique_id`-Schema. Ohne Fahrzeug geht kein Request raus.
- **C5 legt keine Entität an.** Der Koordinator hängt an `entry.runtime_data`.
- **Weder Request noch Antwortkörper gehen ins Log.** Das Debug-Log nennt Auslöser und Ergebnisklasse.
- **Die Subentry-Flows aus `C1-C2` bleiben bei `async_update_and_abort`.** `ConfigSubentryFlow.async_update_reload_and_abort` wirft bei vorhandenem Update-Listener `ValueError` (Home Assistant 2026.4.1, `config_entries.py` Zeile 3716).
- **Die 35 Kontrakt-Artefakte werden nie von Hand geändert** — `tests/fixtures/contract/**` und `contract.lock.json`.
- **Zeilenenden LF am gestagten Blob.** Der Arbeitsbaum trägt CRLF. Vor jedem Commit gibt `git diff --cached --name-only | while read f; do git show ":$f" | grep -q $'\r' && echo "CRLF: $f"; done` nichts aus.
- **Commit-Nachrichten** englisch, Imperativ, letzte Zeile `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- **Die Suite ist vor jedem Commit grün:** `.venv/Scripts/python.exe -m pytest -q`. Ausgangsstand: 176 bestandene Tests.
- **`<scratchpad>`** steht für das Scratchpad-Verzeichnis der ausführenden Sitzung. Was dort liegt, wird nicht committet.

---

## Dateien

| Datei | Verantwortung |
|---|---|
| `custom_components/meteo_volt/standort.py` | **neu.** Ladepunkt, Ladestand, Request, nächster Versuch, was gerade gilt, Repair-Issue-Zeitpunkt. Ohne Home Assistant. |
| `custom_components/meteo_volt/plankoordinator.py` | **neu.** Der Koordinator: Auslöser, Bündelung, Sperre, Timer, Repair-Issue. |
| `custom_components/meteo_volt/__init__.py` | **ergänzt.** Startet den Koordinator und hängt ihn an `runtime_data`. |
| `custom_components/meteo_volt/const.py` | **ergänzt.** `CONF_SITE_MAX_POWER`, `ISSUE_PLAN_VERALTET`. |
| `custom_components/meteo_volt/config_flow.py` | **geändert.** Feld Hausanschluss; Neu konfigurieren ersetzt die Daten, statt sie zusammenzuführen. |
| `custom_components/meteo_volt/translations/de.json`, `en.json` | **geändert.** Hausanschluss mit Hinweis, neuer Ladepunkt-Hinweis, Repair-Issue. |
| `custom_components/meteo_volt/dev.py`, `services.yaml` | **geändert, temporär.** Die Dev-Action holt über den Koordinator. |
| `custom_components/meteo_volt/manifest.json` | **geändert.** Version `1.1.0-beta.8`. |
| `tests/test_standort.py` | **neu.** Prüft `standort.py` gegen Request-Schema und Response-Fixtures. |
| `tests/test_uebersetzungen.py` | **ergänzt.** Hausanschluss und Repair-Issue sind in beiden Sprachen beschriftet. |

**Was das Gate nicht sieht:** Home Assistant. `tests/test_overrides.py` parst jede `.py`-Datei der Integration und fängt Syntaxfehler, aber keine falschen Namen. Dafür prüft Task 4 einmalig jeden benutzten Namen gegen den Quelltext von Home Assistant 2026.4.1, mit Gegenprobe. Das Verhalten sieht nur die Abnahme.

**Geprüft beim Schreiben dieses Plans, am 2026-09-14,** in einer Kopie gegen die echten Fixtures: Task 1 ohne Modul rot, mit Modul 27 grün; Task 2 gegen das Modul aus Task 1 rot, danach 62 grün; `test_uebersetzungen.py` vorher 28, mit den neuen Tests 6 rot, mit den Texten 34 grün. Die Namensprüfung fand alle 45 Namen, und mit einem vertippten Namen scheiterte sie.

---

## Vor Task 1: Plan und Wegweiser committen

- [ ] **Step 1: Den Wegweiser nachziehen**

In `CLAUDE.md` ersetzen:

```markdown
Kontraktregeln, `docs/FEATURES.md` für den Stand. Dieses Repo betreffen `S1`, `S2`, `C1`–`C7` und
`D2`.
```

durch:

```markdown
Kontraktregeln, `docs/FEATURES.md` für den Stand. Dieses Repo betreffen `S1`, `S2`, `C1`–`C7`,
`D2` und `E1`.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md docs/superpowers/plans/2026-09-14-c5-standort-koordinator.md
git diff --cached --name-only | while read f; do git show ":$f" | grep -q $'\r' && echo "CRLF: $f"; done
git commit -F - <<'EOF'
Plan the C5 site coordinator

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 1: `standort.py` — der Request

**Files:**
- Create: `custom_components/meteo_volt/standort.py`
- Modify: `custom_components/meteo_volt/const.py` (am Ende)
- Test: `tests/test_standort.py`

**Interfaces:**
- Consumes: `stammdaten.zu_ladepunkt(daten, ladepunkt_id)`, `stammdaten.zu_fahrzeug(daten, fahrzeug_id, soc_pct, soc_measured_at=None, station_id=None)`, `stammdaten.FELD_LADEPUNKT`, `stammdaten.FELD_SOC_ENTITAET`, `stammdaten.LADEPUNKT_DEFAULTS`, `stammdaten.FAHRZEUG_DEFAULTS`, `const.CONF_GRID_FEES`.
- Produces:
  - `const.CONF_SITE_MAX_POWER = "site_max_power_kw"`.
  - `standort.GRUND_KEIN_LADEPUNKT = "kein_ladepunkt"`, `GRUND_LADEPUNKT_GELOESCHT = "ladepunkt_geloescht"`, `GRUND_LADESTAND = "ladestand_nicht_lesbar"`.
  - `standort.Messung(zustand: str, geaendert: datetime)`, frozen dataclass.
  - `standort.ladestand_lesen(zustand: str | None) -> float | None`.
  - `standort.ladepunkt_zuordnen(fahrzeug: dict, ladepunkt_ids: list[str]) -> tuple[str | None, str | None]` — `(station_id, None)` oder `(None, Grund)`.
  - `standort.anfrage_bauen(ladepunkte: list[tuple[str, dict]], fahrzeuge: list[tuple[str, dict]], messungen: dict[str, Messung | None], haupteintrag: dict, zeitzone: str) -> tuple[dict | None, dict[str, str]]` — Request oder `None`, dazu Fahrzeug-ID → Grund.

- [ ] **Step 1: Den Test schreiben**

`tests/test_standort.py`:

```python
"""Prueft den Standort-Koordinator ohne Home Assistant.

Geprueft wird gegen die vendorten Kontrakt-Artefakte, nicht gegen eine hier
nochmal hingeschriebene Erwartung: der gebaute Request gegen
plan-request.schema.json, das Ablesen aus dem Plan gegen die Response-
Fixtures -- im ersten Slot muss es genau die Felder des Servers ergeben.

Was dieser Test NICHT sieht: Listener, Buendelung, Timer, das Repair-Issue,
die Dev-Action und Home Assistant ueberhaupt. Das deckt die Abnahme.
"""

import importlib
import json
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jsonschema
import pytest

WURZEL = Path(__file__).resolve().parents[1]
INTEGRATION = WURZEL / "custom_components" / "meteo_volt"
CONTRACT = WURZEL / "tests" / "fixtures" / "contract"

# standort.py importiert stammdaten, planabruf und const relativ, als Teil des
# Pakets. Geladen wird es deshalb ueber ein Paket, dessen __init__.py NICHT
# laeuft -- die zieht homeassistant herein, das in den Testabhaengigkeiten
# nicht steckt. Bekaeme eines der vier Module einen Import aus Home Assistant
# oder aiohttp, scheitert schon dieses Laden.
_PAKET = "meteo_volt_c5"
if _PAKET not in sys.modules:
    _paket = types.ModuleType(_PAKET)
    _paket.__path__ = [str(INTEGRATION)]
    sys.modules[_PAKET] = _paket
standort = importlib.import_module(f"{_PAKET}.standort")
stammdaten = importlib.import_module(f"{_PAKET}.stammdaten")
planabruf = importlib.import_module(f"{_PAKET}.planabruf")
const = importlib.import_module(f"{_PAKET}.const")


def _laden(pfad: Path) -> dict:
    roh = json.loads(pfad.read_text(encoding="utf-8"))
    return {k: v for k, v in roh.items() if k != "x-meteo-volt-contract"}


REQUEST_SCHEMA = _laden(CONTRACT / "plan-request.schema.json")
MESSZEIT = datetime(2026, 9, 14, 8, 0, tzinfo=timezone.utc)


def _ladepunkt(**felder) -> dict:
    return {**stammdaten.LADEPUNKT_DEFAULTS, **felder}


def _fahrzeug(**felder) -> dict:
    return {
        **stammdaten.FAHRZEUG_DEFAULTS,
        stammdaten.FELD_SOC_ENTITAET: "sensor.soc",
        **felder,
    }


def _messung(zustand: str = "47.5"):
    return standort.Messung(zustand=zustand, geaendert=MESSZEIT)


EIN_LADEPUNKT = [("wb-1", _ladepunkt())]
EIN_FAHRZEUG = [("auto-1", _fahrzeug())]


def _bauen(ladepunkte, fahrzeuge, messungen=None, haupteintrag=None):
    if messungen is None:
        messungen = {fahrzeug_id: _messung() for fahrzeug_id, _ in fahrzeuge}
    if haupteintrag is None:
        haupteintrag = {const.CONF_GRID_FEES: 0.0}
    return standort.anfrage_bauen(
        list(ladepunkte), list(fahrzeuge), messungen, haupteintrag, "Europe/Berlin")


# --- Ladestand, Spec Abschnitt 3 --------------------------------------------


@pytest.mark.parametrize(("zustand", "erwartet"), [
    ("47.5", 47.5), ("0", 0.0), ("100", 100.0), (" 80 ", 80.0),
])
def test_ein_ladestand_ist_lesbar(zustand, erwartet):
    assert standort.ladestand_lesen(zustand) == erwartet


@pytest.mark.parametrize("zustand", [
    "unavailable", "unknown", "abc", "", "nan", "inf", "-0.1", "100.1", None,
])
def test_ein_ladestand_ist_nicht_lesbar(zustand):
    assert standort.ladestand_lesen(zustand) is None


# --- Welcher Ladepunkt gilt, Spec Abschnitt 2 -------------------------------


def test_der_gebundene_ladepunkt_gilt():
    assert standort.ladepunkt_zuordnen(
        _fahrzeug(station_id="wb-2"), ["wb-1", "wb-2"]) == ("wb-2", None)


def test_ohne_bindung_gilt_der_zuerst_angelegte():
    assert standort.ladepunkt_zuordnen(_fahrzeug(), ["wb-1", "wb-2"]) == ("wb-1", None)


def test_ohne_ladepunkt_ist_es_ein_fehler():
    assert standort.ladepunkt_zuordnen(_fahrzeug(), []) == (
        None, standort.GRUND_KEIN_LADEPUNKT)


def test_ein_geloeschter_gebundener_ladepunkt_ist_ein_fehler():
    """Die Bindung ist ein Filter. Trifft er nichts mehr, weicht C5 nicht aus."""
    assert standort.ladepunkt_zuordnen(_fahrzeug(station_id="wb-weg"), ["wb-1"]) == (
        None, standort.GRUND_LADEPUNKT_GELOESCHT)


# --- Der Request, Spec Abschnitt 4 ------------------------------------------


def test_die_vorbelegung_ergibt_einen_kontraktkonformen_request():
    anfrage, ausgelassen = _bauen(EIN_LADEPUNKT, EIN_FAHRZEUG)
    jsonschema.validate(anfrage, REQUEST_SCHEMA)
    assert ausgelassen == {}
    assert anfrage["timezone"] == "Europe/Berlin"
    assert anfrage["site"] == {"grid_fees_eur_kwh": 0.0}
    fahrzeug = anfrage["vehicles"][0]
    assert fahrzeug["connection"] == {"station_id": "wb-1"}
    assert fahrzeug["soc_pct"] == 47.5
    assert fahrzeug["soc_measured_at"] == MESSZEIT.isoformat()


def test_now_steht_nicht_im_request():
    """Die Uhr hat der Dienst."""
    anfrage, _ = _bauen(EIN_LADEPUNKT, EIN_FAHRZEUG)
    assert "now" not in anfrage


def test_der_hausanschluss_geht_als_site_max_power_kw_mit():
    anfrage, _ = _bauen(EIN_LADEPUNKT, EIN_FAHRZEUG, haupteintrag={
        const.CONF_GRID_FEES: 0.18, const.CONF_SITE_MAX_POWER: 30.0})
    jsonschema.validate(anfrage, REQUEST_SCHEMA)
    assert anfrage["site"] == {"grid_fees_eur_kwh": 0.18, "max_power_kw": 30.0}


def test_ohne_netzkosten_und_hausanschluss_fehlt_der_site_block():
    anfrage, _ = _bauen(EIN_LADEPUNKT, EIN_FAHRZEUG, haupteintrag={})
    jsonschema.validate(anfrage, REQUEST_SCHEMA)
    assert "site" not in anfrage


def test_zwei_ladepunkte_ohne_bindung_ergeben_den_zuerst_angelegten():
    ladepunkte = [("wb-1", _ladepunkt()), ("wb-2", _ladepunkt(max_power_kw=22.0))]
    anfrage, _ = _bauen(ladepunkte, EIN_FAHRZEUG)
    jsonschema.validate(anfrage, REQUEST_SCHEMA)
    assert [station["id"] for station in anfrage["stations"]] == ["wb-1", "wb-2"]
    assert anfrage["vehicles"][0]["connection"] == {"station_id": "wb-1"}


def test_der_steckerzustand_aendert_den_request_nicht():
    """Die Angesteckt-Entitaet ist nur Ausloeser, Spec Abschnitt 2."""
    ohne, _ = _bauen(EIN_LADEPUNKT, EIN_FAHRZEUG)
    mit, _ = _bauen(EIN_LADEPUNKT, [
        ("auto-1", _fahrzeug(plugged_entity="binary_sensor.stecker"))])
    assert mit == ohne


def test_ein_unlesbarer_ladestand_laesst_nur_dieses_fahrzeug_aus():
    fahrzeuge = [("auto-1", _fahrzeug()), ("auto-2", _fahrzeug(soc_entity="sensor.soc2"))]
    anfrage, ausgelassen = _bauen(EIN_LADEPUNKT, fahrzeuge, messungen={
        "auto-1": _messung("unavailable"), "auto-2": _messung()})
    jsonschema.validate(anfrage, REQUEST_SCHEMA)
    assert ausgelassen == {"auto-1": standort.GRUND_LADESTAND}
    assert [fahrzeug["id"] for fahrzeug in anfrage["vehicles"]] == ["auto-2"]


def test_eine_fehlende_ladestand_entitaet_laesst_das_fahrzeug_aus():
    anfrage, ausgelassen = _bauen(EIN_LADEPUNKT, EIN_FAHRZEUG, messungen={"auto-1": None})
    assert anfrage is None
    assert ausgelassen == {"auto-1": standort.GRUND_LADESTAND}


def test_ohne_ladepunkt_zaehlt_der_ladepunkt_vor_dem_ladestand():
    anfrage, ausgelassen = _bauen([], EIN_FAHRZEUG, messungen={"auto-1": _messung("unknown")})
    assert anfrage is None
    assert ausgelassen == {"auto-1": standort.GRUND_KEIN_LADEPUNKT}


def test_ein_geloeschter_gebundener_ladepunkt_laesst_das_fahrzeug_aus():
    anfrage, ausgelassen = _bauen(EIN_LADEPUNKT, [("auto-1", _fahrzeug(station_id="wb-weg"))])
    assert anfrage is None
    assert ausgelassen == {"auto-1": standort.GRUND_LADEPUNKT_GELOESCHT}
```

- [ ] **Step 2: Den Test scheitern sehen**

Run: `.venv/Scripts/python.exe -m pytest tests/test_standort.py -q`
Expected: `1 error during collection` mit `ModuleNotFoundError: No module named 'meteo_volt_c5.standort'`

- [ ] **Step 3: Den Schlüssel anlegen**

Ans Ende von `custom_components/meteo_volt/const.py`:

```python

# Spec C5 Abschnitt 5: die Hausanschlussgrenze im Haupteintrag. Nicht
# max_power_kw -- das ist schon ein Feld des Ladepunkts.
CONF_SITE_MAX_POWER = "site_max_power_kw"
```

- [ ] **Step 4: Das Modul schreiben**

`custom_components/meteo_volt/standort.py`:

```python
"""Der Standort-Koordinator ohne Home Assistant.

Dieses Modul importiert bewusst NICHTS aus Home Assistant und nichts aus
aiohttp -- wie stammdaten.py und planabruf.py, auf denen es aufbaut. Hier
steht, was C5 entscheidet: welcher Ladepunkt gilt, wann ein Fahrzeug
ausgelassen wird, wie der Request aussieht, wann der naechste Versuch kommt
und was aus einem gehaltenen Plan gerade gilt. plankoordinator.py verdrahtet
das mit Home Assistant und entscheidet selbst nichts.

Der Steckerzustand kommt hier nicht vor. Er geht nicht in den Request: mit
station_id null plant der Server ueber den ganzen Horizont kein Laden, und
die Planung soll gerade sagen, wann eingesteckt werden muss.

Spec: meteo-volt-brain/docs/features/C5-standort-koordinator/spec.md
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from . import stammdaten
from .const import CONF_GRID_FEES, CONF_SITE_MAX_POWER

# --- Gruende, Spec Abschnitt 3 ---------------------------------------------
# Ein ausgelassenes Fahrzeug traegt genau einen, geprueft in dieser Reihenfolge.

GRUND_KEIN_LADEPUNKT = "kein_ladepunkt"
GRUND_LADEPUNKT_GELOESCHT = "ladepunkt_geloescht"
GRUND_LADESTAND = "ladestand_nicht_lesbar"


@dataclass(frozen=True)
class Messung:
    """Zustand und last_changed einer Entitaet, von plankoordinator.py gelesen."""

    zustand: str
    geaendert: datetime


def ladestand_lesen(zustand: str | None) -> float | None:
    """Der Zustand der Ladestand-Entitaet als Zahl, oder None. Spec Abschnitt 3.

    None heisst nicht lesbar: unavailable, unknown, keine Zahl, nicht endlich,
    ausserhalb 0 bis 100, oder die Entitaet fehlt. Ein Wert ausserhalb liesse
    den Server den ganzen Request ablehnen -- und dann bekaeme kein Fahrzeug
    einen Plan.
    """
    if zustand is None:
        return None
    try:
        wert = float(zustand)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(wert) or not 0.0 <= wert <= 100.0:
        return None
    return wert


def ladepunkt_zuordnen(
    fahrzeug: dict, ladepunkt_ids: list[str]
) -> tuple[str | None, str | None]:
    """(station_id, None) oder (None, Grund). Spec Abschnitt 2.

    ladepunkt_ids steht in Anlagereihenfolge. Die Bindung ist ein Filter:
    zeigt sie auf einen geloeschten Ladepunkt, weicht C5 nicht auf einen
    anderen aus. Ohne Bindung gilt der zuerst angelegte -- bewusst beliebig,
    gemeinsame Planung mehrerer Fahrzeuge gibt es erst mit E1.
    """
    if not ladepunkt_ids:
        return None, GRUND_KEIN_LADEPUNKT
    gebunden = fahrzeug.get(stammdaten.FELD_LADEPUNKT)
    if not gebunden:
        return ladepunkt_ids[0], None
    if gebunden not in ladepunkt_ids:
        return None, GRUND_LADEPUNKT_GELOESCHT
    return gebunden, None


def anfrage_bauen(
    ladepunkte: list[tuple[str, dict]],
    fahrzeuge: list[tuple[str, dict]],
    messungen: dict[str, Messung | None],
    haupteintrag: dict,
    zeitzone: str,
) -> tuple[dict | None, dict[str, str]]:
    """Der Request und die ausgelassenen Fahrzeuge. Spec Abschnitte 2 bis 4.

    ladepunkte und fahrzeuge sind (subentry_id, data) in Anlagereihenfolge,
    messungen bildet die Fahrzeug-ID auf die Messung ihrer Ladestand-Entitaet
    ab, None wenn die Entitaet fehlt. Bleibt kein Fahrzeug uebrig, ist der
    Request None.

    now fehlt mit Absicht: die Uhr hat der Dienst, und eine falsch gehende
    Uhr im Haus verschoebe den Beginn des Plans.
    """
    ids = [ladepunkt_id for ladepunkt_id, _ in ladepunkte]
    ausgelassen: dict[str, str] = {}
    fragmente = []
    for fahrzeug_id, daten in fahrzeuge:
        station_id, grund = ladepunkt_zuordnen(daten, ids)
        messung = messungen.get(fahrzeug_id)
        soc = ladestand_lesen(None if messung is None else messung.zustand)
        if grund is None and soc is None:
            grund = GRUND_LADESTAND
        if grund is not None:
            ausgelassen[fahrzeug_id] = grund
            continue
        fragmente.append(
            stammdaten.zu_fahrzeug(
                daten,
                fahrzeug_id,
                soc,
                soc_measured_at=messung.geaendert.isoformat(),
                station_id=station_id,
            )
        )
    if not fragmente:
        return None, ausgelassen

    anfrage = {
        "schema_version": 1,
        # Wirkt mit consumption none noch nicht. Ohne sie stimmte der Default
        # Europe/Berlin still nicht, sobald Z3 Fahrten nach Wochentag schickt.
        "timezone": zeitzone,
        "stations": [
            stammdaten.zu_ladepunkt(daten, ladepunkt_id)
            for ladepunkt_id, daten in ladepunkte
        ],
        "vehicles": fragmente,
    }
    site = {}
    if CONF_GRID_FEES in haupteintrag:
        site["grid_fees_eur_kwh"] = float(haupteintrag[CONF_GRID_FEES])
    if haupteintrag.get(CONF_SITE_MAX_POWER) is not None:
        # Der Planer vergleicht heute nur den einzelnen Ladevorgang. Mit E1
        # greift der Wert, ohne dass HA noch einmal angefasst wird.
        site["max_power_kw"] = float(haupteintrag[CONF_SITE_MAX_POWER])
    if site:
        anfrage["site"] = site
    return anfrage, ausgelassen
```

- [ ] **Step 5: Den Test bestehen sehen**

Run: `.venv/Scripts/python.exe -m pytest tests/test_standort.py -q`
Expected: `27 passed`

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: `203 passed`

- [ ] **Step 6: Commit**

```bash
git add custom_components/meteo_volt/standort.py custom_components/meteo_volt/const.py tests/test_standort.py
git diff --cached --name-only | while read f; do git show ":$f" | grep -q $'\r' && echo "CRLF: $f"; done
git commit -F - <<'EOF'
Build the site request without Home Assistant

Which charge point applies, when a vehicle is left out and what the
request carries, checked against the vendored request schema.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 2: `standort.py` — was gilt, nächster Versuch, Repair-Issue

**Files:**
- Modify: `custom_components/meteo_volt/standort.py` (Importblock, Anhang am Ende)
- Test: `tests/test_standort.py` (Anhang am Ende)

**Interfaces:**
- Consumes: aus Task 1 `anfrage_bauen`, `Messung` und die drei Gründe; aus C7 `planabruf.PlanFehler`, `PlanRateLimit(retry_after=..., **felder)`, `PlanAbgelehnt`, `PlanNichtAutorisiert`, `PlanNichtVerfuegbar`.
- Produces:
  - `standort.GRUNDTAKT = timedelta(minutes=60)`, `BUENDELN_S = 30.0`, `NACHHOLEN_NICHT_VERFUEGBAR_S = 300.0`, `VERALTET_NACH = timedelta(hours=12)`.
  - `standort.WEITER_IM_GRUNDTAKT = "grundtakt"`, `NACHHOLEN = "nachholen"`, `PAUSE = "pause"`, `QUELLE_PLAN = "plan"`, `QUELLE_DEFAULT = "default"`.
  - `standort.Planstand(plan=None, erhalten_um=None, anfrage=None, ausgelassen={}, fehler=None, letzter_versuch_um=None)`, frozen dataclass.
  - `standort.naechster_versuch(fehler: PlanFehler | None) -> tuple[str, float | None]`.
  - `standort.was_gilt(stand: Planstand, fahrzeug_id: str, jetzt: datetime, soc_pct: float | None) -> dict` mit `charge_now`, `charge_now_kw`, `charge_now_station_id`, `current_slot_end`, `next_charge_start` (Zeitpunkte als `datetime`) und `quelle`.
  - `standort.issue_pruefen_um(stand: Planstand, seit: datetime) -> datetime`, `standort.issue_faellig(stand: Planstand, seit: datetime, jetzt: datetime, hat_fahrzeuge: bool) -> bool`, `standort.issue_text(stand: Planstand) -> str`.

- [ ] **Step 1: Die Tests anhängen**

Ans Ende von `tests/test_standort.py`, nach zwei Leerzeilen:

```python
# --- Naechster Versuch, Spec Abschnitt 7 ------------------------------------


@pytest.mark.parametrize(("fehler", "erwartet"), [
    (None, (standort.WEITER_IM_GRUNDTAKT, None)),
    (planabruf.PlanRateLimit(retry_after=39.0, status=429), (standort.NACHHOLEN, 39.0)),
    (planabruf.PlanNichtVerfuegbar(status=503), (standort.NACHHOLEN, 300.0)),
    (planabruf.PlanAbgelehnt(status=404), (standort.PAUSE, None)),
    (planabruf.PlanNichtAutorisiert(status=401), (standort.PAUSE, None)),
], ids=["erfolg", "rate-limit", "nicht-verfuegbar", "abgelehnt", "nicht-autorisiert"])
def test_jede_fehlerklasse_hat_ihren_naechsten_versuch(fehler, erwartet):
    assert standort.naechster_versuch(fehler) == erwartet


# --- Was gerade gilt, Spec Abschnitt 8 --------------------------------------

FUENF_FELDER = ("charge_now", "charge_now_kw", "charge_now_station_id",
                "current_slot_end", "next_charge_start")


def _fixture_namen() -> list[str]:
    return sorted(p.name.split(".")[0] for p in CONTRACT.glob("*.response.json"))


def _fixture(name: str) -> tuple[dict, dict]:
    return (_laden(CONTRACT / f"{name}.request.json"),
            _laden(CONTRACT / f"{name}.response.json"))


def _zeit(text: str | None) -> datetime | None:
    return None if text is None else datetime.fromisoformat(text)


def _stand(anfrage: dict, plan: dict, erhalten_um: datetime):
    return standort.Planstand(plan=plan, erhalten_um=erhalten_um, anfrage=anfrage)


def test_es_gibt_response_fixtures():
    """Die Parametrisierung unten saehe ohne Fixtures null Faelle und bliebe gruen."""
    assert _fixture_namen(), "keine Response-Fixtures; export_contract.py --to-ha ausfuehren"


@pytest.mark.parametrize("name", _fixture_namen())
def test_im_ersten_slot_gilt_genau_was_der_server_schickte(name):
    anfrage, plan = _fixture(name)
    jetzt = datetime.fromisoformat(anfrage["now"])
    stand = _stand(anfrage, plan, jetzt)
    for fahrzeugplan in plan["vehicles"]:
        gilt = standort.was_gilt(stand, fahrzeugplan["id"], jetzt, None)
        assert gilt["quelle"] == standort.QUELLE_PLAN
        assert {feld: gilt[feld] for feld in FUENF_FELDER} == {
            "charge_now": fahrzeugplan["charge_now"],
            "charge_now_kw": fahrzeugplan["charge_now_kw"],
            "charge_now_station_id": fahrzeugplan["charge_now_station_id"],
            "current_slot_end": _zeit(fahrzeugplan["current_slot_end"]),
            "next_charge_start": _zeit(fahrzeugplan["next_charge_start"]),
        }, (name, fahrzeugplan["id"])


def _abend(uhrzeit: str | None) -> datetime | None:
    """Eine Uhrzeit am Abend des 2026-08-18. 00:00 ist die Mitternacht danach."""
    if uhrzeit is None:
        return None
    tag = "2026-08-19" if uhrzeit == "00:00" else "2026-08-18"
    return datetime.fromisoformat(f"{tag}T{uhrzeit}:00+02:00")


@pytest.mark.parametrize(("beginn", "laden", "kw", "station", "ende", "naechster"), [
    ("22:00", True, 11.0, "wb", "22:15", "23:15"),
    ("22:15", True, 11.0, "wb", "22:30", "23:15"),
    ("22:30", False, 0.0, None, "22:45", "23:15"),
    ("22:45", False, 0.0, None, "23:00", "23:15"),
    ("23:00", False, 0.0, None, "23:15", "23:15"),
    ("23:15", True, 11.0, "wb", "23:30", None),
    ("23:30", True, 11.0, "wb", "23:45", None),
    ("23:45", False, 0.0, None, "00:00", None),
])
def test_second_block_gilt_slot_fuer_slot(beginn, laden, kw, station, ende, naechster):
    """Muster CC...CC.: der laufende Block, eine Luecke, der naechste Block.
    Geprueft am Beginn des Slots und mitten darin."""
    anfrage, plan = _fixture("second_block")
    stand = _stand(anfrage, plan, datetime.fromisoformat(anfrage["now"]))
    for jetzt in (_abend(beginn), _abend(beginn) + timedelta(minutes=7)):
        assert standort.was_gilt(stand, "auto-a", jetzt, None) == {
            "charge_now": laden,
            "charge_now_kw": kw,
            "charge_now_station_id": station,
            "current_slot_end": _abend(ende),
            "next_charge_start": _abend(naechster),
            "quelle": standort.QUELLE_PLAN,
        }


def test_ab_horizon_end_gilt_der_default():
    anfrage, plan = _fixture("second_block")
    stand = _stand(anfrage, plan, datetime.fromisoformat(anfrage["now"]))
    assert standort.was_gilt(stand, "auto-a", _abend("00:00"), None)["quelle"] == (
        standort.QUELLE_DEFAULT)


def test_ein_plan_gilt_bis_kurz_vor_12_stunden_nach_empfang():
    anfrage, plan = _fixture("minimal")
    jetzt = datetime.fromisoformat(anfrage["now"])
    knapp = _stand(anfrage, plan, jetzt - standort.VERALTET_NACH + timedelta(seconds=1))
    veraltet = _stand(anfrage, plan, jetzt - standort.VERALTET_NACH)
    assert standort.was_gilt(knapp, "auto-a", jetzt, None)["quelle"] == standort.QUELLE_PLAN
    assert standort.was_gilt(veraltet, "auto-a", jetzt, None)["quelle"] == (
        standort.QUELLE_DEFAULT)


VORMITTAG = datetime(2026, 9, 14, 8, 7, tzinfo=timezone.utc)


def test_der_default_laedt_unter_min_soc():
    """Leistung aus Fahrzeug und Ladepunkt, der Ladepunkt aus dem Request."""
    anfrage, _ = _bauen(EIN_LADEPUNKT, [("auto-1", _fahrzeug(max_charge_kw=7.4))])
    stand = standort.Planstand(anfrage=anfrage)
    assert standort.was_gilt(stand, "auto-1", VORMITTAG, 14.9) == {
        "charge_now": True,
        "charge_now_kw": 7.4,
        "charge_now_station_id": "wb-1",
        "current_slot_end": datetime(2026, 9, 14, 8, 15, tzinfo=timezone.utc),
        "next_charge_start": None,
        "quelle": standort.QUELLE_DEFAULT,
    }


@pytest.mark.parametrize("soc", [15.0, 15.1, 80.0, None])
def test_der_default_laedt_nicht_ab_min_soc_und_nicht_ohne_ladestand(soc):
    anfrage, _ = _bauen(EIN_LADEPUNKT, EIN_FAHRZEUG)
    gilt = standort.was_gilt(standort.Planstand(anfrage=anfrage), "auto-1", VORMITTAG, soc)
    assert (gilt["charge_now"], gilt["charge_now_kw"], gilt["charge_now_station_id"]) == (
        False, 0.0, None)


def test_der_default_laedt_nicht_fuer_ein_fahrzeug_ausserhalb_des_requests():
    gilt = standort.was_gilt(standort.Planstand(), "auto-1", VORMITTAG, 5.0)
    assert gilt["charge_now"] is False


def test_auf_der_grenze_beginnt_die_naechste_viertelstunde():
    grenze = datetime(2026, 9, 14, 10, 15, tzinfo=timezone(timedelta(hours=2)))
    gilt = standort.was_gilt(standort.Planstand(), "auto-1", grenze, None)
    assert gilt["current_slot_end"] == grenze + timedelta(minutes=15)


# --- Das Repair-Issue, Spec Abschnitt 8 -------------------------------------

START = datetime(2026, 9, 14, 6, 0, tzinfo=timezone.utc)


def test_das_issue_zaehlt_ab_dem_was_zuletzt_kam():
    ohne_plan = standort.Planstand()
    plan_danach = standort.Planstand(erhalten_um=START + timedelta(hours=3))
    plan_davor = standort.Planstand(erhalten_um=START - timedelta(hours=3))
    assert standort.issue_pruefen_um(ohne_plan, START) == START + timedelta(hours=12)
    assert standort.issue_pruefen_um(plan_danach, START) == START + timedelta(hours=15)
    assert standort.issue_pruefen_um(plan_davor, START) == START + timedelta(hours=12)


def test_das_issue_ist_ab_12_stunden_faellig_und_nur_mit_fahrzeug():
    stand = standort.Planstand()
    knapp = START + standort.VERALTET_NACH - timedelta(seconds=1)
    faellig = START + standort.VERALTET_NACH
    assert not standort.issue_faellig(stand, START, knapp, hat_fahrzeuge=True)
    assert standort.issue_faellig(stand, START, faellig, hat_fahrzeuge=True)
    assert not standort.issue_faellig(stand, START, faellig, hat_fahrzeuge=False)


def test_das_issue_nennt_den_letzten_fehler_sonst_die_gruende():
    fehler = planabruf.PlanAbgelehnt(status=404, titel="Not Found")
    assert standort.issue_text(standort.Planstand(fehler=fehler)) == (
        "PlanAbgelehnt: Status 404; Not Found")
    ausgelassen = {"auto-1": standort.GRUND_LADESTAND}
    assert standort.issue_text(standort.Planstand(ausgelassen=ausgelassen)) == (
        standort.GRUND_LADESTAND)
```

- [ ] **Step 2: Die Tests scheitern sehen**

Run: `.venv/Scripts/python.exe -m pytest tests/test_standort.py -q`
Expected: `1 error during collection` mit `AttributeError: module 'meteo_volt_c5.standort' has no attribute 'WEITER_IM_GRUNDTAKT'`

- [ ] **Step 3: Den Importblock erweitern**

In `custom_components/meteo_volt/standort.py` ersetzen:

```python
from dataclasses import dataclass
from datetime import datetime

from . import stammdaten
from .const import CONF_GRID_FEES, CONF_SITE_MAX_POWER
```

durch:

```python
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from . import stammdaten
from .const import CONF_GRID_FEES, CONF_SITE_MAX_POWER
from .planabruf import PlanAbgelehnt, PlanFehler, PlanNichtAutorisiert, PlanRateLimit
```

- [ ] **Step 4: Den Anhang schreiben**

Ans Ende von `custom_components/meteo_volt/standort.py`, nach zwei Leerzeilen:

```python
# --- Zeiten, Spec Abschnitte 6 bis 8 ---------------------------------------

GRUNDTAKT = timedelta(minutes=60)
BUENDELN_S = 30.0
NACHHOLEN_NICHT_VERFUEGBAR_S = 300.0
VERALTET_NACH = timedelta(hours=12)

# Jeder Zeitzonen-Offset, den es gibt, ist ein Vielfaches einer Viertelstunde.
# In UTC gerechnet liegen die Grenzen deshalb auch lokal richtig.
_VIERTELSTUNDE_S = 900

# --- Naechster Versuch, Spec Abschnitt 7 -----------------------------------

WEITER_IM_GRUNDTAKT = "grundtakt"
NACHHOLEN = "nachholen"
PAUSE = "pause"

# --- Was gerade gilt, Spec Abschnitt 8 -------------------------------------

QUELLE_PLAN = "plan"
QUELLE_DEFAULT = "default"


@dataclass(frozen=True)
class Planstand:
    """Was C5 haelt. Spec Abschnitt 9.

    Jeder Lauf erzeugt einen neuen Planstand, keiner wird veraendert.
    """

    plan: dict | None = None
    erhalten_um: datetime | None = None
    anfrage: dict | None = None
    ausgelassen: dict[str, str] = field(default_factory=dict)
    fehler: PlanFehler | None = None
    letzter_versuch_um: datetime | None = None


def naechster_versuch(fehler: PlanFehler | None) -> tuple[str, float | None]:
    """Was nach einem Aufruf kommt. Spec Abschnitt 7.

    ("grundtakt", None)  weiter im Grundtakt
    ("nachholen", s)     einmal nach s Sekunden, danach im Grundtakt
    ("pause", None)      erst beim naechsten Ausloeser, der Grundtakt pausiert

    Abgelehnt und nicht autorisiert pausieren, weil dieselbe Anfrage wieder
    scheitert -- und weil die main-Umgebung heute keine Plan-Route hat: jeder
    Beta-Nutzer mit Fahrzeug schickte sonst stuendlich einen 404.
    """
    if fehler is None:
        return WEITER_IM_GRUNDTAKT, None
    if isinstance(fehler, PlanRateLimit):
        return NACHHOLEN, fehler.retry_after
    if isinstance(fehler, (PlanAbgelehnt, PlanNichtAutorisiert)):
        return PAUSE, None
    return NACHHOLEN, NACHHOLEN_NICHT_VERFUEGBAR_S


def was_gilt(
    stand: Planstand, fahrzeug_id: str, jetzt: datetime, soc_pct: float | None
) -> dict:
    """Was fuer ein Fahrzeug zum Zeitpunkt jetzt gilt. Spec Abschnitt 8.

    Aus dem Plan, solange er brauchbar ist, sonst der sichere Default. Im
    ersten Slot eines Plans ergibt das genau die Felder, die der Server
    geschickt hat. soc_pct ist der Ladestand zum Zeitpunkt des Aufrufs, None
    wenn er nicht lesbar ist -- nur der Default braucht ihn.
    """
    fahrzeugplan = _brauchbarer_plan(stand, fahrzeug_id, jetzt)
    if fahrzeugplan is not None:
        schritt = timedelta(minutes=stand.plan["slot_minutes"])
        slots = fahrzeugplan["slots"]
        for index, slot in enumerate(slots):
            beginn = datetime.fromisoformat(slot["t"])
            if beginn <= jetzt < beginn + schritt:
                laden = slot["charge"]
                return {
                    "charge_now": laden,
                    "charge_now_kw": (slot.get("kw") or 0.0) if laden else 0.0,
                    "charge_now_station_id": slot.get("station_id") if laden else None,
                    "current_slot_end": beginn + schritt,
                    "next_charge_start": _naechster_ladestart(slots, index),
                    "quelle": QUELLE_PLAN,
                }
    return _sicherer_default(stand, fahrzeug_id, jetzt, soc_pct)


def _brauchbarer_plan(stand: Planstand, fahrzeug_id: str, jetzt: datetime) -> dict | None:
    """Der Fahrzeugplan, wenn der Plan da, juenger als 12 h und nicht abgelaufen ist."""
    if stand.plan is None or stand.erhalten_um is None:
        return None
    if jetzt - stand.erhalten_um >= VERALTET_NACH:
        return None
    if jetzt >= datetime.fromisoformat(stand.plan["horizon_end"]):
        return None
    for fahrzeugplan in stand.plan.get("vehicles", []):
        if fahrzeugplan.get("id") == fahrzeug_id:
            return fahrzeugplan
    return None


def _naechster_ladestart(slots: list[dict], index: int) -> datetime | None:
    """Ab dem laufenden Slot der erste Ladeslot, dessen Vorgaenger nicht laedt.

    Dieselbe Regel wie _next_charge_start in meteovolt_planner/plan.py, nur ab
    index statt ab dem ersten Slot (A0-Spec 3.10).
    """
    for vorher, slot in zip(slots[index:], slots[index + 1:]):
        if slot["charge"] and not vorher["charge"]:
            return datetime.fromisoformat(slot["t"])
    return None


def _sicherer_default(
    stand: Planstand, fahrzeug_id: str, jetzt: datetime, soc_pct: float | None
) -> dict:
    """Laden nur unter Min-SoC. Fahrzeug und Ladepunkt aus dem zuletzt gebauten Request.

    Fehlt das Fahrzeug dort, wird nicht geladen: ohne Ladepunkt gibt es keine
    Leistung, ohne Ladestand keinen Vergleich.
    """
    fahrzeug = _eintrag(stand.anfrage, "vehicles", fahrzeug_id)
    station_id = None if fahrzeug is None else fahrzeug["connection"]["station_id"]
    station = _eintrag(stand.anfrage, "stations", station_id)
    laden = (
        station is not None
        and soc_pct is not None
        and soc_pct < fahrzeug["soc_min_pct"]
    )
    return {
        "charge_now": laden,
        "charge_now_kw": (
            min(fahrzeug["max_charge_kw"], station["max_power_kw"]) if laden else 0.0
        ),
        "charge_now_station_id": station_id if laden else None,
        "current_slot_end": _ende_der_viertelstunde(jetzt),
        "next_charge_start": None,
        "quelle": QUELLE_DEFAULT,
    }


def _eintrag(anfrage: dict | None, liste: str, kennung: str | None) -> dict | None:
    """Ein Ladepunkt oder Fahrzeug aus dem Request, nach seiner id."""
    if anfrage is None or kennung is None:
        return None
    for eintrag in anfrage[liste]:
        if eintrag["id"] == kennung:
            return eintrag
    return None


def _ende_der_viertelstunde(jetzt: datetime) -> datetime:
    """Genau auf einer Grenze beginnt die naechste Viertelstunde."""
    grenze = (math.floor(jetzt.timestamp()) // _VIERTELSTUNDE_S + 1) * _VIERTELSTUNDE_S
    return datetime.fromtimestamp(grenze, tz=timezone.utc)


def issue_pruefen_um(stand: Planstand, seit: datetime) -> datetime:
    """Wann das Repair-Issue faellig wird. Spec Abschnitt 8.

    seit ist der Start des Eintrags, oder das erste angelegte Fahrzeug, wenn
    es spaeter kam. Gezaehlt wird ab dem, was zuletzt kam: seit oder dem
    letzten Plan.
    """
    bezug = seit if stand.erhalten_um is None else max(stand.erhalten_um, seit)
    return bezug + VERALTET_NACH


def issue_faellig(
    stand: Planstand, seit: datetime, jetzt: datetime, hat_fahrzeuge: bool
) -> bool:
    """12 h ohne neuen Plan, obwohl Fahrzeuge angelegt sind."""
    return hat_fahrzeuge and jetzt >= issue_pruefen_um(stand, seit)


def issue_text(stand: Planstand) -> str:
    """{fehler} im Issue: die Meldung des letzten PlanFehler, sonst die Gruende."""
    if stand.fehler is not None:
        return f"{type(stand.fehler).__name__}: {stand.fehler}"
    if stand.ausgelassen:
        return ", ".join(sorted(set(stand.ausgelassen.values())))
    return "-"
```

- [ ] **Step 5: Die Tests bestehen sehen**

Run: `.venv/Scripts/python.exe -m pytest tests/test_standort.py -q`
Expected: `62 passed`

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: `238 passed`

- [ ] **Step 6: Commit**

```bash
git add custom_components/meteo_volt/standort.py tests/test_standort.py
git diff --cached --name-only | while read f; do git show ":$f" | grep -q $'\r' && echo "CRLF: $f"; done
git commit -F - <<'EOF'
Read what applies now from a held plan

In the first slot this yields exactly the server's fields. Without a
usable plan the safe default charges only below the minimum. The next
attempt and the stale-plan issue follow the spec.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 3: Der Hausanschluss und die Texte

**Files:**
- Modify: `custom_components/meteo_volt/const.py` (am Ende)
- Modify: `custom_components/meteo_volt/config_flow.py` (Import, Schema, Neu konfigurieren)
- Modify: `custom_components/meteo_volt/translations/de.json`, `custom_components/meteo_volt/translations/en.json`
- Test: `tests/test_uebersetzungen.py`

**Interfaces:**
- Consumes: `const.CONF_SITE_MAX_POWER` aus Task 1.
- Produces: `const.ISSUE_PLAN_VERALTET = "plan_veraltet"`. In beiden Sprachen `config.step.user` und `config.step.reconfigure` mit `data.site_max_power_kw` und `data_description.site_max_power_kw`, dazu `issues.plan_veraltet.title` und `issues.plan_veraltet.description` mit dem Platzhalter `{fehler}`.

- [ ] **Step 1: Die Tests schreiben**

In `tests/test_uebersetzungen.py` nach der Zeile

```python
_SPEC.loader.exec_module(stammdaten)
```

einfügen:

```python

# const.py importiert ebenfalls nichts aus Home Assistant. Die Schluessel
# des Hausanschlusses und des Repair-Issues kommen von dort, damit ein
# umbenannter Schluessel hier auffaellt.
_CONST = importlib.util.spec_from_file_location("meteo_volt_const", INTEGRATION / "const.py")
const = importlib.util.module_from_spec(_CONST)
_CONST.loader.exec_module(const)
```

Ans Ende der Datei, nach zwei Leerzeilen:

```python
@pytest.mark.parametrize("sprache", SPRACHEN)
@pytest.mark.parametrize("schritt", SCHRITTE)
def test_der_hausanschluss_ist_beschriftet_und_erklaert(sprache, schritt):
    """Spec C5 Abschnitt 5: das Feld wirkt noch nicht, und der Hinweis sagt es."""
    daten = _laden(sprache)["config"]["step"][schritt]
    assert const.CONF_SITE_MAX_POWER in daten.get("data", {}), f"{sprache}/{schritt}"
    assert const.CONF_SITE_MAX_POWER in daten.get("data_description", {}), f"{sprache}/{schritt}"


@pytest.mark.parametrize("sprache", SPRACHEN)
def test_das_repair_issue_ist_beschriftet(sprache):
    """Spec C5 Abschnitt 8. Ohne Uebersetzung zeigte HA den rohen Schluessel,
    und ohne {fehler} im Text verschwaende der Grund still."""
    issue = _laden(sprache).get("issues", {}).get(const.ISSUE_PLAN_VERALTET, {})
    assert issue.get("title"), sprache
    assert "{fehler}" in issue.get("description", ""), sprache
```

- [ ] **Step 2: Die Tests scheitern sehen**

Run: `.venv/Scripts/python.exe -m pytest tests/test_uebersetzungen.py -q`
Expected: `6 failed, 28 passed`

- [ ] **Step 3: Den Issue-Schlüssel anlegen**

Ans Ende von `custom_components/meteo_volt/const.py`:

```python

# Spec C5 Abschnitt 8: das Repair-Issue nach 12 h ohne neuen Plan.
ISSUE_PLAN_VERALTET = "plan_veraltet"
```

- [ ] **Step 4: Die Texte setzen**

Geändert wird über das dict, nicht über Text: `json.dumps(indent=2, ensure_ascii=False)` gibt beide Dateien Zeichen für Zeichen zurück, gemessen am 2026-09-14. Das Skript wird nicht committet. Als `<scratchpad>/uebersetzungen_c5.py` speichern:

```python
"""C5: Hausanschluss, neuer Ladepunkt-Hinweis und das Repair-Issue in beiden Sprachen.

json.dumps mit indent=2 und ensure_ascii=False gibt die beiden Dateien heute
Zeichen fuer Zeichen zurueck, gemessen am 2026-09-14. Deshalb wird hier ueber
das dict geaendert statt ueber Textersetzung.
"""

import json
import sys
from pathlib import Path

UEBERSETZUNGEN = Path(sys.argv[1] if len(sys.argv) > 1 else "custom_components/meteo_volt/translations")

TEXTE = {
    "de": {
        "hausanschluss": "Hausanschluss (kW)",
        "hausanschluss_hinweis": "Wird erst mit der Planung mehrerer Fahrzeuge berücksichtigt.",
        "ladepunkt_hinweis": (
            "Optional. Wenn gesetzt, lädt das Fahrzeug nur hier, sonst am zuerst angelegten "
            "Ladepunkt. Mehrere Fahrzeuge werden noch nicht gemeinsam geplant."),
        "issue_titel": "Ladeplanung ohne neuen Plan",
        "issue_text": "Seit 12 Stunden kam kein neuer Ladeplan. Letzter Fehler: {fehler}",
    },
    "en": {
        "hausanschluss": "Grid connection (kW)",
        "hausanschluss_hinweis": "Only taken into account once several vehicles are planned together.",
        "ladepunkt_hinweis": (
            "Optional. If set, the vehicle charges only here, otherwise at the charge point "
            "created first. Several vehicles are not yet planned together."),
        "issue_titel": "Charge planning without a new plan",
        "issue_text": "No new charge plan for 12 hours. Last error: {fehler}",
    },
}

for sprache, text in TEXTE.items():
    pfad = UEBERSETZUNGEN / f"{sprache}.json"
    daten = json.loads(pfad.read_text(encoding="utf-8"))
    for schritt in ("user", "reconfigure"):
        haupt = daten["config"]["step"][schritt]
        haupt["data"]["site_max_power_kw"] = text["hausanschluss"]
        haupt.setdefault("data_description", {})["site_max_power_kw"] = text["hausanschluss_hinweis"]
        fahrzeug = daten["config_subentries"]["vehicle"]["step"][schritt]
        fahrzeug["sections"]["entitaeten"]["data_description"]["station_id"] = text["ladepunkt_hinweis"]
    daten["issues"] = {
        "plan_veraltet": {"title": text["issue_titel"], "description": text["issue_text"]},
    }
    pfad.write_text(
        json.dumps(daten, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"[OK] {pfad}")
```

Run: `.venv/Scripts/python.exe <scratchpad>/uebersetzungen_c5.py`
Expected: je eine Zeile `[OK]` für `de.json` und `en.json`

Run: `git diff custom_components/meteo_volt/translations`
Expected: nur die Einträge `site_max_power_kw` in `user` und `reconfigure`, die zwei `station_id`-Hinweise im Fahrzeug und der Block `issues` am Ende — sonst keine Zeile, in beiden Dateien.

- [ ] **Step 5: Das Feld im Config-Flow**

In `custom_components/meteo_volt/config_flow.py` drei Stellen.

Der Import — ersetzen:

```python
from .const import DOMAIN, CONF_API_TOKEN, CONF_GRID_FEES, API_URL
```

durch:

```python
from .const import DOMAIN, CONF_API_TOKEN, CONF_GRID_FEES, CONF_SITE_MAX_POWER, API_URL
```

Das Schema — ersetzen:

```python
        vol.Optional(CONF_GRID_FEES, default=0.0): vol.Coerce(float),
    }
)
```

durch:

```python
        vol.Optional(CONF_GRID_FEES, default=0.0): vol.Coerce(float),
        # Spec C5 Abschnitt 5: ohne Vorbelegung. Leer heisst, der Request traegt
        # kein site.max_power_kw -- der Planer nutzt es erst mit E1.
        vol.Optional(CONF_SITE_MAX_POWER): vol.All(
            vol.Coerce(float), vol.Range(min=0, min_included=False)
        ),
    }
)
```

Das Neu konfigurieren — ersetzen:

```python
            else:
                # Die unique_id ueber async_update_entry: dieser Weg ist belegt,
                # ein unique_id-Parameter am Helfer darunter nicht.
                self.hass.config_entries.async_update_entry(entry, unique_id=neuer_key)
                return self.async_update_reload_and_abort(
                    entry, data_updates=user_input, reason="reconfigure_successful"
                )
```

durch:

```python
            else:
                # Ersetzen statt zusammenfuehren, Spec C5 Abschnitt 5: ein
                # geleertes optionales Feld fehlt in user_input, und mit
                # data_updates bliebe der alte Wert stehen.
                daten = {**entry.data, **user_input}
                if CONF_SITE_MAX_POWER not in user_input:
                    daten.pop(CONF_SITE_MAX_POWER, None)
                # Die unique_id ueber async_update_entry: dieser Weg ist belegt,
                # ein unique_id-Parameter am Helfer darunter nicht.
                self.hass.config_entries.async_update_entry(entry, unique_id=neuer_key)
                return self.async_update_reload_and_abort(
                    entry, data=daten, reason="reconfigure_successful"
                )
```

- [ ] **Step 6: Die Tests bestehen sehen**

Run: `.venv/Scripts/python.exe -m pytest tests/test_uebersetzungen.py -q`
Expected: `34 passed`

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: `244 passed`

- [ ] **Step 7: Commit**

```bash
git add custom_components/meteo_volt/const.py custom_components/meteo_volt/config_flow.py custom_components/meteo_volt/translations/de.json custom_components/meteo_volt/translations/en.json tests/test_uebersetzungen.py
git diff --cached --name-only | while read f; do git show ":$f" | grep -q $'\r' && echo "CRLF: $f"; done
git commit -F - <<'EOF'
Let the main entry carry the grid connection limit

The field takes effect once E1 plans vehicles together, and its hint
says so. Reconfigure now replaces the data, so clearing the field
removes the value. The charge point hint names the first-created rule,
and the stale-plan issue has its texts.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 4: `plankoordinator.py` — der Koordinator in Home Assistant

**Files:**
- Create: `custom_components/meteo_volt/plankoordinator.py`
- Modify: `custom_components/meteo_volt/__init__.py` (vollständig)

**Interfaces:**
- Consumes: aus `standort.py` alles aus Task 1 und 2; `const.DOMAIN`, `const.ISSUE_PLAN_VERALTET`; aus C7 `MeteoVoltApiClient.async_create_plan(hass, anfrage) -> dict` und `planabruf.PlanFehler`; `stammdaten.TYP_LADEPUNKT`, `TYP_FAHRZEUG`, `FELD_ANGESTECKT`, `FELD_SOC_ENTITAET`.
- Produces:
  - `MeteoVoltPlanKoordinator(hass: HomeAssistant, entry: ConfigEntry, client: MeteoVoltApiClient)`, ein `DataUpdateCoordinator[Planstand]`. `data` ist nie `None`.
  - `.async_starten() -> None` — verdrahtet Auslöser und Timer, kehrt sofort zurück.
  - `async .async_jetzt_planen() -> Planstand` — sofort, ohne Bündelung, für die Dev-Action.
  - `.was_gilt_jetzt() -> dict[str, dict]` — `was_gilt` je Fahrzeug mit dem aktuellen Ladestand.
  - `entry.runtime_data` ist der Koordinator, wenn sein Start gelang.

Kein automatischer Test: der Koordinator braucht Home Assistant. Einmalig geprüft wird, dass jeder benutzte Name in Home Assistant 2026.4.1 existiert; das Verhalten prüft die Abnahme.

Zwei Befunde aus dem Quelltext von Home Assistant 2026.4.1, auf denen der Code steht:

- `DataUpdateCoordinator` plant seinen Takt nur, solange er Listener hat (`update_coordinator.py`, `async_add_listener` und das Ende von `_async_refresh`). C5 legt keine Entität an — der Grundtakt läuft deshalb über `async_track_time_interval`, `update_interval` bleibt `None`.
- Ein Subentry anlegen, ändern oder löschen feuert die Update-Listener des Eintrags (`config_entries.py`, `_async_save_and_notify`). Der Listener liest neu und lädt nicht neu.

- [ ] **Step 1: Den Koordinator schreiben**

`custom_components/meteo_volt/plankoordinator.py`:

```python
"""Der Standort-Koordinator in Home Assistant: Ausloeser, Buendelung, Timer.

Was C5 entscheidet, steht in standort.py und ist dort ohne Home Assistant
geprueft. Hier steht nur die Verdrahtung: welche Ereignisse einen Plan
ausloesen, dass nur ein Aufruf zur Zeit laeuft, wann nachgeholt wird und wann
das Repair-Issue kommt. Das sieht kein automatischer Test, nur die Abnahme.

Der Grundtakt laeuft nicht ueber update_interval: DataUpdateCoordinator
taktet nur, solange er Listener hat, und C5 legt keine Entitaet an. Den Takt
haelt deshalb ein eigener Timer.

Spec: meteo-volt-brain/docs/features/C5-standort-koordinator/spec.md
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.event import (
    async_call_later,
    async_track_point_in_utc_time,
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from . import stammdaten, standort
from .api import MeteoVoltApiClient
from .const import DOMAIN, ISSUE_PLAN_VERALTET
from .planabruf import PlanFehler

_LOGGER = logging.getLogger(__name__)


class MeteoVoltPlanKoordinator(DataUpdateCoordinator[standort.Planstand]):
    """Ein Koordinator je Eintrag, also je Standort. Spec C5 Abschnitt 9.

    data ist immer ein Planstand, nie None. Ein PlanFehler macht den
    Koordinator nicht unavailable, er steht in data.fehler.
    """

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: MeteoVoltApiClient
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_plan",
            update_interval=None,
            # Spec Abschnitt 6: der erste Ausloeser geht sofort raus, weitere
            # binnen 30 s ergeben einen einzigen Request am Ende der 30 s.
            request_refresh_debouncer=Debouncer(
                hass, _LOGGER, cooldown=standort.BUENDELN_S, immediate=True
            ),
        )
        self.client = client
        self.data = standort.Planstand()
        # Der Plan-Client haelt gleichzeitige Aufrufe nicht auseinander
        # (C7-Spec Abschnitt 4). Die Dev-Action umgeht die Buendelung, diese
        # Sperre nicht.
        self._sperre = asyncio.Lock()
        self._ausloeser: set[str] = set()
        self._grundtakt_pausiert = False
        self._letzte_fehlerklasse: str | None = None
        self._subentries = self._subentry_abbild()
        # Ab hier zaehlt das Repair-Issue, solange kein Plan kam: der Start,
        # oder das erste Fahrzeug, wenn es spaeter angelegt wird.
        self._seit = dt_util.utcnow()
        self._nachholen_abbrechen: Callable[[], None] | None = None
        self._issue_abbrechen: Callable[[], None] | None = None
        self._entitaeten_abbrechen: list[Callable[[], None]] = []

    # --- Start und Ende ---------------------------------------------------

    @callback
    def async_starten(self) -> None:
        """Verdrahtet Ausloeser und Timer und kehrt sofort zurueck."""
        entry = self.config_entry
        entry.async_on_unload(self._aufraeumen)
        entry.async_on_unload(entry.add_update_listener(self._eintrag_geaendert))
        entry.async_on_unload(
            async_track_time_interval(
                self.hass,
                self._grundtakt,
                standort.GRUNDTAKT,
                name=f"{DOMAIN} Grundtakt",
                cancel_on_shutdown=True,
            )
        )
        # Startet Home Assistant, dann erst, wenn es gestartet ist: vorher
        # fehlen die Ladestaende anderer Integrationen noch. Beim Neuladen des
        # Eintrags laeuft das sofort.
        entry.async_on_unload(async_at_started(self.hass, self._beim_start))
        self._entitaeten_anmelden()
        self._issue_pruefung_planen()

    @callback
    def _aufraeumen(self) -> None:
        self._nachholen_absagen()
        if self._issue_abbrechen is not None:
            self._issue_abbrechen()
            self._issue_abbrechen = None
        self._entitaeten_abmelden()
        ir.async_delete_issue(self.hass, DOMAIN, self._issue_id)

    # --- Ausloeser, Spec Abschnitt 6 ----------------------------------------

    @callback
    def _ausloesen(self, kennung: str) -> None:
        """Merkt die Kennung fuer das Debug-Log und fordert gebuendelt an."""
        self._ausloeser.add(kennung)
        self.config_entry.async_create_background_task(
            self.hass, self.async_request_refresh(), name=f"{DOMAIN} Plan {kennung}"
        )

    @callback
    def _beim_start(self, _hass: HomeAssistant) -> None:
        self._ausloesen("start")

    @callback
    def _grundtakt(self, _jetzt: datetime) -> None:
        # Spec Abschnitt 7: nach abgelehnt oder nicht autorisiert pausiert er.
        if not self._grundtakt_pausiert:
            self._ausloesen("grundtakt")

    async def _eintrag_geaendert(self, _hass: HomeAssistant, _entry: ConfigEntry) -> None:
        """Nur geaenderte Subentries zaehlen.

        Eine Aenderung am Haupteintrag laedt den Eintrag ohnehin neu (S2). Hier
        wird nicht neu geladen: das holte jedes Mal die Prognose mit, und die
        Sensoren wuerden kurz unavailable.
        """
        abbild = self._subentry_abbild()
        if abbild == self._subentries:
            return
        hatte_fahrzeuge = self._hat_fahrzeuge(self._subentries)
        self._subentries = abbild
        if not self._hat_fahrzeuge(abbild):
            ir.async_delete_issue(self.hass, DOMAIN, self._issue_id)
        elif not hatte_fahrzeuge:
            self._seit = dt_util.utcnow()
        self._issue_pruefung_planen()
        self._entitaeten_anmelden()
        self._ausloesen("subentry")

    @callback
    def _stecker_geaendert(self, event: Event[EventStateChangedData]) -> None:
        neu, alt = event.data["new_state"], event.data["old_state"]
        if neu is not None and neu.state == "on" and (alt is None or alt.state != "on"):
            self._ausloesen("stecker")

    @callback
    def _ladestand_geaendert(self, event: Event[EventStateChangedData]) -> None:
        """Nur fuer ein Fahrzeug, das wegen seines Ladestands fehlt."""
        neu = event.data["new_state"]
        if neu is None or standort.ladestand_lesen(neu.state) is None:
            return
        for fahrzeug_id, daten in self._subentries_vom_typ(stammdaten.TYP_FAHRZEUG):
            if (
                daten.get(stammdaten.FELD_SOC_ENTITAET) == event.data["entity_id"]
                and self.data.ausgelassen.get(fahrzeug_id) == standort.GRUND_LADESTAND
            ):
                self._ausloesen("ladestand")
                return

    @callback
    def _nachholen(self, _jetzt: datetime) -> None:
        self._nachholen_abbrechen = None
        self._ausloesen("nachholen")

    async def async_jetzt_planen(self) -> standort.Planstand:
        """Fuer die Dev-Action: sofort, ohne Buendelung, nie an der Sendepause vorbei."""
        self._ausloeser.add("dev")
        await self.async_refresh()
        return self.data

    # --- Der Lauf ----------------------------------------------------------

    async def _async_update_data(self) -> standort.Planstand:
        """Ein Lauf. Wirft nie fuer einen PlanFehler, der steht im Planstand."""
        async with self._sperre:
            kennung = ",".join(sorted(self._ausloeser)) or "grundtakt"
            self._ausloeser.clear()
            # Spec Abschnitt 7: ein Nachholversuch entfaellt, wenn vorher ein
            # anderer Aufruf kommt.
            self._nachholen_absagen()

            anfrage, ausgelassen = standort.anfrage_bauen(
                self._subentries_vom_typ(stammdaten.TYP_LADEPUNKT),
                self._subentries_vom_typ(stammdaten.TYP_FAHRZEUG),
                self._messungen(),
                dict(self.config_entry.data),
                self.hass.config.time_zone,
            )
            stand = replace(self.data, anfrage=anfrage, ausgelassen=ausgelassen)
            if anfrage is None:
                # Spec Abschnitt 3: kein Request, der gehaltene Plan bleibt.
                _LOGGER.debug("Plan %s: kein planbares Fahrzeug, nichts gesendet", kennung)
                return stand

            versuch_um = dt_util.utcnow()
            try:
                plan = await self.client.async_create_plan(self.hass, anfrage)
            except PlanFehler as fehler:
                stand = replace(stand, fehler=fehler, letzter_versuch_um=versuch_um)
            else:
                stand = replace(
                    stand,
                    plan=plan,
                    erhalten_um=dt_util.utcnow(),
                    fehler=None,
                    letzter_versuch_um=versuch_um,
                )
            # Kennung und Ergebnisklasse, nie Inhalt: im Request stehen
            # Ladestaende (Basiskontrakt 3.7).
            _LOGGER.debug(
                "Plan %s: %s",
                kennung,
                "erhalten" if stand.fehler is None else type(stand.fehler).__name__,
            )
            self._nach_dem_aufruf(stand)
            return stand

    @callback
    def _nach_dem_aufruf(self, stand: standort.Planstand) -> None:
        art, sekunden = standort.naechster_versuch(stand.fehler)
        self._grundtakt_pausiert = art == standort.PAUSE
        if art == standort.NACHHOLEN:
            self._nachholen_abbrechen = async_call_later(self.hass, sekunden, self._nachholen)

        klasse = None if stand.fehler is None else type(stand.fehler).__name__
        if klasse is not None and klasse != self._letzte_fehlerklasse:
            # Spec Abschnitt 7: einmal, wenn er auftritt oder die Klasse wechselt.
            _LOGGER.warning("Kein neuer Ladeplan: %s: %s", klasse, stand.fehler)
        self._letzte_fehlerklasse = klasse

        if stand.fehler is None:
            ir.async_delete_issue(self.hass, DOMAIN, self._issue_id)
            self._issue_pruefung_planen(stand)

    @callback
    def _nachholen_absagen(self) -> None:
        if self._nachholen_abbrechen is not None:
            self._nachholen_abbrechen()
            self._nachholen_abbrechen = None

    # --- Repair-Issue, Spec Abschnitt 8 -------------------------------------

    @property
    def _issue_id(self) -> str:
        return f"{ISSUE_PLAN_VERALTET}_{self.config_entry.entry_id}"

    @callback
    def _issue_pruefung_planen(self, stand: standort.Planstand | None = None) -> None:
        """Das Issue haengt an der Uhr, nicht am naechsten Versuch.

        Nach abgelehnt pausiert der Grundtakt. Ein Issue, das erst beim
        naechsten Versuch geprueft wuerde, kaeme dann nie.
        """
        if self._issue_abbrechen is not None:
            self._issue_abbrechen()
        faellig_um = standort.issue_pruefen_um(stand or self.data, self._seit)
        self._issue_abbrechen = async_track_point_in_utc_time(
            self.hass, self._issue_pruefen, faellig_um
        )

    @callback
    def _issue_pruefen(self, jetzt: datetime) -> None:
        self._issue_abbrechen = None
        hat_fahrzeuge = self._hat_fahrzeuge(self._subentries)
        if standort.issue_faellig(self.data, self._seit, jetzt, hat_fahrzeuge):
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                self._issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key=ISSUE_PLAN_VERALTET,
                translation_placeholders={"fehler": standort.issue_text(self.data)},
            )

    # --- Lesen aus Home Assistant --------------------------------------------

    def _subentries_vom_typ(self, typ: str) -> list[tuple[str, dict]]:
        """(subentry_id, data) in Anlagereihenfolge."""
        return [
            (subentry.subentry_id, dict(subentry.data))
            for subentry in self.config_entry.subentries.values()
            if subentry.subentry_type == typ
        ]

    def _subentry_abbild(self) -> dict[str, tuple[str, dict]]:
        return {
            subentry.subentry_id: (subentry.subentry_type, dict(subentry.data))
            for subentry in self.config_entry.subentries.values()
        }

    @staticmethod
    def _hat_fahrzeuge(abbild: dict[str, tuple[str, dict]]) -> bool:
        return any(typ == stammdaten.TYP_FAHRZEUG for typ, _ in abbild.values())

    def _messungen(self) -> dict[str, standort.Messung | None]:
        """Die Ladestand-Entitaet je Fahrzeug, None wenn sie fehlt."""
        messungen: dict[str, standort.Messung | None] = {}
        for fahrzeug_id, daten in self._subentries_vom_typ(stammdaten.TYP_FAHRZEUG):
            zustand = self.hass.states.get(daten.get(stammdaten.FELD_SOC_ENTITAET) or "")
            messungen[fahrzeug_id] = (
                None
                if zustand is None
                else standort.Messung(zustand=zustand.state, geaendert=zustand.last_changed)
            )
        return messungen

    def was_gilt_jetzt(self) -> dict[str, dict]:
        """Fuer die Dev-Action: was je Fahrzeug gerade gilt, mit dem aktuellen Ladestand."""
        jetzt = dt_util.utcnow()
        return {
            fahrzeug_id: standort.was_gilt(
                self.data,
                fahrzeug_id,
                jetzt,
                standort.ladestand_lesen(None if messung is None else messung.zustand),
            )
            for fahrzeug_id, messung in self._messungen().items()
        }

    @callback
    def _entitaeten_anmelden(self) -> None:
        """Angesteckt- und Ladestand-Entitaeten aller Fahrzeuge, neu angemeldet."""
        self._entitaeten_abmelden()
        fahrzeuge = [daten for _, daten in self._subentries_vom_typ(stammdaten.TYP_FAHRZEUG)]
        for feld, reaktion in (
            (stammdaten.FELD_ANGESTECKT, self._stecker_geaendert),
            (stammdaten.FELD_SOC_ENTITAET, self._ladestand_geaendert),
        ):
            entitaeten = sorted({daten[feld] for daten in fahrzeuge if daten.get(feld)})
            if entitaeten:
                self._entitaeten_abbrechen.append(
                    async_track_state_change_event(self.hass, entitaeten, reaktion)
                )

    @callback
    def _entitaeten_abmelden(self) -> None:
        while self._entitaeten_abbrechen:
            self._entitaeten_abbrechen.pop()()
```

- [ ] **Step 2: Den Koordinator starten**

`custom_components/meteo_volt/__init__.py` vollständig:

```python
"""The Meteo-Volt integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .api import MeteoVoltApiClient
from .const import DOMAIN, CONF_API_TOKEN, API_URL
from .overrides import load_overrides
from .coordinator import MeteoVoltDataUpdateCoordinator
from .plankoordinator import MeteoVoltPlanKoordinator
# Temporaer, Spec C7 Abschnitt 7: geht zusammen mit dev.py und dem Aufruf unten.
from .dev import async_dev_action_registrieren

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Meteo-Volt from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    api_token = entry.data[CONF_API_TOKEN]
    # Dateizugriff gehoert nicht in den Event-Loop. Siehe overrides.py: fehlt
    # die Datei -- der Normalfall -- kommt hier ein leeres dict zurueck.
    overrides = await hass.async_add_executor_job(load_overrides)
    client = MeteoVoltApiClient(api_token, api_url=overrides.get("api_url", API_URL))

    coordinator = MeteoVoltDataUpdateCoordinator(hass, client)

    # Fetch initial data so we have data when entities subscribe
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Spec C5 Abschnitt 6: der Standort-Koordinator wartet auf nichts, und
    # scheitert sein Start, laeuft die Prognose trotzdem weiter -- sie hat
    # zahlende Nutzer (Bestandsschutz). Er haengt an runtime_data; hass.data
    # und sensor.py bleiben, wie sie sind.
    try:
        plan_koordinator = MeteoVoltPlanKoordinator(hass, entry, client)
        plan_koordinator.async_starten()
    except Exception:  # pylint: disable=broad-except
        _LOGGER.exception("Standort-Koordinator nicht gestartet, die Prognose laeuft weiter")
    else:
        entry.runtime_data = plan_koordinator

    # Temporaer, Spec C7 Abschnitt 7: nur wenn const_overwrite.json wirkt.
    if overrides:
        async_dev_action_registrieren(hass)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
```

- [ ] **Step 3: Jeden Namen gegen Home Assistant 2026.4.1 prüfen**

Einmalig und nicht committet. Als `<scratchpad>/ha_namen_pruefen.py` speichern:

```python
"""Einmal-Pruefung: gibt es jeden Namen aus Home Assistant, den C5 benutzt, in 2026.4.1?

Das Gate kann Home Assistant nicht laden. Ein falscher Name faellt erst beim
Laden der Integration auf -- und dann laeuft auch die Prognose nicht.

Aufruf aus dem ha-Repo:  .venv/Scripts/python.exe <pfad>/ha_namen_pruefen.py
"""

import ast
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASIS = "https://raw.githubusercontent.com/home-assistant/core/2026.4.1/"
INTEGRATION = Path(sys.argv[1] if len(sys.argv) > 1 else "custom_components/meteo_volt")
DATEIEN = ("plankoordinator.py", "__init__.py", "dev.py", "config_flow.py")

# Namen, die als Attribut oder Methode benutzt und nicht importiert werden.
AUFRUFE = [
    ("homeassistant.helpers.issue_registry", "async_create_issue"),
    ("homeassistant.helpers.issue_registry", "async_delete_issue"),
    ("homeassistant.helpers.issue_registry", "IssueSeverity"),
    ("homeassistant.util.dt", "utcnow"),
    ("homeassistant.config_entries", "async_loaded_entries"),
    ("homeassistant.config_entries", "async_create_background_task"),
    ("homeassistant.config_entries", "add_update_listener"),
    ("homeassistant.config_entries", "async_on_unload"),
    ("homeassistant.config_entries", "async_update_reload_and_abort"),
    ("homeassistant.config_entries", "subentry_type"),
    ("homeassistant.helpers.update_coordinator", "async_request_refresh"),
    ("homeassistant.helpers.update_coordinator", "async_refresh"),
    ("homeassistant.core", "last_changed"),
]

_quellen: dict[str, str | None] = {}


def quelle(modul: str) -> str | None:
    if modul not in _quellen:
        pfad = modul.replace(".", "/")
        _quellen[modul] = None
        for kandidat in (f"{pfad}.py", f"{pfad}/__init__.py"):
            try:
                with urllib.request.urlopen(BASIS + kandidat, timeout=30) as antwort:
                    _quellen[modul] = antwort.read().decode("utf-8")
                    break
            except urllib.error.HTTPError:
                continue
    return _quellen[modul]


def definiert(modul: str, name: str) -> bool:
    text = quelle(modul)
    if text is None:
        return False
    muster = (
        rf"^\s*(?:class|def|async def|type) {re.escape(name)}\b"
        rf"|^\s*{re.escape(name)}\s*[:=]"
    )
    if re.search(muster, text, re.MULTILINE):
        return True
    # from homeassistant.helpers import issue_registry: ein Untermodul.
    return quelle(f"{modul}.{name}") is not None


fehlend = []
geprueft = 0
for datei in DATEIEN:
    baum = ast.parse((INTEGRATION / datei).read_text(encoding="utf-8"))
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.ImportFrom) and (knoten.module or "").startswith("homeassistant"):
            for alias in knoten.names:
                geprueft += 1
                if not definiert(knoten.module, alias.name):
                    fehlend.append(f"{datei}: from {knoten.module} import {alias.name}")
for modul, name in AUFRUFE:
    geprueft += 1
    if not definiert(modul, name):
        fehlend.append(f"{modul}: {name}")

if fehlend:
    print("FEHLT in Home Assistant 2026.4.1:")
    print("\n".join(f"  {zeile}" for zeile in fehlend))
    sys.exit(1)
print(f"alle {geprueft} Namen in Home Assistant 2026.4.1 gefunden")
```

Zuerst die Gegenprobe — eine Prüfung, die nichts findet, darf nicht grün werden:

```bash
rm -rf "<scratchpad>/gegenprobe" && mkdir -p "<scratchpad>/gegenprobe"
cp custom_components/meteo_volt/*.py "<scratchpad>/gegenprobe/"
sed -i 's/async_track_state_change_event,/async_track_state_change_evnt,/' "<scratchpad>/gegenprobe/plankoordinator.py"
.venv/Scripts/python.exe "<scratchpad>/ha_namen_pruefen.py" "<scratchpad>/gegenprobe"; echo "exit=$?"
```

Expected: `FEHLT in Home Assistant 2026.4.1:` mit der Zeile `plankoordinator.py: from homeassistant.helpers.event import async_track_state_change_evnt`, danach `exit=1`

Run: `.venv/Scripts/python.exe <scratchpad>/ha_namen_pruefen.py`
Expected: `alle 45 Namen in Home Assistant 2026.4.1 gefunden`

- [ ] **Step 4: Suite und Commit**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: `244 passed` — `test_overrides.py` parst dabei auch `plankoordinator.py`.

```bash
git add custom_components/meteo_volt/plankoordinator.py custom_components/meteo_volt/__init__.py
git diff --cached --name-only | while read f; do git show ":$f" | grep -q $'\r' && echo "CRLF: $f"; done
git commit -F - <<'EOF'
Coordinate one plan per site in Home Assistant

Triggers, bundling, a single call at a time, catch-up after a pause and
the stale-plan issue. The coordinator hangs off runtime_data; if it
fails to start, the forecast keeps running.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 5: Die Dev-Action holt über den Koordinator

**Files:**
- Modify: `custom_components/meteo_volt/dev.py` (vollständig)
- Modify: `custom_components/meteo_volt/services.yaml`

**Interfaces:**
- Consumes: `entry.runtime_data.async_jetzt_planen()` und `entry.runtime_data.was_gilt_jetzt()` aus Task 4; `hass.config_entries.async_loaded_entries(DOMAIN)`.
- Produces: `meteo_volt.dev_plan` antwortet mit `anfrage`, `ausgelassen`, `plan`, `erhalten_um`, `fehler` (`klasse`, `meldung` oder `null`), `letzter_versuch_um` und `jetzt`.

- [ ] **Step 1: `dev.py` vollständig ersetzen**

`custom_components/meteo_volt/dev.py`:

```python
"""Temporaer: eine Action, die sofort einen Plan ueber den Koordinator holt.

Nur fuer die Entwicklung, und sie fliegt wieder raus: dann gehen diese Datei,
ihr Eintrag in services.yaml sowie Import und Aufruf in __init__.py -- bleibt
der Import stehen, laedt die ganze Integration nicht mehr. Registriert wird
sie nur, wenn const_overwrite.json wirkt (siehe overrides.py) -- ein normaler
Nutzer sieht sie nie.

Keine Felder, keine Uebersetzung, keine Entitaet. Die Antwort zeigt den
Planstand und je Fahrzeug, was gerade gilt. Bis C5 schickte sie einen festen
Request (C7-Spec Abschnitt 7).

Spec: meteo-volt-brain/docs/features/C5-standort-koordinator/spec.md, Abschnitt 10
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN

DEV_ACTION = "dev_plan"


def _json(wert: Any) -> Any:
    """datetime als ISO-Text, rekursiv durch dict und list.

    Die Antwort einer Action muss JSON sein, der Planstand traegt Zeitpunkte.
    """
    if isinstance(wert, datetime):
        return wert.isoformat()
    if isinstance(wert, dict):
        return {schluessel: _json(inhalt) for schluessel, inhalt in wert.items()}
    if isinstance(wert, list):
        return [_json(inhalt) for inhalt in wert]
    return wert


def async_dev_action_registrieren(hass: HomeAssistant) -> None:
    """Registriert meteo_volt.dev_plan, einmal je Home-Assistant-Lauf."""
    if hass.services.has_service(DOMAIN, DEV_ACTION):
        return

    async def _plan_holen(call: ServiceCall) -> ServiceResponse:
        koordinatoren = [
            eintrag.runtime_data
            for eintrag in hass.config_entries.async_loaded_entries(DOMAIN)
            if getattr(eintrag, "runtime_data", None) is not None
        ]
        if not koordinatoren:
            raise HomeAssistantError("Kein Standort-Koordinator geladen")
        koordinator = koordinatoren[0]
        stand = await koordinator.async_jetzt_planen()
        fehler = None
        if stand.fehler is not None:
            fehler = {"klasse": type(stand.fehler).__name__, "meldung": str(stand.fehler)}
        return _json(
            {
                "anfrage": stand.anfrage,
                "ausgelassen": stand.ausgelassen,
                "plan": stand.plan,
                "erhalten_um": stand.erhalten_um,
                "fehler": fehler,
                "letzter_versuch_um": stand.letzter_versuch_um,
                "jetzt": koordinator.was_gilt_jetzt(),
            }
        )

    hass.services.async_register(
        DOMAIN, DEV_ACTION, _plan_holen, supports_response=SupportsResponse.ONLY
    )
```

- [ ] **Step 2: Die Beschreibung in `services.yaml`**

In `custom_components/meteo_volt/services.yaml` ersetzen:

```yaml
  description: Temporaer. Schickt einen festen Plan-Request und zeigt die Antwort.
```

durch:

```yaml
  description: Temporaer. Holt sofort einen Plan ueber den Standort-Koordinator und zeigt den Planstand.
```

- [ ] **Step 3: Namen, Suite, Commit**

Run: `.venv/Scripts/python.exe <scratchpad>/ha_namen_pruefen.py`
Expected: `alle 45 Namen in Home Assistant 2026.4.1 gefunden`

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: `244 passed`

```bash
git add custom_components/meteo_volt/dev.py custom_components/meteo_volt/services.yaml
git diff --cached --name-only | while read f; do git show ":$f" | grep -q $'\r' && echo "CRLF: $f"; done
git commit -F - <<'EOF'
Let the dev action fetch through the coordinator

It no longer sends a fixed request. It triggers a plan at once and shows
the held state, including what applies to each vehicle now.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 6: Die Beta

**Files:**
- Modify: `custom_components/meteo_volt/manifest.json`

**Interfaces:**
- Consumes: den Stand nach Task 5.
- Produces: den Prerelease `1.1.0-beta.8` auf dem Commit dieses Tasks.

Die Regeln stehen in `CLAUDE.md`, Abschnitt „Betas gehen über HACS". `gh` ist auf diesem Rechner nicht installiert — das Release entsteht in der GitHub-Oberfläche.

- [ ] **Step 1: Die Version setzen**

In `custom_components/meteo_volt/manifest.json` ersetzen:

```json
  "version": "1.1.0-beta.7"
```

durch:

```json
  "version": "1.1.0-beta.8"
```

- [ ] **Step 2: Suite, Kontrakt, Commit**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: `244 passed`

Run: `.venv/Scripts/python.exe scripts/check_contract.py`
Expected: `Kontrakt in sync (35 Dateien geprueft)`

```bash
git add custom_components/meteo_volt/manifest.json
git diff --cached --name-only | while read f; do git show ":$f" | grep -q $'\r' && echo "CRLF: $f"; done
git commit -F - <<'EOF'
Number this beta 1.1.0-beta.8

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

- [ ] **Step 3: Patrick fragen, dann pushen**

Erst nach seinem Ja, in beiden Repos:

```bash
git ls-remote origin refs/tags/1.1.0-beta.8
git push -u origin c5-standort-koordinator
git rev-parse HEAD
```

Expected: die erste Zeile gibt nichts aus (der Tag ist neu), der Push geht durch, die letzte Zeile nennt den Commit für das Release. Im Brain nur der Push des Branches `c5-standort-koordinator`.

- [ ] **Step 4: Patrick legt das Prerelease an**

In GitHub unter Releases: Tag `1.1.0-beta.8` — GitHub muss ihn als **neu** anzeigen. Target ist der Commit aus Step 3, gewählt unter „Recent commits". „Set as a pre-release" an, „Set as the latest release" aus.

- [ ] **Step 5: Nachmessen**

```bash
git fetch --tags origin
git ls-remote origin refs/tags/1.1.0-beta.8
git show 1.1.0-beta.8:custom_components/meteo_volt/manifest.json | grep '"version"'
```

Expected: der Tag zeigt auf den Commit aus Step 3, das Manifest im Tag nennt `1.1.0-beta.8`. Stimmt eins nicht: Release samt Tag löschen und neu anlegen, solange niemand die Version installiert hat.

---

## Abnahme — macht Patrick

Auf der eigenen Instanz mit Home Assistant 2026.4.1 und `1.1.0-beta.8`. Vorher ist C5 nicht fertig.

**Vorbereitung.** In HACS „Repository-Informationen aktualisieren", `1.1.0-beta.8` herunterladen, Home Assistant neu starten. Für die Schritte mit Log: auf der Seite der Integration „Debug-Logging aktivieren". Zum Umschalten helfen zwei `input_boolean`: einer für einen Template-Binary-Sensor „Angesteckt", einer als Verfügbarkeits-Template eines Template-Sensors für den Ladestand.

1. **Ohne `const_overwrite.json` und ohne Fahrzeug:** die Integration startet, die sechs Sensoren laufen, `meteo_volt.dev_plan` gibt es nicht, und unter Reparaturen steht nichts von Meteo-Volt.
2. **Überschreibung** auf eine Umgebung mit Plan-Route, wie bei C7, dann neu starten. Mit einem Ladepunkt und einem Fahrzeug zeigt `dev_plan` einen Request mit diesem Ladepunkt und einen Plan; `fehler` ist leer.
3. **Zweiter Ladepunkt,** das Fahrzeug ungebunden: der Request trägt den zuerst angelegten. An den zweiten gebunden: den zweiten.
4. **Den gebundenen Ladepunkt löschen:** das Fahrzeug steht unter `ausgelassen` mit `ladepunkt_geloescht`. Danach die Bindung zurücksetzen.
5. **Ladestand nicht lesbar:** Template-Sensor unavailable schalten, `dev_plan` zeigt `ladestand_nicht_lesbar`. Wieder verfügbar schalten: binnen 30 s steht `Plan ladestand: erhalten` im Log.
6. **Einstecken:** Angesteckt auf `on` — binnen 30 s `Plan stecker: erhalten` im Log. Auf `off` — keine solche Zeile.
7. **Fahrzeug ändern,** etwa die Kapazität: binnen 30 s `Plan subentry: erhalten`, und `dev_plan` zeigt den neuen Wert im Request.
8. **Hausanschluss** über Neu konfigurieren eintragen: der Request trägt `site.max_power_kw`. Wieder leeren: das Feld fehlt im Request.
9. **Texte:** Einrichten und Neu konfigurieren zeigen unter dem Hausanschluss den Hinweis, das Fahrzeugformular unter Ladepunkt den neuen. Beides auf Deutsch und Englisch.
10. **Sendepause:** vier `dev_plan` binnen einer Minute — `fehler` ist `PlanRateLimit`. Nach der Pause steht ohne Zutun `Plan nachholen: erhalten` im Log.
11. **Abgelehnt:** Überschreibung auf die `main`-Umgebung, neu starten. Im Log `Plan start: PlanAbgelehnt` und einmal `Kein neuer Ladeplan: PlanAbgelehnt: Status 404; …`, danach eine Stunde lang keine Zeile `Plan grundtakt`.
12. **12-h-Regel:** über Nacht gegen einen nicht erreichbaren Host. Nach 12 h steht unter Reparaturen „Ladeplanung ohne neuen Plan" mit dem Fehler, und `dev_plan` zeigt unter `jetzt` die Quelle `default`. Wieder erreichbar und neu geladen: das Issue ist weg.
13. **Durchgehend:** die sechs Sensoren laufen in allen Schritten weiter.

**Aufräumen:** `const_overwrite.json` löschen, neu starten, Debug-Logging aus.

## Nach der Abnahme

Erst nach Patricks Ja:

- **Brain**, Branch `c5-standort-koordinator`: in `docs/features/C5-standort-koordinator/feature.md` `status = "spezifiziert"` auf `status = "fertig"`, beim Punkt `C5S` ebenso. Dann `meteovolt_plan/.venv/Scripts/python.exe scripts/build_docs.py` und das Gate `meteovolt_plan/.venv/Scripts/python.exe scripts/run_tests.py -q`, Commit.
- **Beide Branches nach `beta` mergen**, im Brain und im ha-Repo, jeweils mit `--no-ff`. Pushen erst nach Rückfrage.

## Was dieser Plan nicht baut

| Nicht hier | Wo |
|---|---|
| Welcher Ladepunkt wann gilt, mehrere Fahrzeuge, die Summe gegen den Hausanschluss | `E1` |
| Die Beschreibung von `Connection` und Basiskontrakt 3.2 | `A5`, Punkt `A5C` |
| Entitäten, Anzeige, der Aufruf von `was_gilt` an jeder Slotgrenze | `C6` |
| `risk` und die übrigen Regler | `C3` |
| Ziele und `meteo_volt.replan` | `C4` |
| Fahrprofil und Abwesenheit | `Z3` |
| Den Plan über einen Neustart retten | offen |
