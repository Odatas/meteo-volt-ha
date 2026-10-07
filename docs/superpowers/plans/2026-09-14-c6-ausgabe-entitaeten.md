# C6 Ausgabe-Entitäten — Umsetzungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Jedes Fahrzeug bekommt ein Gerät mit acht Entitäten. Der Plan aus C5 wird sichtbar und automatisierbar, „Jetzt laden" stoppt am gemessenen Ladestand, und weicht die Ladegeschwindigkeit um mehr als 5 % vom Plan ab, erscheint ein Reparatur-Issue.

**Architecture:** Alles, was C6 entscheidet — Werte und Attribute der acht Entitäten, der Stopp am Ladestand mit Sperre, die Messung der Ladegeschwindigkeit und ihre Bewertung — liegt im neuen Modul `ausgabe.py`, ohne Import aus Home Assistant, und ist gegen die vendorten Fixtures geprüft. `fahrzeugausgabe.py` verdrahtet es: eine Auswertung je Fahrzeug mit Listenern auf den Plan-Koordinator und die Ladestand-Entität, einem Timer und dem Issue, dazu die Basisklasse der Entitäten und das Anlegen für später angelegte Fahrzeuge. `sensor.py` lädt `fahrzeugsensor.py` erst nach den sechs Sensoren der Prognose und im `try`, die neue Plattform `binary_sensor.py` ebenso `fahrzeugbinaersensor.py`.

**Tech Stack:** Python 3.12 (Venv `.venv`), pytest + jsonschema. Zur Laufzeit Home Assistant 2026.4.1 — nicht in den Testabhängigkeiten.

**Spec:** `meteo-volt-brain/docs/features/C6-ausgabe-entitaeten/spec.md`, Branch `c6-ausgabe-entitaeten`. Bei Widerspruch gilt die Spec, nicht dieser Plan.

## Global Constraints

