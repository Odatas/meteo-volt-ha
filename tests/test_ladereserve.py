"""Prueft die Rechnung hinter dem Haken, ohne Home Assistant. Spec C10 Abschnitte 2 und 5.

Die Zahlen stammen aus den Fahrzeug-Defaults: 58 kWh, 19,5 kWh/100 km,
Min-SoC 15 %. 175 km kosten damit 58,8 Prozentpunkte.

Was dieser Test NICHT sieht: ob das Panel dieselbe Zahl rechnet. Das ist die
Gegenprobe in tests/test_panel.py.
"""

import importlib
import sys
import types
from pathlib import Path

INTEGRATION = Path(__file__).resolve().parents[1] / "custom_components" / "meteo_volt"

_PAKET = "meteo_volt_c3"
if _PAKET not in sys.modules:
    _paket = types.ModuleType(_PAKET)
    _paket.__path__ = [str(INTEGRATION)]
    sys.modules[_PAKET] = _paket
ladereserve = importlib.import_module(f"{_PAKET}.ladereserve")

AUTO = ladereserve.Fahrzeugwerte(soc_min_pct=15.0, capacity_kwh=58.0, consumption_kwh_per_100km=19.5)


def test_die_fahrt_kostet_km_mal_verbrauch_durch_kapazitaet():
    assert ladereserve.fahrt_pct(175, AUTO) == 175 * 19.5 / 58.0
    assert ladereserve.fahrt_pct(0, AUTO) == 0.0


def test_gesichert_ist_min_soc_plus_fahrt_aufgerundet():
    # 15 + 58.836... = 73.836..., aufgerundet 74
    assert ladereserve.gesichert(175, AUTO) == 74.0


def test_gesichert_rundet_auf_und_nicht_ab():
    schmal = ladereserve.Fahrzeugwerte(soc_min_pct=15.0, capacity_kwh=100.0, consumption_kwh_per_100km=10.0)
    # 15 + 10.1 = 25.1, abgerundet waere 25 und damit unter der Zusage
    assert ladereserve.gesichert(101, schmal) == 26.0


def test_gesichert_endet_bei_hundert():
    assert ladereserve.gesichert(400, AUTO) == 100.0


def test_bei_null_kilometern_ist_gesichert_der_min_soc():
    assert ladereserve.gesichert(0, AUTO) == 15.0


def test_ohne_haken_und_ohne_ziel_ist_der_ladestand_offen():
    assert ladereserve.befund(42, None, False, AUTO) == ladereserve.LADESTAND_OFFEN


def test_ein_ladestand_unter_dem_min_soc_ist_kein_ziel():
    assert ladereserve.befund(42, 10, False, AUTO) == ladereserve.LADESTAND_OFFEN


def test_ein_zu_kleines_eigenes_ziel_zieht_unter_den_min_soc():
    # 40 - 58.8 liegt unter 15
    assert ladereserve.befund(175, 40, False, AUTO) == ladereserve.FAHRT_UNTER_MIN


def test_ein_grosses_eigenes_ziel_reicht():
    assert ladereserve.befund(175, 100, False, AUTO) is None


def test_der_haken_allein_genuegt():
    assert ladereserve.befund(175, None, True, AUTO) is None


def test_auch_voll_geladen_reicht_es_nicht():
    # 400 km kosten 134,5 Punkte, zwischen 100 und 15 liegen 85
    assert ladereserve.befund(400, None, True, AUTO) == ladereserve.FAHRT_ZU_WEIT
    assert ladereserve.befund(400, 100, False, AUTO) == ladereserve.FAHRT_ZU_WEIT


def test_genau_aufgehend_warnt_nicht():
    genau = ladereserve.Fahrzeugwerte(soc_min_pct=15.0, capacity_kwh=100.0, consumption_kwh_per_100km=100.0)
    # 85 km kosten genau 85 Punkte: 100 - 85 == 15, der Min-SoC ist erreicht
    assert ladereserve.befund(85, 100, False, genau) is None
    assert ladereserve.befund(85.1, 100, False, genau) == ladereserve.FAHRT_ZU_WEIT
