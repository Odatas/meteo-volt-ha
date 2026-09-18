"""Prueft das Ausrollen der Termine ohne Home Assistant. Spec C3 Abschnitte 2 und 10.

Gerechnet wird in Europe/Berlin, mit echter Zeitumstellung: am 29.03.2026
fehlt 02:00 bis 03:00, am 25.10.2026 gibt es 02:00 bis 03:00 zweimal. Unter
Windows braucht ZoneInfo dafuer das Paket tzdata (tests/requirements-test.txt);
fehlt es, scheitert schon das Laden dieses Tests, statt still gruen zu werden.

Was dieser Test NICHT sieht: den Store auf der Platte und Home Assistant.
"""

import importlib
import sys
import types
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

INTEGRATION = Path(__file__).resolve().parents[1] / "custom_components" / "meteo_volt"

# Geladen ueber ein Paket, dessen __init__.py NICHT laeuft -- die zieht
# homeassistant herein. Bekaeme termine.py einen Import aus Home Assistant
# oder aiohttp, scheiterte schon dieses Laden.
_PAKET = "meteo_volt_c3"
if _PAKET not in sys.modules:
    _paket = types.ModuleType(_PAKET)
    _paket.__path__ = [str(INTEGRATION)]
    sys.modules[_PAKET] = _paket
termine = importlib.import_module(f"{_PAKET}.termine")

BERLIN = ZoneInfo("Europe/Berlin")


def _eintrag(abfahrt="2026-09-16T08:00:00", dauer=600, wiederholung="once", **felder):
    return {
        "id": "e1",
        "vehicle": "auto-1",
        "departure": abfahrt,
        "duration_min": dauer,
        "repeat": wiederholung,
        "distance_km": 42,
        "driver": None,
        "soc": None,
        "until": None,
        "exceptions": {},
        **felder,
    }


def _zeit(text: str) -> datetime:
    return termine.lokal(text, BERLIN)


def _daten(eintrag, von="2026-09-14T00:00:00", bis="2026-10-12T00:00:00"):
    return [t.datum.isoformat() for t in termine.termine_von(eintrag, BERLIN, _zeit(von), _zeit(bis))]


# --- Wiederholung, Spec Abschnitt 2 -----------------------------------------


def test_einmalig_nur_die_abfahrt():
    assert _daten(_eintrag()) == ["2026-09-16"]


def test_taeglich_jeden_tag():
    assert _daten(_eintrag(wiederholung="daily"), bis="2026-09-20T00:00:00") == [
        "2026-09-16", "2026-09-17", "2026-09-18", "2026-09-19"]


def test_werktags_montag_bis_freitag():
    assert _daten(_eintrag(wiederholung="weekdays"), bis="2026-09-23T00:00:00") == [
        "2026-09-16", "2026-09-17", "2026-09-18", "2026-09-21", "2026-09-22"]


def test_werktags_ab_einem_samstag_ist_der_erste_termin_der_montag():
    eintrag = _eintrag("2026-09-19T08:00:00", wiederholung="weekdays")
    assert termine.erster_termin(eintrag) == date(2026, 9, 21)
    assert _daten(eintrag, bis="2026-09-23T00:00:00") == ["2026-09-21", "2026-09-22"]


def test_woechentlich_am_wochentag_der_abfahrt():
    assert _daten(_eintrag(wiederholung="weekly")) == [
        "2026-09-16", "2026-09-23", "2026-09-30", "2026-10-07"]


def test_monatlich_am_nten_wochentag():
    # 16.09.2026 ist der dritte Mittwoch: ceil(16 / 7) = 3.
    eintrag = _eintrag(wiederholung="monthly")
    assert _daten(eintrag, bis="2027-01-01T00:00:00") == [
        "2026-09-16", "2026-10-21", "2026-11-18", "2026-12-16"]