- **Branch** ist `c6-ausgabe-entitaeten`, im ha-Repo und im Brain. Gemergt wird nach `beta`. **Niemals nach `master` oder `main`.**
- **Die Abnahme macht Patrick** auf seiner Instanz (Abschnitt „Abnahme"). Vorher ist C6 nicht fertig: kein Status `fertig`, kein Merge nach `beta`.
- **Python** ist `.venv/Scripts/python.exe`. Ein blankes `python` ist der Windows-Store-Alias. **Kein Venv-Update**, keine neue Testabhängigkeit.
- **`custom_components/` ist Endnutzer-Code.** HACS paketiert genau dieses Verzeichnis.
- **`ausgabe.py` importiert nichts aus Home Assistant und nichts aus aiohttp**, ebenso wenig die Module, die es lädt (`standort.py` und was daran hängt). Der Test lädt es über ein Paket, dessen `__init__.py` nicht läuft.
- **Bestandsschutz:** Die sechs Sensoren, ihr `unique_id`-Schema `meteo_volt_{entry_id}_{key}` und `hass.data[DOMAIN]` bleiben unberührt. `sensor.py` legt die sechs zuerst an; die Fahrzeugsensoren folgen in einem `try`, **der Import eingeschlossen**. `binary_sensor.py` lädt seine Klassen ebenso, und kein Rückruf an `async_on_unload` gibt etwas zurück (Spec Abschnitt 8). Neue Entitäten tragen `meteo_volt_{subentry_id}_{schlüssel}`.
- **Kein Attribut der acht Entitäten geht in den Recorder** (Spec Abschnitt 3).
- **Aus C5 benutzt C6 nur die zugesagte Oberfläche:** `entry.runtime_data`, `Planstand`, `was_gilt`, `ladestand_lesen`, `VERALTET_NACH` und die Gründe (C5-Spec Abschnitt 9). `standort.py` und `plankoordinator.py` bleiben unverändert.
- **Die 35 Kontrakt-Artefakte werden nie von Hand geändert** — `tests/fixtures/contract/**` und `contract.lock.json`.
- **Zeilenenden LF am gestagten Blob.** Der Arbeitsbaum trägt CRLF. Vor jedem Commit gibt `git diff --cached --name-only | while read f; do git show ":$f" | grep -q $'\r' && echo "CRLF: $f"; done` nichts aus.
- **Commit-Nachrichten** englisch, Imperativ, letzte Zeile `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- **Die Suite ist vor jedem Commit grün:** `.venv/Scripts/python.exe -m pytest -q`. Ausgangsstand: 262 bestandene Tests.
- **`<scratchpad>`** steht für das Scratchpad-Verzeichnis der ausführenden Sitzung. Was dort liegt, wird nicht committet.

---

## Dateien

| Datei | Verantwortung |
|---|---|
| `custom_components/meteo_volt/ausgabe.py` | **neu.** Werte und Attribute der acht Entitäten, Stopp am Ladestand, Sperre, Messung, Bewertung, Issue-Texte. Ohne Home Assistant. |
| `custom_components/meteo_volt/fahrzeugausgabe.py` | **neu.** Auswertung je Fahrzeug mit Listenern, Timer und Issue; Basisklasse der Entitäten; Anlegen für später angelegte Fahrzeuge. |
| `custom_components/meteo_volt/binary_sensor.py` | **neu.** Die Plattform. Lädt `fahrzeugbinaersensor.py` erst im `try`. |
| `custom_components/meteo_volt/fahrzeugbinaersensor.py` | **neu.** Jetzt laden, Plan erfüllbar. |
| `custom_components/meteo_volt/fahrzeugsensor.py` | **neu.** Die sechs Sensoren je Fahrzeug, von `sensor.py` abgeschirmt geladen. |
| `custom_components/meteo_volt/sensor.py` | **ergänzt.** Nach den sechs Sensoren der Aufruf von `fahrzeugsensor.py` im `try`. |
| `custom_components/meteo_volt/__init__.py` | **ergänzt.** Plattform `binary_sensor`, Start der Auswertungen hinter dem Koordinator. |
| `custom_components/meteo_volt/const.py` | **ergänzt.** `ISSUE_ABWEICHUNG`, `ISSUE_SCHNELLER`, `ISSUE_LANGSAMER`. |
| `custom_components/meteo_volt/translations/de.json`, `en.json` | **ergänzt.** Namen der Entitäten, Zustände des Ladeplans, zwei Issues. |
| `custom_components/meteo_volt/manifest.json` | **geändert.** Version `1.1.0-beta.9`. |
| `tests/test_ausgabe.py` | **neu.** Prüft `ausgabe.py` gegen die Response-Fixtures und erzeugte Ladestände. |
| `tests/test_uebersetzungen.py` | **ergänzt.** Namen, Zustände und Issues sind in beiden Sprachen beschriftet. |
| `tests/test_verdrahtung.py` | **neu.** Am Quelltext: keine `lambda` an `async_on_unload`, und C6 wird außerhalb von C6 nur im `try` importiert. |
| `README.md` | **ergänzt.** Abschnitt „Charge planning" mit Automation und ApexCharts-Karte. |

**Was das Gate nicht sieht:** Home Assistant. `tests/test_overrides.py` parst jede `.py`-Datei der Integration und fängt Syntaxfehler, aber keine falschen Namen. Dafür prüft Task 3 einmalig jeden benutzten Namen gegen den Quelltext von Home Assistant 2026.4.1, mit Gegenprobe. `tests/test_verdrahtung.py` prüft zwei Regeln der Verdrahtung am Quelltext. Das Verhalten sieht nur die Abnahme.

**Geprüft beim Schreiben dieses Plans, am 2026-09-14,** in einer Kopie gegen die echten Fixtures: Task 1 ohne Modul beim Sammeln rot, mit Modul 40 grün — erst nachdem die 5-%-Grenze als Differenz verglichen wurde; als Quotient ergab `105 / 100 - 1` in Gleitkomma `0.05000000000000004`. `test_uebersetzungen.py` mit den neuen Tests und den alten Texten 10 rot, mit den Texten 44 grün; die Suite danach 312 grün. Die Namensprüfung fand alle 62 Namen und scheiterte mit einem vertippten. Ihr erster Lauf meldete `SensorDeviceClass` fälschlich als fehlend: `sensor/__init__.py` reicht die Klasse aus `const.py` nur weiter. Die Prüfung erkennt seitdem weitergereichte Namen.

---

## Vor Task 1: Plan committen

- [ ] **Step 1: Commit**

```bash
git add docs/superpowers/plans/2026-09-14-c6-ausgabe-entitaeten.md
git diff --cached --name-only | while read f; do git show ":$f" | grep -q $'\r' && echo "CRLF: $f"; done
git commit -F - <<'EOF'
Plan the C6 output entities

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 1: `ausgabe.py` — Entitäten, Schaltlogik, Messung

**Files:**
- Modify: `custom_components/meteo_volt/const.py` (anhängen)
- Create: `custom_components/meteo_volt/ausgabe.py`
- Test: `tests/test_ausgabe.py`

**Interfaces:**
- Consumes: aus `standort.py` `Planstand`, `was_gilt(stand, fahrzeug_id, jetzt, soc_pct) -> dict`, `QUELLE_PLAN`, `VERALTET_NACH`, `GRUND_KEIN_LADEPUNKT`, `GRUND_LADEPUNKT_GELOESCHT`, `GRUND_LADESTAND`.
- Produces:
  - Schlüssel `JETZT_LADEN = "charge_now"`, `LADELEISTUNG = "charge_now_kw"`, `NAECHSTER_LADESTART = "next_charge_start"`, `ENERGIE = "total_kwh"`, `KOSTEN = "total_cost"`, `LADESTAND_PLANENDE = "soc_end_pct"`, `ERFUELLBAR = "feasible"`, `LADEPLAN = "plan"`; `BINAERSENSOREN`, `SENSOREN` (Tupel dieser Schlüssel); `ZUSTAENDE` (die fünf Zustände des Ladeplans); Attributnamen `QUELLE`, `ZIEL_ERREICHT`, `VIOLATIONS`, `SLOTS`, `INTERVALS`, `WARNINGS`, `FEHLER`.
  - `Zustand(gesperrt_bis: datetime | None, abgleich: Abgleich)`, `Abgleich(...)`, `Bewertung(gemessen: float, geplant: float)` mit `.abweichung` und `.ausserhalb`.
  - `auswerten(stand, fahrzeug_id, jetzt, soc_pct, gemeldet, zustand) -> Auswertung` mit `.werte: dict`, `.attribute: dict`, `.naechste: datetime`, `.zustand: Zustand`, `.bewertung: Bewertung | None`.
  - `abgleichen(alt, jetzt, rate, soc) -> tuple[Abgleich, Bewertung | None]`, `bewerten(abgleich) -> Bewertung | None`.
  - `issue_uebersetzung(bewertung) -> str`, `issue_platzhalter(bewertung, fahrzeug, sprache) -> dict[str, str]`.
  - In `const.py`: `ISSUE_ABWEICHUNG = "ladung_abweichung"`, `ISSUE_SCHNELLER = "ladung_schneller"`, `ISSUE_LANGSAMER = "ladung_langsamer"`.

- [ ] **Step 1: Den Test schreiben**

`tests/test_ausgabe.py`:

```python
"""Prueft die Ausgabe-Entitaeten ohne Home Assistant.

Geprueft wird gegen die vendorten Response-Fixtures, nicht gegen eine hier
nochmal hingeschriebene Erwartung: zum now ihres Requests tragen die
Entitaeten genau die Felder des Servers. Die Schaltlogik und die Messung
laufen ueber dieselben Fixtures mit erzeugten Ladestaenden.

Was dieser Test NICHT sieht: Plattformen, Listener, Timer, das Geraet, das
Anlegen und Entfernen von Entitaeten, _unrecorded_attributes im Recorder,
das Issue in Home Assistant und Home Assistant ueberhaupt. Das deckt die
Abnahme.
"""

import importlib
import json
import math
import sys
import types
from datetime import datetime, timedelta
from pathlib import Path

import pytest

WURZEL = Path(__file__).resolve().parents[1]
INTEGRATION = WURZEL / "custom_components" / "meteo_volt"
CONTRACT = WURZEL / "tests" / "fixtures" / "contract"

# Wie in test_standort.py: ueber ein Paket geladen, dessen __init__.py NICHT
# laeuft. Bekaeme ausgabe.py oder eines der Module, die es laedt, einen Import
# aus Home Assistant oder aiohttp, scheitert schon dieses Laden.
_PAKET = "meteo_volt_c6"
if _PAKET not in sys.modules:
    _paket = types.ModuleType(_PAKET)
    _paket.__path__ = [str(INTEGRATION)]
    sys.modules[_PAKET] = _paket
ausgabe = importlib.import_module(f"{_PAKET}.ausgabe")
standort = importlib.import_module(f"{_PAKET}.standort")
planabruf = importlib.import_module(f"{_PAKET}.planabruf")
const = importlib.import_module(f"{_PAKET}.const")

JETZT = datetime.fromisoformat("2026-08-18T22:00:00+02:00")
LEER = ausgabe.Zustand()


def _laden(pfad: Path) -> dict:
    roh = json.loads(pfad.read_text(encoding="utf-8"))
    return {k: v for k, v in roh.items() if k != "x-meteo-volt-contract"}


def _fixture_namen() -> list[str]:
    return sorted(p.name.split(".")[0] for p in CONTRACT.glob("*.response.json"))


def _fixture(name: str) -> tuple[dict, dict]:
    return (_laden(CONTRACT / f"{name}.request.json"),
            _laden(CONTRACT / f"{name}.response.json"))


def _stand(name: str, **felder):
    anfrage, plan = _fixture(name)
    return standort.Planstand(plan=plan, erhalten_um=JETZT, anfrage=anfrage, **felder)


def _zeit(text: str | None) -> datetime | None:
    return None if text is None else datetime.fromisoformat(text)


def _abend(uhrzeit: str) -> datetime:
    """Eine Uhrzeit am Abend des 2026-08-18. 00:00 ist die Mitternacht danach."""
    tag = "2026-08-19" if uhrzeit == "00:00" else "2026-08-18"
    return datetime.fromisoformat(f"{tag}T{uhrzeit}:00+02:00")


def _auswerten(stand, jetzt, soc=None, gemeldet=None, zustand=LEER, fahrzeug_id="auto-a"):
    return ausgabe.auswerten(stand, fahrzeug_id, jetzt, soc, gemeldet, zustand)


# --- Die Entitaeten, Spec Abschnitt 2 ---------------------------------------


def test_es_gibt_response_fixtures():
    """Die Parametrisierung unten saehe ohne Fixtures null Faelle und bliebe gruen."""
    assert _fixture_namen(), "keine Response-Fixtures; export_contract.py --to-ha ausfuehren"


def test_es_sind_acht_entitaeten_und_fuenf_zustaende():
    assert len(ausgabe.BINAERSENSOREN) + len(ausgabe.SENSOREN) == 8
    assert len(set(ausgabe.BINAERSENSOREN + ausgabe.SENSOREN)) == 8
    assert ausgabe.ZUSTAENDE == (
        "kein_ladepunkt", "ladepunkt_geloescht", "ladestand_nicht_lesbar", "aktuell", "kein_plan")


@pytest.mark.parametrize("name", _fixture_namen())
def test_zum_now_tragen_die_entitaeten_den_plan(name):
    anfrage, plan = _fixture(name)
    stand = standort.Planstand(plan=plan, erhalten_um=JETZT, anfrage=anfrage)
    for fahrzeugplan in plan["vehicles"]:
        auswertung = _auswerten(stand, JETZT, fahrzeug_id=fahrzeugplan["id"])
        assert auswertung.werte == {
            "charge_now": fahrzeugplan["charge_now"],
            "charge_now_kw": fahrzeugplan["charge_now_kw"],
            "next_charge_start": _zeit(fahrzeugplan["next_charge_start"]),
            "total_kwh": fahrzeugplan["total_kwh"],
            "total_cost": fahrzeugplan.get(
                "total_cost_incl_fees_eur", fahrzeugplan["total_cost_eur"]),
            "soc_end_pct": fahrzeugplan["soc_end_pct"],
            "feasible": fahrzeugplan["feasible"],
            "plan": "aktuell",
        }, (name, fahrzeugplan["id"])
        assert auswertung.attribute["charge_now"] == {"quelle": "plan", "ziel_erreicht": False}
        assert auswertung.attribute["feasible"] == {"violations": fahrzeugplan["violations"]}
        ladeplan = auswertung.attribute["plan"]
        # Unveraendert heisst: dasselbe Objekt, kein Nachbau.
        assert ladeplan["slots"] is fahrzeugplan["slots"]
        assert ladeplan["intervals"] is fahrzeugplan["intervals"]
        assert ladeplan["fehler"] is None


def test_die_kosten_tragen_das_netzentgelt_wenn_der_plan_es_liefert():
    """A0-Spec 3.2: sonst zeigte der Sensor einen Betrag, den niemand so bezahlt."""
    assert _auswerten(_stand("grid_fees"), JETZT).werte["total_cost"] == 1.22
    assert _auswerten(_stand("minimal"), JETZT).werte["total_cost"] == 0.23


def test_jedes_fahrzeug_sieht_die_warnungen_die_es_nennen_oder_gar_keins():
    anfrage, plan = _fixture("station_overbooked")
    plan = {**plan, "warnings": [
        *plan["warnings"],
        {"type": "soc_stale", "vehicle_id": "auto-a", "message": "SoC ist 47 min alt"},
        {"type": "prediction_stale", "message": "Prognose ist 3 h alt"},
    ]}
    stand = standort.Planstand(plan=plan, erhalten_um=JETZT, anfrage=anfrage)

    def typen(fahrzeug_id):
        warnungen = _auswerten(stand, JETZT, fahrzeug_id=fahrzeug_id).attribute["plan"]["warnings"]
        return [w["type"] for w in warnungen]

    assert typen("auto-a") == ["station_overbooked", "soc_stale", "prediction_stale"]
    assert typen("auto-b") == ["station_overbooked", "prediction_stale"]


def test_ohne_brauchbaren_plan_sind_die_planwerte_unbekannt():
    anfrage, plan = _fixture("minimal")
    stand = standort.Planstand(
        plan=plan, erhalten_um=JETZT - standort.VERALTET_NACH, anfrage=anfrage,
        fehler=planabruf.PlanNichtVerfuegbar(status=503))
    auswertung = _auswerten(stand, JETZT, soc=50.0, gemeldet=JETZT)
    assert {k: auswertung.werte[k] for k in (
        "total_kwh", "total_cost", "soc_end_pct", "feasible", "plan")} == {
        "total_kwh": None, "total_cost": None, "soc_end_pct": None, "feasible": None,
        "plan": "kein_plan"}
    assert auswertung.attribute["charge_now"]["quelle"] == "default"
    assert auswertung.attribute["feasible"] == {}
    assert auswertung.attribute["plan"] == {"fehler": "PlanNichtVerfuegbar: Status 503"}


@pytest.mark.parametrize("grund", [
    "kein_ladepunkt", "ladepunkt_geloescht", "ladestand_nicht_lesbar"])
def test_der_grund_aus_ausgelassen_geht_vor(grund):
    auswertung = _auswerten(_stand("minimal", ausgelassen={"auto-a": grund}), JETZT)
    assert auswertung.werte["plan"] == grund


def test_mit_unlesbarem_ladestand_bleiben_die_planwerte():
    """C5-Spec Abschnitt 8: ein unlesbarer Ladestand laesst den Plan gelten."""
    stand = _stand("minimal", ausgelassen={"auto-a": standort.GRUND_LADESTAND})
    auswertung = _auswerten(stand, JETZT)
    assert (auswertung.werte["total_kwh"], auswertung.attribute["charge_now"]["quelle"]) == (
        5.5, "plan")


# --- Wann ausgewertet wird, Spec Abschnitt 4 --------------------------------


def test_die_naechste_auswertung_ist_die_slotgrenze():
    assert _auswerten(_stand("second_block"), _abend("22:05")).naechste == _abend("22:15")


def test_kommen_die_12_stunden_frueher_zaehlen_sie():
    anfrage, plan = _fixture("second_block")
    erhalten = _abend("22:08") - standort.VERALTET_NACH
    stand = standort.Planstand(plan=plan, erhalten_um=erhalten, anfrage=anfrage)
    assert _auswerten(stand, _abend("22:05")).naechste == _abend("22:08")


# --- Jetzt laden: Plan gegen Ladestand, Spec Abschnitt 5 --------------------
# second_block laedt CC...CC.: Block 22:00-22:30 mit Ziel 55.82, Block
# 23:15-23:45 mit Ziel 64.65.


def test_am_ziel_des_blocks_geht_jetzt_laden_aus():
    auswertung = _auswerten(_stand("second_block"), _abend("22:20"), 55.82, _abend("22:20"))
    assert (auswertung.werte["charge_now"], auswertung.werte["charge_now_kw"]) == (False, 0.0)
    assert auswertung.attribute["charge_now"] == {"quelle": "plan", "ziel_erreicht": True}
    assert auswertung.zustand.gesperrt_bis == _abend("22:30")


def test_das_ziel_eines_slots_mitten_im_block_zaehlt_nicht():
    """Der Slot 22:00 endet bei 51.41; der Folgeslot laedt, das Blockziel ist 55.82."""
    auswertung = _auswerten(_stand("second_block"), _abend("22:05"), 52.0, _abend("22:05"))
    assert auswertung.werte["charge_now"] is True
    assert auswertung.zustand.gesperrt_bis is None


def test_mehr_als_einen_slot_voraus_geht_jetzt_laden_aus():
    auswertung = _auswerten(_stand("second_block"), _abend("22:05"), 56.0, _abend("22:05"))
    assert auswertung.werte["charge_now"] is False
    assert auswertung.zustand.gesperrt_bis == _abend("22:30")


def test_die_sperre_haelt_bis_zum_blockende():
    stand = _stand("second_block")
    gesperrt = ausgabe.Zustand(gesperrt_bis=_abend("22:30"))
    faellt = _auswerten(stand, _abend("22:25"), 54.0, _abend("22:25"), gesperrt)
    assert faellt.werte["charge_now"] is False
    neuer_plan = standort.Planstand(plan=stand.plan, erhalten_um=_abend("22:24"),
                                    anfrage=stand.anfrage)
    assert _auswerten(neuer_plan, _abend("22:25"), 54.0, _abend("22:25"),
                      gesperrt).werte["charge_now"] is False
    naechster_block = _auswerten(stand, _abend("23:15"), 56.0, _abend("23:15"), faellt.zustand)
    assert naechster_block.werte["charge_now"] is True
    assert naechster_block.zustand.gesperrt_bis is None


def test_ein_veralteter_ladestand_stoppt_nicht():
    stand = _stand("second_block")
    jetzt = _abend("22:20")
    alt = _auswerten(stand, jetzt, 60.0, jetzt - timedelta(minutes=31))
    assert alt.werte["charge_now"] is True
    gerade_noch = _auswerten(stand, jetzt, 60.0, jetzt - timedelta(minutes=30))
    assert gerade_noch.werte["charge_now"] is False


def test_langsamer_als_geplant_endet_der_block_zur_planzeit():
    auswertung = _auswerten(_stand("second_block"), _abend("22:30"), 50.0, _abend("22:29"))
    assert auswertung.werte["charge_now"] is False
    assert auswertung.attribute["charge_now"]["ziel_erreicht"] is False


def test_ohne_plan_reagiert_der_default_auf_den_ladestand():
    anfrage, _ = _fixture("minimal")
    stand = standort.Planstand(anfrage=anfrage)
    grenze = anfrage["vehicles"][0]["soc_min_pct"]
    unter = _auswerten(stand, JETZT, grenze - 1, JETZT)
    ueber = _auswerten(stand, JETZT, grenze + 1, JETZT)
    assert (unter.werte["charge_now"], ueber.werte["charge_now"]) == (True, False)
    assert unter.attribute["charge_now"] == {"quelle": "default", "ziel_erreicht": False}


# --- Die Abweichungswarnung, Spec Abschnitt 6 -------------------------------
# infeasible laedt von 22:00 bis 00:00 durch, Ziel 82.3. Geplant sind
# 11 kW x 0.94 / 58 kWh = 17.83 Prozentpunkte je Stunde.

GEPLANT = 11.0 * 0.94 / 58.0 * 100


def _laden_ueber(stand, rate, start, bis, alle_min=5, abrunden=False):
    """Wertet von 22:00 bis bis aus, mit einem Ladestand, der mit rate steigt."""
    zustand, auswertungen = ausgabe.Zustand(), []
    jetzt = JETZT
    while jetzt <= bis:
        soc = start + rate * (jetzt - JETZT).total_seconds() / 3600
        if abrunden:
            soc = float(math.floor(soc))
        auswertung = _auswerten(stand, jetzt, soc, jetzt, zustand)
        zustand = auswertung.zustand
        auswertungen.append(auswertung)
        jetzt += timedelta(minutes=alle_min)
    return auswertungen


def _bewertungen(auswertungen):
    return [a.bewertung for a in auswertungen if a.bewertung is not None]


def test_genau_nach_plan_gibt_es_keine_warnung():
    bewertungen = _bewertungen(_laden_ueber(_stand("infeasible"), GEPLANT, 30.0, _abend("00:00")))
    assert len(bewertungen) == 1
    assert bewertungen[0].gemessen == pytest.approx(GEPLANT)
    assert bewertungen[0].geplant == pytest.approx(GEPLANT)
    assert not bewertungen[0].ausserhalb


@pytest.mark.parametrize(("faktor", "uebersetzung"), [
    (1.08, "ladung_schneller"), (0.92, "ladung_langsamer")])
def test_acht_prozent_daneben_warnt_mit_richtung(faktor, uebersetzung):
    bewertungen = _bewertungen(
        _laden_ueber(_stand("infeasible"), GEPLANT * faktor, 30.0, _abend("00:00")))
    assert len(bewertungen) == 1
    assert bewertungen[0].abweichung == pytest.approx(faktor - 1)
    assert bewertungen[0].ausserhalb
    assert ausgabe.issue_uebersetzung(bewertungen[0]) == uebersetzung


def test_ganzzahlig_alle_15_minuten_nach_plan_gibt_es_keine_warnung():
    auswertungen = _laden_ueber(
        _stand("infeasible"), GEPLANT, 30.0, _abend("00:00"), alle_min=15, abrunden=True)
    bewertungen = _bewertungen(auswertungen)
    assert len(bewertungen) == 1
    assert not bewertungen[0].ausserhalb, bewertungen[0].abweichung


def test_unter_zwei_stunden_wird_nicht_bewertet():
    assert _bewertungen(
        _laden_ueber(_stand("infeasible"), GEPLANT, 30.0, _abend("23:55"))) == []


def test_ohne_anstieg_wird_nicht_bewertet():
    assert _bewertungen(_laden_ueber(_stand("infeasible"), 0.0, 30.0, _abend("00:00"))) == []


def _messpunkt(abgleich, jetzt, rate, soc):
    return ausgabe.abgleichen(abgleich, jetzt, rate, soc)[0]


def test_unter_drei_verwertbaren_punkten_wird_nicht_bewertet():
    """Ein Einschalten mit einem Punkt traegt zur Steigung nichts bei."""
    abgleich = ausgabe.Abgleich(
        ladezeit_s=7200.0, geplant_pp=2 * GEPLANT,
        punkte=((1, 0.0, 30.0), (2, 3600.0, 48.0), (2, 7200.0, 66.0)))
    assert ausgabe.bewerten(abgleich) is None


def test_pause_und_gefahrener_ladestand_zwischen_zwei_bloecken_zaehlen_nicht():
    """Eine Stunde laden, drei Stunden Pause mit Fahrt, eine Stunde laden."""
    abgleich = ausgabe.Abgleich()
    beginn = JETZT
    for minute in range(0, 61, 5):
        abgleich = _messpunkt(abgleich, beginn + timedelta(minutes=minute),
                              GEPLANT, 40.0 + GEPLANT * minute / 60)
    abgleich = _messpunkt(abgleich, beginn + timedelta(minutes=61), None, None)
    zweiter = beginn + timedelta(hours=4)
    bewertung = None
    for minute in range(0, 61, 5):
        abgleich, bewertung = ausgabe.abgleichen(
            abgleich, zweiter + timedelta(minutes=minute),
            GEPLANT, 35.0 + GEPLANT * minute / 60)
        if bewertung is not None:
            break
    assert bewertung is not None
    assert bewertung.gemessen == pytest.approx(GEPLANT)


@pytest.mark.parametrize(("gemessen", "ausserhalb"), [(105.0, False), (95.0, False),
                                                      (105.1, True), (94.9, True)])
def test_genau_fuenf_prozent_liegt_noch_innerhalb(gemessen, ausserhalb):
    assert ausgabe.Bewertung(gemessen=gemessen, geplant=100.0).ausserhalb is ausserhalb


def test_das_issue_nennt_die_zahlen_in_der_sprache():
    bewertung = ausgabe.Bewertung(gemessen=12.14, geplant=13.14)
    assert ausgabe.issue_platzhalter(bewertung, "ID. Buzz", "de") == {
        "fahrzeug": "ID. Buzz", "gemessen": "12,1", "geplant": "13,1", "abweichung": "8"}
    assert ausgabe.issue_platzhalter(bewertung, "ID. Buzz", "en-GB")["gemessen"] == "12.1"
    assert ausgabe.issue_uebersetzung(bewertung) == const.ISSUE_LANGSAMER
```

- [ ] **Step 2: Rot sehen**

Run: `.venv/Scripts/python.exe -m pytest -q tests/test_ausgabe.py`
Expected: `ERROR tests/test_ausgabe.py` beim Sammeln, `1 error` — `ausgabe.py` gibt es noch nicht.

- [ ] **Step 3: Die Issue-Kennungen anhängen**

Ans Ende von `custom_components/meteo_volt/const.py`:

```python
# Spec C6 Abschnitt 6: das Issue, wenn die Ladegeschwindigkeit mehr als 5 % vom
# Plan abweicht. Die Kennung traegt dahinter die Fahrzeug-ID, die Uebersetzung
# haengt an der Richtung.
ISSUE_ABWEICHUNG = "ladung_abweichung"
ISSUE_SCHNELLER = "ladung_schneller"
ISSUE_LANGSAMER = "ladung_langsamer"
```

- [ ] **Step 4: Das Modul schreiben**

`custom_components/meteo_volt/ausgabe.py`:

```python
"""Die Ausgabe-Entitaeten ohne Home Assistant.

Dieses Modul importiert bewusst NICHTS aus Home Assistant und nichts aus
aiohttp -- wie standort.py, auf dem es aufbaut. Hier steht, was C6
entscheidet: welche Werte die acht Entitaeten eines Fahrzeugs tragen, wann
"Jetzt laden" am gemessenen Ladestand abschaltet und wie die
Ladegeschwindigkeit gegen den Plan gemessen wird. fahrzeugausgabe.py
verdrahtet das mit Home Assistant und entscheidet selbst nichts.

Spec: meteo-volt-brain/docs/features/C6-ausgabe-entitaeten/spec.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from . import standort
from .const import ISSUE_LANGSAMER, ISSUE_SCHNELLER

# --- Die Entitaeten, Spec Abschnitt 2 ---------------------------------------
# Zugleich translation_key und Ende der unique_id.

JETZT_LADEN = "charge_now"
LADELEISTUNG = "charge_now_kw"
NAECHSTER_LADESTART = "next_charge_start"
ENERGIE = "total_kwh"
KOSTEN = "total_cost"
LADESTAND_PLANENDE = "soc_end_pct"
ERFUELLBAR = "feasible"
LADEPLAN = "plan"

BINAERSENSOREN = (JETZT_LADEN, ERFUELLBAR)
SENSOREN = (LADELEISTUNG, NAECHSTER_LADESTART, ENERGIE, KOSTEN, LADESTAND_PLANENDE, LADEPLAN)

# --- Der Zustand des Ladeplans, Spec Abschnitt 2.2 --------------------------
# Die Gruende aus ausgelassen gehen vor: sie sagen, was der Nutzer tun kann.

AKTUELL = "aktuell"
KEIN_PLAN = "kein_plan"
GRUENDE = (
    standort.GRUND_KEIN_LADEPUNKT,
    standort.GRUND_LADEPUNKT_GELOESCHT,
    standort.GRUND_LADESTAND,
)
ZUSTAENDE = (*GRUENDE, AKTUELL, KEIN_PLAN)

# --- Die Attribute, Spec Abschnitt 2.3 --------------------------------------
# Keins davon geht in den Recorder (Abschnitt 3).

QUELLE = "quelle"
ZIEL_ERREICHT = "ziel_erreicht"
VIOLATIONS = "violations"
SLOTS = "slots"
INTERVALS = "intervals"
WARNINGS = "warnings"
FEHLER = "fehler"

# --- Grenzen, Spec Abschnitte 5 und 6 ---------------------------------------

# Dieselbe Grenze wie soc_stale im Plan-Dienst. Ein aelterer Ladestand stoppt nicht.
FRISCH = timedelta(minutes=30)
# Gemessen am 2026-09-10: darunter erzeugt die Messung allein mehr als 5 %.
BEWERTEN_AB = timedelta(hours=2)
TOLERANZ = 0.05
MIN_PUNKTE = 3


@dataclass(frozen=True)
class Abgleich:
    """Die laufende Messung der Ladegeschwindigkeit. Spec Abschnitt 6.

    Die Zeitachse ist die Ladezeit in Sekunden: Pausen zaehlen nicht mit.
    punkte traegt (einschalten, ladezeit_s, ladestand). Jedes Einschalten
    zaehlt hoch und bekommt in der Regression einen eigenen
    Achsenabschnitt -- wird das Auto zwischen zwei Bloecken gefahren, aendert
    das nur die Hoehe, nicht die Steigung.
    """

    ladezeit_s: float = 0.0
    geplant_pp: float = 0.0
    punkte: tuple[tuple[int, float, float], ...] = ()
    einschalten: int = 0
    seit: datetime | None = None
    rate: float | None = None


@dataclass(frozen=True)
class Zustand:
    """Was von einer Auswertung eines Fahrzeugs zur naechsten bleibt."""

    gesperrt_bis: datetime | None = None
    abgleich: Abgleich = field(default_factory=Abgleich)


@dataclass(frozen=True)
class Bewertung:
    """Gemessene und geplante Rate in Prozentpunkten je Stunde."""

    gemessen: float
    geplant: float

    @property
    def abweichung(self) -> float:
        return self.gemessen / self.geplant - 1

    @property
    def ausserhalb(self) -> bool:
        # Als Differenz, nicht als Quotient: 105 / 100 - 1 ergibt in Gleitkomma
        # 0.05000000000000004, und genau 5 % laege dann schon ausserhalb.
        return abs(self.gemessen - self.geplant) > TOLERANZ * self.geplant


@dataclass(frozen=True)
class Auswertung:
    """Das Ergebnis einer Auswertung. Spec Abschnitt 4.

    werte und attribute sind nach den Schluesseln aus Abschnitt 2 geordnet.
    naechste ist, wann spaetestens neu ausgewertet wird. bewertung steht nur,
    wenn in dieser Auswertung eine Messung bewertet wurde.
    """

    werte: dict
    attribute: dict
    naechste: datetime
    zustand: Zustand
    bewertung: Bewertung | None = None


def auswerten(
    stand: standort.Planstand,
    fahrzeug_id: str,
    jetzt: datetime,
    soc_pct: float | None,
    gemeldet: datetime | None,
    zustand: Zustand,
) -> Auswertung:
    """Eine Auswertung fuer ein Fahrzeug. Spec Abschnitte 2 bis 6.

    soc_pct ist der Ladestand nach standort.ladestand_lesen, gemeldet sein
    last_reported. zustand kommt aus der vorigen Auswertung.
    """
    gilt = standort.was_gilt(stand, fahrzeug_id, jetzt, soc_pct)
    mit_plan = gilt["quelle"] == standort.QUELLE_PLAN
    frisch = soc_pct is not None and gemeldet is not None and jetzt - gemeldet <= FRISCH
    fahrzeugplan, block = _plan_und_block(stand, fahrzeug_id, gilt) if mit_plan else (None, None)

    laden, kw = gilt["charge_now"], gilt["charge_now_kw"]
    gesperrt_bis = zustand.gesperrt_bis
    if gesperrt_bis is not None and jetzt >= gesperrt_bis:
        gesperrt_bis = None
    if block is not None:
        ende, ziel = block
        # Abschnitt 5, Regeln 1 und 3: nur ein frischer Ladestand stoppt.
        if gesperrt_bis is None and frisch and soc_pct >= ziel:
            gesperrt_bis = ende
        # Regel 2: die Sperre haelt bis zum Blockende, auch gegen einen neuen Plan.
        if gesperrt_bis is not None:
            laden, kw = False, 0.0

    rate = _geplante_rate(stand, fahrzeug_id, kw) if mit_plan and laden else None
    abgleich, bewertung = abgleichen(zustand.abgleich, jetzt, rate, soc_pct if frisch else None)

    return Auswertung(
        werte=_werte(stand, fahrzeug_id, gilt, fahrzeugplan, laden, kw),
        attribute=_attribute(stand, fahrzeug_id, gilt, fahrzeugplan, mit_plan and gesperrt_bis is not None),
        naechste=_naechste(stand, jetzt, gilt["current_slot_end"]),
        zustand=Zustand(gesperrt_bis=gesperrt_bis, abgleich=abgleich),
        bewertung=bewertung,
    )


def _plan_und_block(
    stand: standort.Planstand, fahrzeug_id: str, gilt: dict
) -> tuple[dict | None, tuple[datetime, float] | None]:
    """Der Fahrzeugplan und, wenn gerade geladen wird, Ende und Ziel des Blocks.

    Der Plan-Client prueft eine 200 nicht gegen das Schema (C7-Spec
    Abschnitt 5). Fehlt dem Plan etwas, gibt es keinen Stopp am Ladestand,
    und die Planwerte bleiben unbekannt.
    """
    try:
        fahrzeugplan = next(
            fp for fp in stand.plan["vehicles"] if fp.get("id") == fahrzeug_id
        )
        if not gilt["charge_now"]:
            return fahrzeugplan, None
        return fahrzeugplan, _block(
            fahrzeugplan["slots"], gilt["current_slot_end"], stand.plan["slot_minutes"]
        )
    except (AttributeError, KeyError, StopIteration, TypeError, ValueError):
        return None, None


def _block(slots: list[dict], slot_ende: datetime, slot_minutes: int) -> tuple[datetime, float]:
    """Ende und Ziel des Ladeblocks, dessen laufender Slot bei slot_ende endet.

    Ein Block ist eine lueckenlose Folge von Ladeslots (A0-Spec 3.10), sein
    Ziel das soc_end_pct seines letzten Slots.
    """
    schritt = timedelta(minutes=slot_minutes)
    index = next(
        i for i, slot in enumerate(slots)
        if datetime.fromisoformat(slot["t"]) + schritt == slot_ende
    )
    while index + 1 < len(slots) and slots[index + 1]["charge"]:
        index += 1
    return datetime.fromisoformat(slots[index]["t"]) + schritt, float(slots[index]["soc_end_pct"])


def _geplante_rate(stand: standort.Planstand, fahrzeug_id: str, kw: float) -> float | None:
    """charge_now_kw x eta / Kapazitaet x 100, in Prozentpunkten je Stunde.

    eta und Kapazitaet kommen aus dem zuletzt gebauten Request.
    """
    for fahrzeug in (stand.anfrage or {}).get("vehicles", []):
        if fahrzeug.get("id") == fahrzeug_id:
            try:
                return kw * fahrzeug["efficiency_curve"][0]["eta"] / fahrzeug["capacity_kwh"] * 100
            except (IndexError, KeyError, TypeError, ZeroDivisionError):
                return None
    return None


def abgleichen(
    alt: Abgleich, jetzt: datetime, rate: float | None, soc: float | None
) -> tuple[Abgleich, Bewertung | None]:
    """Fuehrt die Messung um eine Auswertung weiter. Spec Abschnitt 6.

    rate ist die geplante Rate, solange gemessen wird, sonst None. soc ist der
    Ladestand, wenn er frisch ist, sonst None. Messpunkte sind der Ladestand
    beim Einschalten und jede Aenderung danach, auch die, die das Ziel
    erreicht und damit abschaltet.
    """
    aktiv = rate is not None
    lief = alt.seit is not None
    ladezeit, geplant = alt.ladezeit_s, alt.geplant_pp
    if lief:
        dauer = max(0.0, (jetzt - alt.seit).total_seconds())
        ladezeit += dauer
        geplant += alt.rate * dauer / 3600
    einschalten = alt.einschalten + 1 if aktiv and not lief else alt.einschalten
    punkte = alt.punkte
    if soc is not None and (aktiv or lief):
        letzter = punkte[-1] if punkte else None
        if letzter is None or letzter[0] != einschalten or letzter[2] != soc:
            punkte = (*punkte, (einschalten, ladezeit, soc))
    neu = Abgleich(ladezeit, geplant, punkte, einschalten, jetzt if aktiv else None, rate)
    if ladezeit < BEWERTEN_AB.total_seconds():
        return neu, None
    # Bewertet, die Messung beginnt neu. Laeuft sie weiter, zaehlt das als
    # neues Einschalten: der naechste Punkt beginnt eine eigene Gerade.
    naechste_messung = Abgleich(
        einschalten=einschalten + 1 if aktiv else einschalten, seit=neu.seit, rate=rate
    )
    return naechste_messung, bewerten(neu)


def bewerten(abgleich: Abgleich) -> Bewertung | None:
    """Die gemeinsame Steigung mit eigenem Achsenabschnitt je Einschalten.

    None heisst nicht bewertet: weniger als MIN_PUNKTE verwertbare Punkte --
    das sind Punkte eines Einschaltens mit mindestens zwei --, oder bei
    keinem Einschalten liegt der letzte Punkt hoeher als der erste. Dann
    wurde nicht geladen, und das liegt nicht an den Einstellungen.
    """
    gruppen: dict[int, list[tuple[float, float]]] = {}
    for einschalten, ladezeit, soc in abgleich.punkte:
        gruppen.setdefault(einschalten, []).append((ladezeit, soc))
    zaehler = nenner = 0.0
    verwertbar = 0
    steigt = False
    for punkte in gruppen.values():
        if len(punkte) < 2:
            continue
        verwertbar += len(punkte)
        steigt = steigt or punkte[-1][1] > punkte[0][1]
        mitte_t = sum(t for t, _ in punkte) / len(punkte)
        mitte_soc = sum(s for _, s in punkte) / len(punkte)
        zaehler += sum((t - mitte_t) * (s - mitte_soc) for t, s in punkte)
        nenner += sum((t - mitte_t) ** 2 for t, _ in punkte)
    if verwertbar < MIN_PUNKTE or not steigt or nenner <= 0 or abgleich.geplant_pp <= 0:
        return None
    return Bewertung(
        gemessen=zaehler / nenner * 3600,
        geplant=abgleich.geplant_pp / abgleich.ladezeit_s * 3600,
    )


def _werte(
    stand: standort.Planstand,
    fahrzeug_id: str,
    gilt: dict,
    fahrzeugplan: dict | None,
    laden: bool,
    kw: float,
) -> dict:
    """Die Zustaende der acht Entitaeten. Spec Abschnitte 2, 2.1 und 2.2."""
    grund = stand.ausgelassen.get(fahrzeug_id)
    if grund in GRUENDE:
        plan = grund
    elif fahrzeugplan is not None:
        plan = AKTUELL
    else:
        plan = KEIN_PLAN
    fp = fahrzeugplan or {}
    return {
        JETZT_LADEN: laden,
        LADELEISTUNG: kw,
        NAECHSTER_LADESTART: gilt["next_charge_start"],
        ENERGIE: fp.get("total_kwh"),
        # A0-Spec 3.2: mit Netzentgelt, wenn der Plan es liefert.
        KOSTEN: fp.get("total_cost_incl_fees_eur", fp.get("total_cost_eur")),
        LADESTAND_PLANENDE: fp.get("soc_end_pct"),
        ERFUELLBAR: fp.get("feasible"),
        LADEPLAN: plan,
    }


def _attribute(
    stand: standort.Planstand,
    fahrzeug_id: str,
    gilt: dict,
    fahrzeugplan: dict | None,
    ziel_erreicht: bool,
) -> dict:
    """Die Attribute je Entitaet. Spec Abschnitt 2.3."""
    fehler = None if stand.fehler is None else f"{type(stand.fehler).__name__}: {stand.fehler}"
    attribute = {
        JETZT_LADEN: {QUELLE: gilt["quelle"], ZIEL_ERREICHT: ziel_erreicht},
        ERFUELLBAR: {},
        LADEPLAN: {FEHLER: fehler},
    }
    if fahrzeugplan is not None:
        attribute[ERFUELLBAR] = {VIOLATIONS: fahrzeugplan.get("violations", [])}
        attribute[LADEPLAN] = {
            SLOTS: fahrzeugplan.get("slots", []),
            INTERVALS: fahrzeugplan.get("intervals", []),
            WARNINGS: _warnungen(stand.plan, fahrzeug_id),
            FEHLER: fehler,
        }
    return attribute


def _warnungen(plan: dict, fahrzeug_id: str) -> list[dict]:
    """Die Warnungen, die dieses Fahrzeug nennen oder gar keins."""
    return [w for w in plan.get("warnings") or [] if _nennt(w, fahrzeug_id)]


def _nennt(warnung: dict, fahrzeug_id: str) -> bool:
    if "vehicle_id" in warnung:
        return warnung["vehicle_id"] == fahrzeug_id
    if "vehicle_ids" in warnung:
        return fahrzeug_id in warnung["vehicle_ids"]
    return True


def _naechste(stand: standort.Planstand, jetzt: datetime, slot_ende: datetime) -> datetime:
    """Die Slotgrenze, oder 12 h nach Empfang, wenn das frueher kommt. Spec Abschnitt 4."""
    if stand.erhalten_um is not None:
        veraltet = stand.erhalten_um + standort.VERALTET_NACH
        if jetzt < veraltet < slot_ende:
            return veraltet
    return slot_ende


# --- Das Issue, Spec Abschnitt 6 --------------------------------------------


def issue_uebersetzung(bewertung: Bewertung) -> str:
    return ISSUE_SCHNELLER if bewertung.abweichung > 0 else ISSUE_LANGSAMER


def issue_platzhalter(bewertung: Bewertung, fahrzeug: str, sprache: str) -> dict[str, str]:
    """Zahlen mit einer Nachkommastelle, Dezimalzeichen nach der Sprache."""
    deutsch = (sprache or "en").split("-")[0].lower() == "de"

    def zahl(wert: float) -> str:
        text = f"{wert:.1f}"
        return text.replace(".", ",") if deutsch else text

    return {
        "fahrzeug": fahrzeug,
        "gemessen": zahl(bewertung.gemessen),
        "geplant": zahl(bewertung.geplant),
        "abweichung": str(round(abs(bewertung.abweichung) * 100)),
    }
```

- [ ] **Step 5: Grün sehen**

Run: `.venv/Scripts/python.exe -m pytest -q tests/test_ausgabe.py`
Expected: `40 passed`

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: `302 passed`

- [ ] **Step 6: Commit**

```bash
git add custom_components/meteo_volt/const.py custom_components/meteo_volt/ausgabe.py tests/test_ausgabe.py
git diff --cached --name-only | while read f; do git show ":$f" | grep -q $'\r' && echo "CRLF: $f"; done
git commit -F - <<'EOF'
Decide what the eight vehicle entities show

The values follow was_gilt and the vehicle plan. Charge now stops at the
target of the running block and holds until it ends, and two hours of
charging are measured against the planned rate. None of this imports
Home Assistant, so it runs against the vendored fixtures.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---
### Task 2: Übersetzungen — Namen, Zustände, Issues

**Files:**
- Modify: `custom_components/meteo_volt/translations/de.json`
- Modify: `custom_components/meteo_volt/translations/en.json`
- Test: `tests/test_uebersetzungen.py` (anhängen)

**Interfaces:**
- Consumes: aus Task 1 `ausgabe.BINAERSENSOREN`, `ausgabe.SENSOREN`, `ausgabe.LADEPLAN`, `ausgabe.ZUSTAENDE`; `const.ISSUE_SCHNELLER`, `const.ISSUE_LANGSAMER`.
- Produces: `entity.binary_sensor.<schlüssel>.name`, `entity.sensor.<schlüssel>.name`, `entity.sensor.plan.state.<zustand>`, `issues.ladung_schneller` und `issues.ladung_langsamer` mit `title` und `description` und den Platzhaltern `{fahrzeug}`, `{gemessen}`, `{geplant}`, `{abweichung}`.

- [ ] **Step 1: Die Tests anhängen**

Ans Ende von `tests/test_uebersetzungen.py`:

```python
# --- Die Entitaeten und das Issue aus C6 ------------------------------------
# ausgabe.py laedt standort.py relativ und kommt deshalb ueber ein Paket herein,
# dessen __init__.py nicht laeuft -- wie in test_ausgabe.py.

import importlib  # noqa: E402
import sys  # noqa: E402
import types  # noqa: E402

_PAKET = "meteo_volt_c6"
if _PAKET not in sys.modules:
    _paket = types.ModuleType(_PAKET)
    _paket.__path__ = [str(INTEGRATION)]
    sys.modules[_PAKET] = _paket
ausgabe = importlib.import_module(f"{_PAKET}.ausgabe")

PLATTFORMEN = (("binary_sensor", ausgabe.BINAERSENSOREN), ("sensor", ausgabe.SENSOREN))


@pytest.mark.parametrize("sprache", SPRACHEN)
@pytest.mark.parametrize(("plattform", "schluessel"), PLATTFORMEN)
def test_jede_entitaet_hat_einen_namen(sprache, plattform, schluessel):
    """Spec C6 Abschnitt 11. Ohne Namen leitete Home Assistant die entity_id
    allein aus dem Geraetenamen ab -- und die bleibt."""
    entitaeten = _laden(sprache).get("entity", {}).get(plattform, {})
    fehlend = [s for s in schluessel if not entitaeten.get(s, {}).get("name")]
    assert not fehlend, f"{sprache}/{plattform}: ohne Namen: {fehlend}"


@pytest.mark.parametrize("sprache", SPRACHEN)
def test_jeder_zustand_des_ladeplans_hat_einen_text(sprache):
    zustaende = _laden(sprache)["entity"]["sensor"][ausgabe.LADEPLAN].get("state", {})
    assert set(zustaende) == set(ausgabe.ZUSTAENDE), sprache
    assert all(zustaende.values()), sprache


@pytest.mark.parametrize("sprache", SPRACHEN)
@pytest.mark.parametrize("schluessel", [const.ISSUE_SCHNELLER, const.ISSUE_LANGSAMER])
def test_das_abweichungs_issue_ist_beschriftet(sprache, schluessel):
    """Spec C6 Abschnitt 6: jeder Platzhalter steht im Text, sonst verschwaende er still."""
    issue = _laden(sprache).get("issues", {}).get(schluessel, {})
    assert "{fahrzeug}" in issue.get("title", ""), f"{sprache}/{schluessel}"
    for platzhalter in ("{gemessen}", "{geplant}", "{abweichung}"):
        assert platzhalter in issue.get("description", ""), f"{sprache}/{schluessel}: {platzhalter}"
```

- [ ] **Step 2: Rot sehen**

Run: `.venv/Scripts/python.exe -m pytest -q tests/test_uebersetzungen.py`
Expected: `10 failed, 34 passed`

- [ ] **Step 3: Die deutschen Texte**

In `custom_components/meteo_volt/translations/de.json` ersetzen:

```json
  "issues": {
    "plan_veraltet": {
      "title": "Ladeplanung ohne neuen Plan",
      "description": "Seit 12 Stunden kam kein neuer Ladeplan. Letzter Fehler: {fehler}"
    }
  }
}
```

durch:

```json
  "entity": {
    "binary_sensor": {
      "charge_now": {
        "name": "Jetzt laden"
      },
      "feasible": {
        "name": "Plan erfüllbar"
      }
    },
    "sensor": {
      "charge_now_kw": {
        "name": "Geplante Ladeleistung"
      },
      "next_charge_start": {
        "name": "Nächster Ladestart"
      },
      "total_kwh": {
        "name": "Geplante Energie"
      },
      "total_cost": {
        "name": "Geplante Kosten"
      },
      "soc_end_pct": {
        "name": "Ladestand am Planende"
      },
      "plan": {
        "name": "Ladeplan",
        "state": {
          "kein_ladepunkt": "Kein Ladepunkt",
          "ladepunkt_geloescht": "Ladepunkt gelöscht",
          "ladestand_nicht_lesbar": "Ladestand nicht lesbar",
          "aktuell": "Aktuell",
          "kein_plan": "Kein Plan"
        }
      }
    }
  },
  "issues": {
    "plan_veraltet": {
      "title": "Ladeplanung ohne neuen Plan",
      "description": "Seit 12 Stunden kam kein neuer Ladeplan. Letzter Fehler: {fehler}"
    },
    "ladung_schneller": {
      "title": "{fahrzeug} lädt schneller als geplant",
      "description": "Gemessen {gemessen} %/h, geplant {geplant} %/h, also {abweichung} % schneller. Wahrscheinlich ist der Wirkungsgrad zu niedrig, die Kapazität zu groß oder die Ladeleistung zu klein eingetragen."
    },
    "ladung_langsamer": {
      "title": "{fahrzeug} lädt langsamer als geplant",
      "description": "Gemessen {gemessen} %/h, geplant {geplant} %/h, also {abweichung} % langsamer. Wahrscheinlich ist der Wirkungsgrad zu hoch, die Kapazität zu klein oder die Ladeleistung zu groß eingetragen. Es kann auch sein, dass die Wallbox weniger liefert, die Automation verspätet schaltet oder das Fahrzeug selbst begrenzt."
    }
  }
}
```

- [ ] **Step 4: Die englischen Texte**

In `custom_components/meteo_volt/translations/en.json` ersetzen:

```json
  "issues": {
    "plan_veraltet": {
      "title": "Charge planning without a new plan",
      "description": "No new charge plan for 12 hours. Last error: {fehler}"
    }
  }
}
```

durch:

```json
  "entity": {
    "binary_sensor": {
      "charge_now": {
        "name": "Charge now"
      },
      "feasible": {
        "name": "Plan feasible"
      }
    },
    "sensor": {
      "charge_now_kw": {
        "name": "Planned charging power"
      },
      "next_charge_start": {
        "name": "Next charge start"
      },
      "total_kwh": {
        "name": "Planned energy"
      },
      "total_cost": {
        "name": "Planned cost"
      },
      "soc_end_pct": {
        "name": "State of charge at plan end"
      },
      "plan": {
        "name": "Charge plan",
        "state": {
          "kein_ladepunkt": "No charge point",
          "ladepunkt_geloescht": "Charge point deleted",
          "ladestand_nicht_lesbar": "State of charge unreadable",
          "aktuell": "Current",
          "kein_plan": "No plan"
        }
      }
    }
  },
  "issues": {
    "plan_veraltet": {
      "title": "Charge planning without a new plan",
      "description": "No new charge plan for 12 hours. Last error: {fehler}"
    },
    "ladung_schneller": {
      "title": "{fahrzeug} charges faster than planned",
      "description": "Measured {gemessen} %/h, planned {geplant} %/h, {abweichung} % faster. The charging efficiency is probably set too low, the capacity too high or the charging power too low."
    },
    "ladung_langsamer": {
      "title": "{fahrzeug} charges slower than planned",
      "description": "Measured {gemessen} %/h, planned {geplant} %/h, {abweichung} % slower. The charging efficiency is probably set too high, the capacity too low or the charging power too high. The wallbox may also deliver less, the automation may switch late, or the vehicle may limit charging itself."
    }
  }
}
```

- [ ] **Step 5: Grün sehen**

Run: `.venv/Scripts/python.exe -m pytest -q tests/test_uebersetzungen.py`
Expected: `44 passed`

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: `312 passed`

- [ ] **Step 6: Commit**

```bash
git add custom_components/meteo_volt/translations/de.json custom_components/meteo_volt/translations/en.json tests/test_uebersetzungen.py
git diff --cached --name-only | while read f; do git show ":$f" | grep -q $'\r' && echo "CRLF: $f"; done
git commit -F - <<'EOF'
Name the vehicle entities and the deviation issue in both languages

