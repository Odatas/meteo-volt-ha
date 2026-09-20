"""Prueft, was das Panel liest, ohne Home Assistant. Spec C3 Abschnitte 6 und 10.

Die Plaene sind hier erzeugt: 48 Slots ab 12:00 in Berlin, soc_end_pct im
Slot i ist 50 + i. So steht jeder erwartete Wert direkt im Test.

Was dieser Test NICHT sieht: die Websocket-Befehle, ihre Meldungen und die
Entitaeten aus C6 in Home Assistant. Das zeigt die Abnahme.
"""

import importlib
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

INTEGRATION = Path(__file__).resolve().parents[1] / "custom_components" / "meteo_volt"

_PAKET = "meteo_volt_c3"
if _PAKET not in sys.modules:
    _paket = types.ModuleType(_PAKET)
    _paket.__path__ = [str(INTEGRATION)]
    sys.modules[_PAKET] = _paket
ansicht = importlib.import_module(f"{_PAKET}.ansicht")
termine = importlib.import_module(f"{_PAKET}.termine")
standort = importlib.import_module(f"{_PAKET}.standort")
planabruf = importlib.import_module(f"{_PAKET}.planabruf")

BERLIN = ZoneInfo("Europe/Berlin")
JETZT = datetime(2026, 9, 16, 10, 0, tzinfo=timezone.utc)  # 12:00 in Berlin
BEGINN = datetime(2026, 9, 16, 12, 0, tzinfo=BERLIN)


def _plan(verletzungen=()):
    slots = [{"t": (BEGINN + timedelta(minutes=15 * i)).isoformat(), "charge": False,
              "price": 0.2, "source": "epex", "soc_end_pct": 50.0 + i} for i in range(48)]
    return {
        "slot_minutes": 15,
        "horizon_end": "2026-09-17T00:00:00+02:00",
        "prices_known_until": "2026-09-16T23:45:00+02:00",
        "computed_at": "2026-09-16T11:50:00+02:00",
        "vehicles": [{"id": "auto-1", "slots": slots, "intervals": [], "total_kwh": 0.0,
                      "total_cost_eur": 0.0, "soc_end_pct": 97.0, "violations": list(verletzungen)}],
    }


def _stand(plan=None, erhalten_um=JETZT - timedelta(minutes=5), **felder):
    return standort.Planstand(
        plan=_plan() if plan is None else plan,
        erhalten_um=erhalten_um,
        anfrage={"vehicles": [{"id": "auto-1", "soc_pct": 47.5, "connection": {"station_id": None}}],
                 "stations": []},
        **felder)


def _termin(abfahrt, dauer=60, eintrag="e1", fahrzeug="auto-1", fahrer=None, **felder):
    eintrag_dict = {"id": eintrag, "vehicle": fahrzeug, "departure": abfahrt, "duration_min": dauer,
                    "repeat": "once", "distance_km": 42, "driver": fahrer, "soc": None, "until": None,
                    "exceptions": {}, **felder}
    (termin,) = termine.termine_von(eintrag_dict, BERLIN, JETZT - timedelta(days=1), JETZT + timedelta(days=3))
    return termin


# --- Planwerte je Termin --------------------------------------------------------


def test_die_ladestaende_vor_und_nach_der_fahrt():
    werte = ansicht.planwerte(_termin("2026-09-16T14:00:00"), _stand(), JETZT, 15.0)
    assert werte == {"soc_at_departure": 57.0, "soc_after_trip": 58.0, "target_missing_kwh": None,
                     "below_min": False, "running_until": None}


def test_die_abfahrt_im_ersten_slot_nimmt_den_ladestand_aus_dem_request():
    werte = ansicht.planwerte(_termin("2026-09-16T12:05:00"), _stand(), JETZT, 15.0)
    assert (werte["soc_at_departure"], werte["soc_after_trip"]) == (47.5, 50.0)


