"""Die Pruefungen der Termine ohne Home Assistant. Spec C3 Abschnitt 2.3.

Dieses Modul importiert bewusst NICHTS aus Home Assistant und nichts aus
aiohttp. Das Panel prueft beim Eingeben, dieses Modul beim Speichern
dasselbe: die Actions gehen auch ohne Panel. Jede Meldung hat einen
Schluessel und ein Feld; der Schluessel ist zugleich der translation_key.
Fehler werfen Terminfehler, Warnungen kommen in der Antwort zurueck.

Hier stehen auch die Actions mit ihren Feldern: eine Quelle fuer das Schema
in aktionen.py, services.yaml und tests/test_uebersetzungen.py.

Spec: meteo-volt-brain/docs/features/C3-konfig-entitaeten/spec.md, Abschnitte 2.3 und 5
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, tzinfo

from . import termine
from .planabruf import PlanNichtAutorisiert, PlanRateLimit

# --- Die Schluessel, Spec Abschnitt 2.3 -------------------------------------

ZEIT_FEHLT = "zeit_fehlt"
RUECKKEHR_VOR_ABFAHRT = "rueckkehr_vor_abfahrt"
RUECKKEHR_VORBEI = "rueckkehr_vorbei"
DAUER_ZU_LANG = "dauer_zu_lang"
STRECKE_FEHLT = "strecke_fehlt"
STRECKE_NEGATIV = "strecke_negativ"
LADESTAND_BEREICH = "ladestand_bereich"
LADESTAND_UNTER_MIN = "ladestand_unter_min"
FAHRER_DOPPELT = "fahrer_doppelt"
FAHRZEUG_UNBEKANNT = "fahrzeug_unbekannt"
EINTRAG_UNBEKANNT = "eintrag_unbekannt"
TERMIN_UNBEKANNT = "termin_unbekannt"
UMFANG_UNZULAESSIG = "umfang_unzulaessig"
RUECKGAENGIG_UNMOEGLICH = "rueckgaengig_unmoeglich"
PLAN_PAUSE = "plan_pause"
PLAN_GESTOPPT = "plan_gestoppt"

# Jeder Schluessel mit den Platzhaltern seines Textes.
MELDUNGEN = {
    ZEIT_FEHLT: (),
    RUECKKEHR_VOR_ABFAHRT: (),
    RUECKKEHR_VORBEI: (),
    DAUER_ZU_LANG: (),
    STRECKE_FEHLT: (),
    STRECKE_NEGATIV: (),
    LADESTAND_BEREICH: (),
    LADESTAND_UNTER_MIN: ("min",),
    FAHRER_DOPPELT: ("fahrer", "datum", "fahrzeug"),
    FAHRZEUG_UNBEKANNT: (),
    EINTRAG_UNBEKANNT: (),
    TERMIN_UNBEKANNT: (),
    UMFANG_UNZULAESSIG: (),
    RUECKGAENGIG_UNMOEGLICH: (),
    PLAN_PAUSE: ("sekunden",),
    PLAN_GESTOPPT: (),
}

# Der Fahrer wird so weit voraus geprueft, Spec Abschnitt 2.3.
FAHRER_VORAUS = timedelta(weeks=8)

# --- Die Actions und ihre Felder, Spec Abschnitt 5 ---------------------------

TERMIN_FELDER = ("vehicle", "departure", "return", "repeat", "distance_km", "driver", "soc")
AKTIONEN = {
    "create_appointment": TERMIN_FELDER,
    "update_appointment": ("entry", "date", "scope", *TERMIN_FELDER),
    "delete_appointment": ("entry", "date", "scope"),
    "cancel_appointments": ("appointments", "step"),
    "undo": ("step",),
    "set_risk": ("risk", "config_entry"),
    "replan": ("config_entry",),
}


@dataclass(frozen=True)
class Meldung:
    schluessel: str
    feld: str | None = None
    platzhalter: dict[str, str] = field(default_factory=dict)

    def als_dict(self) -> dict:
        """Eine Warnung in der Antwort: key, field, placeholders."""
        return {"key": self.schluessel, "field": self.feld, "placeholders": dict(self.platzhalter)}


class Terminfehler(Exception):
    """Ein Fehler aus Abschnitt 2.3. aktionen.py macht daraus einen ServiceValidationError."""

    def __init__(self, meldung: Meldung) -> None:
        super().__init__(meldung.schluessel)
        self.meldung = meldung


def fehler(schluessel: str, feld: str | None = None, **platzhalter: str) -> Terminfehler:
    return Terminfehler(Meldung(schluessel, feld, platzhalter))


@dataclass(frozen=True)
class Werte:
    """Die geprueften Werte eines Termins, so wie der Store sie traegt."""

    fahrzeug: str
    abfahrt: str  # lokal, ISO 8601 ohne Offset
    dauer_min: int
    wiederholung: str
    strecke_km: int
    fahrer: str | None
    ladestand: float | None
    sichern: bool


# --- Die Pruefung beim Speichern ----------------------------------------------


def fahrzeug_aus_geraet(
    kennungen: set[tuple[str, str]], domain: str, fahrzeuge: dict[str, set[str]]
) -> tuple[str, str]:
    """(entry_id, subentry_id) zu den identifiers eines Geraets.

    fahrzeuge bildet jeden Standort auf seine Fahrzeuge ab. Das Geraet der
    Prognose traegt (meteo_volt, entry_id) und ist kein Fahrzeug.
    """
    for eigene_domain, kennung in kennungen:
        if eigene_domain != domain:
            continue
        for entry_id, ids in fahrzeuge.items():
            if kennung in ids:
                return entry_id, kennung
    raise fehler(FAHRZEUG_UNBEKANNT, "vehicle")


def _lokal_text(wert, tz: tzinfo) -> str | None:
    """Eine Eingabe als lokale Zeit ohne Offset, oder None, wenn sie keine Zeit ist.

    Die Datums-Auswahl von Home Assistant liefert '2026-09-21 08:00:00'. Traegt
    eine Eingabe doch einen Offset, wird sie in die Zeitzone umgerechnet.
    """
    if not isinstance(wert, str) or not wert.strip():
        return None
    try:
        zeitpunkt = datetime.fromisoformat(wert.strip())
    except ValueError:
        return None
    if zeitpunkt.tzinfo is not None:
        zeitpunkt = zeitpunkt.astimezone(tz)
    return zeitpunkt.replace(tzinfo=None).isoformat()


def werte_pruefen(
    felder: dict,
    fahrzeug: str,
    jetzt: datetime,
    tz: tzinfo,
    vorgabe_wiederholung: str = termine.EINMALIG,
    vorgabe_sichern: bool = True,
) -> Werte:
    """Die Felder eines Termins, geprueft in der Reihenfolge der Tabelle 2.3.

    fahrzeug ist schon aufgeloest: die subentry_id eines Fahrzeugs dieses
    Standorts. Fehlt repeat, gilt vorgabe_wiederholung -- beim Anlegen
    once, beim Aendern die Wiederholung des Eintrags.

    Fehlt keep_min_soc, gilt vorgabe_sichern -- beim Anlegen True, beim
    Aendern der bisherige Wert des Termins (C10-Spec Abschnitt 8). Sonst
    naehme ein Aendern ohne das Feld einem Termin still seine Sicherung.
    """
    abfahrt_text = _lokal_text(felder.get("departure"), tz)
    rueckkehr_text = _lokal_text(felder.get("return"), tz)
    if abfahrt_text is None:
        raise fehler(ZEIT_FEHLT, "departure")
    if rueckkehr_text is None:
        raise fehler(ZEIT_FEHLT, "return")
    wiederholung = felder.get("repeat") or vorgabe_wiederholung
    if wiederholung not in termine.WIEDERHOLUNGEN:
        raise ValueError(f"unbekannte Wiederholung: {wiederholung}")
    abfahrt = termine.lokal(abfahrt_text, tz)
    rueckkehr = termine.lokal(rueckkehr_text, tz)
    dauer = termine.dauer_min(abfahrt, rueckkehr)
    if dauer <= 0:
        raise fehler(RUECKKEHR_VOR_ABFAHRT, "return")
    if wiederholung == termine.EINMALIG and termine.utc(rueckkehr) <= termine.utc(jetzt):
        raise fehler(RUECKKEHR_VORBEI, "return")
    if wiederholung != termine.EINMALIG and timedelta(minutes=dauer) >= termine.ABSTAND[wiederholung]:
        raise fehler(DAUER_ZU_LANG, "return")
    strecke = felder.get("distance_km")
    if strecke is None or not math.isfinite(strecke):
        # nan und inf aus YAML oder Templates sind keine Strecke.
        raise fehler(STRECKE_FEHLT, "distance_km")
    if strecke < 0:
        raise fehler(STRECKE_NEGATIV, "distance_km")
    ladestand = felder.get("soc")
    if ladestand is not None and not 0 <= ladestand <= 100:
        raise fehler(LADESTAND_BEREICH, "soc")
    return Werte(
        fahrzeug=fahrzeug,
        abfahrt=abfahrt_text,
        dauer_min=dauer,
        wiederholung=wiederholung,
        # Ganze Kilometer, kaufmaennisch gerundet. round() rundete 42.5 auf 42.
        strecke_km=math.floor(strecke + 0.5),
        fahrer=felder.get("driver") or None,
        ladestand=None if ladestand is None else float(ladestand),
        sichern=vorgabe_sichern if felder.get(termine.SICHERN) is None else bool(felder[termine.SICHERN]),
    )


# --- Die Warnungen ------------------------------------------------------------

_WOCHENTAGE = {
    "de": ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"),
    "en": ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"),
}
_MONATE_EN = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _sprache(sprache: str) -> str:
    """'de-CH' -> 'de'. Alles ausser Deutsch ist Englisch."""
    return "de" if (sprache or "").split("-")[0].lower() == "de" else "en"


def zahl_text(wert: float, sprache: str) -> str:
    """15.0 -> '15'; 15.5 -> '15,5' deutsch und '15.5' englisch. Wie in ausgabe.py."""
    text = f"{wert:g}"
    return text.replace(".", ",") if _sprache(sprache) == "de" else text


def datum_text(zeitpunkt: datetime, sprache: str) -> str:
    """'Sa 19.09.' deutsch, 'Sat 19 Sep' englisch."""
    if _sprache(sprache) == "de":
        return f"{_WOCHENTAGE['de'][zeitpunkt.weekday()]} {zeitpunkt:%d.%m.}"
    return f"{_WOCHENTAGE['en'][zeitpunkt.weekday()]} {zeitpunkt.day} {_MONATE_EN[zeitpunkt.month - 1]}"


def warnungen(
    werte: Werte,
    eintrag_id: str,
    eintraege: list[dict],
    tz: tzinfo,
    jetzt: datetime,
    soc_min: float,
    personen: dict[str, str],
    titel: dict[str, str],
    sprache: str,
) -> list[Meldung]:
    """Die Warnungen nach dem Speichern. Gespeichert ist trotzdem.

    eintrag_id traegt die neuen Werte, eintraege ist der Stand danach.
    personen bildet jede person-Entitaet auf ihren Namen ab, titel jedes
    Fahrzeug auf seinen Titel.
    """
    meldungen = []
    if werte.ladestand is not None and werte.ladestand < soc_min:
        meldungen.append(Meldung(LADESTAND_UNTER_MIN, "soc", {"min": zahl_text(soc_min, sprache)}))
    if werte.fahrer in personen:
        bis = jetzt + FAHRER_VORAUS
        alle = termine.ausrollen(eintraege, tz, jetzt, bis)
        eigene = [t for t in alle if t.eintrag == eintrag_id and t.fahrer == werte.fahrer]
        andere = [t for t in alle if t.fahrzeug != werte.fahrzeug and t.fahrer == werte.fahrer]
        for termin in eigene:
            konflikt = next((a for a in andere if termine.ueberschneiden(termin, a)), None)
            if konflikt is not None:
                meldungen.append(Meldung(FAHRER_DOPPELT, "driver", {
                    "fahrer": personen[werte.fahrer],
                    "datum": datum_text(termin.abfahrt, sprache),
                    "fahrzeug": titel.get(konflikt.fahrzeug, konflikt.fahrzeug),
                }))
                break
    return meldungen


# --- Neu planen, Spec Abschnitt 5 ----------------------------------------------


def neu_planen_pruefen(vorher, nachher) -> Meldung | None:
    """Was meteo_volt.replan wirft, oder None. vorher und nachher sind Planstaende.

    Nach einem Key-Fehler plant C5 nichts mehr: plan_gestoppt. Eine
    Sendepause nennt ihre Restdauer, aber nur, wenn dieser Lauf gesendet
    hat oder senden wollte -- ohne planbares Fahrzeug bleibt ein alter
    Fehler stehen und hiesse nichts. Jeder andere Fehler steht im Plan.
    """
    if isinstance(nachher.fehler, PlanNichtAutorisiert):
        return Meldung(PLAN_GESTOPPT)
    versucht = nachher.letzter_versuch_um != vorher.letzter_versuch_um
    if isinstance(nachher.fehler, PlanRateLimit) and versucht:
        return Meldung(PLAN_PAUSE, platzhalter={"sekunden": str(math.ceil(nachher.fehler.retry_after))})
    return None
