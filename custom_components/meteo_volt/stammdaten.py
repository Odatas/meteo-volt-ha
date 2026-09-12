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


def zu_fahrzeug(
    daten: dict,
    fahrzeug_id: str,
    soc_pct: float,
    soc_measured_at: str | None = None,
    station_id: str | None = None,
) -> dict:
    """Ein VehicleProfile-Fragment des Kontrakts.

    soc_pct, soc_measured_at und station_id misst kein Formular. Sie kommen
    aus den Entitaeten des Nutzers und werden hereingereicht -- dieses Modul
    liest selbst nichts. Was bei einem unavailable-Zustand geschieht,
    entscheidet C5.
    """
    max_ladeleistung = float(daten[FELD_MAX_LADELEISTUNG])
    wirkungsgrad_pct = float(
        daten.get(FELD_WIRKUNGSGRAD, FAHRZEUG_DEFAULTS[FELD_WIRKUNGSGRAD]))

    fragment = {
        "id": fahrzeug_id,
        "capacity_kwh": float(daten[FELD_KAPAZITAET]),
        "soc_pct": float(soc_pct),
        "max_charge_kw": max_ladeleistung,
        "min_charge_kw": float(
            daten.get(FELD_MIN_LADELEISTUNG,
                      FAHRZEUG_DEFAULTS[FELD_MIN_LADELEISTUNG])),
        # Ein Stuetzpunkt heisst konstanter Wirkungsgrad ueber die ganze
        # Leistung: der Kontrakt klemmt ausserhalb auf den naechsten Punkt.
        "efficiency_curve": [
            {"kw": max_ladeleistung, "eta": wirkungsgrad_pct / 100},
        ],
        "soc_min_pct": float(daten[FELD_SOC_MIN]),
        "soc_max_pct": float(daten[FELD_SOC_MAX]),
        "consumption_kwh_per_100km": float(daten[FELD_VERBRAUCH]),
        "connection": {"station_id": station_id},
        # Eine Kopie, kein geteiltes dict: sonst aenderte ein Aufrufer die
        # Werte aller anderen mit.
        "consumption": dict(VERBRAUCHSMODELL),
    }

    # Weglassen ist etwas anderes als null: ein fehlender Zeitpunkt soll
    # fehlen und nicht als gemessen gelten.
    if soc_measured_at is not None:
        fragment["soc_measured_at"] = soc_measured_at

    return fragment


# --- Formularabschnitte -----------------------------------------------------
# HA liefert section-Felder verschachtelt unter ihrem Schluessel zurueck.

ABSCHNITT_ERWEITERT = "erweitert"
ABSCHNITT_BATTERIE = "batterie"
ABSCHNITT_GUARD = "guard"
ABSCHNITT_LADEN = "laden"
ABSCHNITT_FAHREN = "fahren"
ABSCHNITT_LAUFZEIT = "laufzeit"

ABSCHNITTE_LADEPUNKT = (ABSCHNITT_ERWEITERT,)
ABSCHNITTE_FAHRZEUG = (
    ABSCHNITT_BATTERIE,
    ABSCHNITT_GUARD,
    ABSCHNITT_LADEN,
    ABSCHNITT_FAHREN,
    ABSCHNITT_LAUFZEIT,
    ABSCHNITT_ERWEITERT,
)

# --- Namensvergabe ----------------------------------------------------------
# Der Titel wird erzeugt, nicht uebersetzt: HA hat fuer erzeugte Titel keinen
# Uebersetzungsschluessel. Deshalb hier eine kleine Tabelle statt einer
# deutschen Vorgabe in einer englischen Oberflaeche.

_NAMENSMUSTER = {
    "de": {TYP_LADEPUNKT: "Wallbox {}", TYP_FAHRZEUG: "Fahrzeug {}"},
    "en": {TYP_LADEPUNKT: "Wallbox {}", TYP_FAHRZEUG: "Vehicle {}"},
}


def naechster_name(vorhandene_titel, typ: str, sprache: str = "en") -> str:
    """Kleinste freie Nummer ab 1, etwa 'Fahrzeug 1', 'Fahrzeug 2'.

    Nicht len()+1: wer 'Fahrzeug 1' loescht und neu anlegt, bekaeme sonst eine
    Dublette zu 'Fahrzeug 2'.
    """
    muster = _NAMENSMUSTER.get(sprache, _NAMENSMUSTER["en"])[typ]
    belegt = set(vorhandene_titel)
    nummer = 1
    while muster.format(nummer) in belegt:
        nummer += 1
    return muster.format(nummer)


def ladepunkt_aufloesen(
    gewaehlt: str | None,
    bekannte_ids,
    angesteckt: bool | None = None,
) -> str | None:
    """connection.station_id aus Auswahl und Angesteckt-Sensor.

    Aufgerufen wird das nicht hier, sondern in C5, das die Entitaeten liest.
    Die Funktion steht trotzdem in diesem Modul: hier liegt die Abbildung, und
    hier ist sie ohne Home Assistant pruefbar.

    angesteckt ist None, wenn der Nutzer keine Entitaet gewaehlt hat -- dann
    gilt das Fahrzeug als angesteckt. Wallboxen muessen nicht smart sein und
    Autos auch nicht; die Gegenannahme machte den Plan fuer jeden nutzlos, der
    keinen solchen Sensor hat.

    Ein Ladepunkt, den es nicht mehr gibt, wird null statt eines haengenden
    Verweises: es gibt keine Fehler-Fixture fuer eine unbekannte station_id,
    der Server pinnt sein Verhalten dort also nicht.
    """
    if not gewaehlt:
        return None
    if gewaehlt not in bekannte_ids:
        return None
    if angesteckt is False:
        return None
    return gewaehlt


def flach_aus_abschnitten(user_input: dict, abschnitte) -> dict:
    """Zieht die benannten Formularabschnitte flach.

    Nur die benannten. Jedes dict aufzuloesen hiesse raten, und ein falsch
    aufgeloestes faellt spaeter still als fehlendes Feld auf.
    """
    flach: dict = {}
    for schluessel, wert in user_input.items():
        if schluessel in abschnitte and isinstance(wert, dict):
            flach.update(wert)
        else:
            flach[schluessel] = wert
    return flach
