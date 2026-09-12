"""Bildet die beiden Subentry-Typen auf Kontrakt-Fragmente ab.

Dieses Modul importiert bewusst NICHTS aus Home Assistant -- wie overrides.py.
Nur so laesst es sich in der Testsuite dieses Repos laden; homeassistant steckt
nicht in den Testabhaengigkeiten, und die HA-Abnahme laeuft von Hand auf einer
echten Instanz.

Der Schnitt hat einen zweiten Zweck. Die Abbildung ist die Stelle, an der ein
Fehler wehtut: ein vertauschter Faktor 100 beim Wirkungsgrad faellt in keinem
Formular auf, wohl aber in der Rechnung des Planers. Sie liegt deshalb hier und
nicht im Config-Flow, wo sie ohne Home Assistant nicht pruefbar waere.

Spec: meteo-volt-brain/docs/features/C1-C2-stammdaten-subentries/spec.md
"""

from __future__ import annotations

# --- Subentry-Typen ---------------------------------------------------------

TYP_LADEPUNKT = "station"
TYP_FAHRZEUG = "vehicle"

# --- Feldnamen --------------------------------------------------------------
# Zugleich die Schluessel im Formular und in den Uebersetzungen.
# tests/test_uebersetzungen.py prueft beide Sprachen gegen genau diese Listen.

FELD_NAME = "name"

FELD_MAX_LEISTUNG = "max_power_kw"
FELD_VERFUEGBAR = "available"
FELD_MIN_LEISTUNG = "min_power_kw"
FELD_PHASEN = "phases"

FELD_KAPAZITAET = "capacity_kwh"
FELD_SOC_MIN = "soc_min_pct"
FELD_SOC_MAX = "soc_max_pct"
FELD_MAX_LADELEISTUNG = "max_charge_kw"
FELD_VERBRAUCH = "consumption_kwh_per_100km"
FELD_SOC_ENTITAET = "soc_entity"
# Nicht "station": das ist schon der Wert von TYP_LADEPUNKT. Zwei Namensraeume,
# derselbe String -- beim Lesen einer Subentry-dict waere nicht mehr zu sehen,
# welcher von beiden gemeint ist.
FELD_LADEPUNKT = "station_id"
FELD_ANGESTECKT = "plugged_entity"
FELD_MIN_LADELEISTUNG = "min_charge_kw"
FELD_WIRKUNGSGRAD = "efficiency_pct"

LADEPUNKT_FELDER = (
    FELD_NAME,
    FELD_MAX_LEISTUNG,
    FELD_VERFUEGBAR,
    FELD_MIN_LEISTUNG,
    FELD_PHASEN,
)

FAHRZEUG_FELDER = (
    FELD_NAME,
    FELD_KAPAZITAET,
    FELD_SOC_MIN,
    FELD_SOC_MAX,
    FELD_MAX_LADELEISTUNG,
    FELD_VERBRAUCH,
    FELD_SOC_ENTITAET,
    FELD_LADEPUNKT,
    FELD_ANGESTECKT,
    FELD_MIN_LADELEISTUNG,
    FELD_WIRKUNGSGRAD,
)

# --- Vorbelegung ------------------------------------------------------------

LADEPUNKT_DEFAULTS = {
    FELD_MAX_LEISTUNG: 11.0,
    FELD_VERFUEGBAR: True,
    FELD_MIN_LEISTUNG: 1.4,
    FELD_PHASEN: 3,
}

FAHRZEUG_DEFAULTS = {
    FELD_KAPAZITAET: 58.0,
    FELD_SOC_MIN: 15.0,
    FELD_SOC_MAX: 80.0,
    FELD_MAX_LADELEISTUNG: 11.0,
    FELD_VERBRAUCH: 19.5,
    FELD_MIN_LADELEISTUNG: 1.4,
    FELD_WIRKUNGSGRAD: 92.0,
}

# Abschnitt 3 der Spec: der Ladepunkt traegt keinen Wirkungsgrad. Der
# Kontrakt-Default waere 0.99 -- ein Prozent, das der Fahrzeugwert bereits
# enthaelt. Neutral heisst hier 1.0, sonst wird still doppelt gezaehlt.
LADEPUNKT_WIRKUNGSGRAD = 1.0

# Abschnitt 4: die Strecke gehoert zum Fahrprofil und hat hier keinen Ort.
# "none" heisst, der Planer rechnet ohne Fahrverbrauch. Das ist entschieden,
# nicht vergessen -- siehe Abschnitt 11 der Spec.
VERBRAUCHSMODELL = {"type": "none"}


def zu_ladepunkt(daten: dict, ladepunkt_id: str) -> dict:
    """Ein Station-Fragment des Kontrakts.

    ladepunkt_id ist die subentry_id. Der Kontrakt verlangt eine ueber
    Requests stabile ID; ein Slug aus dem Titel waere es nicht, er aendert
    sich beim Umbenennen.
    """
    return {
        "id": ladepunkt_id,
        "max_power_kw": float(daten[FELD_MAX_LEISTUNG]),
        "min_power_kw": float(
            daten.get(FELD_MIN_LEISTUNG, LADEPUNKT_DEFAULTS[FELD_MIN_LEISTUNG])),
        "phases": int(daten.get(FELD_PHASEN, LADEPUNKT_DEFAULTS[FELD_PHASEN])),
        "efficiency": LADEPUNKT_WIRKUNGSGRAD,
        "available": bool(
            daten.get(FELD_VERFUEGBAR, LADEPUNKT_DEFAULTS[FELD_VERFUEGBAR])),
    }
