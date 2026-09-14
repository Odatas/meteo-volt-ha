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


# --- Naechster Versuch, Spec Abschnitt 7 ------------------------------------


@pytest.mark.parametrize(("fehler", "erwartet"), [
    (None, (standort.WEITER_IM_GRUNDTAKT, None)),
    (planabruf.PlanRateLimit(retry_after=39.0, status=429), (standort.NACHHOLEN, 39.0)),
    (planabruf.PlanNichtVerfuegbar(status=503), (standort.NACHHOLEN, 300.0)),
    (planabruf.PlanAbgelehnt(status=404), (standort.PAUSE, None)),
    (planabruf.PlanNichtAutorisiert(status=401), (standort.STOPP, None)),
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


# --- Nachgebessert nach der Pruefung am 2026-09-14 --------------------------


@pytest.mark.parametrize("fehler", [
    planabruf.PlanNichtVerfuegbar(status=503),
    planabruf.PlanRateLimit(retry_after=39.0, status=429),
], ids=["nicht-verfuegbar", "rate-limit"])
def test_ein_gescheiterter_nachholversuch_plant_keinen_weiteren(fehler):
    """Spec Abschnitt 7: einmal nachholen, danach im Grundtakt -- nicht alle 5 min."""
    assert standort.naechster_versuch(fehler, nur_nachholen=True) == (
        standort.WEITER_IM_GRUNDTAKT, None)


def test_abgelehnt_und_key_fehler_gelten_auch_beim_nachholen():
    abgelehnt = planabruf.PlanAbgelehnt(status=404)
    key_fehler = planabruf.PlanNichtAutorisiert(status=401)
    assert standort.naechster_versuch(abgelehnt, nur_nachholen=True) == (standort.PAUSE, None)
    assert standort.naechster_versuch(key_fehler, nur_nachholen=True) == (standort.STOPP, None)


@pytest.mark.parametrize("grund", [
    standort.GRUND_KEIN_LADEPUNKT, standort.GRUND_LADEPUNKT_GELOESCHT])
def test_ohne_gueltigen_ladepunkt_steuert_der_alte_plan_nicht_weiter(grund):
    """Spec Abschnitt 8: ein Plan fuer einen geloeschten Ladepunkt gilt nicht mehr."""
    anfrage, plan = _fixture("minimal")
    jetzt = datetime.fromisoformat(anfrage["now"])
    stand = standort.Planstand(plan=plan, erhalten_um=jetzt, ausgelassen={"auto-a": grund})
    gilt = standort.was_gilt(stand, "auto-a", jetzt, 5.0)
    assert (gilt["quelle"], gilt["charge_now"]) == (standort.QUELLE_DEFAULT, False)


def test_ein_unlesbarer_ladestand_laesst_den_alten_plan_gelten():
    anfrage, plan = _fixture("minimal")
    jetzt = datetime.fromisoformat(anfrage["now"])
    stand = standort.Planstand(
        plan=plan, erhalten_um=jetzt, ausgelassen={"auto-a": standort.GRUND_LADESTAND})
    assert standort.was_gilt(stand, "auto-a", jetzt, None)["quelle"] == standort.QUELLE_PLAN


@pytest.mark.parametrize("plan", [
    {},
    {"horizon_end": "2026-08-19T00:00:00+02:00", "slot_minutes": 15, "vehicles": None},
    {"horizon_end": "kein Datum", "slot_minutes": 15, "vehicles": []},
    {"horizon_end": "2026-08-19T00:00:00+02:00", "slot_minutes": 15,
     "vehicles": [{"id": "auto-a", "slots": [{"charge": True}]}]},
], ids=["leer", "vehicles-null", "horizon-kaputt", "slot-ohne-t"])
def test_eine_antwort_ohne_plan_form_ergibt_den_default(plan):
    """Spec Abschnitt 8: der Plan-Client prueft eine 200 nicht gegen das Schema."""
    jetzt = datetime.fromisoformat("2026-08-18T22:00:00+02:00")
    stand = standort.Planstand(plan=plan, erhalten_um=jetzt)
    assert standort.was_gilt(stand, "auto-a", jetzt, None)["quelle"] == standort.QUELLE_DEFAULT


def test_der_default_laedt_nicht_an_einem_nicht_verfuegbaren_ladepunkt():
    anfrage, _ = _bauen([("wb-1", _ladepunkt(available=False))], EIN_FAHRZEUG)
    gilt = standort.was_gilt(standort.Planstand(anfrage=anfrage), "auto-1", VORMITTAG, 5.0)
    assert (gilt["charge_now"], gilt["charge_now_kw"]) == (False, 0.0)


def test_negative_netzkosten_fehlen_im_request():
    """Spec Abschnitt 4: der Kontrakt verlangt >= 0 und lehnte sonst jeden Request ab."""
    anfrage, _ = _bauen(EIN_LADEPUNKT, EIN_FAHRZEUG, haupteintrag={const.CONF_GRID_FEES: -0.02})
    jsonschema.validate(anfrage, REQUEST_SCHEMA)
    assert "site" not in anfrage


def test_geht_die_uhr_im_haus_nach_gilt_der_erste_slot():
    """Spec Abschnitt 8: weniger als einen Slot vor dem ersten gilt der erste."""
    anfrage, plan = _fixture("second_block")
    beginn = datetime.fromisoformat(anfrage["now"])
    stand = _stand(anfrage, plan, beginn)
    knapp = standort.was_gilt(stand, "auto-a", beginn - timedelta(seconds=2), None)
    assert (knapp["quelle"], knapp["charge_now"], knapp["current_slot_end"]) == (
        standort.QUELLE_PLAN, True, beginn + timedelta(minutes=15))
    zu_weit = standort.was_gilt(stand, "auto-a", beginn - timedelta(minutes=15), None)
    assert zu_weit["quelle"] == standort.QUELLE_DEFAULT


@pytest.mark.parametrize(("takt", "vor", "erwartet"), [
    ("grundtakt", timedelta(minutes=5), "grundtakt"),
    ("pause", timedelta(hours=11, minutes=59), None),
    ("pause", timedelta(hours=12), "herzschlag"),
    ("pause", None, "herzschlag"),
    ("stopp", timedelta(days=3), None),
], ids=["grundtakt", "pause-knapp", "pause-herzschlag", "pause-ohne-versuch", "stopp"])
def test_nach_abgelehnt_nur_der_herzschlag_nach_key_fehler_nichts(takt, vor, erwartet):
    """Spec Abschnitt 7, entschieden am 2026-09-14."""
    jetzt = datetime(2026, 9, 14, 20, 0, tzinfo=timezone.utc)
    letzter = None if vor is None else jetzt - vor
    assert standort.takt_ausloeser(takt, letzter, jetzt) == erwartet