Without a name Home Assistant would derive the entity_id from the device
name alone, and an entity_id stays.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 3: Die Verdrahtung in Home Assistant

**Files:**
- Create: `custom_components/meteo_volt/fahrzeugausgabe.py`
- Create: `custom_components/meteo_volt/binary_sensor.py`
- Create: `custom_components/meteo_volt/fahrzeugsensor.py`
- Modify: `custom_components/meteo_volt/sensor.py` (nach den sechs Sensoren)
- Modify: `custom_components/meteo_volt/__init__.py` (Plattform, Start der Auswertungen)

**Interfaces:**
- Consumes: alles aus Task 1; `const.DOMAIN`, `const.ISSUE_ABWEICHUNG`; `stammdaten.TYP_FAHRZEUG`, `stammdaten.FELD_SOC_ENTITAET`; `standort.ladestand_lesen`; vom Plan-Koordinator `data` (ein `Planstand`) und `async_add_listener`.
- Produces:
  - `fahrzeugausgabe.AUSGABEN = "meteo_volt_ausgaben"` — `hass.data[AUSGABEN][entry_id]` ist die `Fahrzeugausgaben` des Eintrags.
  - `Fahrzeugausgaben(hass, entry, koordinator)` mit `.async_starten()`, `.fahrzeug_ids() -> list[str]`, `.fuer(fahrzeug_id) -> Fahrzeugausgabe`.
  - `Fahrzeugausgabe` mit `.auswertung: ausgabe.Auswertung | None`, `.device_info`, `.async_zuhoeren(zuhoerer) -> CALLBACK_TYPE`.
  - `FahrzeugEntitaet(fahrzeugausgabe, beschreibung)` — `unique_id` `meteo_volt_{subentry_id}_{schlüssel}`, Gerät `(meteo_volt, <subentry_id>)`.
  - `fahrzeuge_anbinden(hass, entry, async_add_entities, bauen)`, `fahrzeugsensor.fahrzeugsensoren_anbinden(hass, entry, async_add_entities)`.

