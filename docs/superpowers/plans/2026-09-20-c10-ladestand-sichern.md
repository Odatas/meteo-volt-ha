# C10 Ladestand sichern — Umsetzungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Jeder Termin bekommt den Haken „Min-SoC sichern“; gesetzt hebt er die Abfahrt auf Min-SoC plus Verbrauch der Fahrt, und das Formular warnt, wenn die Fahrt rechnerisch nicht aufgeht.

**Architecture:** Die Rechnung steht zweimal — in `ladereserve.py` fürs Backend und in `frontend/ladereserve.js` fürs Panel —, und eine Gegenprobe im Gate hält beide zusammen. Der Haken ist ein Bool am Eintrag und an jeder Ausnahme; aus ihm entsteht beim Bauen des Requests ein gewöhnliches `target`. Kontrakt, Planer und Plan-Dienst bleiben unberührt.

**Tech Stack:** Python 3.12 (Home-Assistant-Integration), Plain JavaScript ohne Build (Panel), pytest, `node --test`.

**Spec:** `meteo-volt-brain/docs/features/C10-ladestand-sichern/spec.md`. Bei Widerspruch gilt die Spec, nicht dieser Plan.

## Global Constraints

- **Branch:** `c10-ladestand-sichern`, liegt schon an. Fertig wird nach `beta` gemergt, **niemals** nach `master`.
- **Python:** `.venv/Scripts/python.exe` aus dem Repo-Wurzelverzeichnis. Ein blankes `python` ist der Windows-Store-Alias.
- **Gate:** `.venv/Scripts/python.exe -m pytest tests/ -q` (460 Tests vor C10) und `.venv/Scripts/python.exe scripts/check_contract.py`. Beide müssen am Ende grün sein.
- **Node ≥ 22.12** für `tests/panel/`. Vorhanden: v24.14.0.
- **`custom_components/` ist Endnutzer-Code.** HACS paketiert genau dieses Verzeichnis.
- **Kein Import aus Home Assistant** in `termine.py`, `terminanfrage.py`, `pruefungen.py`, `terminbuch.py`, `ansicht.py` und im neuen `ladereserve.py`. `tests/test_verdrahtung.py` prüft das mit.
- **Kein `/tmp`** für Windows-Python. Unter Git Bash ein MSYS-Pfad, den der Interpreter nicht auflöst.
- **Zeilenenden LF.** Der Arbeitsbaum trägt CRLF, das Repo LF. Geprüft wird am **gestagten Blob**: `git show :<pfad> | grep -c $'\r'` muss 0 sein.
- **Gegenproben ohne Bytecode-Cache:** `PYTHONDONTWRITEBYTECODE=1` setzen, sonst lädt Python bei gleich langer Verfälschung alten Bytecode.
- **Der Feldname auf dem Draht ist `keep_min_soc`**, ein Bool. Die Python-Konstante heißt `SICHERN`.
- **Die drei neuen Schlüssel heißen `fahrt_zu_weit`, `fahrt_unter_min`, `ladestand_offen`.** Jeder steht in `pruefungen.MELDUNGEN`, in `translations/de.json` und `en.json` unter `exceptions`, und mit **wortgleichem** Text in `frontend/texte.js` — `tests/panel/texte.test.mjs` vergleicht beide Seiten.
- **Die Texte** stehen in Spec Abschnitt 5 und werden von dort **wörtlich** übernommen.

---

## File Structure

| Datei | Verantwortung | Task |
|---|---|---|
| `custom_components/meteo_volt/ladereserve.py` | **neu.** Fahrzeugwerte, `fahrt_pct`, `gesichert`, `befund` | 1 |
| `custom_components/meteo_volt/termine.py` | `SICHERN`, `sichern_von`, `Termin.sichern`, `AUSNAHME_FELDER` | 2 |
| `custom_components/meteo_volt/terminbuch.py` | der Haken im neuen Eintrag und in der Ausnahme | 2 |
| `custom_components/meteo_volt/pruefungen.py` | `Werte.sichern`, `werte_pruefen`, die drei Schlüssel, `warnungen` | 2, 4, 5 |
| `custom_components/meteo_volt/terminanfrage.py` | das `target` aus dem höheren der beiden Werte | 3 |
| `custom_components/meteo_volt/terminverwaltung.py` | `_fahrzeugwerte`, die Vorgabe beim Ändern, `standort()` | 3, 4, 6 |
| `custom_components/meteo_volt/aktionen.py`, `services.yaml` | das Action-Feld und sein Selector | 5 |
| `custom_components/meteo_volt/translations/{de,en}.json` | Action-Feld und die drei Schlüssel | 4, 5 |
| `custom_components/meteo_volt/ansicht.py` | `keep_min_soc` am Termin | 6 |
| `custom_components/meteo_volt/frontend/ladereserve.js` | **neu.** Zwilling von `ladereserve.py` | 7 |
| `custom_components/meteo_volt/frontend/pruefung.js` | Orte und Warnung am Platz „Ladestand“ | 8 |
| `custom_components/meteo_volt/frontend/texte.js` | fünf neue Texte in de und en | 8 |
| `custom_components/meteo_volt/frontend/dialoge.js` | der Haken und die Hinweiszeile im Formular | 9 |

---

## Task 1: Die Rechnung — `ladereserve.py`

**Files:**
- Create: `custom_components/meteo_volt/ladereserve.py`
- Create: `tests/test_ladereserve.py`

**Interfaces:**
- Consumes: nichts
- Produces: `Fahrzeugwerte(soc_min_pct: float, capacity_kwh: float, consumption_kwh_per_100km: float)`; `fahrt_pct(strecke_km: float, werte: Fahrzeugwerte) -> float`; `gesichert(strecke_km: float, werte: Fahrzeugwerte) -> float`; `befund(strecke_km: float, ladestand: float | None, sichern: bool, werte: Fahrzeugwerte) -> str | None`; die Konstanten `FAHRT_ZU_WEIT`, `FAHRT_UNTER_MIN`, `LADESTAND_OFFEN`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_ladereserve.py`:

```python
"""Prueft die Rechnung hinter dem Haken, ohne Home Assistant. Spec C10 Abschnitte 2 und 5.

Die Zahlen stammen aus den Fahrzeug-Defaults: 58 kWh, 19,5 kWh/100 km,
Min-SoC 15 %. 175 km kosten damit 58,8 Prozentpunkte.

Was dieser Test NICHT sieht: ob das Panel dieselbe Zahl rechnet. Das ist die
Gegenprobe in tests/test_panel.py.
"""

import importlib
import sys
import types
from pathlib import Path

INTEGRATION = Path(__file__).resolve().parents[1] / "custom_components" / "meteo_volt"

_PAKET = "meteo_volt_c3"
if _PAKET not in sys.modules:
    _paket = types.ModuleType(_PAKET)
    _paket.__path__ = [str(INTEGRATION)]
    sys.modules[_PAKET] = _paket
ladereserve = importlib.import_module(f"{_PAKET}.ladereserve")

AUTO = ladereserve.Fahrzeugwerte(soc_min_pct=15.0, capacity_kwh=58.0, consumption_kwh_per_100km=19.5)


def test_die_fahrt_kostet_km_mal_verbrauch_durch_kapazitaet():
    assert ladereserve.fahrt_pct(175, AUTO) == 175 * 19.5 / 58.0
    assert ladereserve.fahrt_pct(0, AUTO) == 0.0


def test_gesichert_ist_min_soc_plus_fahrt_aufgerundet():
    # 15 + 58.836... = 73.836..., aufgerundet 74
    assert ladereserve.gesichert(175, AUTO) == 74.0


def test_gesichert_rundet_auf_und_nicht_ab():
    schmal = ladereserve.Fahrzeugwerte(soc_min_pct=15.0, capacity_kwh=100.0, consumption_kwh_per_100km=10.0)
    # 15 + 10.1 = 25.1, abgerundet waere 25 und damit unter der Zusage
    assert ladereserve.gesichert(101, schmal) == 26.0


def test_gesichert_endet_bei_hundert():
    assert ladereserve.gesichert(400, AUTO) == 100.0


def test_bei_null_kilometern_ist_gesichert_der_min_soc():
    assert ladereserve.gesichert(0, AUTO) == 15.0


def test_ohne_haken_und_ohne_ziel_ist_der_ladestand_offen():
    assert ladereserve.befund(42, None, False, AUTO) == ladereserve.LADESTAND_OFFEN


def test_ein_ladestand_unter_dem_min_soc_ist_kein_ziel():
    assert ladereserve.befund(42, 10, False, AUTO) == ladereserve.LADESTAND_OFFEN


def test_ein_zu_kleines_eigenes_ziel_zieht_unter_den_min_soc():
    # 40 - 58.8 liegt unter 15
    assert ladereserve.befund(175, 40, False, AUTO) == ladereserve.FAHRT_UNTER_MIN


def test_ein_grosses_eigenes_ziel_reicht():
    assert ladereserve.befund(175, 100, False, AUTO) is None


def test_der_haken_allein_genuegt():
    assert ladereserve.befund(175, None, True, AUTO) is None


def test_auch_voll_geladen_reicht_es_nicht():
    # 400 km kosten 134,5 Punkte, zwischen 100 und 15 liegen 85
    assert ladereserve.befund(400, None, True, AUTO) == ladereserve.FAHRT_ZU_WEIT
    assert ladereserve.befund(400, 100, False, AUTO) == ladereserve.FAHRT_ZU_WEIT


