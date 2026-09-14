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
# Die Daten aus dem Subentry. ausgabe.py vergleicht sie nur, ein Ausschnitt genuegt.
DATEN = {"name": "Auto A", "capacity_kwh": 58.0, "efficiency_pct": 94}


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


def _auswerten(stand, jetzt, soc=None, gemeldet=None, zustand=LEER, fahrzeug_id="auto-a",
               daten=DATEN):
    # Jedes Mal eine neue Kopie: verglichen wird der Inhalt, nicht das Objekt.
    return ausgabe.auswerten(stand, fahrzeug_id, jetzt, soc, gemeldet, zustand, dict(daten))


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


def _issues(auswertungen):
    return [a.issue for a in auswertungen if a.issue is not None]


def test_genau_nach_plan_gibt_es_keine_warnung():
    auswertungen = _laden_ueber(_stand("infeasible"), GEPLANT, 30.0, _abend("00:00"))
    bewertungen = _bewertungen(auswertungen)
    assert len(bewertungen) == 1
    assert bewertungen[0].gemessen == pytest.approx(GEPLANT)
    assert bewertungen[0].geplant == pytest.approx(GEPLANT)
    assert not bewertungen[0].ausserhalb
    assert _issues(auswertungen) == [ausgabe.ENTFERNEN]


@pytest.mark.parametrize(("faktor", "uebersetzung"), [
    (1.08, "ladung_schneller"), (0.92, "ladung_langsamer")])
def test_acht_prozent_daneben_warnt_mit_richtung(faktor, uebersetzung):
    auswertungen = _laden_ueber(_stand("infeasible"), GEPLANT * faktor, 30.0, _abend("00:00"))
    bewertungen = _bewertungen(auswertungen)
    assert len(bewertungen) == 1
    assert bewertungen[0].abweichung == pytest.approx(faktor - 1)
    assert bewertungen[0].ausserhalb
    assert ausgabe.issue_uebersetzung(bewertungen[0]) == uebersetzung
    assert _issues(auswertungen) == [ausgabe.ANLEGEN]


def test_ganzzahlig_alle_15_minuten_nach_plan_gibt_es_keine_warnung():
    auswertungen = _laden_ueber(
        _stand("infeasible"), GEPLANT, 30.0, _abend("00:00"), alle_min=15, abrunden=True)
    bewertungen = _bewertungen(auswertungen)
    assert len(bewertungen) == 1
    assert not bewertungen[0].ausserhalb, bewertungen[0].abweichung


def test_unter_zwei_stunden_wird_nicht_bewertet():
    assert _bewertungen(
        _laden_ueber(_stand("infeasible"), GEPLANT, 30.0, _abend("23:55"))) == []


@pytest.mark.parametrize(("letzter", "bewertet"), [(50.0, False), (52.0, True)])
def test_ohne_anstieg_wird_nicht_bewertet(letzter, bewertet):
    """Fuenf Punkte in 2 h, der Ladestand pendelt nur zwischen 50 und 51.

    Endet dieselbe Reihe bei 52, wird sie bewertet: das None kommt von der
    Regel, nicht von zu wenigen Punkten.
    """
    punkte = tuple((1, 1800.0 * i, soc)
                   for i, soc in enumerate((50.0, 51.0, 50.0, 51.0, letzter)))
    abgleich = ausgabe.Abgleich(ladezeit_s=7200.0, geplant_pp=2 * GEPLANT, punkte=punkte)
    assert (ausgabe.bewerten(abgleich) is not None) is bewertet


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


def test_geaenderte_daten_beginnen_die_messung_neu_und_nehmen_das_issue_zurueck():
    """Wirkungsgrad um 23:00 geaendert: bis Mitternacht kommt die neue Messung nicht auf 2 h.

    Dieselben Daten in einem neuen Objekt aendern nichts. Das zeigt
    test_genau_nach_plan_gibt_es_keine_warnung, deren Messung durchlaeuft.
    """
    stand, zustand = _stand("infeasible"), ausgabe.Zustand()
    geaendert = {**DATEN, "efficiency_pct": 80}
    issues, bewertungen = [], []
    jetzt = JETZT
    while jetzt <= _abend("00:00"):
        soc = 30.0 + GEPLANT * (jetzt - JETZT).total_seconds() / 3600
        auswertung = _auswerten(stand, jetzt, soc, jetzt, zustand,
                                daten=DATEN if jetzt < _abend("23:00") else geaendert)
        zustand = auswertung.zustand
        issues.append((jetzt, auswertung.issue))
        bewertungen.append(auswertung.bewertung)
        jetzt += timedelta(minutes=5)
    assert [(t, issue) for t, issue in issues if issue is not None] == [
        (_abend("23:00"), ausgabe.ENTFERNEN)]
    assert bewertungen == [None] * len(bewertungen)


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
