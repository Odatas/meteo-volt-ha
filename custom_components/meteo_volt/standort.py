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
from dataclasses import dataclass
from datetime import datetime

from . import stammdaten
from .const import CONF_GRID_FEES, CONF_SITE_MAX_POWER

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
