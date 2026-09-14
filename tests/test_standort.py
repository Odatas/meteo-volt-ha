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
