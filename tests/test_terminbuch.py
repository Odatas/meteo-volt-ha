"""Prueft Serien, Absagen und Rueckgaengig ohne Home Assistant. Spec C3 Abschnitte 2.1, 2.2 und 10.

Was dieser Test NICHT sieht: den Store auf der Platte, die Signale an das
Panel und den Plan, den ein Schritt ausloest. Das zeigt die Abnahme.
"""

import importlib
import itertools
import sys
import types
from datetime import date, datetime
from zoneinfo import ZoneInfo
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
        "strecke_km": 42, "fahrer": None, "ladestand": None, "sichern": True, **felder})


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
    assert set(info.value.meldung.platzhalter) == set(pruefungen.MELDUNGEN[schluessel])


# --- Anlegen und einmalige Termine ------------------------------------------


def test_anlegen_legt_einen_eintrag_und_einen_schritt_an():
    buch, _, eintrag = _buch_mit_serie()
    assert buch.eintraege[eintrag] == {
        "id": eintrag, "vehicle": "auto-1", "departure": "2026-09-16T08:00:00", "duration_min": 600,
        "repeat": "weekdays", "distance_km": 42, "driver": None, "soc": None, "keep_min_soc": True,
        "until": None, "exceptions": {}}
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
        "driver": None, "soc": None, "keep_min_soc": True}}
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


def _ausnahme(abfahrt, strecke_km=42, keep_min_soc=True):
    return {"departure": abfahrt, "duration_min": 600, "distance_km": strecke_km,
            "driver": None, "soc": None, "keep_min_soc": keep_min_soc}


def _verlegte_serie():
    """Woechentlich ab Mi 16.09., der 30.09. einzeln auf Do 01.10. verlegt, der 14.10. abgesagt."""
    buch, neue_id, serie = _buch_mit_serie(wiederholung="weekly")
    terminbuch.aendern(buch, serie, date(2026, 9, 30), "this",
                       _werte("2026-10-01T08:00:00", wiederholung="weekly"), neue_id)
    terminbuch.absagen(buch, [(serie, date(2026, 10, 14))], None, neue_id)
    return buch, neue_id, serie


def test_all_an_einem_verlegten_termin_behaelt_die_serie():
    """Spec 2.1, entschieden am 2026-09-19: verschoben ist ein Datum gegen das angezeigte."""
    buch, neue_id, serie = _verlegte_serie()
    terminbuch.aendern(buch, serie, date(2026, 9, 30), "all",
                       _werte("2026-10-01T08:00:00", wiederholung="weekly", strecke_km=50), neue_id)
    eintrag = buch.eintraege[serie]
    assert (eintrag["departure"], eintrag["distance_km"]) == ("2026-09-16T08:00:00", 50)
    assert eintrag["exceptions"] == {
        "2026-09-30": _ausnahme("2026-10-01T08:00:00", 50), "2026-10-14": None}


def test_following_an_einem_verlegten_termin_behaelt_den_wochentag():
    buch, neue_id, serie = _verlegte_serie()
    _, (folge, _) = terminbuch.aendern(
        buch, serie, date(2026, 9, 30), "following",
        _werte("2026-10-01T08:00:00", wiederholung="weekly", strecke_km=50), neue_id)
    assert buch.eintraege[serie]["until"] == "2026-09-30"
    assert buch.eintraege[folge]["departure"] == "2026-09-30T08:00:00"
    assert buch.eintraege[folge]["exceptions"] == {
        "2026-09-30": _ausnahme("2026-10-01T08:00:00", 50), "2026-10-14": None}


def test_all_verschiebt_um_die_aenderung_gegen_das_angezeigte_datum():
    """Do 01.10. im Formular auf Fr 02.10.: die Serie wandert einen Tag, der Termin steht am Freitag."""
    buch, neue_id, serie = _verlegte_serie()
    terminbuch.aendern(buch, serie, date(2026, 9, 30), "all",
                       _werte("2026-10-02T08:00:00", wiederholung="weekly"), neue_id)
    eintrag = buch.eintraege[serie]
    assert eintrag["departure"] == "2026-09-17T08:00:00"
    assert eintrag["exceptions"] == {"2026-10-01": _ausnahme("2026-10-02T08:00:00")}


