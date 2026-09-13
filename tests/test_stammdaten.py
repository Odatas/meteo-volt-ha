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


def test_ladepunkt_schickt_nur_was_der_planer_liest():
    """meteovolt_planner/slots.py liest vom Ladepunkt max_power_kw, efficiency
    und available -- nichts sonst. min_power_kw und phases fehlen deshalb im
    Fragment, der Server nimmt ihre Defaults. Ueber den Kontrakt entscheidet A5."""
    fragment = stammdaten.zu_ladepunkt({stammdaten.FELD_MAX_LEISTUNG: 22.0}, "wb-2")
    assert set(fragment) == {"id", "max_power_kw", "efficiency", "available"}
    assert fragment["available"] is True
    jsonschema.validate(fragment, teilschema("Station"))


def test_alte_felder_aus_beta3_sickern_nicht_durch():
    """Ein in 1.1.0-beta.3 angelegter Ladepunkt traegt min_power_kw und phases
    noch in seinen gespeicherten Daten. Die Abbildung darf sie nicht
    weiterreichen, sonst entschiede ein Altbestand ueber das Fragment."""
    alt = {stammdaten.FELD_MAX_LEISTUNG: 11.0, "min_power_kw": 2.0, "phases": 1}
    fragment = stammdaten.zu_ladepunkt(alt, "wb-alt")
    assert "min_power_kw" not in fragment
    assert "phases" not in fragment


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


def test_ein_weggelassener_wirkungsgrad_ergibt_die_vorbelegung():
    daten = {
        stammdaten.FELD_KAPAZITAET: 77.0,
        stammdaten.FELD_SOC_MIN: 20.0,
        stammdaten.FELD_SOC_MAX: 90.0,
        stammdaten.FELD_MAX_LADELEISTUNG: 7.4,
        stammdaten.FELD_VERBRAUCH: 21.0,
    }
    fragment = stammdaten.zu_fahrzeug(daten, "auto-3", soc_pct=33.0)
    assert fragment["efficiency_curve"] == [{"kw": 7.4, "eta": 0.92}]
    jsonschema.validate(fragment, teilschema("VehicleProfile"))


def test_min_charge_kw_geht_nicht_mehr_mit():
    """meteovolt_planner liest min_charge_kw an keiner Stelle. Es fehlt im
    Formular und im Fragment, der Server nimmt den Default -- auch wenn ein in
    1.1.0-beta.4 angelegtes Fahrzeug den Wert noch in seinen Daten traegt.
    Ueber den Kontrakt entscheidet A5."""
    alt = dict(stammdaten.FAHRZEUG_DEFAULTS)
    alt["min_charge_kw"] = 3.7
    fragment = stammdaten.zu_fahrzeug(alt, "auto-alt", soc_pct=40.0)
    assert "min_charge_kw" not in fragment
    jsonschema.validate(fragment, teilschema("VehicleProfile"))


# --- Namensvergabe ----------------------------------------------------------
# Leeres Namensfeld -> Name aus der kennzeichnenden Zahl. Entschieden am
# 2026-09-13, beim Aendern der Leistung wird er nicht nachgezogen.

LP = stammdaten.TYP_LADEPUNKT
FZ = stammdaten.TYP_FAHRZEUG


def test_ladepunkt_heisst_nach_seiner_leistung():
    daten = {stammdaten.FELD_MAX_LEISTUNG: 11.0}
    assert stammdaten.naechster_name([], LP, daten, "de") == "Wallbox 11 kW"


def test_fahrzeug_heisst_nach_seiner_kapazitaet():
    daten = {stammdaten.FELD_KAPAZITAET: 58.0}
    assert stammdaten.naechster_name([], FZ, daten, "de") == "Fahrzeug 58 kWh"
    assert stammdaten.naechster_name([], FZ, daten, "en") == "Vehicle 58 kWh"


def test_die_zahl_folgt_der_sprache():
    """'7.4 kW' in einer deutschen Oberflaeche sieht aus wie ein Tippfehler."""
    daten = {stammdaten.FELD_MAX_LEISTUNG: 7.4}
    assert stammdaten.naechster_name([], LP, daten, "de") == "Wallbox 7,4 kW"
    assert stammdaten.naechster_name([], LP, daten, "en") == "Wallbox 7.4 kW"


def test_eine_regionale_sprache_nimmt_ihre_grundsprache():
    """hass.config.language kann 'de-CH' sein. Ohne Grundsprache fiele die
    Schweiz auf Englisch zurueck."""
    daten = {stammdaten.FELD_KAPAZITAET: 58.0}
    assert stammdaten.naechster_name([], FZ, daten, "de-CH") == "Fahrzeug 58 kWh"


def test_eine_unbekannte_sprache_faellt_auf_englisch_zurueck():
    daten = {stammdaten.FELD_KAPAZITAET: 58.0}
    assert stammdaten.naechster_name([], FZ, daten, "fr") == "Vehicle 58 kWh"


def test_ein_doppelter_name_bekommt_die_kleinste_freie_nummer():
    """Zwei gleich starke Boxen muessen auseinanderzuhalten sein -- das war
    der Grund fuer das Namensfeld ueberhaupt. Und eine Luecke wird gefuellt,
    statt hochzuzaehlen."""
    daten = {stammdaten.FELD_MAX_LEISTUNG: 11.0}
    assert stammdaten.naechster_name(
        ["Wallbox 11 kW"], LP, daten, "de") == "Wallbox 11 kW (2)"
    assert stammdaten.naechster_name(
        ["Wallbox 11 kW", "Wallbox 11 kW (3)"], LP, daten, "de") == "Wallbox 11 kW (2)"


def test_eigene_namen_stoeren_die_vergabe_nicht():
    daten = {stammdaten.FELD_MAX_LEISTUNG: 11.0}
    assert stammdaten.naechster_name(["Garage"], LP, daten, "de") == "Wallbox 11 kW"


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