Kein automatischer Test: die Verdrahtung braucht Home Assistant. Einmalig geprüft wird, dass jeder benutzte Name in Home Assistant 2026.4.1 existiert; das Verhalten prüft die Abnahme.

Befunde aus dem Quelltext von Home Assistant 2026.4.1, auf denen der Code steht:

- Ein gelöschter Subentry räumt Geräte- und Entitätsregister (`config_entries.py`, `async_remove_subentry` ruft `async_clear_config_subentry`), und eine Entität, deren Registry-Eintrag verschwindet, verlässt Home Assistant (`helpers/entity.py`, `_async_registry_updated`).
- `async_add_entities(..., config_subentry_id=...)` funktioniert auch nach dem Setup der Plattform (`helpers/entity_platform.py`).
- Einen Subentry anlegen oder ändern lädt den Eintrag nicht neu, sondern ruft die Update-Listener. C5 löst dann einen Lauf aus, und `DataUpdateCoordinator` meldet jeden Lauf seinen Listenern (`always_update=True`).
- Den Namen aus `DeviceInfo` schreibt das Geräteregister jedes Mal, wenn Entitäten angelegt werden (`helpers/device_registry.py`, `async_get_or_create`).
- `SensorDeviceClass.ENUM` verlangt den Wert in `options`, `TIMESTAMP` eine Zeitzone (`components/sensor/__init__.py`). Ein nicht persistentes Issue kommt nach einem Neustart nicht wieder (`helpers/issue_registry.py`).

