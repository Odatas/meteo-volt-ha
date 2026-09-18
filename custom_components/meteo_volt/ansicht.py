"""Was das Panel liest, ohne Home Assistant. Spec C3 Abschnitt 6.

Dieses Modul importiert bewusst NICHTS aus Home Assistant und nichts aus
aiohttp. Hier entsteht der Inhalt der Websocket-Befehle: die Termine mit
Planwerten und Hinweisen, der Plan eines Fahrzeugs und die Preise.
terminwebsocket.py liest dafuer aus Home Assistant und schickt ab.

Zeitpunkte gehen als ISO 8601 mit Offset hinaus.

Spec: meteo-volt-brain/docs/features/C3-konfig-entitaeten/spec.md, Abschnitt 6
"""

from __future__ import annotations

from datetime import datetime, timedelta, tzinfo

from . import standort
from .terminanfrage import ZIEL, zerlegen
from .termine import Termin, ueberschneiden, utc

# Die Prognose rechnet in Viertelstunden.
PREISSLOT = timedelta(minutes=15)


# --- Termine, Spec Abschnitt 6 ----------------------------------------------


def planwerte(termin: Termin, stand: standort.Planstand, jetzt: datetime, soc_min: float) -> dict | None:
    """Die Planwerte eines Termins, oder None.

    None hinter horizon_end und ohne brauchbaren Plan (C5-Spec Abschnitt 8,
    abgelesen ueber was_gilt). Laeuft der Termin schon, gibt es keinen Slot
    mit der Abfahrt: die Ladestaende sind dann None, running_until nennt
    die Rueckkehr.
    """
    if standort.was_gilt(stand, termin.fahrzeug, jetzt, None)["quelle"] != standort.QUELLE_PLAN:
        return None
    try:
        plan = stand.plan
        if utc(termin.abfahrt) >= utc(datetime.fromisoformat(plan["horizon_end"])):
            return None
        fahrzeugplan = next(v for v in plan["vehicles"] if v.get("id") == termin.fahrzeug)
        schritt = timedelta(minutes=plan["slot_minutes"])
        slots = fahrzeugplan["slots"]
        index = next(
            (i for i, slot in enumerate(slots)
             if utc(datetime.fromisoformat(slot["t"])) <= utc(termin.abfahrt)
             < utc(datetime.fromisoformat(slot["t"])) + schritt),
            None,
        )
        bei_abfahrt = nach_fahrt = None
        if index is not None:
            nach_fahrt = slots[index]["soc_end_pct"]
            bei_abfahrt = slots[index - 1]["soc_end_pct"] if index > 0 else _ladestand_im_request(stand, termin.fahrzeug)
        fehlend = next(
            (v.get("missing_kwh") for v in fahrzeugplan.get("violations") or []
             if v.get("type") == "target_unreachable"
             and zerlegen(v.get("constraint_id")) == (termin.eintrag, termin.datum, ZIEL)),
            None,
        )
    except (AttributeError, KeyError, StopIteration, TypeError, ValueError):
        return None  # ein Plan ohne die Form des Kontrakts
    laeuft = utc(termin.abfahrt) <= utc(jetzt) < utc(termin.rueckkehr)
    return {
        "soc_at_departure": bei_abfahrt,
        "soc_after_trip": nach_fahrt,
        "target_missing_kwh": fehlend,
        "below_min": nach_fahrt is not None and nach_fahrt < soc_min,
        "running_until": termin.rueckkehr.isoformat() if laeuft else None,
    }


def _ladestand_im_request(stand: standort.Planstand, fahrzeug_id: str) -> float | None:
    """Liegt die Abfahrt im ersten Slot, gilt der Ladestand aus dem Request."""
    for fahrzeug in (stand.anfrage or {}).get("vehicles", []):
        if fahrzeug.get("id") == fahrzeug_id:
            return fahrzeug.get("soc_pct")
    return None


def hinweise(termin: Termin, umfeld: list[Termin], geraete: dict[str, str], personen: set[str]) -> list[dict]:
    """overlap und driver_busy. umfeld sind alle Termine aller Fahrzeuge um diesen herum.

    overlap einmal, driver_busy einmal je anderem Fahrzeug, mit dessen
    Geraete-ID. Ein geloeschter Fahrer zaehlt nicht.
    """
    ergebnis = []
    if any(
        anderer.fahrzeug == termin.fahrzeug
        and (anderer.eintrag, anderer.datum) != (termin.eintrag, termin.datum)
        and ueberschneiden(termin, anderer)
        for anderer in umfeld
    ):
        ergebnis.append({"type": "overlap"})
    if termin.fahrer in personen:
        belegt: list[str] = []
        for anderer in umfeld:
            if (anderer.fahrzeug != termin.fahrzeug and anderer.fahrer == termin.fahrer
                    and anderer.fahrzeug not in belegt and ueberschneiden(termin, anderer)):
                belegt.append(anderer.fahrzeug)
        ergebnis += [{"type": "driver_busy", "vehicle": geraete.get(fahrzeug)} for fahrzeug in belegt]
    return ergebnis