def test_werktags_auf_einen_samstag_bleibt_der_termin_einmalig():
    """In einer Werktags-Serie hat ein Samstag keinen Platz. Verschwinden darf der Termin nicht."""
    buch, neue_id, serie = _buch_mit_serie()
    _, eintraege = terminbuch.aendern(buch, serie, FR, "all", _werte("2026-09-19T08:00:00"), neue_id)
    assert eintraege[0] == serie and len(eintraege) == 2
    einmalig = buch.eintraege[eintraege[1]]
    assert (einmalig["departure"], einmalig["repeat"]) == ("2026-09-19T08:00:00", "once")
    assert buch.eintraege[serie]["departure"] == "2026-09-17T08:00:00"


def test_eine_neue_wiederholung_beginnt_am_termin_aus_dem_formular():
    for wiederholung in ("once", "yearly"):
        buch, neue_id, serie = _buch_mit_serie(wiederholung="weekly", abfahrt="2026-09-02T08:00:00")
        terminbuch.aendern(buch, serie, date(2026, 9, 23), "all",
                           _werte("2026-09-23T08:00:00", wiederholung=wiederholung), neue_id)
        eintrag = buch.eintraege[serie]
        assert (eintrag["departure"], eintrag["repeat"]) == ("2026-09-23T08:00:00", wiederholung)


def test_following_am_ersten_nicht_abgesagten_termin_wirkt_wie_all():
    buch, neue_id, serie = _buch_mit_serie()
    terminbuch.absagen(buch, [(serie, MI)], None, neue_id)
    _, eintraege = terminbuch.aendern(buch, serie, DO, "following", _werte("2026-09-17T09:00:00"), neue_id)
    assert eintraege == [serie] and list(buch.eintraege) == [serie]
    assert buch.eintraege[serie]["departure"] == "2026-09-16T09:00:00"
    assert buch.eintraege[serie]["exceptions"] == {"2026-09-16": None}
    buch, neue_id, serie = _buch_mit_serie()
    terminbuch.absagen(buch, [(serie, MI)], None, neue_id)
    terminbuch.loeschen(buch, serie, DO, "following", neue_id)
    assert buch.eintraege == {}


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


def test_rueckgaengig_nach_geloeschtem_termin_und_fahrzeug_geht_nicht():
    """Das Fahrzeug nimmt auch die Schritte seiner Termine mit (Spec 2.2)."""
    buch, neue_id, eintrag = _buch_mit_serie(wiederholung="once")
    schritt = terminbuch.loeschen(buch, eintrag, MI, None, neue_id)
    assert not terminbuch.fahrzeuge_bereinigen(buch, {"auto-2"})
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


# --- Ignorieren, Spec C9R Abschnitte 2 und 3 ---------------------------------

BERLIN = ZoneInfo("Europe/Berlin")
MI_MITTAG = datetime(2026, 9, 16, 12, 0, tzinfo=BERLIN)  # der Termin am MI laeuft 08:00 bis 18:00


def test_ein_laufender_termin_wird_ignoriert_und_wieder_beachtet():
    buch, _, eintrag = _buch_mit_serie()
    terminbuch.ignorieren(buch, eintrag, MI, True, MI_MITTAG, BERLIN)
    assert buch.ignoriert == {(eintrag, MI)}
    terminbuch.ignorieren(buch, eintrag, MI, False, MI_MITTAG, BERLIN)
    assert buch.ignoriert == set()


