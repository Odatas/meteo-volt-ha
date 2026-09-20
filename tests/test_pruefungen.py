"""Prueft die Pruefungen beim Speichern ohne Home Assistant. Spec C3 Abschnitte 2.3 und 10.

Jeder Schluessel aus 2.3 mit seinem Feld. Fuenf davon entstehen woanders
und sind dort geprueft: eintrag_unbekannt, termin_unbekannt,
umfang_unzulaessig und rueckgaengig_unmoeglich in tests/test_terminbuch.py,
fahrzeug_unbekannt, plan_pause und plan_gestoppt hier.

Was dieser Test NICHT sieht: dass Home Assistant aus einem Terminfehler einen
uebersetzten ServiceValidationError macht. Das zeigt die Abnahme.
"""

import importlib
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

INTEGRATION = Path(__file__).resolve().parents[1] / "custom_components" / "meteo_volt"

_PAKET = "meteo_volt_c3"
if _PAKET not in sys.modules:
    _paket = types.ModuleType(_PAKET)
    _paket.__path__ = [str(INTEGRATION)]
    sys.modules[_PAKET] = _paket
pruefungen = importlib.import_module(f"{_PAKET}.pruefungen")
termine = importlib.import_module(f"{_PAKET}.termine")
standort = importlib.import_module(f"{_PAKET}.standort")
planabruf = importlib.import_module(f"{_PAKET}.planabruf")

BERLIN = ZoneInfo("Europe/Berlin")
JETZT = datetime(2026, 9, 16, 10, 0, tzinfo=timezone.utc)  # 12:00 in Berlin


def _felder(**felder):
    return {"departure": "2026-09-17 08:00:00", "return": "2026-09-17 18:00:00",
            "distance_km": 42, **felder}


def _pruefen(**felder):
    return pruefungen.werte_pruefen(_felder(**felder), "auto-1", JETZT, BERLIN)


def _fehler(schluessel, feld, **felder):
    with pytest.raises(pruefungen.Terminfehler) as info:
        _pruefen(**felder)
    assert (info.value.meldung.schluessel, info.value.meldung.feld) == (schluessel, feld)
    assert set(info.value.meldung.platzhalter) == set(pruefungen.MELDUNGEN[schluessel])


# --- Die Werte --------------------------------------------------------------


def test_gueltige_werte_so_wie_der_store_sie_traegt():
    werte = _pruefen(driver="person.anna", soc=80)
    assert werte == pruefungen.Werte(
        fahrzeug="auto-1", abfahrt="2026-09-17T08:00:00", dauer_min=600,
        wiederholung="once", strecke_km=42, fahrer="person.anna", ladestand=80.0, sichern=True)


def test_ohne_wiederholung_gilt_die_vorgabe():
    werte = pruefungen.werte_pruefen(_felder(), "auto-1", JETZT, BERLIN, "weekly")
    assert werte.wiederholung == "weekly"


def test_eine_zeit_mit_offset_wird_lokal():
    werte = _pruefen(departure="2026-09-17T06:00:00+00:00")
    assert werte.abfahrt == "2026-09-17T08:00:00"


def test_die_strecke_wird_kaufmaennisch_gerundet():
    assert _pruefen(distance_km=42.5).strecke_km == 43
    assert _pruefen(distance_km=0).strecke_km == 0


# --- Jeder Fehler mit Schluessel und Feld ------------------------------------


def test_zeit_fehlt():
    _fehler("zeit_fehlt", "departure", departure=None)
    _fehler("zeit_fehlt", "return", **{"return": ""})
    _fehler("zeit_fehlt", "departure", departure="morgen frueh")


def test_rueckkehr_vor_abfahrt():
    _fehler("rueckkehr_vor_abfahrt", "return", **{"return": "2026-09-17 08:00:00"})
    _fehler("rueckkehr_vor_abfahrt", "return", **{"return": "2026-09-17 07:00:00"})


def test_rueckkehr_vorbei_nur_bei_einmalig():
    vergangen = {"departure": "2026-09-15 08:00:00", "return": "2026-09-15 18:00:00"}
    _fehler("rueckkehr_vorbei", "return", **vergangen)
    assert _pruefen(**vergangen, repeat="daily").wiederholung == "daily"


