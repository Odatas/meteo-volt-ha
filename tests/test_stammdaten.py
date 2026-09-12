"""Prueft die Abbildung Subentry -> Kontrakt-Fragment.

Die Abbildung ist die Stelle, an der ein Fehler wehtut: ein vertauschter
Faktor 100 beim Wirkungsgrad faellt in keinem Formular auf, wohl aber in der
Rechnung des Planers. Geprueft wird gegen die vendorten Schemas, nicht gegen
eine hier nochmal hingeschriebene Erwartung.

Was dieser Test NICHT sieht: das Formular, den Config-Flow und die
Uebersetzungen. Die brauchen Home Assistant und werden von Hand abgenommen.
"""

import importlib.util
import json
from pathlib import Path

import jsonschema
import pytest

WURZEL = Path(__file__).resolve().parents[1]
INTEGRATION = WURZEL / "custom_components" / "meteo_volt"
CONTRACT = WURZEL / "tests" / "fixtures" / "contract"

# Per Pfad geladen, NICHT als custom_components.meteo_volt.stammdaten: das
# Paket zu importieren zieht dessen __init__.py und damit homeassistant
# herein, das in den Testabhaengigkeiten nicht steckt. Der Ladeweg ist
# zugleich die schaerfste Fassung der Auflage "stammdaten.py hat keine
# HA-Importe" -- bekaeme das Modul je einen, scheitert schon dieser Import.
_SPEC = importlib.util.spec_from_file_location(
    "meteo_volt_stammdaten", INTEGRATION / "stammdaten.py")
stammdaten = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(stammdaten)


def _schema() -> dict:
    roh = json.loads((CONTRACT / "plan-request.schema.json").read_text(encoding="utf-8"))
    return {k: v for k, v in roh.items() if k != "x-meteo-volt-contract"}


REQUEST_SCHEMA = _schema()


def teilschema(name: str) -> dict:
    """Ein einzelnes Modell aus $defs, allein validierbar."""
    return {"$ref": f"#/$defs/{name}", "$defs": REQUEST_SCHEMA["$defs"]}


def test_das_teilschema_faengt_ueberhaupt_etwas():
    """Gegenprobe zuerst. Ein Validator, der alles durchwinkt, waere schlimmer
    als keiner -- und genau das passiert, wenn der $ref ins Leere zeigt."""
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"id": "x", "max_power_kw": 11.0, "phases": 2},
                            teilschema("Station"))


def test_ladepunkt_aus_vorbelegung_ist_kontraktkonform():
    fragment = stammdaten.zu_ladepunkt(dict(stammdaten.LADEPUNKT_DEFAULTS), "wb-1")
    jsonschema.validate(fragment, teilschema("Station"))
    assert fragment["id"] == "wb-1"


def test_ladepunkt_traegt_keinen_wirkungsgrad_des_kontrakt_defaults():
    """Abschnitt 3 der Spec: 1.0, nicht der Kontrakt-Default 0.99. Sonst wird
    das eine Prozent doppelt gezaehlt, weil der Fahrzeugwert es schon enthaelt
    -- und zwar still."""
    fragment = stammdaten.zu_ladepunkt(dict(stammdaten.LADEPUNKT_DEFAULTS), "wb-1")
    assert fragment["efficiency"] == 1.0


def test_weggelassene_optionale_felder_ergeben_die_vorbelegung():
    """Min. Leistung und Phasen stehen im eingeklappten Abschnitt. Wer ihn nie
    aufklappt, schickt sie nicht mit -- dann darf kein None ankommen."""
    fragment = stammdaten.zu_ladepunkt({stammdaten.FELD_MAX_LEISTUNG: 22.0}, "wb-2")
    assert fragment["min_power_kw"] == 1.4
    assert fragment["phases"] == 3
    assert fragment["available"] is True
    jsonschema.validate(fragment, teilschema("Station"))


def test_fahrzeug_aus_vorbelegung_ist_kontraktkonform():
    fragment = stammdaten.zu_fahrzeug(
        dict(stammdaten.FAHRZEUG_DEFAULTS), "auto-1", soc_pct=47.0)
    jsonschema.validate(fragment, teilschema("VehicleProfile"))
    assert fragment["id"] == "auto-1"
    assert fragment["soc_pct"] == 47.0


def test_der_wirkungsgrad_wird_ein_stuetzpunkt_bei_voller_leistung():
    """92 Prozent werden zu eta 0.92, und der Punkt liegt bei max_charge_kw.
    Der Faktor 100 ist die Stelle, an der ein Fehler am teuersten waere: er
    faellt in keinem Formular auf."""
    fragment = stammdaten.zu_fahrzeug(
        dict(stammdaten.FAHRZEUG_DEFAULTS), "auto-1", soc_pct=50.0)
    assert fragment["efficiency_curve"] == [{"kw": 11.0, "eta": 0.92}]