def test_ignorieren_ist_kein_schritt_und_laesst_rueckgaengig_stehen():
    buch, neue_id, eintrag = _buch_mit_serie()
    schritt = terminbuch.aendern(buch, eintrag, DO, None, _werte(abfahrt="2026-09-17T09:00:00"), neue_id)[0]
    vorher = dict(buch.eintraege)
    terminbuch.ignorieren(buch, eintrag, MI, True, MI_MITTAG, BERLIN)
    assert len(buch.schritte) == 2 and buch.eintraege == vorher  # anlegen und aendern
    terminbuch.rueckgaengig(buch, schritt)


def test_nur_ein_laufender_termin_laesst_sich_ignorieren():
    buch, _, eintrag = _buch_mit_serie()
    for datum, jetzt in (
        (DO, MI_MITTAG),  # kuenftig
        (MI, datetime(2026, 9, 16, 18, 0, tzinfo=BERLIN)),  # genau zur Rueckkehr vorbei
        (MI, datetime(2026, 9, 16, 7, 59, tzinfo=BERLIN)),  # noch nicht losgefahren
    ):
        _fehler("termin_laeuft_nicht", "date", terminbuch.ignorieren, buch, eintrag, datum, True, jetzt, BERLIN)
    terminbuch.ignorieren(buch, eintrag, MI, True, datetime(2026, 9, 16, 8, 0, tzinfo=BERLIN), BERLIN)
    assert buch.ignoriert == {(eintrag, MI)}


def test_beachten_ohne_markierung_ist_kein_fehler_auch_nicht_an_einem_kuenftigen():
    buch, _, eintrag = _buch_mit_serie()
    terminbuch.ignorieren(buch, eintrag, DO, False, MI_MITTAG, BERLIN)
    assert buch.ignoriert == set()


def test_ignorieren_prueft_eintrag_vor_datum_vor_laufen():
    buch, _, eintrag = _buch_mit_serie()
    _fehler("eintrag_unbekannt", "entry", terminbuch.ignorieren, buch, "fehlt", MI, True, MI_MITTAG, BERLIN)
    samstag = date(2026, 9, 19)
    _fehler("termin_unbekannt", "date", terminbuch.ignorieren, buch, eintrag, samstag, True, MI_MITTAG, BERLIN)
    _fehler("termin_unbekannt", "date", terminbuch.ignorieren, buch, eintrag, samstag, False, MI_MITTAG, BERLIN)


def test_bereinigen_laesst_nur_laufende_markierungen_stehen():
    buch, neue_id, eintrag = _buch_mit_serie()
    terminbuch.ignorieren(buch, eintrag, MI, True, MI_MITTAG, BERLIN)
    assert terminbuch.ignoriert_bereinigen(buch, MI_MITTAG, BERLIN) is False
    assert buch.ignoriert == {(eintrag, MI)}
    assert terminbuch.ignoriert_bereinigen(buch, datetime(2026, 9, 16, 18, 0, tzinfo=BERLIN), BERLIN) is True
    assert buch.ignoriert == set()


@pytest.mark.parametrize("schritt", ["verschoben", "abgesagt", "geloescht"])
def test_bereinigen_nach_einem_schritt_der_den_termin_wegnimmt(schritt):
    buch, neue_id, eintrag = _buch_mit_serie()
    terminbuch.ignorieren(buch, eintrag, MI, True, MI_MITTAG, BERLIN)
    if schritt == "verschoben":
        terminbuch.aendern(buch, eintrag, MI, None, _werte(abfahrt="2026-09-16T14:00:00"), neue_id)
    elif schritt == "abgesagt":
        terminbuch.absagen(buch, [(eintrag, MI)], None, neue_id)
    else:
        terminbuch.loeschen(buch, eintrag, MI, "all", neue_id)
    assert terminbuch.ignoriert_bereinigen(buch, MI_MITTAG, BERLIN) is True
    assert buch.ignoriert == set()