def test_ein_unerreichbares_ziel_nennt_die_fehlenden_kwh():
    verletzung = {"type": "target_unreachable", "constraint_id": "e1/2026-09-16/ziel",
                  "missing_kwh": 13.4, "message": "..."}
    fremd = {**verletzung, "constraint_id": "e2/2026-09-16/ziel", "missing_kwh": 9.9}
    basis = {**verletzung, "constraint_id": "base", "missing_kwh": 1.0}
    stand = _stand(_plan([fremd, basis, verletzung]))
    assert ansicht.planwerte(_termin("2026-09-16T14:00:00"), stand, JETZT, 15.0)["target_missing_kwh"] == 13.4


def test_unter_dem_min_soc_nach_der_fahrt():
    assert ansicht.planwerte(_termin("2026-09-16T14:00:00"), _stand(), JETZT, 58.1)["below_min"]
    assert not ansicht.planwerte(_termin("2026-09-16T14:00:00"), _stand(), JETZT, 58.0)["below_min"]


def test_ein_laufender_termin_nennt_seine_rueckkehr():
    werte = ansicht.planwerte(_termin("2026-09-16T11:00:00", dauer=120), _stand(), JETZT, 15.0)
    assert werte == {"soc_at_departure": None, "soc_after_trip": None, "target_missing_kwh": None,
                     "below_min": False, "running_until": "2026-09-16T13:00:00+02:00"}


def test_hinter_dem_horizont_und_ohne_brauchbaren_plan_kein_planwert():
    assert ansicht.planwerte(_termin("2026-09-17T08:00:00"), _stand(), JETZT, 15.0) is None
    alt = _stand(erhalten_um=JETZT - timedelta(hours=12))
    assert ansicht.planwerte(_termin("2026-09-16T14:00:00"), alt, JETZT, 15.0) is None
    assert ansicht.planwerte(_termin("2026-09-16T14:00:00"), standort.Planstand(), JETZT, 15.0) is None
    kaputt = _stand({**_plan(), "slot_minutes": "15"})
    assert ansicht.planwerte(_termin("2026-09-16T14:00:00"), kaputt, JETZT, 15.0) is None


# --- Hinweise -------------------------------------------------------------------


def test_overlap_mit_einem_anderen_termin_desselben_fahrzeugs():
    a = _termin("2026-09-16T14:00:00", eintrag="e1")
    b = _termin("2026-09-16T14:30:00", eintrag="e2")
    anschluss = _termin("2026-09-16T15:00:00", eintrag="e3")
    assert ansicht.hinweise(a, [a, b, anschluss], {}, set()) == [{"type": "overlap"}]
    assert ansicht.hinweise(anschluss, [a, anschluss], {}, set()) == []


def test_driver_busy_nennt_das_andere_fahrzeug():
    eigener = _termin("2026-09-16T14:00:00", eintrag="e1", fahrer="person.anna")
    anderer = _termin("2026-09-16T14:30:00", eintrag="e2", fahrzeug="auto-2", fahrer="person.anna")
    spaeter = _termin("2026-09-16T15:00:00", eintrag="e3", fahrzeug="auto-3", fahrer="person.anna")
    geraete = {"auto-1": "geraet-1", "auto-2": "geraet-2", "auto-3": "geraet-3"}
    assert ansicht.hinweise(eigener, [eigener, anderer, spaeter], geraete, {"person.anna"}) == [
        {"type": "driver_busy", "vehicle": "geraet-2"}]
    assert ansicht.hinweise(eigener, [eigener, anderer], geraete, set()) == []


# --- Die Termine fuer das Panel ------------------------------------------------------


def test_ein_termin_fuer_das_panel():
    termin = _termin("2026-09-16T14:00:00", fahrer="person.weg")
    (eintrag,) = ansicht.termine_ansicht([termin], [termin], _stand(), JETZT, {"auto-1": 15.0},
                                         {"auto-1": "geraet-1"}, set())
    assert eintrag == {
        "entry": "e1", "date": "2026-09-16", "vehicle": "geraet-1",
        "departure": "2026-09-16T14:00:00+02:00", "return": "2026-09-16T15:00:00+02:00",
        "distance_km": 42, "driver": None, "soc": None, "keep_min_soc": False,
        "repeat": "once", "changed": False,
        "plan": {"soc_at_departure": 57.0, "soc_after_trip": 58.0, "target_missing_kwh": None,
                 "below_min": False, "running_until": None},
        "hints": []}


