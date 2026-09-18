"""Prueft Serien, Absagen und Rueckgaengig ohne Home Assistant. Spec C3 Abschnitte 2.1, 2.2 und 10.

Was dieser Test NICHT sieht: den Store auf der Platte, die Signale an das
Panel und den Plan, den ein Schritt ausloest. Das zeigt die Abnahme.
"""

import importlib
import itertools
import sys
import types
from datetime import date
from pathlib import Path

import pytest

INTEGRATION = Path(__file__).resolve().parents[1] / "custom_components" / "meteo_volt"

_PAKET = "meteo_volt_c3"
if _PAKET not in sys.modules:
    _paket = types.ModuleType(_PAKET)
    _paket.__path__ = [str(INTEGRATION)]
    sys.modules[_PAKET] = _paket
terminbuch = importlib.import_module(f"{_PAKET}.terminbuch")
pruefungen = importlib.import_module(f"{_PAKET}.pruefungen")

MI = date(2026, 9, 16)  # der erste Termin der Serien unten, ein Mittwoch
DO = date(2026, 9, 17)
FR = date(2026, 9, 18)


def _werte(abfahrt="2026-09-16T08:00:00", wiederholung="weekdays", fahrzeug="auto-1", **felder):
    return pruefungen.Werte(**{
        "fahrzeug": fahrzeug, "abfahrt": abfahrt, "dauer_min": 600, "wiederholung": wiederholung,
        "strecke_km": 42, "fahrer": None, "ladestand": None, **felder})


def _ids():
    zaehler = itertools.count(1)
    return lambda: f"k{next(zaehler)}"


def _buch_mit_serie(**felder):
    buch, neue_id = terminbuch.Buch(), _ids()
    schritt, (eintrag,) = terminbuch.anlegen(buch, _werte(**felder), neue_id)
    return buch, neue_id, eintrag


def _fehler(schluessel, feld, aufruf, *argumente):
    with pytest.raises(pruefungen.Terminfehler) as info:
        aufruf(*argumente)
    assert (info.value.meldung.schluessel, info.value.meldung.feld) == (schluessel, feld)


# --- Anlegen und einmalige Termine ------------------------------------------


def test_anlegen_legt_einen_eintrag_und_einen_schritt_an():
    buch, _, eintrag = _buch_mit_serie()
    assert buch.eintraege[eintrag] == {
        "id": eintrag, "vehicle": "auto-1", "departure": "2026-09-16T08:00:00", "duration_min": 600,
        "repeat": "weekdays", "distance_km": 42, "driver": None, "soc": None, "until": None,
        "exceptions": {}}
    assert len(buch.schritte) == 1


def test_ein_einmaliger_termin_uebergeht_den_umfang():
    buch, neue_id, eintrag = _buch_mit_serie(wiederholung="once")
    neu = _werte("2026-09-18T09:00:00", wiederholung="daily", fahrzeug="auto-2")
    _, eintraege = terminbuch.aendern(buch, eintrag, MI, "following", neu, neue_id)
    assert eintraege == [eintrag]
    assert buch.eintraege[eintrag]["departure"] == "2026-09-18T09:00:00"
    assert (buch.eintraege[eintrag]["repeat"], buch.eintraege[eintrag]["vehicle"]) == ("daily", "auto-2")


def test_ein_einmaliger_termin_wird_auch_mit_umfang_ganz_geloescht():
    buch, neue_id, eintrag = _buch_mit_serie(wiederholung="once")
    terminbuch.loeschen(buch, eintrag, MI, "following", neue_id)
    assert buch.eintraege == {}


# --- Aendern mit Umfang, Spec Abschnitt 2.1 -----------------------------------


def test_this_legt_eine_ausnahme_an():
    buch, neue_id, eintrag = _buch_mit_serie()
    _, eintraege = terminbuch.aendern(
        buch, eintrag, DO, "this", _werte("2026-09-17T09:00:00", strecke_km=7), neue_id)
    assert eintraege == [eintrag]
    assert buch.eintraege[eintrag]["exceptions"] == {"2026-09-17": {
        "departure": "2026-09-17T09:00:00", "duration_min": 600, "distance_km": 7,
        "driver": None, "soc": None}}
    assert buch.eintraege[eintrag]["departure"] == "2026-09-16T08:00:00"