def test_monatlich_am_14_der_zweite_und_am_28_der_vierte_wochentag():
    # ceil(14 / 7) = 2: am 14.10.2026, einem Mittwoch, ist das der zweite Mittwoch.
    zweiter = _eintrag("2026-10-14T08:00:00", wiederholung="monthly")
    assert _daten(zweiter, von="2026-10-01T00:00:00", bis="2026-12-01T00:00:00") == [
        "2026-10-14", "2026-11-11"]
    # ceil(28 / 7) = 4 heisst der vierte, nicht der letzte: im April 2026 der 22., nicht der 29.
    vierter = _eintrag("2026-01-28T08:00:00", wiederholung="monthly")
    assert _daten(vierter, von="2026-04-01T00:00:00", bis="2026-05-01T00:00:00") == ["2026-04-22"]


def test_monatlich_ab_dem_29_am_letzten_wochentag():
    # 29.01.2026 ist ein Donnerstag: ceil(29 / 7) = 5, also der letzte Donnerstag.
    eintrag = _eintrag("2026-01-29T08:00:00", wiederholung="monthly")
    assert _daten(eintrag, von="2026-01-01T00:00:00", bis="2026-05-01T00:00:00") == [
        "2026-01-29", "2026-02-26", "2026-03-26", "2026-04-30"]


def test_jaehrlich_am_datum_der_abfahrt():
    eintrag = _eintrag(wiederholung="yearly")
    assert _daten(eintrag, bis="2028-12-31T00:00:00") == ["2026-09-16", "2027-09-16", "2028-09-16"]


def test_der_29_februar_nur_im_schaltjahr():
    eintrag = _eintrag("2028-02-29T08:00:00", wiederholung="yearly")
    assert _daten(eintrag, von="2028-01-01T00:00:00", bis="2033-01-01T00:00:00") == [
        "2028-02-29", "2032-02-29"]


def test_until_beendet_die_serie_vor_dem_datum():
    eintrag = _eintrag(wiederholung="daily", until="2026-09-19")
    assert _daten(eintrag) == ["2026-09-16", "2026-09-17", "2026-09-18"]


# --- Zeitumstellung ---------------------------------------------------------


def test_eine_abfahrt_die_es_nicht_gibt_liegt_eine_stunde_spaeter():
    # 29.03.2026: 02:30 gibt es in Berlin nicht.
    assert _zeit("2026-03-29T02:30:00").isoformat() == "2026-03-29T03:30:00+02:00"


def test_eine_abfahrt_die_es_zweimal_gibt_gilt_beim_ersten_mal():
    # 25.10.2026: 02:30 gibt es zweimal, zuerst in Sommerzeit.
    assert _zeit("2026-10-25T02:30:00").isoformat() == "2026-10-25T02:30:00+02:00"


def test_eine_serie_behaelt_ihre_uhrzeit_ueber_die_umstellung():
    eintrag = _eintrag("2026-10-24T08:00:00", dauer=60, wiederholung="daily")
    reihe = termine.termine_von(eintrag, BERLIN, _zeit("2026-10-24T00:00:00"), _zeit("2026-10-27T00:00:00"))
    assert [t.abfahrt.isoformat() for t in reihe] == [
        "2026-10-24T08:00:00+02:00", "2026-10-25T08:00:00+01:00", "2026-10-26T08:00:00+01:00"]


def test_eine_fahrt_ueber_die_umstellung_behaelt_ihre_dauer():
    # 22:00 Sommerzeit plus 10 h verstrichene Zeit ist 07:00 Winterzeit, nicht 08:00.
    eintrag = _eintrag("2026-10-24T22:00:00", dauer=600)
    (termin,) = termine.termine_von(eintrag, BERLIN, _zeit("2026-10-24T00:00:00"), _zeit("2026-10-26T00:00:00"))
    assert termin.rueckkehr.isoformat() == "2026-10-25T07:00:00+01:00"
    assert termin.rueckkehr.astimezone(timezone.utc) - termin.abfahrt.astimezone(timezone.utc) == timedelta(hours=10)


def test_die_dauer_zaehlt_verstrichene_minuten():
    assert termine.dauer_min(_zeit("2026-10-24T22:00:00"), _zeit("2026-10-25T07:00:00")) == 600
    assert termine.dauer_min(_zeit("2026-03-28T22:00:00"), _zeit("2026-03-29T07:00:00")) == 480


# --- Ausnahmen und Fenster ----------------------------------------------------