# --- Der Plan eines Fahrzeugs ---------------------------------------------------------


def test_der_plan_eines_fahrzeugs():
    stand = _stand(fehler=planabruf.PlanNichtVerfuegbar(status=503))
    c6 = {"charge_now": False, "charge_now_kw": 0.0, "next_charge_start": None}
    plan = ansicht.fahrzeugplan(stand, "auto-1", c6, True)
    assert plan["slots"] == _plan()["vehicles"][0]["slots"]
    assert (plan["soc_end_pct"], plan["horizon_end"]) == (97.0, "2026-09-17T00:00:00+02:00")
    assert plan["received_at"] == "2026-09-16T09:55:00+00:00"
    assert (plan["charge_now"], plan["planning"]) == (False, True)
    assert plan["error"] == "PlanNichtVerfuegbar: Status 503"


def test_ohne_plan_fuer_das_fahrzeug_sind_die_planfelder_leer():
    plan = ansicht.fahrzeugplan(standort.Planstand(), "auto-1", {}, False)
    assert all(plan[k] is None for k in (*ansicht.AUS_DEM_FAHRZEUGPLAN, *ansicht.AUS_DEM_KOPF, "error"))
    assert ansicht.fahrzeugplan(_stand(), "auto-2", {}, False)["slots"] is None


def test_die_werte_aus_c6():
    assert [ansicht.c6_wert("charge_now", z, BERLIN) for z in ("on", "off", "unavailable", None)] == [
        True, False, None, None]
    assert ansicht.c6_wert("charge_now_kw", "11.0", BERLIN) == 11.0
    assert ansicht.c6_wert("charge_now_kw", "unknown", BERLIN) is None
    assert ansicht.c6_wert("next_charge_start", "2026-09-16T20:00:00+00:00", BERLIN) == "2026-09-16T22:00:00+02:00"
    assert ansicht.c6_wert("next_charge_start", "unknown", BERLIN) is None


# --- Die Preise -----------------------------------------------------------------------


def test_die_preise_ab_dem_laufenden_slot():
    prognose = {
        "model": "wx", "computed_at": "2026-09-16T09:50:00+00:00",
        "prices_known_until": "2026-09-16T21:45:00+00:00",
        "slots": [{"target_timestamp": f"2026-09-16T09:{m:02d}:00+00:00", "q10": 0.1, "q50": 0.2,
                   "q90": 0.3, "source": "epex"} for m in (30, 45)]
                 + [{"target_timestamp": "2026-09-16T10:00:00+00:00", "q10": 0.1, "q50": 0.2,
                     "q90": 0.3, "source": "forecast"}],
    }
    preise = ansicht.preise(prognose, JETZT + timedelta(minutes=-1))
    assert [slot["t"] for slot in preise["slots"]] == ["2026-09-16T09:45:00+00:00", "2026-09-16T10:00:00+00:00"]
    assert preise["slots"][1] == {"t": "2026-09-16T10:00:00+00:00", "q10": 0.1, "q50": 0.2, "q90": 0.3,
                                  "source": "forecast"}
    assert (preise["model"], preise["prices_known_until"]) == ("wx", "2026-09-16T21:45:00+00:00")


def test_ohne_prognose_keine_preise():
    assert ansicht.preise(None, JETZT) == {"slots": [], "prices_known_until": None, "computed_at": None,
                                           "model": None}


def test_der_termin_traegt_seinen_haken():
    """Spec C10 Abschnitt 7: das Panel liest ihn beim Bearbeiten."""
    termin = _termin("2026-09-16T14:00:00", keep_min_soc=True)
    (eintrag,) = ansicht.termine_ansicht([termin], [termin], _stand(), JETZT, {"auto-1": 15.0},
                                         {"auto-1": "geraet-1"}, set())
    assert eintrag["keep_min_soc"] is True