def test_ohne_umfang_gilt_this():
    buch, neue_id, eintrag = _buch_mit_serie()
    terminbuch.aendern(buch, eintrag, DO, None, _werte("2026-09-17T09:00:00"), neue_id)
    assert "2026-09-17" in buch.eintraege[eintrag]["exceptions"]


def test_this_mit_anderer_wiederholung_ist_unzulaessig():
    buch, neue_id, eintrag = _buch_mit_serie()
    _fehler("umfang_unzulaessig", "scope", terminbuch.aendern,
            buch, eintrag, DO, "this", _werte("2026-09-17T08:00:00", wiederholung="daily"), neue_id)
    assert buch.eintraege[eintrag]["exceptions"] == {}


def test_this_mit_anderem_fahrzeug_sagt_ab_und_legt_dort_einmalig_an():
    buch, neue_id, eintrag = _buch_mit_serie()
    _, (einmalig, alt) = terminbuch.aendern(
        buch, eintrag, DO, "this", _werte("2026-09-17T08:00:00", fahrzeug="auto-2"), neue_id)
    assert alt == eintrag
    assert buch.eintraege[eintrag]["exceptions"] == {"2026-09-17": None}
    assert (buch.eintraege[einmalig]["vehicle"], buch.eintraege[einmalig]["repeat"]) == ("auto-2", "once")


def test_following_beendet_die_serie_und_beginnt_eine_neue():
    buch, neue_id, eintrag = _buch_mit_serie()
    terminbuch.aendern(buch, eintrag, FR, "this", _werte("2026-09-18T10:00:00"), neue_id)
    terminbuch.aendern(buch, eintrag, date(2026, 9, 22), "this", _werte("2026-09-22T11:00:00"), neue_id)
    terminbuch.absagen(buch, [(eintrag, date(2026, 9, 23))], None, neue_id)
    _, (folge, alt) = terminbuch.aendern(
        buch, eintrag, FR, "following", _werte("2026-09-18T09:00:00", strecke_km=50), neue_id)
    assert alt == eintrag
    assert buch.eintraege[eintrag]["until"] == "2026-09-18"
    assert buch.eintraege[eintrag]["exceptions"] == {}
    assert buch.eintraege[folge]["departure"] == "2026-09-18T09:00:00"
    assert buch.eintraege[folge]["distance_km"] == 50
    # Die Ausnahmen danach wandern mit, die am Datum selbst nicht.
    assert set(buch.eintraege[folge]["exceptions"]) == {"2026-09-22", "2026-09-23"}


def test_following_mit_anderem_tag_setzt_die_ausnahmen_zurueck():
    buch, neue_id, eintrag = _buch_mit_serie(wiederholung="weekly")
    terminbuch.absagen(buch, [(eintrag, date(2026, 9, 30))], None, neue_id)
    _, (folge, _) = terminbuch.aendern(
        buch, eintrag, date(2026, 9, 23), "following", _werte("2026-09-24T08:00:00", wiederholung="weekly"),
        neue_id)
    assert buch.eintraege[folge]["exceptions"] == {}


def test_following_mit_anderer_wiederholung_setzt_die_ausnahmen_zurueck():
    buch, neue_id, eintrag = _buch_mit_serie()
    terminbuch.absagen(buch, [(eintrag, date(2026, 9, 23))], None, neue_id)
    _, (folge, _) = terminbuch.aendern(
        buch, eintrag, FR, "following", _werte("2026-09-18T08:00:00", wiederholung="daily"), neue_id)
    assert buch.eintraege[folge]["exceptions"] == {}


def test_following_am_ersten_termin_wirkt_wie_all():
    buch, neue_id, eintrag = _buch_mit_serie()
    _, eintraege = terminbuch.aendern(
        buch, eintrag, MI, "following", _werte("2026-09-16T09:00:00"), neue_id)
    assert eintraege == [eintrag]
    assert list(buch.eintraege) == [eintrag]
    assert buch.eintraege[eintrag]["departure"] == "2026-09-16T09:00:00"