- [ ] **Step 1: Die Auswertung je Fahrzeug**

`custom_components/meteo_volt/fahrzeugausgabe.py`:

```python
"""Die Ausgabe je Fahrzeug in Home Assistant: Ausloeser, Timer, Issue.

Was C6 entscheidet, steht in ausgabe.py und ist dort ohne Home Assistant
geprueft. Hier steht nur die Verdrahtung: wann ein Fahrzeug ausgewertet wird,
wie seine Entitaeten davon erfahren, wann das Abweichungs-Issue kommt und geht
und wie Entitaeten fuer spaeter angelegte Fahrzeuge entstehen. Das sieht kein
automatischer Test, nur die Abnahme.

Spec: meteo-volt-brain/docs/features/C6-ausgabe-entitaeten/spec.md
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity, EntityDescription
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import (
    async_track_point_in_utc_time,
    async_track_state_change_event,
)
from homeassistant.util import dt as dt_util

from . import ausgabe, stammdaten, standort
from .const import DOMAIN, ISSUE_ABWEICHUNG
from .plankoordinator import MeteoVoltPlanKoordinator

# hass.data[AUSGABEN][entry_id]. Nicht unter hass.data[DOMAIN]: das lesen die
# sechs Sensoren (Bestandsschutz Auflage 5).
AUSGABEN = f"{DOMAIN}_ausgaben"


class Fahrzeugausgabe:
    """Wertet ein Fahrzeug aus und meldet es seinen Entitaeten. Spec Abschnitt 4."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        koordinator: MeteoVoltPlanKoordinator,
        fahrzeug_id: str,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.koordinator = koordinator
        self.fahrzeug_id = fahrzeug_id
        self.auswertung: ausgabe.Auswertung | None = None
        self._zustand = ausgabe.Zustand()
        self._daten: dict | None = None
        self._zuhoerer: list[Callable[[], None]] = []
        self._koordinator_abmelden: CALLBACK_TYPE | None = None
        self._ladestand: tuple[str, CALLBACK_TYPE] | None = None
        self._timer: CALLBACK_TYPE | None = None

    @property
    def device_info(self) -> DeviceInfo:
        """Spec Abschnitt 7. Den Namen schreibt Home Assistant nur beim Anlegen."""
        subentry = self.entry.subentries.get(self.fahrzeug_id)
        return DeviceInfo(
            identifiers={(DOMAIN, self.fahrzeug_id)},
            name=None if subentry is None else subentry.title,
            manufacturer="Meteo-Volt",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def _issue_id(self) -> str:
        return f"{ISSUE_ABWEICHUNG}_{self.fahrzeug_id}"

    @callback
    def async_starten(self) -> None:
        self._koordinator_abmelden = self.koordinator.async_add_listener(self._koordinator_meldet)
        self._auswerten()

    @callback
    def async_beenden(self) -> None:
        """Timer, Listener und Issue gehen mit dem Fahrzeug oder dem Eintrag."""
        if self._koordinator_abmelden is not None:
            self._koordinator_abmelden()
            self._koordinator_abmelden = None
        self._ladestand_abmelden()
        self._timer_absagen()
        ir.async_delete_issue(self.hass, DOMAIN, self._issue_id)

    @callback
    def async_zuhoeren(self, zuhoerer: Callable[[], None]) -> CALLBACK_TYPE:
        self._zuhoerer.append(zuhoerer)

        @callback
        def abmelden() -> None:
            self._zuhoerer.remove(zuhoerer)

        return abmelden

    # --- Anlaesse, Spec Abschnitt 4 ------------------------------------------

    @callback
    def _koordinator_meldet(self) -> None:
        daten = self._fahrzeugdaten()
        if daten is None:
            return  # geloescht; Fahrzeugausgaben raeumt auf
        if self._daten is not None and daten != self._daten:
            # Spec Abschnitt 6: aendern sich die Daten des Fahrzeugs, beginnt
            # die Messung neu, und das Issue geht.
            self._zustand = replace(self._zustand, abgleich=ausgabe.Abgleich())
            ir.async_delete_issue(self.hass, DOMAIN, self._issue_id)
        self._auswerten()

    @callback
    def _ladestand_meldet(self, _event: Event[EventStateChangedData]) -> None:
        self._auswerten()

    @callback
    def _timer_meldet(self, _jetzt: datetime) -> None:
        self._timer = None
        self._auswerten()

    # --- Die Auswertung --------------------------------------------------------

    @callback
    def _auswerten(self) -> None:
        daten = self._fahrzeugdaten()
        if daten is None:
            return
        self._daten = daten
        entitaet = daten.get(stammdaten.FELD_SOC_ENTITAET)
        self._ladestand_anmelden(entitaet)
        zustand = self.hass.states.get(entitaet) if entitaet else None
        self.auswertung = ausgabe.auswerten(
            self.koordinator.data,
            self.fahrzeug_id,
            dt_util.utcnow(),
            None if zustand is None else standort.ladestand_lesen(zustand.state),
            None if zustand is None else zustand.last_reported,
            self._zustand,
        )
        self._zustand = self.auswertung.zustand
        if self.auswertung.bewertung is not None:
            self._issue(self.auswertung.bewertung)
        self._timer_absagen()
        self._timer = async_track_point_in_utc_time(
            self.hass, self._timer_meldet, self.auswertung.naechste
        )
        for zuhoerer in list(self._zuhoerer):
            zuhoerer()

    @callback
    def _issue(self, bewertung: ausgabe.Bewertung) -> None:
        """Spec Abschnitt 6: ueber 5 % anlegen, sonst entfernen."""
        if not bewertung.ausserhalb:
            ir.async_delete_issue(self.hass, DOMAIN, self._issue_id)
            return
        subentry = self.entry.subentries.get(self.fahrzeug_id)
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            self._issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=ausgabe.issue_uebersetzung(bewertung),
            translation_placeholders=ausgabe.issue_platzhalter(
                bewertung,
                self.fahrzeug_id if subentry is None else subentry.title,
                self.hass.config.language,
            ),
        )

    # --- Hilfen -----------------------------------------------------------------

    def _fahrzeugdaten(self) -> dict | None:
        subentry = self.entry.subentries.get(self.fahrzeug_id)
        return None if subentry is None else dict(subentry.data)

    @callback
    def _ladestand_anmelden(self, entitaet: str | None) -> None:
        """Spec Abschnitt 4: bei der alten Ladestand-Entitaet ab, bei der neuen an."""
        if self._ladestand is not None and self._ladestand[0] == entitaet:
            return
        self._ladestand_abmelden()
        if entitaet:
            self._ladestand = (
                entitaet,
                async_track_state_change_event(self.hass, [entitaet], self._ladestand_meldet),
            )

    @callback
    def _ladestand_abmelden(self) -> None:
        if self._ladestand is not None:
            self._ladestand[1]()
            self._ladestand = None

    @callback
    def _timer_absagen(self) -> None:
        if self._timer is not None:
            self._timer()
            self._timer = None


class Fahrzeugausgaben:
    """Die Auswertungen aller Fahrzeuge eines Eintrags."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, koordinator: MeteoVoltPlanKoordinator
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.koordinator = koordinator
        self._ausgaben: dict[str, Fahrzeugausgabe] = {}

    @callback
    def async_starten(self) -> None:
        self.entry.async_on_unload(self.koordinator.async_add_listener(self._aufraeumen))
        self.entry.async_on_unload(self._alle_beenden)

    def fahrzeug_ids(self) -> list[str]:
        return [
            subentry.subentry_id
            for subentry in self.entry.subentries.values()
            if subentry.subentry_type == stammdaten.TYP_FAHRZEUG
        ]

    @callback
    def fuer(self, fahrzeug_id: str) -> Fahrzeugausgabe:
        if fahrzeug_id not in self._ausgaben:
            neu = Fahrzeugausgabe(self.hass, self.entry, self.koordinator, fahrzeug_id)
            self._ausgaben[fahrzeug_id] = neu
            neu.async_starten()
        return self._ausgaben[fahrzeug_id]

    @callback
    def _aufraeumen(self) -> None:
        """Spec Abschnitt 7: ein geloeschtes Fahrzeug beendet Timer, Listener und Issue."""
        for fahrzeug_id in list(self._ausgaben):
            if fahrzeug_id not in self.entry.subentries:
                self._ausgaben.pop(fahrzeug_id).async_beenden()

    @callback
    def _alle_beenden(self) -> None:
        for fahrzeugausgabe in self._ausgaben.values():
            fahrzeugausgabe.async_beenden()
        self._ausgaben.clear()


class FahrzeugEntitaet(Entity):
    """Eine der acht Entitaeten eines Fahrzeugs. Traegt die letzte Auswertung."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, fahrzeugausgabe: Fahrzeugausgabe, beschreibung: EntityDescription) -> None:
        self.entity_description = beschreibung
        self._fahrzeugausgabe = fahrzeugausgabe
        # Spec Abschnitt 2: meteo_volt_{subentry_id}_{schluessel}
        self._attr_unique_id = f"{DOMAIN}_{fahrzeugausgabe.fahrzeug_id}_{beschreibung.key}"
        self._attr_device_info = fahrzeugausgabe.device_info

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._fahrzeugausgabe.async_zuhoeren(self.async_write_ha_state))

    @property
    def _wert(self):
        auswertung = self._fahrzeugausgabe.auswertung
        return None if auswertung is None else auswertung.werte[self.entity_description.key]

    @property
    def extra_state_attributes(self) -> dict | None:
        auswertung = self._fahrzeugausgabe.auswertung
        if auswertung is None:
            return None
        return auswertung.attribute.get(self.entity_description.key) or None


@callback
def fahrzeuge_anbinden(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
    bauen: Callable[[Fahrzeugausgabe], list[Entity]],
) -> None:
    """Legt die Entitaeten jedes Fahrzeugs an, jetzt und fuer spaeter angelegte.

    Spec Abschnitt 7: ohne Neuladen des Eintrags. C5 loest bei einem neuen
    Fahrzeug einen Lauf aus, und danach meldet sich der Koordinator hier.
    Ohne Koordinator entsteht keine Entitaet (Abschnitt 8).
    """
    ausgaben: Fahrzeugausgaben | None = hass.data.get(AUSGABEN, {}).get(entry.entry_id)
    if ausgaben is None:
        return
    angelegt: set[str] = set()

    @callback
    def anlegen() -> None:
        vorhanden = ausgaben.fahrzeug_ids()
        angelegt.intersection_update(vorhanden)
        for fahrzeug_id in vorhanden:
            if fahrzeug_id not in angelegt:
                angelegt.add(fahrzeug_id)
                async_add_entities(
                    bauen(ausgaben.fuer(fahrzeug_id)), config_subentry_id=fahrzeug_id
                )

    anlegen()
    entry.async_on_unload(ausgaben.koordinator.async_add_listener(anlegen))
```

