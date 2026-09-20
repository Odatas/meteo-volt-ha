"""Was aus den Terminen im Request wird, ohne Home Assistant. Spec C3 Abschnitt 4.

Dieses Modul importiert bewusst NICHTS aus Home Assistant und nichts aus
aiohttp. Aus jedem Termin wird eine Abwesenheit, aus einem kuenftigen eine
Fahrt in consumption.trips (A5-Spec Abschnitt 2), und traegt er einen
Ladestand ab dem Min-SoC oder den Haken "Min-SoC sichern", ein Ziel
(C10-Spec Abschnitt 4). standort.anfrage_bauen setzt die Fragmente je
Fahrzeug in den Request.

Eine Fahrt ist kein Ziel: ein Termin ohne Ladestand erzeugt kein target.

Spec: meteo-volt-brain/docs/features/C3-konfig-entitaeten/spec.md, Abschnitt 4
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from . import ladereserve
from .termine import Termin, utc

# Ohne Plan wird so weit ausgerollt: die Laenge des Admin-Horizonts.
AUSROLLEN_OHNE_PLAN = timedelta(days=14)

# Das Risiko, bis jemand es setzt: 2, "Ausgewogen", der Default des Kontrakts.
RISIKO_VORGABE = 2

# Die Art im dritten Teil einer ID, Spec Abschnitt 4.
WEG = "weg"
ZIEL = "ziel"


def ausrollen_bis(plan: dict | None, jetzt: datetime) -> datetime:
    """Bis wohin ausgerollt wird: horizon_end des letzten Plans, sonst 14 Tage.

    Was hinter dem Horizont liegt, wertet der Planer nicht aus (A0-Spec 3.6).
    Ein horizon_end, das schon vorbei ist, zaehlt wie kein Plan -- sonst
    ginge nach einem langen Ausfall kein einziger Termin mehr in den Request.
    """
    try:
        ende = datetime.fromisoformat(plan["horizon_end"])
    except (KeyError, TypeError, ValueError):
        ende = None
    if ende is None or utc(ende) <= utc(jetzt):
        return jetzt + AUSROLLEN_OHNE_PLAN
    return ende


def kennung(eintrag: str, datum: date, art: str) -> str:
    """'<eintrag>/<JJJJ-MM-TT>/<art>'. Je Fahrzeug eindeutig und nie 'base'."""
    return f"{eintrag}/{datum.isoformat()}/{art}"


def zerlegen(text: str | None) -> tuple[str, date, str] | None:
    """Eine ID zurueck in Eintrag, Datum und Art, oder None.

    None fuer 'base' und alles, was keine ID aus kennung() ist: reason eines
    Slots und constraint_id einer Verletzung tragen auch das Basisziel.
    """
    teile = (text or "").split("/")
    if len(teile) != 3 or not teile[0] or teile[2] not in (WEG, ZIEL):
        return None
    try:
        return teile[0], date.fromisoformat(teile[1]), teile[2]
    except ValueError:
        return None


def fragmente(
    termine: list[Termin], fahrzeuge: dict[str, ladereserve.Fahrzeugwerte], jetzt: datetime
) -> dict[str, dict]:
    """consumption und constraints je Fahrzeug.

    termine sind schon ausgewaehlt: Rueckkehr nach jetzt, Abfahrt vor dem Ende
    des Ausrollens. fahrzeuge nennt jedes Fahrzeug des Standorts mit seinen
    Werten; jedes bekommt trips, ohne Termin als leere Liste. constraints
    fehlt, wenn es leer waere.
    """
    ergebnis: dict[str, dict] = {
        fahrzeug: {"consumption": {"type": "trips", "trips": []}} for fahrzeug in fahrzeuge
    }
    for termin in termine:
        teil = ergebnis.get(termin.fahrzeug)
        if teil is None:
            continue
        auflagen = teil.setdefault("constraints", [])
        # Immer: laeuft der Termin schon, liegt from in der Vergangenheit.
        auflagen.append({
            "type": "unavailable",
            "id": kennung(termin.eintrag, termin.datum, WEG),
            "from": termin.abfahrt.isoformat(),
            "to": termin.rueckkehr.isoformat(),
        })
        if utc(termin.abfahrt) <= utc(jetzt):
            continue  # R4: vergangener Verbrauch steckt im gemessenen Ladestand
        teil["consumption"]["trips"].append(
            {"departure": termin.abfahrt.isoformat(), "km": float(termin.strecke_km)})
        ziel = _ziel(termin, fahrzeuge[termin.fahrzeug])
        if ziel is not None:
            auflagen.append({
                "type": "target",
                "id": kennung(termin.eintrag, termin.datum, ZIEL),
                "deadline": termin.abfahrt.isoformat(),
                "target_soc_pct": ziel,
            })
    return ergebnis


def _ziel(termin: Termin, werte: ladereserve.Fahrzeugwerte) -> float | None:
    """Der hoehere von eigenem und gesichertem Ziel, oder None. Spec C10 Abschnitt 4.

    Das eigene Ziel gilt unveraendert erst ab dem Min-SoC (C3-Spec 4): der
    Haken hebt das Ziel, er rettet den zu kleinen Wert nicht. Es gibt nur ein
    target je Termin -- zwei mit derselben Deadline waeren zwei Decken, von
    denen die niedrigere das Laden davor begrenzt (Basiskontrakt 3.3).
    """
    kandidaten = []
    if termin.ladestand is not None and termin.ladestand >= werte.soc_min_pct:
        kandidaten.append(float(termin.ladestand))
    if termin.sichern:
        kandidaten.append(ladereserve.gesichert(termin.strecke_km, werte))
    return max(kandidaten) if kandidaten else None