def test_genau_aufgehend_warnt_nicht():
    genau = ladereserve.Fahrzeugwerte(soc_min_pct=15.0, capacity_kwh=100.0, consumption_kwh_per_100km=100.0)
    # 85 km kosten genau 85 Punkte: 100 - 85 == 15, der Min-SoC ist erreicht
    assert ladereserve.befund(85, 100, False, genau) is None
    assert ladereserve.befund(85.1, 100, False, genau) == ladereserve.FAHRT_ZU_WEIT
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ladereserve.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'meteo_volt_c3.ladereserve'`

- [ ] **Step 3: Write the implementation**

Create `custom_components/meteo_volt/ladereserve.py`:

```python
"""Der gesicherte Ladestand eines Termins, ohne Home Assistant. Spec C10 Abschnitte 2 und 5.

Dieses Modul importiert bewusst NICHTS aus Home Assistant und nichts aus
aiohttp. Aus Strecke, Kapazitaet und Verbrauch rechnet es, was eine Fahrt an
Ladestand kostet und auf welchen Wert der Haken "Min-SoC sichern" die Abfahrt
hebt. Was daraus im Request wird, steht in terminanfrage.py, was das Formular
davon zeigt, in pruefungen.py und im Panel.

Dieselbe Rechnung steht im Panel in frontend/ladereserve.js. Die Gegenprobe
in tests/test_panel.py haelt beide zusammen: zwei Implementierungen derselben
Formel driften sonst auseinander, ohne dass eine Pruefung rot wird.

Spec: meteo-volt-brain/docs/features/C10-ladestand-sichern/spec.md, Abschnitte 2 und 5
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Die Schluessel der Warnungen, Spec Abschnitt 5. pruefungen.py reicht sie
# als translation_key weiter, das Panel zeigt sie am Platz "Ladestand".
FAHRT_ZU_WEIT = "fahrt_zu_weit"
FAHRT_UNTER_MIN = "fahrt_unter_min"
LADESTAND_OFFEN = "ladestand_offen"


@dataclass(frozen=True)
class Fahrzeugwerte:
    """Was die Rechnung vom Fahrzeug braucht. Alle drei sind Pflicht und > 0 (C1-C2)."""

    soc_min_pct: float
    capacity_kwh: float
    consumption_kwh_per_100km: float


def fahrt_pct(strecke_km: float, werte: Fahrzeugwerte) -> float:
    """Was eine Fahrt an Ladestand kostet, in Prozentpunkten.

    kWh = km * consumption_kwh_per_100km / 100, wie der Planer in
    meteovolt_planner/consumption.py; geteilt durch die Kapazitaet und mal
    100 kuerzt sich die Hundert weg. Ohne Wirkungsgrad: der gilt beim Laden,
    nicht beim Fahren.
    """
    return strecke_km * werte.consumption_kwh_per_100km / werte.capacity_kwh


def gesichert(strecke_km: float, werte: Fahrzeugwerte) -> float:
    """Der Ladestand, auf den der Haken die Abfahrt hebt: Min-SoC plus Fahrt.

    Aufgerundet auf ganze Prozent, weil das Feld "Ladestand bei Abfahrt" ganze
    Prozent traegt und Abrunden die Zusage um bis zu einen Punkt unterliefe.
    Gedeckelt bei 100, weil target_soc_pct dort endet -- NICHT bei
    soc_max_pct: ein Ziel wird nie gekappt, es hebt die Decke fuer seinen
    Zeitraum an (Basiskontrakt 3.3).
    """
    return float(min(100, math.ceil(werte.soc_min_pct + fahrt_pct(strecke_km, werte))))


def befund(
    strecke_km: float, ladestand: float | None, sichern: bool, werte: Fahrzeugwerte
) -> str | None:
    """Der Schluessel der Warnung zur Fahrt, oder None. Spec Abschnitt 5.

    Der Bezugswert ist der Ladestand, den der Plan fuer die Abfahrt zusagt:
    mit Haken der gesicherte Wert, sonst das eigene Ziel ab Min-SoC. Steht
    keiner von beiden, ist nichts zugesagt.

    soc_max_pct ist ausdruecklich KEIN Bezugswert. Dass der Planer heute vor
    der ersten Fahrt dorthin laedt (first_need), faellt mit A6E weg -- eine
    Warnung, die sich darauf stuetzt, waere danach still falsch.
    """
    fahrt = fahrt_pct(strecke_km, werte)
    if fahrt > 100 - werte.soc_min_pct:
        return FAHRT_ZU_WEIT  # auch voll geladen reicht es nicht; der Haken hilft hier nicht
    if sichern:
        bezug = gesichert(strecke_km, werte)
    elif ladestand is not None and ladestand >= werte.soc_min_pct:
        bezug = ladestand
    else:
        return LADESTAND_OFFEN
    return FAHRT_UNTER_MIN if bezug - fahrt < werte.soc_min_pct else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ladereserve.py -q`
Expected: PASS, 12 passed

- [ ] **Step 5: Commit**

```bash
git add custom_components/meteo_volt/ladereserve.py tests/test_ladereserve.py
git commit -m "Add the arithmetic behind the minimum-SoC tick"
```

---

## Task 2: Der Haken am Termin und im Store

**Files:**
- Modify: `custom_components/meteo_volt/termine.py` (Feldkonstanten, `AUSNAHME_FELDER`, `Termin`, `termin_am`)
- Modify: `custom_components/meteo_volt/terminbuch.py` (`_neuer_eintrag`, `_ausnahme`)
- Modify: `custom_components/meteo_volt/pruefungen.py` (`Werte`, `werte_pruefen`)
- Modify: `tests/test_termine.py`, `tests/test_terminbuch.py`

**Interfaces:**
- Consumes: nichts aus Task 1
- Produces: `termine.SICHERN == "keep_min_soc"`; `termine.sichern_von(werte: dict) -> bool`; `Termin.sichern: bool`; `pruefungen.Werte.sichern: bool`; `werte_pruefen(..., vorgabe_sichern: bool = True)`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_termine.py`:

```python
def test_ein_eintrag_ohne_das_feld_hat_den_haken_nicht_gesetzt():
    """Spec C10 Abschnitt 8: bestehende Termine planen wie vorher."""
    eintrag = {"id": "e1", "vehicle": "auto-1", "departure": "2026-09-17T08:00:00",
               "duration_min": 600, "repeat": "once", "distance_km": 42, "driver": None,
               "soc": None, "until": None, "exceptions": {}}
    termin = termine.termin_am(eintrag, date(2026, 9, 17), BERLIN)
    assert termin.sichern is False


def test_der_haken_des_eintrags_steht_am_termin():
    eintrag = {"id": "e1", "vehicle": "auto-1", "departure": "2026-09-17T08:00:00",
               "duration_min": 600, "repeat": "daily", "distance_km": 42, "driver": None,
               "soc": None, "keep_min_soc": True, "until": None, "exceptions": {}}
    assert termine.termin_am(eintrag, date(2026, 9, 17), BERLIN).sichern is True


def test_eine_ausnahme_traegt_ihren_eigenen_haken():
    eintrag = {"id": "e1", "vehicle": "auto-1", "departure": "2026-09-17T08:00:00",
               "duration_min": 600, "repeat": "daily", "distance_km": 42, "driver": None,
               "soc": None, "keep_min_soc": True, "until": None,
               "exceptions": {"2026-09-18": {"departure": "2026-09-18T08:00:00", "duration_min": 600,
                                             "distance_km": 42, "driver": None, "soc": None,
                                             "keep_min_soc": False}}}
    assert termine.termin_am(eintrag, date(2026, 9, 17), BERLIN).sichern is True
    assert termine.termin_am(eintrag, date(2026, 9, 18), BERLIN).sichern is False


def test_eine_ausnahme_aus_der_zeit_vor_c10_hat_den_haken_nicht_gesetzt():
    eintrag = {"id": "e1", "vehicle": "auto-1", "departure": "2026-09-17T08:00:00",
               "duration_min": 600, "repeat": "daily", "distance_km": 42, "driver": None,
               "soc": None, "keep_min_soc": True, "until": None,
               "exceptions": {"2026-09-18": {"departure": "2026-09-18T08:00:00", "duration_min": 600,
                                             "distance_km": 42, "driver": None, "soc": None}}}
    assert termine.termin_am(eintrag, date(2026, 9, 18), BERLIN).sichern is False
```

Wenn `date` oder `BERLIN` in `tests/test_termine.py` anders heißen, die dortigen Namen verwenden — nichts umbenennen.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_termine.py -q -k haken`
Expected: FAIL — `AttributeError: 'Termin' object has no attribute 'sichern'`

- [ ] **Step 3: Implement in `termine.py`**

Bei den Feldkonstanten, nach `LADESTAND = "soc"`:

```python
SICHERN = "keep_min_soc"  # der Haken "Min-SoC sichern", Spec C10 Abschnitt 3
```

`AUSNAHME_FELDER` erweitern:

```python
AUSNAHME_FELDER = (ABFAHRT, DAUER, STRECKE, FAHRER, LADESTAND, SICHERN)
```

Direkt darunter:

```python
def sichern_von(werte: dict) -> bool:
    """Der Haken eines Eintrags oder einer Ausnahme; fehlt er, ist er nicht gesetzt.

    Ein Eintrag aus der Zeit vor C10 traegt das Feld nicht und plant weiter
    wie bisher (C10-Spec Abschnitt 8). Kein Default True: das aenderte den
    Plan bestehender Termine, ohne dass jemand etwas angefasst haette.
    """
    return bool(werte.get(SICHERN, False))
```

`Termin` um ein Feld ergänzen, hinter `geaendert`:

```python
    geaendert: bool  # eine geaenderte Ausnahme
    sichern: bool  # der Haken "Min-SoC sichern", Spec C10 Abschnitt 3
```

In `termin_am` den Aufbau von `werte` und den Aufruf ändern:

```python
    werte = (eintrag.get(AUSNAHMEN) or {}).get(datum.isoformat())
    if werte is None:
        # SICHERN getrennt: ein Eintrag von vor C10 traegt das Feld nicht,
        # die uebrigen Felder sind Pflicht und sollen laut fehlen.
        werte = {feld: eintrag[feld] for feld in AUSNAHME_FELDER if feld != SICHERN}
        werte[SICHERN] = sichern_von(eintrag)
        werte[ABFAHRT] = datum.isoformat() + eintrag[ABFAHRT][10:]
        geaendert = False
    else:
        geaendert = True
```

und am Ende des `Termin(...)`-Aufrufs:

```python
        geaendert=geaendert,
        sichern=sichern_von(werte),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_termine.py -q`
Expected: PASS

- [ ] **Step 5: Implement in `terminbuch.py`**

Den Import erweitern:

```python
from .termine import (
    ABFAHRT, AUSNAHMEN, BIS, DAUER, EINMALIG, FAHRER, FAHRZEUG, ID, LADESTAND, SICHERN, STRECKE,
    WIEDERHOLUNG,
)
```

`_neuer_eintrag` und `_ausnahme` tragen den Haken:

```python
def _neuer_eintrag(kennung: str, werte: Werte) -> dict:
    return {
        ID: kennung,
        FAHRZEUG: werte.fahrzeug,
        ABFAHRT: werte.abfahrt,
        DAUER: werte.dauer_min,
        WIEDERHOLUNG: werte.wiederholung,
        STRECKE: werte.strecke_km,
        FAHRER: werte.fahrer,
        LADESTAND: werte.ladestand,
        SICHERN: werte.sichern,
        BIS: None,
        AUSNAHMEN: {},
    }


def _ausnahme(werte: Werte) -> dict:
    return {ABFAHRT: werte.abfahrt, DAUER: werte.dauer_min, STRECKE: werte.strecke_km,
            FAHRER: werte.fahrer, LADESTAND: werte.ladestand, SICHERN: werte.sichern}
```

- [ ] **Step 6: Implement in `pruefungen.py`**

`Werte` bekommt ein Feld:

```python
@dataclass(frozen=True)
class Werte:
    """Die geprueften Werte eines Termins, so wie der Store sie traegt."""

    fahrzeug: str
    abfahrt: str  # lokal, ISO 8601 ohne Offset
    dauer_min: int
    wiederholung: str
    strecke_km: int
    fahrer: str | None
    ladestand: float | None
    sichern: bool
```

`werte_pruefen` bekommt eine Vorgabe und liest das Feld:

```python
def werte_pruefen(
    felder: dict,
    fahrzeug: str,
    jetzt: datetime,
    tz: tzinfo,
    vorgabe_wiederholung: str = termine.EINMALIG,
    vorgabe_sichern: bool = True,
) -> Werte:
```

Im Docstring hinter dem Satz zu `repeat`:

```
    Fehlt keep_min_soc, gilt vorgabe_sichern -- beim Anlegen True, beim
    Aendern der bisherige Wert des Termins (C10-Spec Abschnitt 8). Sonst
    naehme ein Aendern ohne das Feld einem Termin still seine Sicherung.
```

Im `return Werte(...)` als letzte Zeile:

```python
        sichern=vorgabe_sichern if felder.get(termine.SICHERN) is None else bool(felder[termine.SICHERN]),
```

- [ ] **Step 7: Fix the store test helper**

In `tests/test_terminbuch.py` das lokale `_ausnahme(...)` um das Feld ergänzen, damit die erwarteten Ausnahme-Dicts wieder stimmen. Die vorhandene Fassung suchen (`def _ausnahme(`) und `"keep_min_soc": True` in das zurückgegebene Dict aufnehmen — `True`, weil `werte_pruefen` ohne das Feld beim Anlegen `True` liefert und die Tests dort ihre Werte bauen. Weicht ein einzelner Test davon ab, dort den erwarteten Wert setzen statt den Helfer zu verbiegen.

- [ ] **Step 8: Run the whole suite**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: PASS. Schlägt etwas fehl, liegt es fast sicher an einem erwarteten Eintrags-Dict ohne `keep_min_soc` — dort den Wert ergänzen, nicht die Quelle ändern.

- [ ] **Step 9: Commit**

```bash
git add custom_components/meteo_volt/termine.py custom_components/meteo_volt/terminbuch.py custom_components/meteo_volt/pruefungen.py tests/test_termine.py tests/test_terminbuch.py
git commit -m "Carry the minimum-SoC tick on the appointment and in the store"
```

---

## Task 3: Das Ziel im Request

**Files:**
- Modify: `custom_components/meteo_volt/terminanfrage.py` (`fragmente`)
- Modify: `custom_components/meteo_volt/terminverwaltung.py` (`_soc_min` → `_fahrzeugwerte`, `fragmente`, `async_aendern`)
- Modify: `tests/test_terminanfrage.py`

**Interfaces:**
- Consumes: `ladereserve.Fahrzeugwerte`, `ladereserve.gesichert` (Task 1); `termine.Termin.sichern` (Task 2)
- Produces: `terminanfrage.fragmente(termine: list[Termin], fahrzeuge: dict[str, ladereserve.Fahrzeugwerte], jetzt: datetime) -> dict[str, dict]`; `Terminverwaltung._fahrzeugwerte() -> dict[str, ladereserve.Fahrzeugwerte]`

- [ ] **Step 1: Write the failing test**

In `tests/test_terminanfrage.py` zuerst die beiden Helfer anpassen:

```python
ladereserve = importlib.import_module(f"{_PAKET}.ladereserve")

AUTO = ladereserve.Fahrzeugwerte(soc_min_pct=15.0, capacity_kwh=58.0, consumption_kwh_per_100km=19.5)


def _eintrag(eintrag_id, abfahrt, dauer=600, soc=None, fahrzeug="auto-1", wiederholung="once",
             sichern=False, km=42):
    return {"id": eintrag_id, "vehicle": fahrzeug, "departure": abfahrt, "duration_min": dauer,
            "repeat": wiederholung, "distance_km": km, "driver": None, "soc": soc,
            "keep_min_soc": sichern, "until": None, "exceptions": {}}


def _fragmente(*eintraege, fahrzeuge=None):
    auswahl = termine.ausrollen(list(eintraege), BERLIN, JETZT, BIS)
    return terminanfrage.fragmente(auswahl, fahrzeuge or {"auto-1": AUTO}, JETZT)
```

Jedes vorhandene `_fragmente(..., soc_min={...})` auf `fahrzeuge={...}` umstellen, mit
`ladereserve.Fahrzeugwerte(soc_min_pct=..., capacity_kwh=58.0, consumption_kwh_per_100km=19.5)`
statt der blanken Zahl. Danach anhängen:

```python
def _ziel(teil):
    return next((a for a in teil.get("constraints", []) if a["type"] == "target"), None)


def test_der_haken_hebt_die_abfahrt_auf_min_soc_plus_fahrt():
    # 175 km kosten 58,8 Punkte, 15 + 58,8 aufgerundet sind 74
    teil = _fragmente(_eintrag("e1", "2026-09-17T08:00:00", sichern=True, km=175))["auto-1"]
    assert _ziel(teil)["target_soc_pct"] == 74.0
    assert _ziel(teil)["id"] == "e1/2026-09-17/ziel"


def test_ohne_haken_und_ohne_ladestand_entsteht_kein_ziel():
    teil = _fragmente(_eintrag("e1", "2026-09-17T08:00:00", km=175))["auto-1"]
    assert _ziel(teil) is None


def test_von_beiden_werten_gilt_der_hoehere():
    hoch = _fragmente(_eintrag("e1", "2026-09-17T08:00:00", sichern=True, km=175, soc=100))["auto-1"]
    assert _ziel(hoch)["target_soc_pct"] == 100.0
    niedrig = _fragmente(_eintrag("e1", "2026-09-17T08:00:00", sichern=True, km=175, soc=40))["auto-1"]
    assert _ziel(niedrig)["target_soc_pct"] == 74.0


def test_ein_ladestand_unter_dem_min_soc_bleibt_auch_mit_haken_ignoriert():
    teil = _fragmente(_eintrag("e1", "2026-09-17T08:00:00", sichern=True, km=42, soc=10))["auto-1"]
    # 15 + 14,1 aufgerundet sind 30; die 10 zaehlen nicht mit
    assert _ziel(teil)["target_soc_pct"] == 30.0


def test_das_gesicherte_ziel_endet_bei_hundert():
    teil = _fragmente(_eintrag("e1", "2026-09-17T08:00:00", sichern=True, km=400))["auto-1"]
    assert _ziel(teil)["target_soc_pct"] == 100.0


def test_bei_null_kilometern_sichert_der_haken_den_min_soc():
    teil = _fragmente(_eintrag("e1", "2026-09-17T08:00:00", sichern=True, km=0))["auto-1"]
    assert _ziel(teil)["target_soc_pct"] == 15.0


def test_eine_abfahrt_in_der_vergangenheit_bekommt_auch_mit_haken_kein_ziel():
    teil = _fragmente(_eintrag("e1", "2026-09-16T08:00:00", sichern=True, km=175))["auto-1"]
    assert _ziel(teil) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_terminanfrage.py -q`
Expected: FAIL — `AttributeError: 'dict' object has no attribute 'soc_min_pct'` oder `KeyError`

- [ ] **Step 3: Implement in `terminanfrage.py`**

Den Import ergänzen:

```python
from . import ladereserve
from .termine import Termin, utc
```

`fragmente` ersetzen:

```python
def fragmente(
    termine: list[Termin], fahrzeuge: dict[str, ladereserve.Fahrzeugwerte], jetzt: datetime
) -> dict[str, dict]:
    """consumption und constraints je Fahrzeug.

    termine sind schon ausgewaehlt: Rueckkehr nach jetzt, Abfahrt vor dem Ende
    des Ausrollens. fahrzeuge nennt jedes Fahrzeug des Standorts mit seinen
    Werten; jedes bekommt trips, ohne Termin als leere Liste. constraints
    fehlt, wenn es leer waere.
    """
    ergebnis: dict[str, dict] = {
        fahrzeug: {"consumption": {"type": "trips", "trips": []}} for fahrzeug in fahrzeuge
    }
    for termin in termine:
        teil = ergebnis.get(termin.fahrzeug)
        if teil is None:
            continue
        werte = fahrzeuge[termin.fahrzeug]
        auflagen = teil.setdefault("constraints", [])
        # Immer: laeuft der Termin schon, liegt from in der Vergangenheit.
        auflagen.append({
            "type": "unavailable",
            "id": kennung(termin.eintrag, termin.datum, WEG),
            "from": termin.abfahrt.isoformat(),
            "to": termin.rueckkehr.isoformat(),
        })
        if utc(termin.abfahrt) <= utc(jetzt):
            continue  # R4: vergangener Verbrauch steckt im gemessenen Ladestand
        teil["consumption"]["trips"].append(
            {"departure": termin.abfahrt.isoformat(), "km": float(termin.strecke_km)})
        ziel = _ziel(termin, werte)
        if ziel is not None:
            auflagen.append({
                "type": "target",
                "id": kennung(termin.eintrag, termin.datum, ZIEL),
                "deadline": termin.abfahrt.isoformat(),
                "target_soc_pct": ziel,
            })
    return ergebnis


def _ziel(termin: Termin, werte: ladereserve.Fahrzeugwerte) -> float | None:
    """Der hoehere von eigenem und gesichertem Ziel, oder None. Spec C10 Abschnitt 4.

    Das eigene Ziel gilt unveraendert erst ab dem Min-SoC (C3-Spec 4): der
    Haken hebt das Ziel, er rettet den zu kleinen Wert nicht. Es gibt nur ein
    target je Termin -- zwei mit derselben Deadline waeren zwei Decken, von
    denen die niedrigere das Laden davor begrenzt (Basiskontrakt 3.3).
    """
    kandidaten = []
    if termin.ladestand is not None and termin.ladestand >= werte.soc_min_pct:
        kandidaten.append(float(termin.ladestand))
    if termin.sichern:
        kandidaten.append(ladereserve.gesichert(termin.strecke_km, werte))
    return max(kandidaten) if kandidaten else None
```

Im Modul-Docstring den Satz zum Ziel ersetzen:

```
Aus jedem Termin wird eine Abwesenheit, aus einem kuenftigen eine Fahrt in
consumption.trips (A5-Spec Abschnitt 2), und traegt er einen Ladestand ab dem
Min-SoC oder den Haken "Min-SoC sichern", ein Ziel (C10-Spec Abschnitt 4).
```

- [ ] **Step 4: Implement the plumbing in `terminverwaltung.py`**

Den Import ergänzen: `from . import ladereserve` (zu den vorhandenen relativen Importen).

`_soc_min` ersetzen durch:

```python
    def _fahrzeugwerte(self) -> dict[str, ladereserve.Fahrzeugwerte]:
        """Je Fahrzeug, was die Rechnung hinter dem Haken braucht. Spec C10 Abschnitt 2."""
        return {
            fid: ladereserve.Fahrzeugwerte(
                soc_min_pct=float(daten[stammdaten.FELD_SOC_MIN]),
                capacity_kwh=float(daten[stammdaten.FELD_KAPAZITAET]),
                consumption_kwh_per_100km=float(daten[stammdaten.FELD_VERBRAUCH]),
            )
            for fid, daten in self.fahrzeugdaten().items()
        }

    def _soc_min(self) -> dict[str, float]:
        return {fid: werte.soc_min_pct for fid, werte in self._fahrzeugwerte().items()}
```

`fragmente` übergibt die neuen Werte:

```python
        return terminanfrage.fragmente(auswahl, self._fahrzeugwerte(), jetzt), self.risiko
```

In `async_aendern` die Vorgabe des Hakens aus dem bearbeiteten Termin nehmen:

```python
        eintrag = self.buch.eintraege[eintrag_id]
        if not termine.hat_termin(eintrag, datum):
            raise pruefungen.fehler(pruefungen.TERMIN_UNBEKANNT, "date")
        jetzt = dt_util.utcnow()
        # Fehlt repeat, bleibt die Wiederholung. once waere hier eine stille Aenderung.
        # Fehlt keep_min_soc, bleibt der Haken dieses Termins -- aus der Ausnahme,
        # wenn es eine gibt, sonst aus dem Eintrag (C10-Spec Abschnitt 8).
        vorher = termine.termin_am(eintrag, datum, self.zeitzone())
        werte = pruefungen.werte_pruefen(
            felder, fahrzeug_id, jetzt, self.zeitzone(), eintrag[termine.WIEDERHOLUNG],
            vorgabe_sichern=vorher.sichern)
```

- [ ] **Step 5: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_terminanfrage.py tests/test_standort.py -q`
Expected: PASS

- [ ] **Step 6: Run the whole suite**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add custom_components/meteo_volt/terminanfrage.py custom_components/meteo_volt/terminverwaltung.py tests/test_terminanfrage.py
git commit -m "Turn the tick into a target when the request is built"
```

---

## Task 4: Die drei Warnungen im Backend

**Files:**
- Modify: `custom_components/meteo_volt/pruefungen.py` (Schlüssel, `MELDUNGEN`, `warnungen`)
- Modify: `custom_components/meteo_volt/terminverwaltung.py` (`_warnungen`)
- Modify: `custom_components/meteo_volt/translations/de.json`, `en.json`
- Modify: `tests/test_pruefungen.py`

**Interfaces:**
- Consumes: `ladereserve.befund`, `ladereserve.Fahrzeugwerte` (Task 1); `Werte.sichern` (Task 2); `_fahrzeugwerte` (Task 3)
- Produces: `pruefungen.warnungen(werte, eintrag_id, eintraege, tz, jetzt, fahrzeug: ladereserve.Fahrzeugwerte, personen, titel, sprache) -> list[Meldung]` — **`soc_min: float` ist durch `fahrzeug` ersetzt**

- [ ] **Step 1: Write the failing test**

In `tests/test_pruefungen.py` den Helfer anpassen und Tests anhängen. Der vorhandene `_warnungen` übergibt `soc_min`; er bekommt stattdessen Fahrzeugwerte:

```python
ladereserve = importlib.import_module(f"{_PAKET}.ladereserve")

AUTO = ladereserve.Fahrzeugwerte(soc_min_pct=15.0, capacity_kwh=58.0, consumption_kwh_per_100km=19.5)
```

Im vorhandenen `_warnungen(werte, eintraege, sprache="de")` das Argument `15.0` (oder wie es dort heißt) durch `AUTO` ersetzen. Dann anhängen:

```python
def test_ohne_haken_und_ohne_ziel_ist_der_ladestand_offen():
    (meldung,) = _warnungen(_pruefen(keep_min_soc=False), [])
    assert (meldung.schluessel, meldung.feld) == ("ladestand_offen", "soc")
    assert meldung.platzhalter == {}


def test_der_haken_allein_warnt_nicht():
    assert _warnungen(_pruefen(keep_min_soc=True), []) == []


def test_ein_zu_kleines_eigenes_ziel_warnt():
    werte = _pruefen(keep_min_soc=False, soc=40, distance_km=175)
    (meldung,) = _warnungen(werte, [])
    assert (meldung.schluessel, meldung.feld) == ("fahrt_unter_min", "soc")
    assert meldung.platzhalter == {"min": "15"}


def test_eine_zu_weite_fahrt_warnt_auch_mit_haken():
    werte = _pruefen(keep_min_soc=True, distance_km=400)
    (meldung,) = _warnungen(werte, [])
    assert (meldung.schluessel, meldung.feld) == ("fahrt_zu_weit", "soc")
    assert meldung.platzhalter == {"km": "400"}


def test_der_zu_kleine_ladestand_steht_vor_dem_offenen():
    """Spec C10 Abschnitt 5: wer die Zahl hebt, hat wieder ein Ziel."""
    (meldung,) = _warnungen(_pruefen(keep_min_soc=False, soc=10), [])
    assert meldung.schluessel == "ladestand_unter_min"


def test_am_platz_ladestand_steht_hoechstens_eine_warnung():
    werte = _pruefen(keep_min_soc=False, soc=10, distance_km=400)
    meldungen = [m for m in _warnungen(werte, []) if m.feld == "soc"]
    assert [m.schluessel for m in meldungen] == ["fahrt_zu_weit"]
```

Falls `_pruefen` die Felder nicht durchreicht: Es baut über `_felder(**felder)`, das jedes Schlüsselwort in das Feld-Dict legt — `keep_min_soc=` und `distance_km=` kommen damit an.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_pruefungen.py -q`
Expected: FAIL — `TypeError: warnungen() got an unexpected keyword argument` oder eine leere Meldungsliste

- [ ] **Step 3: Implement in `pruefungen.py`**

Den Import ergänzen:

```python
from . import ladereserve, termine
```

Bei den Schlüsseln, hinter `LADESTAND_UNTER_MIN`:

```python
# Die drei aus C10 stehen in ladereserve.py: dort entscheidet die Rechnung,
# welcher gilt, und das Panel spiegelt dieselbe Reihenfolge.
FAHRT_ZU_WEIT = ladereserve.FAHRT_ZU_WEIT
FAHRT_UNTER_MIN = ladereserve.FAHRT_UNTER_MIN
LADESTAND_OFFEN = ladereserve.LADESTAND_OFFEN
```

In `MELDUNGEN` hinter `LADESTAND_UNTER_MIN: ("min",),`:

```python
    FAHRT_ZU_WEIT: ("km",),
    FAHRT_UNTER_MIN: ("min",),
    LADESTAND_OFFEN: (),
```

`warnungen` umbauen — Signatur und der Block zum Ladestand:

```python
def warnungen(
    werte: Werte,
    eintrag_id: str,
    eintraege: list[dict],
    tz: tzinfo,
    jetzt: datetime,
    fahrzeug: ladereserve.Fahrzeugwerte,
    personen: dict[str, str],
    titel: dict[str, str],
    sprache: str,
) -> list[Meldung]:
    """Die Warnungen nach dem Speichern. Gespeichert ist trotzdem.

    eintrag_id traegt die neuen Werte, eintraege ist der Stand danach.
    personen bildet jede person-Entitaet auf ihren Namen ab, titel jedes
    Fahrzeug auf seinen Titel.

    Am Platz "soc" steht hoechstens eine Warnung, in der Reihenfolge aus
    C10-Spec Abschnitt 5. Das Panel zeigt dort nur eine; kaeme hier mehr als
    eine an, entschiede die Reihenfolge der Liste statt der Spec.
    """
    meldungen = []
    min_text = zahl_text(fahrzeug.soc_min_pct, sprache)
    befund = ladereserve.befund(werte.strecke_km, werte.ladestand, werte.sichern, fahrzeug)
    if befund == FAHRT_ZU_WEIT:
        meldungen.append(Meldung(FAHRT_ZU_WEIT, "soc", {"km": str(werte.strecke_km)}))
    elif befund == FAHRT_UNTER_MIN:
        meldungen.append(Meldung(FAHRT_UNTER_MIN, "soc", {"min": min_text}))
    elif werte.ladestand is not None and werte.ladestand < fahrzeug.soc_min_pct:
        meldungen.append(Meldung(LADESTAND_UNTER_MIN, "soc", {"min": min_text}))
    elif befund == LADESTAND_OFFEN:
        meldungen.append(Meldung(LADESTAND_OFFEN, "soc"))
    if werte.fahrer in personen:
```

Der Rest der Funktion (der Fahrer-Block und `return meldungen`) bleibt unverändert.

- [ ] **Step 4: Implement the caller in `terminverwaltung.py`**

Im `_warnungen`-Helfer `self._soc_min()[werte.fahrzeug]` durch `self._fahrzeugwerte()[werte.fahrzeug]` ersetzen.

- [ ] **Step 5: Add the texts to the translations**

In `custom_components/meteo_volt/translations/de.json` unter `exceptions`, hinter `ladestand_unter_min`:

```json
    "fahrt_zu_weit": { "message": "Auch voll geladen reicht es nicht für {km} km — unterwegs laden." },
    "fahrt_unter_min": { "message": "Die Fahrt zieht den Ladestand unter den Min-SoC von {min} %." },
    "ladestand_offen": { "message": "Ohne Haken und ohne Ziel ist der Ladestand bei der Abfahrt nicht zugesagt." },
```

In `en.json` an derselben Stelle:

```json
    "fahrt_zu_weit": { "message": "Even fully charged it is not enough for {km} km — charge on the way." },
    "fahrt_unter_min": { "message": "The trip pulls the state of charge below the minimum of {min} %." },
    "ladestand_offen": { "message": "Without the tick and without a target the state of charge at departure is not promised." },
```

Die Einrückung der Nachbarzeilen übernehmen. Beide Dateien sind JSON: nach dem Einfügen mit
`.venv/Scripts/python.exe -c "import json;json.load(open('custom_components/meteo_volt/translations/de.json',encoding='utf-8'))"` prüfen, dass sie noch lesbar sind.

- [ ] **Step 6: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_pruefungen.py tests/test_uebersetzungen.py -q`
Expected: PASS. `test_uebersetzungen.py` vergleicht `exceptions` gegen `pruefungen.MELDUNGEN` — fehlt ein Schlüssel oder ein Platzhalter, sagt es welcher.

- [ ] **Step 7: Commit**

```bash
git add custom_components/meteo_volt/pruefungen.py custom_components/meteo_volt/terminverwaltung.py custom_components/meteo_volt/translations/de.json custom_components/meteo_volt/translations/en.json tests/test_pruefungen.py
git commit -m "Warn when the trip does not add up"
```

---

## Task 5: Das Action-Feld

**Files:**
- Modify: `custom_components/meteo_volt/pruefungen.py` (`TERMIN_FELDER`)
- Modify: `custom_components/meteo_volt/aktionen.py` (`_FELDER`)
- Modify: `custom_components/meteo_volt/services.yaml`
- Modify: `custom_components/meteo_volt/translations/de.json`, `en.json`

**Interfaces:**
- Consumes: `werte_pruefen` liest `keep_min_soc` (Task 2)
- Produces: `keep_min_soc` als optionales Bool in `create_appointment` und `update_appointment`

- [ ] **Step 1: Run the test that will fail**

`tests/test_uebersetzungen.py` prüft schon, dass jede Action in `services.yaml` und in beiden Sprachdateien genau die Felder aus `pruefungen.AKTIONEN` trägt. Zuerst nur `TERMIN_FELDER` erweitern, in `pruefungen.py`:

```python
TERMIN_FELDER = ("vehicle", "departure", "return", "repeat", "distance_km", "driver", "soc",
                 "keep_min_soc")
```

Run: `.venv/Scripts/python.exe -m pytest tests/test_uebersetzungen.py -q`
Expected: FAIL — `services.yaml` und beide Sprachdateien kennen `keep_min_soc` nicht

- [ ] **Step 2: Add the schema entry in `aktionen.py`**

In `_FELDER`, hinter `"soc": _ZAHL,`:

```python
    "keep_min_soc": vol.Any(None, cv.boolean),
```

`cv` ist dort schon importiert (`homeassistant.helpers.config_validation`). Fehlt es, den Import ergänzen.

- [ ] **Step 3: Add the field to `services.yaml`**

In **beiden** Blöcken `create_appointment` und `update_appointment`, jeweils hinter dem `soc`-Feld, auf derselben Einrückung:

```yaml
    keep_min_soc:
      selector:
        boolean:
```

- [ ] **Step 4: Add the labels to the translations**

In `de.json` unter `services.create_appointment.fields` und `services.update_appointment.fields`, hinter `soc`:

```json
        "keep_min_soc": { "name": "Min-SoC sichern", "description": "Hebt die Abfahrt auf den Min-SoC plus den Verbrauch der Fahrt. Fehlt das Feld, beim Anlegen an, beim Ändern wie bisher." }
```

In `en.json` an denselben zwei Stellen:

```json
        "keep_min_soc": { "name": "Keep minimum SoC", "description": "Raises the departure to the minimum state of charge plus the trip. If the field is missing: on when creating, unchanged when editing." }
```

- [ ] **Step 5: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_uebersetzungen.py tests/test_verdrahtung.py -q`
Expected: PASS

- [ ] **Step 6: Run the whole suite**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add custom_components/meteo_volt/pruefungen.py custom_components/meteo_volt/aktionen.py custom_components/meteo_volt/services.yaml custom_components/meteo_volt/translations/de.json custom_components/meteo_volt/translations/en.json
git commit -m "Take the tick through the two appointment actions"
```

---

## Task 6: Die Websocket-Oberfläche

**Files:**
- Modify: `custom_components/meteo_volt/ansicht.py` (`termine_ansicht`)
- Modify: `custom_components/meteo_volt/terminverwaltung.py` (`standort`)
- Modify: `tests/test_ansicht.py`

**Interfaces:**
- Consumes: `Termin.sichern` (Task 2)
- Produces: `meteo_volt/appointments` liefert je Termin `keep_min_soc`; `meteo_volt/site` liefert je Fahrzeug `capacity_kwh` und `consumption_kwh_per_100km`

- [ ] **Step 1: Write the failing test**

An `tests/test_ansicht.py` anhängen. Der dortige Helfer, der Termine baut, muss den Haken durchreichen — er arbeitet über `termine.ausrollen` mit Eintrags-Dicts, also genügt `"keep_min_soc": True` im Eintrag:

```python
def test_der_termin_traegt_seinen_haken():
    """Spec C10 Abschnitt 7: das Panel liest ihn beim Bearbeiten."""
    eintrag = {"id": "e1", "vehicle": "auto-1", "departure": "2026-09-17T08:00:00",
               "duration_min": 600, "repeat": "once", "distance_km": 42, "driver": None,
               "soc": None, "keep_min_soc": True, "until": None, "exceptions": {}}
    (ansicht_termin,) = _ansicht(eintrag)
    assert ansicht_termin["keep_min_soc"] is True


def test_ein_termin_von_vor_c10_traegt_den_haken_nicht():
    eintrag = {"id": "e1", "vehicle": "auto-1", "departure": "2026-09-17T08:00:00",
               "duration_min": 600, "repeat": "once", "distance_km": 42, "driver": None,
               "soc": None, "until": None, "exceptions": {}}
    (ansicht_termin,) = _ansicht(eintrag)
    assert ansicht_termin["keep_min_soc"] is False
```

`_ansicht` ist der vorhandene Helfer der Datei; heißt er anders, den dortigen Namen verwenden.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ansicht.py -q -k haken`
Expected: FAIL — `KeyError: 'keep_min_soc'`

- [ ] **Step 3: Implement in `ansicht.py`**

Im Dict von `termine_ansicht`, hinter `"soc": termin.ladestand,`:

```python
            "keep_min_soc": termin.sichern,
```

- [ ] **Step 4: Implement in `terminverwaltung.py`**

In `standort()`, im Fahrzeug-Dict hinter `"max_charge_kw": ...`:

```python
                # C10 rechnet den gesicherten Ladestand im Panel mit; ohne die
                # beiden Werte kann es weder Hinweiszeile noch Warnung zeigen.
                "capacity_kwh": float(daten[stammdaten.FELD_KAPAZITAET]),
                "consumption_kwh_per_100km": float(daten[stammdaten.FELD_VERBRAUCH]),
```

- [ ] **Step 5: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add custom_components/meteo_volt/ansicht.py custom_components/meteo_volt/terminverwaltung.py tests/test_ansicht.py
git commit -m "Serve the tick and the two vehicle figures to the panel"
```

---

## Task 7: Die Rechnung im Panel und die Gegenprobe

**Files:**
- Create: `custom_components/meteo_volt/frontend/ladereserve.js`
- Modify: `tests/test_panel.py` (Gegenprobe)

**Interfaces:**
- Consumes: `ladereserve.py` (Task 1)
- Produces: `fahrtPct(km, v)`, `gesichert(km, v)`, `befund(km, soc, sichern, v)`, `hinweis(km, v)` und die Konstanten `FAHRT_ZU_WEIT`, `FAHRT_UNTER_MIN`, `LADESTAND_OFFEN` als ES-Modul. `v` ist ein Fahrzeug aus `meteo_volt/site`: `{ soc_min_pct, capacity_kwh, consumption_kwh_per_100km }`.

`hinweis` hat keinen Zwilling in Python: Das Backend zeigt keine Hinweiszeile. Es steht hier, damit die Zeile eine reine Funktion ist und `tests/panel/ladereserve.test.mjs` sie prüfen kann — sonst gäbe es sie nur im DOM von `dialoge.js`, wo kein Test hinsieht.

- [ ] **Step 1: Write the failing cross-check**

An `tests/test_panel.py` anhängen — direkt hinter `test_das_panel_rollt_aus_wie_termine_py`:

```python
# Gegenprobe: das Panel rechnet den gesicherten Ladestand wie ladereserve.py.
# (km, soc oder None, Haken, soc_min, Kapazitaet, Verbrauch)
RESERVE_FAELLE = [
    (175, None, True, 15.0, 58.0, 19.5),
    (175, 40, False, 15.0, 58.0, 19.5),
    (175, 100, False, 15.0, 58.0, 19.5),
    (400, None, True, 15.0, 58.0, 19.5),
    (0, None, True, 15.0, 58.0, 19.5),
    (42, 10, False, 15.0, 58.0, 19.5),
    (42, None, False, 15.0, 58.0, 19.5),
    (101, None, True, 15.0, 100.0, 10.0),
    (85, 100, False, 15.0, 100.0, 100.0),
    (7, None, True, 15.5, 58.0, 19.5),
]

RESERVE_SKRIPT = """
import { gesichert, fahrtPct, befund } from %s;
let text = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', (teil) => { text += teil; });
process.stdin.on('end', () => {
  const aus = JSON.parse(text).map(([km, soc, sichern, socMin, kwh, verbrauch]) => {
    const v = { soc_min_pct: socMin, capacity_kwh: kwh, consumption_kwh_per_100km: verbrauch };
    return [gesichert(km, v), fahrtPct(km, v), befund(km, soc, sichern, v)];
  });
  process.stdout.write(JSON.stringify(aus));
});
"""


def test_das_panel_rechnet_die_reserve_wie_ladereserve_py():
    ladereserve = _modul("ladereserve")
    erwartet = []
    for km, soc, sichern, soc_min, kwh, verbrauch in RESERVE_FAELLE:
        werte = ladereserve.Fahrzeugwerte(
            soc_min_pct=soc_min, capacity_kwh=kwh, consumption_kwh_per_100km=verbrauch)
        erwartet.append([
            ladereserve.gesichert(km, werte),
            ladereserve.fahrt_pct(km, werte),
            ladereserve.befund(km, soc, sichern, werte),
        ])
    assert {fall[2] for fall in erwartet} == {
        None, "fahrt_zu_weit", "fahrt_unter_min", "ladestand_offen"
    }, "die Faelle decken nicht jeden Befund ab; dann prueft die Gegenprobe zu wenig"
    skript = RESERVE_SKRIPT % json.dumps((FRONTEND / "ladereserve.js").as_uri())
    lauf = subprocess.run(
        [_node(), "--input-type=module", "-e", skript], input=json.dumps(RESERVE_FAELLE),
        capture_output=True, text=True, encoding="utf-8", cwd=WURZEL,
    )
    assert lauf.returncode == 0, lauf.stderr[-4000:]
    assert json.loads(lauf.stdout) == erwartet
```

- [ ] **Step 2: Run it to verify it fails**

Run: `PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest tests/test_panel.py -q -k reserve`
Expected: FAIL — Node meldet `Cannot find module`, weil `frontend/ladereserve.js` fehlt

- [ ] **Step 3: Write the implementation**

Create `custom_components/meteo_volt/frontend/ladereserve.js`:

```js
// Der gesicherte Ladestand eines Termins. Spec C10 Abschnitte 2 und 5.
//
// Dieselbe Rechnung wie ladereserve.py im Backend, Zeile fuer Zeile. Die
// Gegenprobe in tests/test_panel.py faehrt beide ueber dieselben Faelle und
// vergleicht: zwei Implementierungen derselben Formel driften sonst
// auseinander, ohne dass eine Pruefung rot wird.
//
// v ist ein Fahrzeug aus meteo_volt/site: soc_min_pct, capacity_kwh,
// consumption_kwh_per_100km.

export const FAHRT_ZU_WEIT = 'fahrt_zu_weit';
export const FAHRT_UNTER_MIN = 'fahrt_unter_min';
export const LADESTAND_OFFEN = 'ladestand_offen';

// Was eine Fahrt an Ladestand kostet, in Prozentpunkten. Ohne Wirkungsgrad:
// der gilt beim Laden, nicht beim Fahren.
export const fahrtPct = (km, v) => (km * v.consumption_kwh_per_100km) / v.capacity_kwh;

// Min-SoC plus Fahrt, aufgerundet auf ganze Prozent und bei 100 gedeckelt.
// Nicht bei soc_max_pct: ein Ziel wird nie gekappt (Basiskontrakt 3.3).
export const gesichert = (km, v) => Math.min(100, Math.ceil(v.soc_min_pct + fahrtPct(km, v)));

// Der Schluessel der Warnung zur Fahrt, oder null. soc ist das eigene Ziel
// oder null, sichern der Haken. soc_max_pct ist KEIN Bezugswert: dass der
// Planer heute vor der ersten Fahrt dorthin laedt, faellt mit A6E weg.
export function befund(km, soc, sichern, v) {
  const fahrt = fahrtPct(km, v);
  if (fahrt > 100 - v.soc_min_pct) return FAHRT_ZU_WEIT;
  let bezug;
  if (sichern) bezug = gesichert(km, v);
  else if (soc !== null && soc !== undefined && soc >= v.soc_min_pct) bezug = soc;
  else return LADESTAND_OFFEN;
  return bezug - fahrt < v.soc_min_pct ? FAHRT_UNTER_MIN : null;
}

// Die Platzhalter der Hinweiszeile unter dem Haken, oder null: ohne brauchbare
// Strecke gibt es nichts zu rechnen, und die Zeile bleibt weg.
// Spec C10 Abschnitt 5. Nur fuers Panel -- das Backend zeigt keine Zeile.
export function hinweis(km, v) {
  if (km === null || !Number.isFinite(km) || km < 0) return null;
  return { ziel: gesichert(km, v), min: v.soc_min_pct, fahrt: Math.round(fahrtPct(km, v)), km: Math.round(km) };
}
```

- [ ] **Step 4: Test the hint line**

Create `tests/panel/ladereserve.test.mjs`:

```js
// Prueft die Hinweiszeile unter dem Haken. Spec C10 Abschnitt 5.
// Die uebrigen drei Funktionen haelt die Gegenprobe in tests/test_panel.py
// gegen ladereserve.py; hier steht nur, was keinen Zwilling hat.

import assert from 'node:assert/strict';
import { test } from 'node:test';
import { hinweis } from '../../custom_components/meteo_volt/frontend/ladereserve.js';

const AUTO = { soc_min_pct: 15, capacity_kwh: 58, consumption_kwh_per_100km: 19.5 };

test('die Hinweiszeile nennt Ziel, Min-SoC, Fahrt und Strecke', () => {
  assert.deepEqual(hinweis(175, AUTO), { ziel: 74, min: 15, fahrt: 59, km: 175 });
});

test('ohne Strecke gibt es keine Hinweiszeile', () => {
  assert.equal(hinweis(null, AUTO), null);
  assert.equal(hinweis(Number.NaN, AUTO), null);
  assert.equal(hinweis(-1, AUTO), null);
});

test('bei null Kilometern sichert der Haken den Min-SoC', () => {
  assert.deepEqual(hinweis(0, AUTO), { ziel: 15, min: 15, fahrt: 0, km: 0 });
});

test('das Ziel kann ueber der Summe der angezeigten Teile liegen', () => {
  // 15,5 + 58,836 sind 74,336 -- aufgerundet 75, angezeigt als 15,5 plus 59
  const h = hinweis(175, { ...AUTO, soc_min_pct: 15.5 });
  assert.equal(h.ziel, 75);
  assert.equal(h.min + h.fahrt, 74.5);
});
```

Run: `node --test tests/panel/ladereserve.test.mjs`
Expected: PASS

- [ ] **Step 5: Run the cross-check**

Run: `PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest tests/test_panel.py -q`
Expected: PASS

Scheitert der Vergleich an `fahrtPct`: Python und JavaScript rechnen beide IEEE-754 double, `km * c / kapazitaet` in **dieser** Reihenfolge. Steht in einer der beiden Fassungen `km / 100 * c / kapazitaet`, weichen die letzten Bits ab — dann die Reihenfolge angleichen, nicht die Gegenprobe lockern.

- [ ] **Step 6: Commit**

```bash
git add custom_components/meteo_volt/frontend/ladereserve.js tests/panel/ladereserve.test.mjs tests/test_panel.py
git commit -m "Mirror the reserve arithmetic in the panel, held by a cross-check"
```

---

## Task 8: Die Prüfungen und die Texte im Panel

**Files:**
- Modify: `custom_components/meteo_volt/frontend/pruefung.js`
- Modify: `custom_components/meteo_volt/frontend/texte.js`
- Modify: `tests/panel/pruefung.test.mjs`, `tests/panel/texte.test.mjs`

**Interfaces:**
- Consumes: `befund`, `gesichert`, `fahrtPct` aus `./ladereserve.js` (Task 7)
- Produces: `pruefen(f, k)` nimmt zusätzlich `f.sichern` (Bool) und `k.fahrzeug` (`{ soc_min_pct, capacity_kwh, consumption_kwh_per_100km }`); `ORT` kennt die drei neuen Schlüssel; `TEXTE.de`/`TEXTE.en` tragen fünf neue Texte.

- [ ] **Step 1: Write the failing tests**

An `tests/panel/pruefung.test.mjs` anhängen (die vorhandenen Importe und Helfer der Datei weiterverwenden):

```js
const AUTO = { soc_min_pct: 15, capacity_kwh: 58, consumption_kwh_per_100km: 19.5 };

// Ein gueltiges Formular; f ueberschreibt einzelne Felder.
const formular = (f = {}) => ({
  abfahrt: '2026-09-17T08:00:00', rueckkehr: '2026-09-17T18:00:00',
  regel: 'once', km: '42', soc: '', sichern: true, ...f,
});
const kontext = { jetzt: Date.parse('2026-09-16T10:00:00Z'), tz: 'Europe/Berlin', fahrzeug: AUTO, versucht: true };

const warnungen = (f) => pruefen(formular(f), kontext).meldungen.filter((m) => m.art === 'warnung');

test('der Haken allein warnt nicht', () => {
  assert.deepEqual(warnungen({}), []);
});

test('ohne Haken und ohne Ziel ist der Ladestand offen', () => {
  assert.deepEqual(warnungen({ sichern: false }).map((m) => [m.key, m.ort]),
    [['ladestand_offen', 'ladestand']]);
});

test('ein zu kleines eigenes Ziel zieht unter den Min-SoC', () => {
  assert.deepEqual(warnungen({ sichern: false, soc: '40', km: '175' }).map((m) => m.key),
    ['fahrt_unter_min']);
});

test('auch voll geladen reicht es nicht', () => {
  assert.deepEqual(warnungen({ km: '400' }).map((m) => [m.key, m.platzhalter.km]),
    [['fahrt_zu_weit', 400]]);
});

test('der zu kleine Ladestand steht vor dem offenen', () => {
  assert.deepEqual(warnungen({ sichern: false, soc: '10' }).map((m) => m.key),
    ['ladestand_unter_min']);
});

test('am Platz Ladestand steht hoechstens eine Warnung', () => {
  assert.equal(warnungen({ sichern: false, soc: '10', km: '400' }).length, 1);
});

test('ohne Strecke wird nicht gerechnet', () => {
  assert.deepEqual(warnungen({ km: '' }), []);
});
```

In `tests/panel/texte.test.mjs` die Zahl der Meldungen von `16` auf `19` heben — die Zeile
`assert.equal(Object.keys(meldungen).length, 16);`.

- [ ] **Step 2: Run them to verify they fail**

Run: `node --test tests/panel/pruefung.test.mjs tests/panel/texte.test.mjs`
Expected: FAIL — die Warnungen fehlen, und `texte.test.mjs` findet 19 statt 16 Meldungen ohne passende Texte

- [ ] **Step 3: Add the texts in `texte.js`**

In `TEXTE.de`, bei den Meldungsschlüsseln hinter `ladestand_unter_min` — **wortgleich** mit `translations/de.json`, sonst schlägt `texte.test.mjs` fehl:

```js
    fahrt_zu_weit: 'Auch voll geladen reicht es nicht für {km} km — unterwegs laden.',
    fahrt_unter_min: 'Die Fahrt zieht den Ladestand unter den Min-SoC von {min} %.',
    ladestand_offen: 'Ohne Haken und ohne Ziel ist der Ladestand bei der Abfahrt nicht zugesagt.',
```

und bei den Formularschlüsseln hinter `f_ladestand`:

```js
    f_sichern: 'Min-SoC sichern',
    f_sichern_hinweis: 'Sichert {ziel} % — Min-SoC {min} % plus {fahrt} % für {km} km',
```

In `TEXTE.en` an denselben Stellen:

```js
    fahrt_zu_weit: 'Even fully charged it is not enough for {km} km — charge on the way.',
    fahrt_unter_min: 'The trip pulls the state of charge below the minimum of {min} %.',
    ladestand_offen: 'Without the tick and without a target the state of charge at departure is not promised.',
```

```js
    f_sichern: 'Keep minimum SoC',
    f_sichern_hinweis: 'Secures {ziel} % — minimum {min} % plus {fahrt} % for {km} km',
```

- [ ] **Step 4: Implement in `pruefung.js`**

Den Import ergänzen:

```js
import { FAHRT_UNTER_MIN, FAHRT_ZU_WEIT, LADESTAND_OFFEN, befund } from './ladereserve.js';
```

`ORT` um die drei Schlüssel erweitern, hinter `ladestand_unter_min`:

```js
  fahrt_zu_weit: 'ladestand',
  fahrt_unter_min: 'ladestand',
  ladestand_offen: 'ladestand',
```

Den Kommentarkopf der Funktion anpassen und den Ladestand-Block ersetzen. Aus

```js
  const soc = zahlOderNull(f.soc);
  if (soc !== null) {
    if (soc < 0 || soc > 100) melden('ladestand_bereich');
    else if (soc < k.socMin) melden('ladestand_unter_min', 'warnung', { min: k.socMin });
  }
```

wird

```js
  const soc = zahlOderNull(f.soc);
  const socMin = k.fahrzeug.soc_min_pct;
  if (soc !== null && (soc < 0 || soc > 100)) {
    melden('ladestand_bereich');
  } else {
    // Am Platz "Ladestand" steht hoechstens eine Warnung, in der Reihenfolge
    // aus C10-Spec Abschnitt 5. Ohne Strecke wird nicht gerechnet: dann steht
    // dort schon strecke_fehlt.
    const b = km === null ? null : befund(km, soc, Boolean(f.sichern), k.fahrzeug);
    if (b === FAHRT_ZU_WEIT) melden(FAHRT_ZU_WEIT, 'warnung', { km });
    else if (b === FAHRT_UNTER_MIN) melden(FAHRT_UNTER_MIN, 'warnung', { min: socMin });
    else if (soc !== null && soc < socMin) melden('ladestand_unter_min', 'warnung', { min: socMin });
    else if (b === LADESTAND_OFFEN) melden(LADESTAND_OFFEN, 'warnung');
  }
```

Den Kommentar über `pruefen` nachziehen:

```js
// f: { abfahrt, rueckkehr (lokal ohne Offset oder null), regel, km, soc, sichern }
// k: { jetzt, tz, fahrzeug, versucht } -- fahrzeug aus meteo_volt/site,
//     versucht: einmal auf Speichern gedrueckt
```

`melden` nimmt schon `(key, art, platzhalter)`; ohne Platzhalter bleibt `{}`.

- [ ] **Step 5: Run the panel tests**

Run: `node --test tests/panel/*.test.mjs`
Expected: PASS. Meldet `pruefung.test.mjs` einen Fehler an alten Fällen, tragen sie noch `socMin` im Kontext — dort auf `fahrzeug: AUTO` umstellen.

- [ ] **Step 6: Run the whole suite**

Run: `PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest tests/ -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add custom_components/meteo_volt/frontend/pruefung.js custom_components/meteo_volt/frontend/texte.js tests/panel/pruefung.test.mjs tests/panel/texte.test.mjs
git commit -m "Check and name the three trip warnings in the panel"
```

---

## Task 9: Der Haken im Formular

**Files:**
- Modify: `custom_components/meteo_volt/frontend/dialoge.js`
- Modify: `tests/panel/vorschau-dienst.js` (Beispieldaten mit den zwei neuen Fahrzeugfeldern)

**Interfaces:**
- Consumes: `f_sichern`, `f_sichern_hinweis` (Task 8); `gesichert`, `fahrtPct` aus `./ladereserve.js` (Task 7); `keep_min_soc` am Termin und `capacity_kwh`/`consumption_kwh_per_100km` am Fahrzeug (Task 6)
- Produces: der fertige Termindialog

- [ ] **Step 1: Add the tick to the form markup**

In `dialoge.js` die Zeile `feld-ladestand` ersetzen:

```js
        <div class="feld" id="feld-ladestand"><label for="f-soc">${f.t('f_ladestand')}</label>
          <input type="number" id="f-soc" inputmode="numeric" min="0" max="100" step="1" placeholder="${f.t('f_optional')}" value="${termin && termin.soc !== null && termin.soc !== undefined ? termin.soc : ''}">
          <label class="haken"><input type="checkbox" id="f-sichern"${termin ? (termin.keep_min_soc ? html` checked` : '') : html` checked`}><span>${f.t('f_sichern')}</span></label>
          <span class="hinweis" id="sichern-hinweis" hidden></span>
          <span class="warnhinweis" data-warnung="ladestand" hidden></span><span class="fehler" data-ort="ladestand" hidden></span></div>
```

Ein neuer Termin startet mit gesetztem Haken (Spec Abschnitt 3), ein bestehender mit seinem
gespeicherten Wert — `keep_min_soc` ist bei Terminen von vor C10 `false`.

- [ ] **Step 2: Read the tick and pass the vehicle**

`lese()` um das Feld ergänzen:

```js
    soc: q('#f-soc').value,
    sichern: q('#f-sichern').checked,
```

In `pruefenZeigen()` den Kontext umstellen — aus

```js
    const socMin = (z.fahrzeuge.find((v) => v.vehicle === w.fahrzeug) || {}).soc_min_pct ?? 0;
    const e = pruefen(w, { jetzt: Date.now(), tz, socMin, versucht });
```

wird

```js
    const fahrzeug = z.fahrzeuge.find((v) => v.vehicle === w.fahrzeug) || {};
    const e = pruefen(w, { jetzt: Date.now(), tz, fahrzeug, versucht });
```

Steht das Fahrzeug nicht in `site` — es hat kein Gerät —, fehlen `soc_min_pct`, `capacity_kwh` und
`consumption_kwh_per_100km`. Das Formular bietet dann ohnehin kein solches Fahrzeug zur Auswahl an:
`z.fahrzeuge` ist die Quelle der Auswahlliste.

- [ ] **Step 3: Show the hint line**

In `pruefenZeigen()`, direkt hinter der Zeile, die `[data-warnung="ladestand"]` setzt:

```js
    // Spec C10 Abschnitt 5: die Hinweiszeile steht, solange der Haken gesetzt
    // ist und eine Strecke dasteht. Was sie nennt, rechnet ladereserve.js.
    const h = w.sichern && w.km !== '' ? hinweis(Number(w.km), fahrzeug) : null;
    zeige(q('#sichern-hinweis'), h ? f.t('f_sichern_hinweis', {
      ziel: f.zahlKurz(h.ziel), min: f.zahlKurz(h.min),
      fahrt: f.zahlKurz(h.fahrt), km: f.zahlKurz(h.km),
    }) : '');
```

Den Import oben in `dialoge.js` ergänzen:

```js
import { hinweis } from './ladereserve.js';
```

`f.zahlKurz` ist der vorhandene Zahlformatierer des Panels — er schreibt `15,5` deutsch und `15.5`
englisch, wie `zahl_text` im Backend.

- [ ] **Step 4: Send the tick**

In dem Objekt, das die Action-Felder baut (die Zeile mit `driver: w.fahrer, soc: ...`):

```js
      driver: w.fahrer, soc: w.soc === '' ? null : Number(w.soc), keep_min_soc: w.sichern,
```

- [ ] **Step 5: Give the tick a style**

In `stil.js` bei den Formularklassen ergänzen — die vorhandenen Abstände der Nachbarn übernehmen:

```css
.haken { display: flex; align-items: center; gap: 8px; margin-top: 8px; font-weight: normal; }
.haken input { width: auto; margin: 0; }
.hinweis { display: block; margin-top: 4px; font-size: 0.85em; opacity: 0.75; }
```

- [ ] **Step 6: Feed the preview**

In `tests/panel/vorschau-dienst.js` jedem Fahrzeug in den `site`-Beispieldaten
`capacity_kwh: 58, consumption_kwh_per_100km: 19.5` geben und mindestens einem Beispieltermin
`keep_min_soc: true`, einem weiteren `keep_min_soc: false`.

- [ ] **Step 7: Run everything**

Run: `node --test tests/panel/*.test.mjs`
Expected: PASS

Run: `PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest tests/ -q`
Expected: PASS

Run: `.venv/Scripts/python.exe scripts/check_contract.py`
Expected: `Kontrakt in sync (35 Dateien geprueft)`

- [ ] **Step 8: Look at it**

`tests/panel/vorschau.html` im Browser öffnen. Prüfen, in Handy- und Desktop-Breite, hell und dunkel:

1. Neuer Termin: Haken gesetzt, Hinweiszeile nennt den Wert.
2. Strecke auf 400 stellen: `fahrt_zu_weit` steht, Speichern geht weiter.
3. Haken heraus, Feld leer: `ladestand_offen` steht.
4. Haken heraus, Ladestand 40, Strecke 175: `fahrt_unter_min` steht.
5. Haken heraus, Ladestand 10: `ladestand_unter_min` steht, nicht `ladestand_offen`.
6. Strecke leer: keine Hinweiszeile, keine der drei Warnungen.

- [ ] **Step 9: Check line endings and commit**

```bash
git add custom_components/meteo_volt/frontend/dialoge.js custom_components/meteo_volt/frontend/stil.js tests/panel/vorschau-dienst.js
```

```bash
for f in $(git diff --cached --name-only); do git show :$f | grep -q $'\r' && echo "CRLF: $f"; done
```

Keine Ausgabe heißt: alles LF.

```bash
git commit -m "Put the tick and its hint into the appointment form"
```

---

## Task 10: Die Verweise in den Specs von C3 und C8

**Dieser Task läuft im Brain-Repo**, nicht hier: `D:\Projekte\Meteo-Volt\meteo-volt-brain`, Branch
`c10-ladestand-sichern` (liegt schon an). Er ist keine Kür — Spec Abschnitt 7 verlangt ihn. Die
drei Repos werden von getrennten Sessions ohne gemeinsamen Kontext bearbeitet; eine C3-Spec, die
ihre eigene Erweiterung nicht kennt, schickt die nächste Session in die Irre.

**Files:**
- Modify: `docs/features/C3-konfig-entitaeten/spec.md` (Abschnitte 2.3, 3, 4, 5, 6)
- Modify: `docs/features/C8-panel/spec.md` (Abschnitte 7.1, 7.2, 7.3)

**Interfaces:**
- Consumes: die fertige C10-Spec
- Produces: nichts im Code. Nur Verweise — **kein zweiter Wortlaut**, eine Entscheidung steht an einer Stelle.

- [ ] **Step 1: C3-Spec**

Je einen kurzen Satz oder eine Tabellenzeile mit Verweis auf
[`C10`](../C10-ladestand-sichern/spec.md), an diesen fünf Stellen:

| Abschnitt | Was dazukommt |
|---|---|
| 2.3 | die drei Schlüssel `fahrt_zu_weit`, `fahrt_unter_min`, `ladestand_offen`, alle am Feld `soc`, alle Warnung |
| 3 | `keep_min_soc` im Eintrag und unter den Ausnahme-Feldern; fehlt es, ist es `false` |
| 4 | das Ziel entsteht auch ohne eigenen Ladestand, wenn der Haken gesetzt ist; es gilt der höhere Wert |
| 5 | `keep_min_soc` als Feld von `create_appointment` und `update_appointment`; fehlt es, beim Anlegen `true`, beim Ändern wie bisher |
| 6 | `keep_min_soc` am Termin; `capacity_kwh` und `consumption_kwh_per_100km` am Fahrzeug in `meteo_volt/site` |

Abschnitt 9 („Die zugesagte Oberfläche") bekommt einen Satz: dass C10 sie an diesen Stellen
additiv erweitert und C8 sich auch darauf verlassen darf.

- [ ] **Step 2: C8-Spec**

| Abschnitt | Was dazukommt |
|---|---|
| 7.1 | der Haken „Min-SoC sichern" in der Zeile „Ladestand bei Abfahrt", mit Hinweiszeile; neu gesetzt, beim Bearbeiten der Wert des Termins |
| 7.2 | die drei Schlüssel am Platz „Ladestand", mit der Reihenfolge aus C10-Spec 5 |
| 7.3 | `keep_min_soc` als Bool in `create_appointment` und `update_appointment` |

- [ ] **Step 3: Run the doc gate**

```bash
cd ../meteo-volt-brain && meteovolt_plan/.venv/Scripts/python.exe scripts/check_docs.py
```

Expected: jede Zeile `[OK]`. `[Links]` schlägt an, wenn ein Verweis ins Leere zeigt.

- [ ] **Step 4: Commit im Brain-Repo**

```bash
cd ../meteo-volt-brain && git add docs/features/C3-konfig-entitaeten/spec.md docs/features/C8-panel/spec.md
```

```bash
cd ../meteo-volt-brain && git commit -m "Point the C3 and C8 specs at what C10 adds"
```

---

## Abschluss

- [ ] **Das ganze Gate, beide Läufe**

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest tests/ -q
```

```bash
.venv/Scripts/python.exe scripts/check_contract.py
```

Beide grün. Die Testzahl liegt über den 460 vor C10.

- [ ] **Die Spec gegenlesen**

`meteo-volt-brain/docs/features/C10-ladestand-sichern/spec.md` Abschnitt 7 nennt jede Stelle, die
dazukommt. Jede davon abhaken. Weicht der Code ab, gewinnt die Spec — oder die Spec wird geändert,
bevor der Code es wird.

- [ ] **Nicht fertig ohne Abnahme**

Spec Abschnitt 9: Die Abnahme macht Patrick im Panel auf seiner Instanz, über eine Beta. Vorher
wird **nicht** nach `beta` gemergt und **nichts** „fertig" genannt. Die acht Punkte stehen dort.