def test_das_verbrauchsmodell_ist_none_und_nicht_geteilt():
    """type none, weil die Strecke zum Fahrprofil gehoert. Und je Aufruf ein
    eigenes dict -- ein geteiltes liesse einen Aufrufer die Werte aller
    anderen aendern."""
    a = stammdaten.zu_fahrzeug(dict(stammdaten.FAHRZEUG_DEFAULTS), "a", soc_pct=10.0)
    b = stammdaten.zu_fahrzeug(dict(stammdaten.FAHRZEUG_DEFAULTS), "b", soc_pct=10.0)
    assert a["consumption"] == {"type": "none"}
    assert a["consumption"] is not b["consumption"]
    assert a["consumption"] is not stammdaten.VERBRAUCHSMODELL


def test_ohne_ladepunkt_steht_station_id_auf_null():
    fragment = stammdaten.zu_fahrzeug(
        dict(stammdaten.FAHRZEUG_DEFAULTS), "auto-1", soc_pct=50.0)
    assert fragment["connection"] == {"station_id": None}
    jsonschema.validate(fragment, teilschema("VehicleProfile"))


def test_der_messzeitpunkt_faellt_weg_wenn_es_keinen_gibt():
    """soc_measured_at ist kein Pflichtfeld. Ein None mitzuschicken waere
    etwas anderes als es wegzulassen -- der Kontrakt erlaubt beides, aber ein
    fehlender Zeitpunkt soll fehlen und nicht als gemessen gelten."""
    ohne = stammdaten.zu_fahrzeug(
        dict(stammdaten.FAHRZEUG_DEFAULTS), "auto-1", soc_pct=50.0)
    assert "soc_measured_at" not in ohne

    mit = stammdaten.zu_fahrzeug(
        dict(stammdaten.FAHRZEUG_DEFAULTS), "auto-1", soc_pct=50.0,
        soc_measured_at="2026-09-12T08:00:00+02:00")
    assert mit["soc_measured_at"] == "2026-09-12T08:00:00+02:00"
    jsonschema.validate(mit, teilschema("VehicleProfile"))


def test_weggelassene_erweiterte_fahrzeugfelder_ergeben_die_vorbelegung():
    daten = {
        stammdaten.FELD_KAPAZITAET: 77.0,
        stammdaten.FELD_SOC_MIN: 20.0,
        stammdaten.FELD_SOC_MAX: 90.0,
        stammdaten.FELD_MAX_LADELEISTUNG: 7.4,
        stammdaten.FELD_VERBRAUCH: 21.0,
    }
    fragment = stammdaten.zu_fahrzeug(daten, "auto-3", soc_pct=33.0)
    assert fragment["min_charge_kw"] == 1.4
    assert fragment["efficiency_curve"] == [{"kw": 7.4, "eta": 0.92}]
    jsonschema.validate(fragment, teilschema("VehicleProfile"))


# --- Aufloesung der Ladepunkt-Zuordnung -------------------------------------
# Die fuenf Zeilen der Tabelle aus Abschnitt 5 der Spec, einzeln.

def test_ohne_gewaehlten_ladepunkt_keine_station():
    assert stammdaten.ladepunkt_aufloesen(None, {"wb-1"}) is None


def test_geloeschter_ladepunkt_wird_null_statt_haengender_verweis():
    """Es gibt keine Fehler-Fixture fuer eine unbekannte station_id -- der
    Server pinnt sein Verhalten dort nicht. Also darf der Client gar nicht
    erst eine erzeugen."""
    assert stammdaten.ladepunkt_aufloesen("wb-weg", {"wb-1"}) is None


def test_nicht_angesteckt_heisst_keine_station():
    assert stammdaten.ladepunkt_aufloesen("wb-1", {"wb-1"}, angesteckt=False) is None


def test_angesteckt_heisst_die_gewaehlte_station():
    assert stammdaten.ladepunkt_aufloesen("wb-1", {"wb-1"}, angesteckt=True) == "wb-1"


def test_ohne_angesteckt_sensor_gilt_das_fahrzeug_als_angesteckt():
    """Der dumme Fall ist die Grundeinstellung. Die Gegenannahme machte den
    Plan fuer jeden nutzlos, der keinen solchen Sensor hat."""
    assert stammdaten.ladepunkt_aufloesen("wb-1", {"wb-1"}, angesteckt=None) == "wb-1"


# --- Namensvergabe ----------------------------------------------------------

def test_erster_name_ohne_eingabe():
    assert stammdaten.naechster_name([], stammdaten.TYP_FAHRZEUG, "de") == "Fahrzeug 1"


def test_zweiter_name_zaehlt_hoch():
    assert stammdaten.naechster_name(
        ["Fahrzeug 1"], stammdaten.TYP_FAHRZEUG, "de") == "Fahrzeug 2"


def test_eine_geloeschte_nummer_wird_wiederverwendet():
    """Nicht len()+1: wer 'Fahrzeug 1' loescht und neu anlegt, bekaeme sonst
    eine Dublette zu 'Fahrzeug 2'."""
    assert stammdaten.naechster_name(
        ["Fahrzeug 2"], stammdaten.TYP_FAHRZEUG, "de") == "Fahrzeug 1"