- [ ] **Step 2: Die Binärsensoren**

`custom_components/meteo_volt/binary_sensor.py`:

```python
"""Binaersensoren je Fahrzeug: Jetzt laden und Plan erfuellbar.

Eine neue Plattform. Scheitert ihr Aufbau, beruehrt das die sechs Sensoren
der Prognose nicht (Spec C6 Abschnitt 8).

Spec: meteo-volt-brain/docs/features/C6-ausgabe-entitaeten/spec.md
"""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ausgabe
from .fahrzeugausgabe import FahrzeugEntitaet, Fahrzeugausgabe, fahrzeuge_anbinden

BESCHREIBUNGEN = (
    BinarySensorEntityDescription(key=ausgabe.JETZT_LADEN, translation_key=ausgabe.JETZT_LADEN),
    BinarySensorEntityDescription(key=ausgabe.ERFUELLBAR, translation_key=ausgabe.ERFUELLBAR),
)


class FahrzeugBinaersensor(FahrzeugEntitaet, BinarySensorEntity):
    """Spec Abschnitt 2. Kein Attribut geht in den Recorder (Abschnitt 3)."""

    _unrecorded_attributes = frozenset(
        {ausgabe.QUELLE, ausgabe.ZIEL_ERREICHT, ausgabe.VIOLATIONS}
    )

    @property
    def is_on(self) -> bool | None:
        return self._wert


def _bauen(fahrzeugausgabe: Fahrzeugausgabe) -> list[FahrzeugBinaersensor]:
    return [FahrzeugBinaersensor(fahrzeugausgabe, b) for b in BESCHREIBUNGEN]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Die Binaersensoren aller Fahrzeuge, auch der spaeter angelegten."""
    fahrzeuge_anbinden(hass, entry, async_add_entities, _bauen)
```

