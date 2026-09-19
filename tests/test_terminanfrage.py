"""Prueft, was aus Terminen im Request wird, ohne Home Assistant. Spec C3 Abschnitte 4 und 10.

Der Request wird gegen das vendorte plan-request.schema.json geprueft, mit
der Form trips aus A5V. jsonschema prueft format date-time ohne FormatChecker
nicht; dass jeder Zeitpunkt einen Offset traegt (R1), prueft deshalb ein
eigener Test.

Was dieser Test NICHT sieht: wie der Plan-Dienst trips bucht. Das prueft
der Brain.
"""

import importlib
import json
import sys
import types
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import jsonschema

WURZEL = Path(__file__).resolve().parents[1]
INTEGRATION = WURZEL / "custom_components" / "meteo_volt"
CONTRACT = WURZEL / "tests" / "fixtures" / "contract"

_PAKET = "meteo_volt_c3"
if _PAKET not in sys.modules:
    _paket = types.ModuleType(_PAKET)
    _paket.__path__ = [str(INTEGRATION)]
    sys.modules[_PAKET] = _paket
termine = importlib.import_module(f"{_PAKET}.termine")
terminanfrage = importlib.import_module(f"{_PAKET}.terminanfrage")
standort = importlib.import_module(f"{_PAKET}.standort")
stammdaten = importlib.import_module(f"{_PAKET}.stammdaten")

BERLIN = ZoneInfo("Europe/Berlin")
JETZT = datetime(2026, 9, 16, 10, 0, tzinfo=timezone.utc)  # 12:00 in Berlin
BIS = JETZT + timedelta(days=7)

_ROH = json.loads((CONTRACT / "plan-request.schema.json").read_text(encoding="utf-8"))
REQUEST_SCHEMA = {k: v for k, v in _ROH.items() if k != "x-meteo-volt-contract"}


def _eintrag(eintrag_id, abfahrt, dauer=600, soc=None, fahrzeug="auto-1", wiederholung="once"):
    return {"id": eintrag_id, "vehicle": fahrzeug, "departure": abfahrt, "duration_min": dauer,
            "repeat": wiederholung, "distance_km": 42, "driver": None, "soc": soc, "until": None,
            "exceptions": {}}


def _fragmente(*eintraege, soc_min=None):
    auswahl = termine.ausrollen(list(eintraege), BERLIN, JETZT, BIS)
    return terminanfrage.fragmente(auswahl, soc_min or {"auto-1": 15.0}, JETZT)


def _anfrage(termine_je_fahrzeug, risiko=2):
    fahrzeug = {**stammdaten.FAHRZEUG_DEFAULTS, stammdaten.FELD_SOC_ENTITAET: "sensor.soc"}
    anfrage, ausgelassen = standort.anfrage_bauen(
        [("wb-1", dict(stammdaten.LADEPUNKT_DEFAULTS))],
        [("auto-1", fahrzeug), ("auto-2", dict(fahrzeug))],
        {fid: standort.Messung(zustand="47.5", gemeldet=JETZT) for fid in ("auto-1", "auto-2")},
        {"grid_fees": 0.0}, "Europe/Berlin", termine=termine_je_fahrzeug, risiko=risiko)
    assert ausgelassen == {}
    return anfrage


# --- Bis wohin ausgerollt wird ----------------------------------------------


def test_ausgerollt_wird_bis_zum_horizont_des_letzten_plans():
    ende = "2026-09-23T00:00:00+02:00"
    assert terminanfrage.ausrollen_bis({"horizon_end": ende}, JETZT) == datetime.fromisoformat(ende)


def test_ohne_plan_oder_mit_abgelaufenem_14_tage():
    for plan in (None, {}, {"horizon_end": "kaputt"}, {"horizon_end": "2026-09-16T12:00:00+02:00"}):
        assert terminanfrage.ausrollen_bis(plan, JETZT) == JETZT + timedelta(days=14), plan


# --- Die IDs ------------------------------------------------------------------


def test_jede_id_zerlegt_sich_zurueck():
    for art in ("weg", "ziel"):
        text = terminanfrage.kennung("3f2a9c", date(2026, 9, 17), art)
        assert text == f"3f2a9c/2026-09-17/{art}"
        assert terminanfrage.zerlegen(text) == ("3f2a9c", date(2026, 9, 17), art)


def test_base_und_fremdes_zerlegen_sich_nicht():
    for text in ("base", None, "", "a/b", "a/2026-09-17/fahrt", "a/2026-13-01/weg", "/2026-09-17/weg"):
        assert terminanfrage.zerlegen(text) is None, text


# --- Die Fragmente, Spec Abschnitt 4 --------------------------------------------


def test_ein_termin_mit_ladestand_ergibt_abwesenheit_fahrt_und_ziel():
    teil = _fragmente(_eintrag("e1", "2026-09-17T08:00:00", soc=80))["auto-1"]
    assert teil["consumption"] == {"type": "trips", "trips": [
        {"departure": "2026-09-17T08:00:00+02:00", "km": 42.0}]}
    assert teil["constraints"] == [
        {"type": "unavailable", "id": "e1/2026-09-17/weg",
         "from": "2026-09-17T08:00:00+02:00", "to": "2026-09-17T18:00:00+02:00"},
        {"type": "target", "id": "e1/2026-09-17/ziel",
         "deadline": "2026-09-17T08:00:00+02:00", "target_soc_pct": 80.0}]