def test_all_verschiebt_den_beginn_um_dieselben_tage():
    buch, neue_id, eintrag = _buch_mit_serie(wiederholung="weekly", abfahrt="2026-09-16T08:00:00")
    terminbuch.loeschen(buch, eintrag, date(2026, 10, 14), "following", neue_id)
    # Den Termin vom 30.09. auf Donnerstag 01.10. 07:30 legen, fuer alle.
    terminbuch.aendern(
        buch, eintrag, date(2026, 9, 30), "all", _werte("2026-10-01T07:30:00", wiederholung="weekly"), neue_id)
    assert buch.eintraege[eintrag]["departure"] == "2026-09-17T07:30:00"
    assert buch.eintraege[eintrag]["until"] == "2026-10-15"


def test_all_behaelt_die_ausnahmen_ohne_neuen_tag_und_ohne_neue_regel():
    buch, neue_id, eintrag = _buch_mit_serie()
    terminbuch.absagen(buch, [(eintrag, date(2026, 9, 23))], None, neue_id)
    terminbuch.aendern(buch, eintrag, FR, "this", _werte("2026-09-18T10:00:00"), neue_id)
    terminbuch.aendern(buch, eintrag, FR, "all", _werte("2026-09-18T07:00:00"), neue_id)
    assert buch.eintraege[eintrag]["exceptions"] == {"2026-09-23": None}
    assert buch.eintraege[eintrag]["departure"] == "2026-09-16T07:00:00"


def test_all_mit_neuer_regel_setzt_die_ausnahmen_zurueck():
    buch, neue_id, eintrag = _buch_mit_serie()
    terminbuch.absagen(buch, [(eintrag, date(2026, 9, 23))], None, neue_id)
    terminbuch.aendern(buch, eintrag, MI, "all", _werte(wiederholung="daily"), neue_id)
    assert buch.eintraege[eintrag]["exceptions"] == {}


def test_aendern_ohne_eintrag_oder_termin():
    buch, neue_id, eintrag = _buch_mit_serie()
    _fehler("eintrag_unbekannt", "entry", terminbuch.aendern, buch, "weg", DO, "this", _werte(), neue_id)
    samstag = date(2026, 9, 19)
    _fehler("termin_unbekannt", "date", terminbuch.aendern, buch, eintrag, samstag, "this", _werte(), neue_id)
    terminbuch.absagen(buch, [(eintrag, DO)], None, neue_id)
    _fehler("termin_unbekannt", "date", terminbuch.aendern, buch, eintrag, DO, "this", _werte(), neue_id)


# --- Loeschen ------------------------------------------------------------------


def test_loeschen_this_sagt_einen_termin_ab():
    buch, neue_id, eintrag = _buch_mit_serie()
    terminbuch.loeschen(buch, eintrag, DO, "this", neue_id)
    assert buch.eintraege[eintrag]["exceptions"] == {"2026-09-17": None}


def test_loeschen_following_beendet_die_serie():
    buch, neue_id, eintrag = _buch_mit_serie()
    terminbuch.absagen(buch, [(eintrag, date(2026, 9, 23))], None, neue_id)
    terminbuch.loeschen(buch, eintrag, FR, "following", neue_id)
    assert buch.eintraege[eintrag]["until"] == "2026-09-18"
    assert buch.eintraege[eintrag]["exceptions"] == {}


def test_loeschen_following_am_ersten_termin_und_all_loeschen_den_eintrag():
    for umfang, datum in (("following", MI), ("all", FR)):
        buch, neue_id, eintrag = _buch_mit_serie()
        terminbuch.loeschen(buch, eintrag, datum, umfang, neue_id)
        assert buch.eintraege == {}


# --- Absagen und Rueckgaengig, Spec Abschnitt 2.2 ------------------------------


def test_absagen_ohne_schritt_ist_ein_eigener_schritt():
    buch, neue_id, serie = _buch_mit_serie()
    _, (einmalig,) = terminbuch.anlegen(buch, _werte(wiederholung="once", fahrzeug="auto-1"), neue_id)
    schritt = terminbuch.absagen(buch, [(serie, DO), (einmalig, MI)], None, neue_id)
    assert buch.eintraege[serie]["exceptions"] == {"2026-09-17": None}
    assert einmalig not in buch.eintraege
    assert len(buch.schritte) == 3
    terminbuch.rueckgaengig(buch, schritt)
    assert buch.eintraege[serie]["exceptions"] == {}
    assert einmalig in buch.eintraege