- [ ] **Step 3: Die Sensoren je Fahrzeug**

`custom_components/meteo_volt/fahrzeugsensor.py`:

```python
"""Die Sensoren je Fahrzeug, fuer sensor.py.

Ein eigenes Modul, damit sensor.py es erst nach den sechs Sensoren der
Prognose laedt: scheitert schon der Import, laufen die sechs weiter
(Spec C6 Abschnitt 8).

Spec: meteo-volt-brain/docs/features/C6-ausgabe-entitaeten/spec.md
"""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ausgabe
from .fahrzeugausgabe import FahrzeugEntitaet, Fahrzeugausgabe, fahrzeuge_anbinden

# Spec Abschnitt 2. Keine state_class: Planwerte sind keine Zaehler, und mit
# state_class landeten sie in Langzeitstatistik und Energie-Dashboard.
BESCHREIBUNGEN = (
    SensorEntityDescription(
        key=ausgabe.LADELEISTUNG,
        translation_key=ausgabe.LADELEISTUNG,
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
    ),
    SensorEntityDescription(
        key=ausgabe.NAECHSTER_LADESTART,
        translation_key=ausgabe.NAECHSTER_LADESTART,
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    SensorEntityDescription(
        key=ausgabe.ENERGIE,
        translation_key=ausgabe.ENERGIE,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    ),
    SensorEntityDescription(
        key=ausgabe.KOSTEN,
        translation_key=ausgabe.KOSTEN,
        device_class=SensorDeviceClass.MONETARY,
        # MONETARY verlangt den ISO-4217-Code, nicht das Zeichen.
        native_unit_of_measurement="EUR",
    ),
    SensorEntityDescription(
        key=ausgabe.LADESTAND_PLANENDE,
        translation_key=ausgabe.LADESTAND_PLANENDE,
        # Keine Geraeteklasse battery: sonst sammelten Batterie-Karten eine Prognose ein.
        native_unit_of_measurement=PERCENTAGE,
    ),
    SensorEntityDescription(
        key=ausgabe.LADEPLAN,
        translation_key=ausgabe.LADEPLAN,
        device_class=SensorDeviceClass.ENUM,
        options=list(ausgabe.ZUSTAENDE),
    ),
)


class FahrzeugSensor(FahrzeugEntitaet, SensorEntity):
    """Spec Abschnitt 2. Kein Attribut geht in den Recorder (Abschnitt 3)."""

    _unrecorded_attributes = frozenset(
        {ausgabe.SLOTS, ausgabe.INTERVALS, ausgabe.WARNINGS, ausgabe.FEHLER}
    )

    @property
    def native_value(self):
        return self._wert


def _bauen(fahrzeugausgabe: Fahrzeugausgabe) -> list[FahrzeugSensor]:
    return [FahrzeugSensor(fahrzeugausgabe, b) for b in BESCHREIBUNGEN]


@callback
def fahrzeugsensoren_anbinden(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Die Sensoren aller Fahrzeuge, auch der spaeter angelegten."""
    fahrzeuge_anbinden(hass, entry, async_add_entities, _bauen)
```

- [ ] **Step 4: `sensor.py` nach den sechs Sensoren ergänzen**

In `custom_components/meteo_volt/sensor.py` ersetzen:

```python
        MeteoVoltTimestampSensor(coordinator, entry.entry_id, "computed_at", "Computed At"),
    ])
```

durch:

```python
        MeteoVoltTimestampSensor(coordinator, entry.entry_id, "computed_at", "Computed At"),
    ])

    # Spec C6 Abschnitt 8: die sechs zuerst, die Fahrzeugsensoren danach und
    # abgeschirmt. Auch der Import steht im try: scheitert er, laufen die sechs.
    try:
        from .fahrzeugsensor import fahrzeugsensoren_anbinden

        fahrzeugsensoren_anbinden(hass, entry, async_add_entities)
    except Exception:  # pylint: disable=broad-except
        _LOGGER.exception("Fahrzeugsensoren nicht angelegt, die Prognose laeuft weiter")
```

Sonst ändert sich an `sensor.py` nichts.

- [ ] **Step 5: `__init__.py` ergänzen**

In `custom_components/meteo_volt/__init__.py` drei Stellen. Erstens ersetzen:

```python
PLATFORMS: list[Platform] = [Platform.SENSOR]
```

durch:

```python
PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]
```

Zweitens ersetzen:

```python
    else:
        entry.runtime_data = plan_koordinator
```

durch:

```python
    else:
        entry.runtime_data = plan_koordinator
        _ausgaben_starten(hass, entry, plan_koordinator)
```

Drittens vor `async def async_unload_entry(` einfügen:

```python
def _ausgaben_starten(
    hass: HomeAssistant, entry: ConfigEntry, plan_koordinator: MeteoVoltPlanKoordinator
) -> None:
    """Spec C6 Abschnitt 8: die Auswertung je Fahrzeug, fuer beide Plattformen.

    Scheitert sie, fehlen nur die Fahrzeugentitaeten; Prognose und Plan laufen
    weiter. Der Import steht deshalb mit im try.
    """
    try:
        from .fahrzeugausgabe import AUSGABEN, Fahrzeugausgaben

        ausgaben = Fahrzeugausgaben(hass, entry, plan_koordinator)
        ausgaben.async_starten()
    except Exception:  # pylint: disable=broad-except
        _LOGGER.exception("Ausgabe je Fahrzeug nicht gestartet, die Prognose laeuft weiter")
        return
    hass.data.setdefault(AUSGABEN, {})[entry.entry_id] = ausgaben
    entry.async_on_unload(lambda: hass.data[AUSGABEN].pop(entry.entry_id, None))


```

- [ ] **Step 6: Jeden Namen gegen Home Assistant 2026.4.1 prüfen**

Einmalig und nicht committet. Als `<scratchpad>/ha_namen_pruefen.py` speichern:

```python
"""Einmal-Pruefung: gibt es jeden Namen aus Home Assistant, den C6 benutzt, in 2026.4.1?

Das Gate kann Home Assistant nicht laden. Ein falscher Name faellt erst beim
Laden der Integration auf -- in sensor.py dann ohne die Fahrzeugsensoren, in
__init__.py ohne jede Fahrzeugentitaet.

Aufruf aus dem ha-Repo:  .venv/Scripts/python.exe <pfad>/ha_namen_pruefen.py [Integrationsordner]
"""

import ast
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASIS = "https://raw.githubusercontent.com/home-assistant/core/2026.4.1/"
INTEGRATION = Path(sys.argv[1] if len(sys.argv) > 1 else "custom_components/meteo_volt")
DATEIEN = ("fahrzeugausgabe.py", "fahrzeugsensor.py", "binary_sensor.py", "sensor.py", "__init__.py")

# Namen, die als Attribut, Methode oder Parameter benutzt und nicht importiert werden.
AUFRUFE = [
    ("homeassistant.helpers.issue_registry", "async_create_issue"),
    ("homeassistant.helpers.issue_registry", "async_delete_issue"),
    ("homeassistant.helpers.issue_registry", "IssueSeverity"),
    ("homeassistant.util.dt", "utcnow"),
    ("homeassistant.config_entries", "async_on_unload"),
    ("homeassistant.config_entries", "subentries"),
    ("homeassistant.config_entries", "subentry_id"),
    ("homeassistant.config_entries", "subentry_type"),
    ("homeassistant.helpers.update_coordinator", "async_add_listener"),
    ("homeassistant.helpers.entity_platform", "config_subentry_id"),
    ("homeassistant.helpers.entity", "async_on_remove"),
    ("homeassistant.helpers.entity", "async_write_ha_state"),
    ("homeassistant.helpers.entity", "extra_state_attributes"),
    ("homeassistant.helpers.entity", "translation_key"),
    ("homeassistant.helpers.entity", "_attr_has_entity_name"),
    ("homeassistant.helpers.entity", "_attr_should_poll"),
    ("homeassistant.helpers.entity", "_unrecorded_attributes"),
    ("homeassistant.components.sensor", "native_value"),
    ("homeassistant.components.sensor", "options"),
    ("homeassistant.components.binary_sensor", "is_on"),
    ("homeassistant.core", "last_reported"),
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
    # Weitergereicht: "from .const import (..., SensorDeviceClass, ...)" im
    # Paket, auch ueber mehrere Zeilen. So stellt sensor/__init__.py seine
    # Geraeteklassen bereit.
    weitergereicht = (
        rf"^\s*from\s+\S+\s+import\s+[^(\n]*\b{re.escape(name)}\b"
        rf"|^\s*{re.escape(name)}\s*,?\s*$"
    )
    if re.search(weitergereicht, text, re.MULTILINE):
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
sed -i 's/async_track_point_in_utc_time,/async_track_point_in_utc_tim,/' "<scratchpad>/gegenprobe/fahrzeugausgabe.py"
.venv/Scripts/python.exe "<scratchpad>/ha_namen_pruefen.py" "<scratchpad>/gegenprobe"; echo "exit=$?"
```

Expected: `FEHLT in Home Assistant 2026.4.1:` mit genau der Zeile `fahrzeugausgabe.py: from homeassistant.helpers.event import async_track_point_in_utc_tim`, danach `exit=1`

