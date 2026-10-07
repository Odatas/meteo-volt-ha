"""Der gesicherte Ladestand eines Termins, ohne Home Assistant. Spec C10 Abschnitte 2 und 5.

Dieses Modul importiert bewusst NICHTS aus Home Assistant und nichts aus
aiohttp. Aus Strecke, Kapazitaet und Verbrauch rechnet es, was eine Fahrt an
Ladestand kostet und auf welchen Wert der Haken "Min-SoC sichern" die Abfahrt
hebt. Was daraus im Request wird, steht in terminanfrage.py, was das Formular
davon zeigt, in pruefungen.py und im Panel.

Dieselbe Rechnung steht im Panel in frontend/ladereserve.js. Die Gegenprobe
in tests/test_panel.py haelt beide zusammen: zwei Implementierungen derselben
Formel driften sonst auseinander, ohne dass eine Pruefung rot wird.

Spec: meteo-volt-brain/docs/features/C10-ladestand-sichern/spec.md, Abschnitte 2 und 5
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Die Schluessel der Warnungen, Spec Abschnitt 5. pruefungen.py reicht sie
# als translation_key weiter, das Panel zeigt sie am Platz "Ladestand".
FAHRT_ZU_WEIT = "fahrt_zu_weit"
FAHRT_UNTER_MIN = "fahrt_unter_min"
LADESTAND_OFFEN = "ladestand_offen"


@dataclass(frozen=True)
class Fahrzeugwerte:
    """Was die Rechnung vom Fahrzeug braucht. Alle drei sind Pflicht und > 0 (C1-C2)."""

    soc_min_pct: float
    capacity_kwh: float
    consumption_kwh_per_100km: float


def fahrt_pct(strecke_km: float, werte: Fahrzeugwerte) -> float:
    """Was eine Fahrt an Ladestand kostet, in Prozentpunkten.

    kWh = km * consumption_kwh_per_100km / 100, wie der Planer in
    meteovolt_planner/consumption.py; geteilt durch die Kapazitaet und mal
    100 kuerzt sich die Hundert weg. Ohne Wirkungsgrad: der gilt beim Laden,
    nicht beim Fahren.
    """
    return strecke_km * werte.consumption_kwh_per_100km / werte.capacity_kwh


def gesichert(strecke_km: float, werte: Fahrzeugwerte) -> float:
    """Der Ladestand, auf den der Haken die Abfahrt hebt: Min-SoC plus Fahrt.

    Aufgerundet auf ganze Prozent, weil das Feld "Ladestand bei Abfahrt" ganze
    Prozent traegt und Abrunden die Zusage um bis zu einen Punkt unterliefe.
    Gedeckelt bei 100, weil target_soc_pct dort endet -- NICHT bei
    soc_max_pct: ein Ziel wird nie gekappt, es hebt die Decke fuer seinen
    Zeitraum an (Basiskontrakt 3.3).
    """
    return float(min(100, math.ceil(werte.soc_min_pct + fahrt_pct(strecke_km, werte))))


def befund(
    strecke_km: float, ladestand: float | None, sichern: bool, werte: Fahrzeugwerte
) -> str | None:
    """Der Schluessel der Warnung zur Fahrt, oder None. Spec Abschnitt 5.

    Der Bezugswert ist der Ladestand, den der Plan fuer die Abfahrt zusagt:
    mit Haken der gesicherte Wert, sonst das eigene Ziel ab Min-SoC. Steht
    keiner von beiden, ist nichts zugesagt.

    soc_max_pct ist ausdruecklich KEIN Bezugswert. Dass der Planer heute vor
    der ersten Fahrt dorthin laedt (first_need), faellt mit A6E weg -- eine
    Warnung, die sich darauf stuetzt, waere danach still falsch.
    """
    fahrt = fahrt_pct(strecke_km, werte)
    if fahrt > 100 - werte.soc_min_pct:
        return FAHRT_ZU_WEIT  # auch voll geladen reicht es nicht; der Haken hilft hier nicht
    if sichern:
        bezug = gesichert(strecke_km, werte)
    elif ladestand is not None and ladestand >= werte.soc_min_pct:
        bezug = ladestand
    else:
        return LADESTAND_OFFEN
    return FAHRT_UNTER_MIN if bezug - fahrt < werte.soc_min_pct else None