def test_absagen_mit_schritt_gehoert_zum_speichern_davor():
    buch, neue_id, serie = _buch_mit_serie()
    speichern, (einmalig,) = terminbuch.anlegen(
        buch, _werte("2026-09-17T07:00:00", wiederholung="once"), neue_id)
    assert terminbuch.absagen(buch, [(serie, DO)], speichern, neue_id) == speichern
    assert len(buch.schritte) == 2
    terminbuch.rueckgaengig(buch, speichern)
    assert einmalig not in buch.eintraege
    assert buch.eintraege[serie]["exceptions"] == {}


def test_absagen_im_selben_eintrag_behaelt_den_stand_vor_dem_speichern():
    buch, neue_id, serie = _buch_mit_serie()
    speichern, _ = terminbuch.aendern(buch, serie, DO, "this", _werte("2026-09-17T09:00:00"), neue_id)
    terminbuch.absagen(buch, [(serie, FR)], speichern, neue_id)
    terminbuch.rueckgaengig(buch, speichern)
    assert buch.eintraege[serie]["exceptions"] == {}


def test_absagen_mit_unbekanntem_schritt_wird_ein_eigener():
    buch, neue_id, serie = _buch_mit_serie()
    schritt = terminbuch.absagen(buch, [(serie, DO)], "vergessen", neue_id)
    assert schritt != "vergessen" and terminbuch.schritt_bekannt(buch, schritt)


def test_absagen_prueft_jeden_termin_vor_der_ersten_aenderung():
    buch, neue_id, serie = _buch_mit_serie()
    _fehler("eintrag_unbekannt", "entry", terminbuch.absagen, buch, [(serie, DO), ("weg", DO)], None, neue_id)
    _fehler("termin_unbekannt", "date", terminbuch.absagen, buch, [(serie, DO), (serie, DO)], None, neue_id)
    assert buch.eintraege[serie]["exceptions"] == {}
    assert len(buch.schritte) == 1


def test_rueckgaengig_nach_einer_spaeteren_aenderung_geht_nicht():
    buch, neue_id, serie = _buch_mit_serie()
    schritt = terminbuch.loeschen(buch, serie, DO, "this", neue_id)
    terminbuch.loeschen(buch, serie, FR, "this", neue_id)
    _fehler("rueckgaengig_unmoeglich", "step", terminbuch.rueckgaengig, buch, schritt)


def test_rueckgaengig_geht_einmal():
    buch, neue_id, serie = _buch_mit_serie()
    schritt = terminbuch.loeschen(buch, serie, DO, "this", neue_id)
    terminbuch.rueckgaengig(buch, schritt)
    _fehler("rueckgaengig_unmoeglich", "step", terminbuch.rueckgaengig, buch, schritt)


def test_rueckgaengig_nach_geloeschtem_fahrzeug_geht_nicht():
    buch, neue_id, serie = _buch_mit_serie()
    schritt = terminbuch.loeschen(buch, serie, DO, "this", neue_id)
    assert terminbuch.fahrzeuge_bereinigen(buch, {"auto-2"})
    assert buch.eintraege == {}
    _fehler("rueckgaengig_unmoeglich", "step", terminbuch.rueckgaengig, buch, schritt)


def test_der_51_schritt_verdraengt_den_ersten():
    buch, neue_id = terminbuch.Buch(), _ids()
    erster, _ = terminbuch.anlegen(buch, _werte(), neue_id)
    for _ in range(50):
        terminbuch.anlegen(buch, _werte(), neue_id)
    assert len(buch.schritte) == 50
    _fehler("rueckgaengig_unmoeglich", "step", terminbuch.rueckgaengig, buch, erster)


# --- Speicher -------------------------------------------------------------------


def test_die_speicherform_traegt_das_risiko_nur_wenn_es_gesetzt_ist():
    buch, _, eintrag = _buch_mit_serie()
    assert set(buch.speicherform()) == {"entries"}
    buch.risiko = 3
    wieder = terminbuch.Buch(buch.speicherform())
    assert (wieder.risiko, wieder.eintraege) == (3, buch.eintraege)
    assert terminbuch.Buch().risiko is None