def test_eine_fahrt_ist_kein_ziel():
    teil = _fragmente(_eintrag("e1", "2026-09-17T08:00:00"))["auto-1"]
    assert [c["type"] for c in teil["constraints"]] == ["unavailable"]


def test_ein_ladestand_unter_dem_min_soc_ergibt_kein_ziel():
    teil = _fragmente(_eintrag("e1", "2026-09-17T08:00:00", soc=14.9))["auto-1"]
    assert [c["type"] for c in teil["constraints"]] == ["unavailable"]
    teil = _fragmente(_eintrag("e1", "2026-09-17T08:00:00", soc=15))["auto-1"]
    assert [c["type"] for c in teil["constraints"]] == ["unavailable", "target"]


def test_ein_laufender_termin_ist_nur_abwesenheit():
    teil = _fragmente(_eintrag("e1", "2026-09-16T08:00:00", soc=80))["auto-1"]
    assert teil["consumption"]["trips"] == []
    assert teil["constraints"] == [{"type": "unavailable", "id": "e1/2026-09-16/weg",
                                    "from": "2026-09-16T08:00:00+02:00", "to": "2026-09-16T18:00:00+02:00"}]


def test_vorbei_und_hinter_dem_ende_fehlt():
    vorbei = _eintrag("e1", "2026-09-15T08:00:00")
    dahinter = _eintrag("e2", "2026-09-23T12:00:00")  # BIS ist 23.09. 12:00 Berlin
    assert _fragmente(vorbei, dahinter) == {"auto-1": {"consumption": {"type": "trips", "trips": []}}}


def test_jedes_fahrzeug_bekommt_trips_auch_ohne_termin():
    teile = _fragmente(_eintrag("e1", "2026-09-17T08:00:00"), soc_min={"auto-1": 15.0, "auto-2": 20.0})
    assert teile["auto-2"] == {"consumption": {"type": "trips", "trips": []}}


def test_ein_termin_eines_unbekannten_fahrzeugs_faellt_weg():
    assert _fragmente(_eintrag("e1", "2026-09-17T08:00:00", fahrzeug="weg")) == {
        "auto-1": {"consumption": {"type": "trips", "trips": []}}}


# --- Der Request, gegen das Schema ------------------------------------------------


def test_der_request_mit_terminen_validiert_gegen_das_schema():
    serie = _eintrag("e1", "2026-09-16T08:00:00", soc=80, wiederholung="weekdays")
    anfrage = _anfrage(_fragmente(serie, soc_min={"auto-1": 15.0, "auto-2": 15.0}), risiko=3)
    jsonschema.validate(anfrage, REQUEST_SCHEMA)
    assert anfrage["risk"] == 3
    auto_1, auto_2 = anfrage["vehicles"]
    assert len(auto_1["consumption"]["trips"]) == 5  # Do, Fr, Mo, Di und Mi 08:00 vor BIS 12:00
    assert auto_2["consumption"] == {"type": "trips", "trips": []}
    assert "constraints" not in auto_2
    for auflage in auto_1["constraints"]:
        assert terminanfrage.zerlegen(auflage["id"])[0] == "e1"


def test_jeder_zeitpunkt_im_request_traegt_einen_offset():
    serie = _eintrag("e1", "2026-09-16T08:00:00", soc=80, wiederholung="daily")
    anfrage = _anfrage(_fragmente(serie, soc_min={"auto-1": 15.0, "auto-2": 15.0}))
    zeitpunkte = [f["departure"] for f in anfrage["vehicles"][0]["consumption"]["trips"]]
    for auflage in anfrage["vehicles"][0]["constraints"]:
        zeitpunkte += [auflage[k] for k in ("from", "to", "deadline") if k in auflage]
    assert len(zeitpunkte) > 10
    assert all(datetime.fromisoformat(z).tzinfo is not None for z in zeitpunkte)


def test_ein_fahrzeug_ohne_fragment_bekommt_eine_leere_liste():
    anfrage = _anfrage({})
    assert [f["consumption"] for f in anfrage["vehicles"]] == [{"type": "trips", "trips": []}] * 2
    jsonschema.validate(anfrage, REQUEST_SCHEMA)


def test_ohne_c3_geht_der_request_wie_vorher():
    fahrzeug = {**stammdaten.FAHRZEUG_DEFAULTS, stammdaten.FELD_SOC_ENTITAET: "sensor.soc"}
    anfrage, _ = standort.anfrage_bauen(
        [("wb-1", dict(stammdaten.LADEPUNKT_DEFAULTS))], [("auto-1", fahrzeug)],
        {"auto-1": standort.Messung(zustand="47.5", gemeldet=JETZT)}, {}, "Europe/Berlin")
    assert "risk" not in anfrage
    assert anfrage["vehicles"][0]["consumption"] == {"type": "none"}