def termine_ansicht(
    auswahl: list[Termin],
    umfeld: list[Termin],
    stand: standort.Planstand,
    jetzt: datetime,
    soc_min: dict[str, float],
    geraete: dict[str, str],
    personen: set[str],
) -> list[dict]:
    """Die Termine fuer meteo_volt/appointments, nach Abfahrt sortiert. Abgesagte fehlen schon."""
    return [
        {
            "entry": termin.eintrag,
            "date": termin.datum.isoformat(),
            "vehicle": geraete.get(termin.fahrzeug),
            "departure": termin.abfahrt.isoformat(),
            "return": termin.rueckkehr.isoformat(),
            "distance_km": termin.strecke_km,
            # Eine geloeschte Person bleibt im Eintrag, gelesen wird ohne Fahrer.
            "driver": termin.fahrer if termin.fahrer in personen else None,
            "soc": termin.ladestand,
            "repeat": termin.wiederholung,
            "changed": termin.geaendert,
            "plan": planwerte(termin, stand, jetzt, soc_min.get(termin.fahrzeug, 0.0)),
            "hints": hinweise(termin, umfeld, geraete, personen),
        }
        for termin in auswahl
    ]


# --- Der Plan eines Fahrzeugs --------------------------------------------------

AUS_DEM_FAHRZEUGPLAN = ("slots", "intervals", "total_kwh", "total_cost_eur", "soc_end_pct", "violations")
AUS_DEM_KOPF = ("horizon_end", "prices_known_until", "computed_at")


def c6_wert(schluessel: str, zustand: str | None, tz: tzinfo) -> bool | float | str | None:
    """Der Zustand einer Entitaet aus C6 als Wert fuer das Panel, None wenn unbekannt."""
    if zustand is None:
        return None
    if schluessel == "charge_now":
        return {"on": True, "off": False}.get(zustand)
    try:
        if schluessel == "charge_now_kw":
            return float(zustand)
        return datetime.fromisoformat(zustand).astimezone(tz).isoformat()
    except ValueError:
        return None  # unknown, unavailable


def fahrzeugplan(stand: standort.Planstand, fahrzeug_id: str, c6: dict, plant: bool) -> dict:
    """meteo_volt/plan: der Fahrzeugplan der letzten Antwort, unveraendert, dazu der Stand.

    charge_now, charge_now_kw und next_charge_start kommen aus den
    Entitaeten von C6, damit Panel und Entitaeten dasselbe sagen, auch bei
    gesperrtem Block.
    """
    plan = stand.plan if isinstance(stand.plan, dict) else {}
    fahrzeuge = plan.get("vehicles") if isinstance(plan.get("vehicles"), list) else []
    eigener = next((v for v in fahrzeuge if isinstance(v, dict) and v.get("id") == fahrzeug_id), {})
    return {
        **{schluessel: eigener.get(schluessel) for schluessel in AUS_DEM_FAHRZEUGPLAN},
        **{schluessel: plan.get(schluessel) for schluessel in AUS_DEM_KOPF},
        "received_at": None if stand.erhalten_um is None else stand.erhalten_um.isoformat(),
        "charge_now": c6.get("charge_now"),
        "charge_now_kw": c6.get("charge_now_kw"),
        "next_charge_start": c6.get("next_charge_start"),
        "planning": plant,
        "error": None if stand.fehler is None else f"{type(stand.fehler).__name__}: {stand.fehler}",
    }


# --- Die Preise -------------------------------------------------------------------


def preise(prognose: dict | None, jetzt: datetime) -> dict:
    """meteo_volt/prices: ab dem laufenden Slot bis zum Ende der Prognose, ohne Netzentgelt.

    Vergangene Preise liefert C3 nicht, entschieden am 2026-09-16.
    """
    prognose = prognose if isinstance(prognose, dict) else {}
    slots = []
    for slot in prognose.get("slots") or []:
        try:
            beginn = datetime.fromisoformat(slot["target_timestamp"])
        except (KeyError, TypeError, ValueError):
            continue
        if utc(beginn) + PREISSLOT > utc(jetzt):
            slots.append({
                "t": slot["target_timestamp"],
                "q10": slot.get("q10"),
                "q50": slot.get("q50"),
                "q90": slot.get("q90"),
                "source": slot.get("source"),
            })
    return {
        "slots": slots,
        "prices_known_until": prognose.get("prices_known_until"),
        "computed_at": prognose.get("computed_at"),
        "model": prognose.get("model"),
    }