Run: `.venv/Scripts/python.exe <scratchpad>/ha_namen_pruefen.py`
Expected: `alle 62 Namen in Home Assistant 2026.4.1 gefunden`

- [ ] **Step 7: Suite und Commit**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: `312 passed` — `test_overrides.py` parst dabei auch die drei neuen Dateien.

```bash
git add custom_components/meteo_volt/fahrzeugausgabe.py custom_components/meteo_volt/binary_sensor.py custom_components/meteo_volt/fahrzeugsensor.py custom_components/meteo_volt/sensor.py custom_components/meteo_volt/__init__.py
git diff --cached --name-only | while read f; do git show ":$f" | grep -q $'\r' && echo "CRLF: $f"; done
git commit -F - <<'EOF'
Wire the vehicle entities into Home Assistant

Every vehicle gets a device with eight entities, evaluated on each plan,
each state of charge change, each slot boundary and twelve hours after a
plan arrived. Vehicles added later get their entities without a reload.
The six forecast sensors are created first and do not depend on any of it.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---
### Task 4: README — Ladeplanung

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: die Namen aus Task 2 und die Attribute aus Task 1.
- Produces: den Abschnitt „Charge planning" mit der Beispielautomation, die nach A0-Spec Abschnitt 13 die geteilte Wallbox benennt.

- [ ] **Step 1: Den Abschnitt einfügen**

In `README.md` direkt vor der Zeile `## Troubleshooting` einfügen, mit einer Leerzeile danach:

````markdown
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
````

- [ ] **Step 2: Suite und Commit**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: `312 passed`

```bash
git add README.md
git diff --cached --name-only | while read f; do git show ":$f" | grep -q $'\r' && echo "CRLF: $f"; done
git commit -F - <<'EOF'
Document charge planning in the README

What the eight entities mean, an automation that follows Charge now and
names the shared wallbox case, and a chart of the slot grid.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Nachtrag: Befunde der Prüfung

Nach Task 4 hat ein Subagent ohne Vorwissen den Stand geprüft. Zuerst wurde die Spec korrigiert (Brain `55c95b9`), dann der Code, jeder Befund mit Test und grüner Suite. Die Codeblöcke in den Tasks 1 bis 4 zeigen den Stand davor.

| # | Befund | Behoben durch |
|---|---|---|
| 1 | Die `lambda` an `async_on_unload` gab ein Objekt zurück. Das Entladen scheiterte, nach dem Neuladen blieben die sechs Sensoren nicht verfügbar. | eine benannte Funktion; `tests/test_verdrahtung.py` |
| 2 | Eine Ladestand-Meldung speicherte neue Fahrzeugdaten vor dem Vergleich. Messung und Issue blieben. | Vergleich und Entscheidung über das Issue in `ausgabe.py` |
| 3 | Der Test ohne Anstieg scheiterte schon an der Mindestzahl von drei Punkten. | eine Reihe 50/51, Gegenprobe mit 52 |
| 4 | Der Pausentest prüfte nur die gemessene Steigung. | auch Zeitpunkt der Bewertung und geplante Rate |
| 5 | Ein Importfehler in `binary_sensor.py` hätte das Einrichten des ganzen Eintrags abgebrochen. | `fahrzeugbinaersensor.py`, im `try` geladen; `tests/test_verdrahtung.py` |
| 6 | `ladestand_nicht_lesbar` erscheint erst mit dem nächsten Lauf. | Spec Abschnitt 2.2, Abnahmeschritt 8 |
| 7 | Der Test der Sperre gegen einen neuen Plan nutzte denselben Plan. | ein Plan, der den Block verlängert |
| 8 | Die Beispielautomation im README setzte die Ladeleistung nicht. | `number.set_value`, `mode: queued` |

Jeder neue oder geschärfte Test ist gegen eine Mutante geprüft: die Regel verändert, der Test rot. Die Namensprüfung fand danach alle 66 Namen. Suite: 316 grün.

---

### Task 5: Die Beta

**Files:**
- Modify: `custom_components/meteo_volt/manifest.json`

**Interfaces:**
- Consumes: den Stand nach dem Nachtrag.
- Produces: den Prerelease `1.1.0-beta.9` auf dem Commit dieses Tasks.

Die Regeln stehen in `CLAUDE.md`, Abschnitt „Betas gehen über HACS". `gh` ist auf diesem Rechner nicht installiert — das Release entsteht in der GitHub-Oberfläche.

- [ ] **Step 1: Die Version setzen**

In `custom_components/meteo_volt/manifest.json` ersetzen:

```json
  "version": "1.1.0-beta.8"
```

durch:

```json
  "version": "1.1.0-beta.9"
```

- [ ] **Step 2: Suite, Kontrakt, Commit**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: `316 passed`

Run: `.venv/Scripts/python.exe scripts/check_contract.py`
Expected: `Kontrakt in sync (35 Dateien geprueft)`

```bash
git add custom_components/meteo_volt/manifest.json
git diff --cached --name-only | while read f; do git show ":$f" | grep -q $'\r' && echo "CRLF: $f"; done
git commit -F - <<'EOF'
Number this beta 1.1.0-beta.9

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

- [ ] **Step 3: Patrick fragen, dann pushen**

Erst nach seinem Ja, in beiden Repos:

```bash
git ls-remote origin refs/tags/1.1.0-beta.9
git push -u origin c6-ausgabe-entitaeten
git rev-parse HEAD
```

Expected: die erste Zeile gibt nichts aus (der Tag ist neu), der Push geht durch, die letzte Zeile nennt den Commit für das Release. Im Brain nur der Push des Branches `c6-ausgabe-entitaeten`.

- [ ] **Step 4: Patrick legt das Prerelease an**

In GitHub unter Releases: Tag `1.1.0-beta.9` — GitHub muss ihn als **neu** anzeigen. Target ist der Commit aus Step 3, gewählt unter „Recent commits". „Set as a pre-release" an, „Set as the latest release" aus.

- [ ] **Step 5: Nachmessen**

```bash
git fetch --tags origin
git ls-remote origin refs/tags/1.1.0-beta.9
git show 1.1.0-beta.9:custom_components/meteo_volt/manifest.json | grep '"version"'
```

Expected: der Tag zeigt auf den Commit aus Step 3, das Manifest im Tag nennt `1.1.0-beta.9`. Stimmt eins nicht: Release samt Tag löschen und neu anlegen, solange niemand die Version installiert hat.

---

## Abnahme — macht Patrick

Auf der eigenen Instanz mit Home Assistant 2026.4.1 und `1.1.0-beta.9`. Vorher ist C6 nicht fertig. Die Schritte sind die aus Spec Abschnitt 11.

**Vorbereitung.** In HACS „Repository-Informationen aktualisieren", `1.1.0-beta.9` herunterladen, Home Assistant neu starten. `const_overwrite.json` zeigt wie bei C5 auf eine Umgebung mit Plan-Route. Auf der Seite der Integration „Debug-Logging aktivieren". Für Schritt 6 ein Helfer `input_number` von 0 bis 100 in Schritten von 1. Für Schritt 12 ein `input_boolean` als Test-Schalter und ein `input_number` von 0 bis 22 in Schritten von 0,1 als Sollwert; in der Beispielautomation dann `input_boolean.turn_on`, `input_boolean.turn_off` und `input_number.set_value` statt `switch` und `number`.

**Hinweis zur Ladestand-Entität.** Eingetragen ist `sensor.id_buzz_soc`, das wie `…_battery` nur alle 15 min meldet. `sensor.id_buzz_ladezustand` meldete am 2026-09-10 etwa alle 4 min; damit stoppt „Jetzt laden" genauer.

1. **Das Update einspielen:** die sechs Sensoren behalten `entity_id` und Historie.
2. **Das Gerät:** am Fahrzeug steht ein Gerät mit acht Entitäten, benannt in der Sprache der Instanz.
3. **`dev_plan` aufrufen:** Zustände und Attribute passen zu `plan` und `jetzt` der Antwort, die Kosten zu `total_cost_incl_fees_eur`.
4. **Recorder:** nach mehreren Plänen steht im Log keine Warnung, dass Attribute die Größe überschreiten.
5. **Slotgrenze:** an einer Slotgrenze wechselt „Jetzt laden" wie der Plan, ohne neuen Aufruf im Debug-Log.
6. **Stopp am Ladestand:** die Ladestand-Entität des Fahrzeugs auf die `input_number` stellen. Während eines Blocks den Wert auf das Blockziel setzen: „Jetzt laden" geht aus, `ziel_erreicht` ist `true`, die Leistung `0`. Den Wert wieder senken: es bleibt aus bis zum Blockende.
7. **Ohne Plan,** etwa über eine Überschreibung auf einen nicht erreichbaren Host und einen Neustart: der Ladeplan zeigt `kein_plan` mit `fehler`, die Planwerte sind unbekannt, „Jetzt laden" trägt `quelle: default`.
8. **Ladestand nicht lesbar:** die Ladestand-Entität meldet `unavailable`, danach `dev_plan` aufrufen — der Ladeplan zeigt `ladestand_nicht_lesbar`. Ohne Aufruf zeigt er das erst nach dem nächsten Lauf, denn dafür löst C5 keinen aus.
9. **Zweites Fahrzeug:** anlegen — binnen 30 s stehen Gerät und acht Entitäten, und die sechs Sensoren werden dabei nicht unavailable. Wieder löschen — Gerät und Entitäten sind weg.
10. **Neu laden:** den Eintrag neu laden (Integration, ⋮, Neu laden) — im Log steht kein Fehler, die sechs Sensoren und die Entitäten der Fahrzeuge sind wieder da.
11. **Abweichung:** den Wirkungsgrad auf 80 % stellen und mindestens 2 h nach Plan laden — das Issue „lädt schneller" erscheint mit Zahlen. Den Wirkungsgrad zurückstellen — das Issue ist weg.
12. **README:** die Beispielautomation auf die Test-Helfer — der Schalter folgt „Jetzt laden", der Sollwert „Geplante Ladeleistung". Die ApexCharts-Karte zeigt Leistung und Ladestand.
13. **Durchgehend:** die sechs Sensoren laufen in allen Schritten weiter.

Den Rückfall bei veraltetem Ladestand prüft die Abnahme nicht: dafür müsste ein Wert über dem Ziel 31 min lang ohne neue Meldung stehen, während der Plan lädt. Das deckt `tests/test_ausgabe.py`.

**Aufräumen:** die Ladestand-Entität zurückstellen, `const_overwrite.json` löschen, neu starten, Debug-Logging aus.

## Nach der Abnahme

Erst nach Patricks Ja:

- **Brain**, Branch `c6-ausgabe-entitaeten`: in `docs/features/C6-ausgabe-entitaeten/feature.md` `status = "spezifiziert"` auf `status = "fertig"`, beim Punkt `C6A` ebenso. Dann `meteovolt_plan/.venv/Scripts/python.exe scripts/build_docs.py` und das Gate `meteovolt_plan/.venv/Scripts/python.exe scripts/run_tests.py -q`, Commit.
- **Beide Branches nach `beta` mergen**, im Brain und im ha-Repo, jeweils mit `--no-ff`. Pushen erst nach Rückfrage.

## Was dieser Plan nicht baut

| Nicht hier | Wo |
|---|---|
| Werte für den ganzen Standort, `charge_now_station_id`, mehrere Fahrzeuge an einer Wallbox | `E1`, `Z4` |
| Regler je Fahrzeug | `C3` |
| Ziele, `meteo_volt.replan`, ob `get_plan` noch nötig ist | `C4` |
| Ein neuer Plan, wenn ein Block früh stoppt oder sein Ziel verfehlt | offen |
| Plan, Sperre und Messung über einen Neustart retten | offen |
| Die Dev-Action | bleibt temporär, C5-Spec Abschnitt 10 |