def test_eine_abgesagte_ausnahme_fehlt():
    eintrag = _eintrag(wiederholung="daily", exceptions={"2026-09-17": None})
    assert _daten(eintrag, bis="2026-09-19T00:00:00") == ["2026-09-16", "2026-09-18"]
    assert not termine.hat_termin(eintrag, date(2026, 9, 17))


def test_eine_geaenderte_ausnahme_traegt_ihre_werte():
    werte = {"departure": "2026-09-17T09:30:00", "duration_min": 120, "distance_km": 7,
             "driver": "person.anna", "soc": 80}
    eintrag = _eintrag(wiederholung="daily", exceptions={"2026-09-17": werte})
    termin = termine.termin_am(eintrag, date(2026, 9, 17), BERLIN)
    assert termin.geaendert
    assert termin.abfahrt.isoformat() == "2026-09-17T09:30:00+02:00"
    assert termin.rueckkehr.isoformat() == "2026-09-17T11:30:00+02:00"
    assert (termin.strecke_km, termin.fahrer, termin.ladestand) == (7, "person.anna", 80)
    assert not termine.termin_am(eintrag, date(2026, 9, 16), BERLIN).geaendert


def test_eine_verschobene_ausnahme_kommt_ins_fenster_und_geht_hinaus():
    werte = {"departure": "2026-10-05T08:00:00", "duration_min": 60, "distance_km": 7,
             "driver": None, "soc": None}
    eintrag = _eintrag(wiederholung="weekly", exceptions={"2026-09-23": werte})
    assert _daten(eintrag, von="2026-10-05T00:00:00", bis="2026-10-06T00:00:00") == ["2026-09-23"]
    assert _daten(eintrag, von="2026-09-23T00:00:00", bis="2026-09-24T00:00:00") == []


def test_ein_laufender_termin_liegt_im_fenster():
    eintrag = _eintrag("2026-09-16T08:00:00", dauer=600)
    assert _daten(eintrag, von="2026-09-16T12:00:00") == ["2026-09-16"]


def test_die_grenzen_des_fensters_sind_halboffen():
    eintrag = _eintrag("2026-09-16T08:00:00", dauer=600)
    assert _daten(eintrag, von="2026-09-16T18:00:00") == []
    assert _daten(eintrag, von="2026-09-01T00:00:00", bis="2026-09-16T08:00:00") == []


def test_ein_termin_vor_dem_fenster_reicht_hinein():
    # Taeglich 20:00 fuer 23 h: der Termin vom Vortag laeuft ins Fenster.
    eintrag = _eintrag("2026-09-10T20:00:00", dauer=23 * 60, wiederholung="daily")
    assert _daten(eintrag, von="2026-09-16T12:00:00", bis="2026-09-16T13:00:00") == ["2026-09-15"]


def test_ausrollen_sortiert_und_filtert_nach_fahrzeug():
    a = _eintrag("2026-09-17T08:00:00")
    b = {**_eintrag("2026-09-16T08:00:00"), "id": "e2", "vehicle": "auto-2"}
    von, bis = _zeit("2026-09-14T00:00:00"), _zeit("2026-09-20T00:00:00")
    assert [t.eintrag for t in termine.ausrollen([a, b], BERLIN, von, bis)] == ["e2", "e1"]
    assert [t.eintrag for t in termine.ausrollen([a, b], BERLIN, von, bis, fahrzeug="auto-1")] == ["e1"]


def test_ueberschneiden_ist_halboffen():
    eintrag = _eintrag("2026-09-16T08:00:00", dauer=60)
    anschluss = {**_eintrag("2026-09-16T09:00:00", dauer=60), "id": "e2"}
    von, bis = _zeit("2026-09-16T00:00:00"), _zeit("2026-09-17T00:00:00")
    (a,) = termine.termine_von(eintrag, BERLIN, von, bis)
    (b,) = termine.termine_von(anschluss, BERLIN, von, bis)
    assert not termine.ueberschneiden(a, b)
    (c,) = termine.termine_von({**anschluss, "departure": "2026-09-16T08:59:00"}, BERLIN, von, bis)
    assert termine.ueberschneiden(a, c)
