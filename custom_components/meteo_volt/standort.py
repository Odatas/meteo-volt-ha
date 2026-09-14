"""Der Standort-Koordinator ohne Home Assistant.

Dieses Modul importiert bewusst NICHTS aus Home Assistant und nichts aus
aiohttp -- wie stammdaten.py und planabruf.py, auf denen es aufbaut. Hier
steht, was C5 entscheidet: welcher Ladepunkt gilt, wann ein Fahrzeug
ausgelassen wird, wie der Request aussieht, wann der naechste Versuch kommt
und was aus einem gehaltenen Plan gerade gilt. plankoordinator.py verdrahtet
das mit Home Assistant und entscheidet selbst nichts.

Der Steckerzustand kommt hier nicht vor. Er geht nicht in den Request: mit
station_id null plant der Server ueber den ganzen Horizont kein Laden, und
die Planung soll gerade sagen, wann eingesteckt werden muss.

Spec: meteo-volt-brain/docs/features/C5-standort-koordinator/spec.md
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from . import stammdaten
from .const import CONF_GRID_FEES, CONF_SITE_MAX_POWER
from .planabruf import PlanAbgelehnt, PlanFehler, PlanNichtAutorisiert, PlanRateLimit

# --- Gruende, Spec Abschnitt 3 ---------------------------------------------
# Ein ausgelassenes Fahrzeug traegt genau einen, geprueft in dieser Reihenfolge.

GRUND_KEIN_LADEPUNKT = "kein_ladepunkt"
GRUND_LADEPUNKT_GELOESCHT = "ladepunkt_geloescht"
GRUND_LADESTAND = "ladestand_nicht_lesbar"


@dataclass(frozen=True)
class Messung:
    """Zustand und last_changed einer Entitaet, von plankoordinator.py gelesen."""

    zustand: str
    geaendert: datetime


def ladestand_lesen(zustand: str | None) -> float | None:
    """Der Zustand der Ladestand-Entitaet als Zahl, oder None. Spec Abschnitt 3.

    None heisst nicht lesbar: unavailable, unknown, keine Zahl, nicht endlich,
    ausserhalb 0 bis 100, oder die Entitaet fehlt. Ein Wert ausserhalb liesse
    den Server den ganzen Request ablehnen -- und dann bekaeme kein Fahrzeug
    einen Plan.
    """
    if zustand is None:
        return None
    try:
        wert = float(zustand)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(wert) or not 0.0 <= wert <= 100.0:
        return None
    return wert


def ladepunkt_zuordnen(
    fahrzeug: dict, ladepunkt_ids: list[str]
) -> tuple[str | None, str | None]:
    """(station_id, None) oder (None, Grund). Spec Abschnitt 2.

    ladepunkt_ids steht in Anlagereihenfolge. Die Bindung ist ein Filter:
    zeigt sie auf einen geloeschten Ladepunkt, weicht C5 nicht auf einen
    anderen aus. Ohne Bindung gilt der zuerst angelegte -- bewusst beliebig,
    gemeinsame Planung mehrerer Fahrzeuge gibt es erst mit E1.
    """
    if not ladepunkt_ids:
        return None, GRUND_KEIN_LADEPUNKT
    gebunden = fahrzeug.get(stammdaten.FELD_LADEPUNKT)
    if not gebunden:
        return ladepunkt_ids[0], None
    if gebunden not in ladepunkt_ids:
        return None, GRUND_LADEPUNKT_GELOESCHT
    return gebunden, None


def anfrage_bauen(
    ladepunkte: list[tuple[str, dict]],
    fahrzeuge: list[tuple[str, dict]],
    messungen: dict[str, Messung | None],
    haupteintrag: dict,
    zeitzone: str,
) -> tuple[dict | None, dict[str, str]]:
    """Der Request und die ausgelassenen Fahrzeuge. Spec Abschnitte 2 bis 4.

    ladepunkte und fahrzeuge sind (subentry_id, data) in Anlagereihenfolge,
    messungen bildet die Fahrzeug-ID auf die Messung ihrer Ladestand-Entitaet
    ab, None wenn die Entitaet fehlt. Bleibt kein Fahrzeug uebrig, ist der
    Request None.

    now fehlt mit Absicht: die Uhr hat der Dienst, und eine falsch gehende
    Uhr im Haus verschoebe den Beginn des Plans.
    """
    ids = [ladepunkt_id for ladepunkt_id, _ in ladepunkte]
    ausgelassen: dict[str, str] = {}
    fragmente = []
    for fahrzeug_id, daten in fahrzeuge:
        station_id, grund = ladepunkt_zuordnen(daten, ids)
        messung = messungen.get(fahrzeug_id)
        soc = ladestand_lesen(None if messung is None else messung.zustand)
        if grund is None and soc is None:
            grund = GRUND_LADESTAND
        if grund is not None:
            ausgelassen[fahrzeug_id] = grund
            continue
        fragmente.append(
            stammdaten.zu_fahrzeug(
                daten,
                fahrzeug_id,
                soc,
                soc_measured_at=messung.geaendert.isoformat(),
                station_id=station_id,
            )
        )
    if not fragmente:
        return None, ausgelassen

    anfrage = {
        "schema_version": 1,
        # Wirkt mit consumption none noch nicht. Ohne sie stimmte der Default
        # Europe/Berlin still nicht, sobald Z3 Fahrten nach Wochentag schickt.
        "timezone": zeitzone,
        "stations": [
            stammdaten.zu_ladepunkt(daten, ladepunkt_id)
            for ladepunkt_id, daten in ladepunkte
        ],
        "vehicles": fragmente,
    }
    site = {}
    if CONF_GRID_FEES in haupteintrag:
        site["grid_fees_eur_kwh"] = float(haupteintrag[CONF_GRID_FEES])
    if haupteintrag.get(CONF_SITE_MAX_POWER) is not None:
        # Der Planer vergleicht heute nur den einzelnen Ladevorgang. Mit E1
        # greift der Wert, ohne dass HA noch einmal angefasst wird.
        site["max_power_kw"] = float(haupteintrag[CONF_SITE_MAX_POWER])
    if site:
        anfrage["site"] = site
    return anfrage, ausgelassen


# --- Zeiten, Spec Abschnitte 6 bis 8 ---------------------------------------

GRUNDTAKT = timedelta(minutes=60)
BUENDELN_S = 30.0
NACHHOLEN_NICHT_VERFUEGBAR_S = 300.0
VERALTET_NACH = timedelta(hours=12)

# Jeder Zeitzonen-Offset, den es gibt, ist ein Vielfaches einer Viertelstunde.
# In UTC gerechnet liegen die Grenzen deshalb auch lokal richtig.
_VIERTELSTUNDE_S = 900

# --- Naechster Versuch, Spec Abschnitt 7 -----------------------------------

WEITER_IM_GRUNDTAKT = "grundtakt"
NACHHOLEN = "nachholen"
PAUSE = "pause"

# --- Was gerade gilt, Spec Abschnitt 8 -------------------------------------

QUELLE_PLAN = "plan"
QUELLE_DEFAULT = "default"


@dataclass(frozen=True)
class Planstand:
    """Was C5 haelt. Spec Abschnitt 9.

    Jeder Lauf erzeugt einen neuen Planstand, keiner wird veraendert.
    """

    plan: dict | None = None
    erhalten_um: datetime | None = None
    anfrage: dict | None = None
    ausgelassen: dict[str, str] = field(default_factory=dict)
    fehler: PlanFehler | None = None
    letzter_versuch_um: datetime | None = None


def naechster_versuch(fehler: PlanFehler | None) -> tuple[str, float | None]:
    """Was nach einem Aufruf kommt. Spec Abschnitt 7.

    ("grundtakt", None)  weiter im Grundtakt
    ("nachholen", s)     einmal nach s Sekunden, danach im Grundtakt
    ("pause", None)      erst beim naechsten Ausloeser, der Grundtakt pausiert

    Abgelehnt und nicht autorisiert pausieren, weil dieselbe Anfrage wieder
    scheitert -- und weil die main-Umgebung heute keine Plan-Route hat: jeder
    Beta-Nutzer mit Fahrzeug schickte sonst stuendlich einen 404.
    """
    if fehler is None:
        return WEITER_IM_GRUNDTAKT, None
    if isinstance(fehler, PlanRateLimit):
        return NACHHOLEN, fehler.retry_after
    if isinstance(fehler, (PlanAbgelehnt, PlanNichtAutorisiert)):
        return PAUSE, None
    return NACHHOLEN, NACHHOLEN_NICHT_VERFUEGBAR_S


def was_gilt(
    stand: Planstand, fahrzeug_id: str, jetzt: datetime, soc_pct: float | None
) -> dict:
    """Was fuer ein Fahrzeug zum Zeitpunkt jetzt gilt. Spec Abschnitt 8.

    Aus dem Plan, solange er brauchbar ist, sonst der sichere Default. Im
    ersten Slot eines Plans ergibt das genau die Felder, die der Server
    geschickt hat. soc_pct ist der Ladestand zum Zeitpunkt des Aufrufs, None
    wenn er nicht lesbar ist -- nur der Default braucht ihn.
    """
    fahrzeugplan = _brauchbarer_plan(stand, fahrzeug_id, jetzt)
    if fahrzeugplan is not None:
        schritt = timedelta(minutes=stand.plan["slot_minutes"])
        slots = fahrzeugplan["slots"]
        for index, slot in enumerate(slots):
            beginn = datetime.fromisoformat(slot["t"])
            if beginn <= jetzt < beginn + schritt:
                laden = slot["charge"]
                return {
                    "charge_now": laden,
                    "charge_now_kw": (slot.get("kw") or 0.0) if laden else 0.0,
                    "charge_now_station_id": slot.get("station_id") if laden else None,
                    "current_slot_end": beginn + schritt,
                    "next_charge_start": _naechster_ladestart(slots, index),
                    "quelle": QUELLE_PLAN,
                }
    return _sicherer_default(stand, fahrzeug_id, jetzt, soc_pct)


def _brauchbarer_plan(stand: Planstand, fahrzeug_id: str, jetzt: datetime) -> dict | None:
    """Der Fahrzeugplan, wenn der Plan da, juenger als 12 h und nicht abgelaufen ist."""
    if stand.plan is None or stand.erhalten_um is None:
        return None
    if jetzt - stand.erhalten_um >= VERALTET_NACH:
        return None
    if jetzt >= datetime.fromisoformat(stand.plan["horizon_end"]):
        return None
    for fahrzeugplan in stand.plan.get("vehicles", []):
        if fahrzeugplan.get("id") == fahrzeug_id:
            return fahrzeugplan
    return None


def _naechster_ladestart(slots: list[dict], index: int) -> datetime | None:
    """Ab dem laufenden Slot der erste Ladeslot, dessen Vorgaenger nicht laedt.

    Dieselbe Regel wie _next_charge_start in meteovolt_planner/plan.py, nur ab
    index statt ab dem ersten Slot (A0-Spec 3.10).
    """
    for vorher, slot in zip(slots[index:], slots[index + 1:]):
        if slot["charge"] and not vorher["charge"]:
            return datetime.fromisoformat(slot["t"])
    return None


def _sicherer_default(
    stand: Planstand, fahrzeug_id: str, jetzt: datetime, soc_pct: float | None
) -> dict:
    """Laden nur unter Min-SoC. Fahrzeug und Ladepunkt aus dem zuletzt gebauten Request.

    Fehlt das Fahrzeug dort, wird nicht geladen: ohne Ladepunkt gibt es keine
    Leistung, ohne Ladestand keinen Vergleich.
    """
    fahrzeug = _eintrag(stand.anfrage, "vehicles", fahrzeug_id)
    station_id = None if fahrzeug is None else fahrzeug["connection"]["station_id"]
    station = _eintrag(stand.anfrage, "stations", station_id)
    laden = (
        station is not None
        and soc_pct is not None
        and soc_pct < fahrzeug["soc_min_pct"]
    )
    return {
        "charge_now": laden,
        "charge_now_kw": (
            min(fahrzeug["max_charge_kw"], station["max_power_kw"]) if laden else 0.0
        ),
        "charge_now_station_id": station_id if laden else None,
        "current_slot_end": _ende_der_viertelstunde(jetzt),
        "next_charge_start": None,
        "quelle": QUELLE_DEFAULT,
    }


def _eintrag(anfrage: dict | None, liste: str, kennung: str | None) -> dict | None:
    """Ein Ladepunkt oder Fahrzeug aus dem Request, nach seiner id."""
    if anfrage is None or kennung is None:
        return None
    for eintrag in anfrage[liste]:
        if eintrag["id"] == kennung:
            return eintrag
    return None


def _ende_der_viertelstunde(jetzt: datetime) -> datetime:
    """Genau auf einer Grenze beginnt die naechste Viertelstunde."""
    grenze = (math.floor(jetzt.timestamp()) // _VIERTELSTUNDE_S + 1) * _VIERTELSTUNDE_S
    return datetime.fromtimestamp(grenze, tz=timezone.utc)


def issue_pruefen_um(stand: Planstand, seit: datetime) -> datetime:
    """Wann das Repair-Issue faellig wird. Spec Abschnitt 8.

    seit ist der Start des Eintrags, oder das erste angelegte Fahrzeug, wenn
    es spaeter kam. Gezaehlt wird ab dem, was zuletzt kam: seit oder dem
    letzten Plan.
    """
    bezug = seit if stand.erhalten_um is None else max(stand.erhalten_um, seit)
    return bezug + VERALTET_NACH


def issue_faellig(
    stand: Planstand, seit: datetime, jetzt: datetime, hat_fahrzeuge: bool
) -> bool:
    """12 h ohne neuen Plan, obwohl Fahrzeuge angelegt sind."""
    return hat_fahrzeuge and jetzt >= issue_pruefen_um(stand, seit)


def issue_text(stand: Planstand) -> str:
    """{fehler} im Issue: die Meldung des letzten PlanFehler, sonst die Gruende."""
    if stand.fehler is not None:
        return f"{type(stand.fehler).__name__}: {stand.fehler}"
    if stand.ausgelassen:
        return ", ".join(sorted(set(stand.ausgelassen.values())))
    return "-"