def test_eigene_namen_stoeren_die_nummerierung_nicht():
    assert stammdaten.naechster_name(
        ["Papas Kombi"], stammdaten.TYP_FAHRZEUG, "de") == "Fahrzeug 1"


def test_ladepunkt_heisst_in_beiden_sprachen_wallbox():
    assert stammdaten.naechster_name([], stammdaten.TYP_LADEPUNKT, "de") == "Wallbox 1"
    assert stammdaten.naechster_name([], stammdaten.TYP_LADEPUNKT, "en") == "Wallbox 1"


def test_eine_unbekannte_sprache_faellt_auf_englisch_zurueck():
    assert stammdaten.naechster_name(
        [], stammdaten.TYP_FAHRZEUG, "fr") == "Vehicle 1"


# --- Abschnitte -------------------------------------------------------------

def test_abschnitte_werden_flachgezogen():
    """HA liefert section-Felder verschachtelt zurueck. Gespeichert wird flach,
    damit zu_fahrzeug nichts von Formularabschnitten wissen muss."""
    verschachtelt = {
        "name": "Kombi",
        "batterie": {"capacity_kwh": 58.0},
        "erweitert": {"min_charge_kw": 1.4, "efficiency_pct": 92.0},
    }
    flach = stammdaten.flach_aus_abschnitten(
        verschachtelt, ("batterie", "erweitert"))
    assert flach == {
        "name": "Kombi",
        "capacity_kwh": 58.0,
        "min_charge_kw": 1.4,
        "efficiency_pct": 92.0,
    }


def test_ein_unerwartetes_dict_bleibt_stehen():
    """Nur benannte Abschnitte werden aufgeloest. Alles andere durchzureichen
    hiesse raten -- und ein falsch aufgeloestes dict faellt spaeter still
    als fehlendes Feld auf."""
    flach = stammdaten.flach_aus_abschnitten(
        {"fremd": {"a": 1}}, ("batterie",))
    assert flach == {"fremd": {"a": 1}}


# --- Der Aufbau ist die eine Quelle -----------------------------------------

def test_jedes_vorbelegte_feld_steht_auch_im_formular():
    """Sonst gaebe es eine Vorbelegung fuer ein Feld, das niemand sieht -- und
    umgekehrt ein Feld ohne Vorbelegung, das als None ankaeme."""
    assert set(stammdaten.LADEPUNKT_DEFAULTS) <= set(stammdaten.LADEPUNKT_FELDER)
    assert set(stammdaten.FAHRZEUG_DEFAULTS) <= set(stammdaten.FAHRZEUG_FELDER)


def test_kein_feld_steht_in_zwei_abschnitten():
    """Ein doppelt gefuehrtes Feld erschiene zweimal im Formular und traefe
    beim Flachziehen eine Zufallsentscheidung."""
    for aufbau in (stammdaten.LADEPUNKT_AUFBAU, stammdaten.FAHRZEUG_AUFBAU):
        felder = stammdaten._felder(aufbau)
        assert len(felder) == len(set(felder)), felder


# --- Die Grenzen des Battery-Guards -----------------------------------------

def test_guard_in_richtiger_reihenfolge_ist_in_ordnung():
    daten = {stammdaten.FELD_SOC_MIN: 15.0, stammdaten.FELD_SOC_MAX: 80.0}
    assert stammdaten.soc_grenzen_pruefen(daten) is None


def test_guard_verkehrt_herum_wird_abgewiesen():
    daten = {stammdaten.FELD_SOC_MIN: 80.0, stammdaten.FELD_SOC_MAX: 15.0}
    assert stammdaten.soc_grenzen_pruefen(daten) == {"base": "soc_range"}


def test_guard_mit_gleichstand_wird_abgewiesen():
    """Die Grenze selbst, nicht nur die eindeutig falsche Seite. Bei
    soc_min == soc_max bleibt dem Plan kein Spielraum -- ein spaeteres > statt
    >= faellt sonst erst der manuellen Abnahme auf, und auch nur, wenn jemand
    genau den Gleichstand probiert."""
    daten = {stammdaten.FELD_SOC_MIN: 50.0, stammdaten.FELD_SOC_MAX: 50.0}
    assert stammdaten.soc_grenzen_pruefen(daten) == {"base": "soc_range"}


# --- Die Grenze zum Aufrufer ------------------------------------------------

def test_ein_state_string_statt_eines_bool_scheitert_laut():
    """'off' ist truthy. Waere das erlaubt, gaelte ein nicht angestecktes
    Fahrzeug als angesteckt -- still das Falsche, an genau der Stelle, an der
    C5 spaeter einen HA-State uebergeben koennte."""
    with pytest.raises(TypeError, match="bool oder None"):
        stammdaten.ladepunkt_aufloesen("wb-1", {"wb-1"}, angesteckt="off")