def test_ein_laufender_termin_ist_erlaubt():
    assert _pruefen(departure="2026-09-16 08:00:00", **{"return": "2026-09-16 18:00:00"})


@pytest.mark.parametrize(("wiederholung", "rueckkehr"), [
    ("daily", "2026-09-18 08:00:00"),
    ("weekdays", "2026-09-18 08:00:00"),
    ("weekly", "2026-09-24 08:00:00"),
    ("monthly", "2026-10-15 08:00:00"),
    ("yearly", "2027-09-17 08:00:00"),
])
def test_dauer_zu_lang_ab_dem_abstand(wiederholung, rueckkehr):
    _fehler("dauer_zu_lang", "return", repeat=wiederholung, **{"return": rueckkehr})


def test_eine_minute_unter_dem_abstand_geht():
    assert _pruefen(repeat="daily", **{"return": "2026-09-18 07:59:00"}).dauer_min == 24 * 60 - 1


def test_strecke_fehlt_und_negativ():
    _fehler("strecke_fehlt", "distance_km", distance_km=None)
    _fehler("strecke_negativ", "distance_km", distance_km=-1)


def test_eine_strecke_ohne_endliche_zahl_fehlt():
    """nan und inf kommen ueber YAML oder Templates. math.floor wuerfe sonst einen allgemeinen Fehler."""
    for wert in (float("nan"), float("inf"), float("-inf")):
        _fehler("strecke_fehlt", "distance_km", distance_km=wert)
    _fehler("ladestand_bereich", "soc", soc=float("nan"))


def test_ladestand_bereich():
    _fehler("ladestand_bereich", "soc", soc=-0.1)
    _fehler("ladestand_bereich", "soc", soc=100.1)
    assert _pruefen(soc=0).ladestand == 0.0
    assert _pruefen(soc=100).ladestand == 100.0


def test_die_reihenfolge_der_tabelle():
    """Zwei Fehler zugleich: der aus der frueheren Zeile kommt."""
    _fehler("rueckkehr_vor_abfahrt", "return", distance_km=None, **{"return": "2026-09-17 07:00:00"})


def test_fahrzeug_unbekannt():
    fahrzeuge = {"eintrag-1": {"auto-1"}}
    assert pruefungen.fahrzeug_aus_geraet({("meteo_volt", "auto-1")}, "meteo_volt", fahrzeuge) == (
        "eintrag-1", "auto-1")
    for kennungen in ({("meteo_volt", "eintrag-1")}, {("andere", "auto-1")}, set()):
        with pytest.raises(pruefungen.Terminfehler) as info:
            pruefungen.fahrzeug_aus_geraet(kennungen, "meteo_volt", fahrzeuge)
        assert (info.value.meldung.schluessel, info.value.meldung.feld) == ("fahrzeug_unbekannt", "vehicle")


# --- Die Warnungen ------------------------------------------------------------


def _eintrag(eintrag_id, fahrzeug, abfahrt, fahrer, wiederholung="once"):
    return {"id": eintrag_id, "vehicle": fahrzeug, "departure": abfahrt, "duration_min": 600,
            "repeat": wiederholung, "distance_km": 42, "driver": fahrer, "soc": None,
            "until": None, "exceptions": {}}


def _warnungen(werte, eintraege, sprache="de"):
    return pruefungen.warnungen(
        werte, "neu", eintraege, BERLIN, JETZT, 15.0,
        {"person.anna": "Anna"}, {"auto-1": "ID. Buzz", "auto-2": "Zoe"}, sprache)


def test_ladestand_unter_min_warnt_mit_dem_min_soc():
    (meldung,) = _warnungen(_pruefen(soc=10), [])
    assert meldung.als_dict() == {"key": "ladestand_unter_min", "field": "soc",
                                  "placeholders": {"min": "15"}}
    assert _warnungen(_pruefen(soc=15), []) == []


def test_fahrer_doppelt_nennt_fahrer_datum_und_fahrzeug():
    werte = _pruefen(driver="person.anna", repeat="weekly")
    eigener = _eintrag("neu", "auto-1", "2026-09-17T08:00:00", "person.anna", "weekly")
    anderer = _eintrag("alt", "auto-2", "2026-10-01T12:00:00", "person.anna")
    (meldung,) = _warnungen(werte, [eigener, anderer])
    assert meldung.als_dict() == {"key": "fahrer_doppelt", "field": "driver", "placeholders": {
        "fahrer": "Anna", "datum": "Do 01.10.", "fahrzeug": "Zoe"}}
    (englisch,) = _warnungen(werte, [eigener, anderer], "en-GB")
    assert englisch.platzhalter["datum"] == "Thu 1 Oct"