def test_die_speicherform_traegt_ignored_nur_wenn_es_eine_markierung_gibt():
    buch, _, eintrag = _buch_mit_serie()
    terminbuch.ignorieren(buch, eintrag, MI, True, MI_MITTAG, BERLIN)
    assert buch.speicherform()["ignored"] == [{"entry": eintrag, "date": "2026-09-16"}]
    assert terminbuch.Buch(buch.speicherform()).ignoriert == {(eintrag, MI)}
    terminbuch.ignorieren(buch, eintrag, MI, False, MI_MITTAG, BERLIN)
    assert "ignored" not in buch.speicherform()
    assert terminbuch.Buch({"entries": []}).ignoriert == set()


def test_ohne_angabe_wird_ignoriert():
    """C9R-Spec Abschnitt 4: fehlt ignored an der Action, ist es an."""
    buch, _, eintrag = _buch_mit_serie()
    terminbuch.ignorieren(buch, eintrag, MI, None, MI_MITTAG, BERLIN)
    assert buch.ignoriert == {(eintrag, MI)}


# --- Heimkehr, Spec C9Z Abschnitt 8 ------------------------------------------------
# Der Termin am MI laeuft 08:00 bis 18:00, zehn Stunden: die letzten 30 % beginnen um 15:00.


@pytest.mark.parametrize(("alt", "neu", "erwartet"), [
    ("not_home", "home", True),
    ("Arbeit", "home", True),
    ("home", "home", False),
    ("unavailable", "home", False),
    ("unknown", "home", False),
    (None, "home", False),
    ("home", "not_home", False),
    ("not_home", None, False),
])
def test_nur_ein_echter_wechsel_nach_home_ist_eine_heimkehr(alt, neu, erwartet):
    assert terminbuch.heimgekehrt(alt, neu) is erwartet


def _um(stunde, minute=0):
    return datetime(2026, 9, 16, stunde, minute, tzinfo=BERLIN)


def test_nur_in_den_letzten_30_prozent():
    buch, _, eintrag = _buch_mit_serie()
    assert terminbuch.heimkehr(buch, BERLIN, _um(14, 59), fahrzeug="auto-1") == []
    assert terminbuch.heimkehr(buch, BERLIN, _um(15), fahrzeug="auto-1") == [(eintrag, MI)]
    assert terminbuch.heimkehr(buch, BERLIN, _um(17, 59), fahrzeug="auto-1") == [(eintrag, MI)]
    assert terminbuch.heimkehr(buch, BERLIN, _um(18), fahrzeug="auto-1") == []


def test_der_standort_trifft_nur_sein_fahrzeug_die_person_nur_ihre_termine():
    buch, neue_id, eigener = _buch_mit_serie(fahrer="person.ela")
    _, (fremder,) = terminbuch.anlegen(buch, _werte(fahrzeug="auto-2", fahrer="person.ela"), neue_id)
    _, (ohne,) = terminbuch.anlegen(buch, _werte(fahrzeug="auto-2"), neue_id)
    assert terminbuch.heimkehr(buch, BERLIN, _um(16), fahrzeug="auto-1") == [(eigener, MI)]
    assert sorted(terminbuch.heimkehr(buch, BERLIN, _um(16), fahrer="person.ela")) == sorted(
        [(eigener, MI), (fremder, MI)])
    assert terminbuch.heimkehr(buch, BERLIN, _um(16), fahrer="person.anna") == []
    assert set(terminbuch.heimkehr(buch, BERLIN, _um(16), fahrzeug="auto-2")) == {(fremder, MI), (ohne, MI)}


def test_ein_schon_ignorierter_termin_kommt_nicht_noch_einmal():
    buch, _, eintrag = _buch_mit_serie()
    terminbuch.ignorieren(buch, eintrag, MI, True, _um(16), BERLIN)
    assert terminbuch.heimkehr(buch, BERLIN, _um(16), fahrzeug="auto-1") == []


def test_ohne_quelle_keine_heimkehr():
    buch, _, _ = _buch_mit_serie()
    assert terminbuch.heimkehr(buch, BERLIN, _um(16)) == []
