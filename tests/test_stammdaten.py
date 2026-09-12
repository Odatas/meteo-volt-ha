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