def test_fahrer_doppelt_nur_in_den_naechsten_acht_wochen_und_mit_anderem_fahrzeug():
    werte = _pruefen(driver="person.anna", repeat="weekly")
    eigener = _eintrag("neu", "auto-1", "2026-09-17T08:00:00", "person.anna", "weekly")
    spaet = _eintrag("alt", "auto-2", "2026-11-19T12:00:00", "person.anna")
    gleiches_auto = _eintrag("alt2", "auto-1", "2026-09-24T12:00:00", "person.anna")
    assert _warnungen(werte, [eigener, spaet, gleiches_auto]) == []


def test_ein_geloeschter_fahrer_warnt_nicht():
    werte = _pruefen(driver="person.weg")
    eigener = _eintrag("neu", "auto-1", "2026-09-17T08:00:00", "person.weg")
    anderer = _eintrag("alt", "auto-2", "2026-09-17T12:00:00", "person.weg")
    assert _warnungen(werte, [eigener, anderer]) == []


# --- Neu planen ---------------------------------------------------------------

VORHER = standort.Planstand(letzter_versuch_um=datetime(2026, 9, 16, 9, 0, tzinfo=timezone.utc))
VERSUCHT = datetime(2026, 9, 16, 10, 0, tzinfo=timezone.utc)


def test_plan_pause_nennt_die_restdauer():
    nachher = standort.Planstand(fehler=planabruf.PlanRateLimit(retry_after=41.2), letzter_versuch_um=VERSUCHT)
    meldung = pruefungen.neu_planen_pruefen(VORHER, nachher)
    assert (meldung.schluessel, meldung.platzhalter) == ("plan_pause", {"sekunden": "42"})


def test_ein_alter_rate_limit_ohne_neuen_versuch_ist_kein_fehler():
    nachher = standort.Planstand(fehler=planabruf.PlanRateLimit(retry_after=41.2),
                                 letzter_versuch_um=VORHER.letzter_versuch_um)
    assert pruefungen.neu_planen_pruefen(VORHER, nachher) is None


def test_plan_gestoppt_nach_einem_key_fehler():
    nachher = standort.Planstand(fehler=planabruf.PlanNichtAutorisiert(status=401),
                                 letzter_versuch_um=VORHER.letzter_versuch_um)
    assert pruefungen.neu_planen_pruefen(VORHER, nachher).schluessel == "plan_gestoppt"


def test_jeder_andere_fehler_steht_im_plan():
    for fehler in (None, planabruf.PlanAbgelehnt(status=400), planabruf.PlanNichtVerfuegbar(status=503)):
        nachher = standort.Planstand(fehler=fehler, letzter_versuch_um=VERSUCHT)
        assert pruefungen.neu_planen_pruefen(VORHER, nachher) is None


def test_jede_meldung_mit_platzhaltern_traegt_genau_diese():
    """MELDUNGEN ist die Quelle fuer tests/test_uebersetzungen.py.

    Sendet der Code andere Platzhalter als die Tabelle nennt, fehlt im Text ein
    Wert oder bleibt ein {name} stehen. Die Fehler ohne Platzhalter prueft _fehler.
    """
    werte = _pruefen(soc=10, driver="person.anna", repeat="weekly")
    eigener = _eintrag("neu", "auto-1", "2026-09-17T08:00:00", "person.anna", "weekly")
    anderer = _eintrag("alt", "auto-2", "2026-09-17T12:00:00", "person.anna")
    gesendet = _warnungen(werte, [eigener, anderer])
    nachher = standort.Planstand(fehler=planabruf.PlanRateLimit(retry_after=5.0), letzter_versuch_um=VERSUCHT)
    gesendet.append(pruefungen.neu_planen_pruefen(VORHER, nachher))
    assert {m.schluessel for m in gesendet} == {k for k, namen in pruefungen.MELDUNGEN.items() if namen}
    for meldung in gesendet:
        assert set(meldung.platzhalter) == set(pruefungen.MELDUNGEN[meldung.schluessel]), meldung.schluessel
