"""Der Inhalt des Terminspeichers und seine Schritte, ohne Home Assistant.

Dieses Modul importiert bewusst NICHTS aus Home Assistant und nichts aus
aiohttp. Hier steht, was Anlegen, Aendern, Loeschen, Absagen und
Rueckgaengig mit den Eintraegen tun: Serien, Ausnahmen, Umfang.

Jeder schreibende Aufruf ist ein Schritt mit einer Kennung. Rueckgaengig
stellt die Eintraege des Schritts her, wie sie vor ihm waren, solange sie
seitdem niemand anders geaendert hat. Die Schritte liegen nur im Speicher,
die letzten 50 je Standort. Das Risiko ist kein Schritt. Speichern, Signale
und neu planen macht terminverwaltung.py.

Jede Operation prueft zuerst und aendert dann: scheitert sie, bleibt das
Buch, wie es war.

Spec: meteo-volt-brain/docs/features/C3-konfig-entitaeten/spec.md, Abschnitte 2.1, 2.2 und 3
"""

from __future__ import annotations

import copy
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date

from . import termine
from .pruefungen import (
    EINTRAG_UNBEKANNT,
    RUECKGAENGIG_UNMOEGLICH,
    TERMIN_UNBEKANNT,
    UMFANG_UNZULAESSIG,
    Werte,
    fehler,
)
from .termine import ABFAHRT, AUSNAHMEN, BIS, DAUER, EINMALIG, FAHRER, FAHRZEUG, ID, LADESTAND, STRECKE, WIEDERHOLUNG

# --- Umfang, Spec Abschnitt 2.1 ---------------------------------------------

DIESER = "this"
FOLGENDE = "following"
ALLE = "all"
UMFAENGE = (DIESER, FOLGENDE, ALLE)

MAX_SCHRITTE = 50

# Der Store, Spec Abschnitt 3
RISIKO = "risk"
EINTRAEGE = "entries"


@dataclass
class Schritt:
    """Was ein Schritt geaendert hat: je Eintrag der Stand davor und danach, None fuer 'fehlt'."""

    kennung: str
    vorher: dict[str, dict | None]
    nachher: dict[str, dict | None]


class Buch:
    """Risiko und Eintraege eines Standorts, dazu seine Schritte."""

    def __init__(self, daten: dict | None = None, schritte: deque | None = None) -> None:
        daten = daten or {}
        self.risiko: int | None = daten.get(RISIKO)
        self.eintraege: dict[str, dict] = {eintrag[ID]: eintrag for eintrag in daten.get(EINTRAEGE, [])}
        self.schritte: deque[Schritt] = deque(maxlen=MAX_SCHRITTE) if schritte is None else schritte

    def speicherform(self) -> dict:
        """Was in den Store geht. Das Risiko nur, wenn es jemand gesetzt hat."""
        daten: dict = {EINTRAEGE: [copy.deepcopy(eintrag) for eintrag in self.eintraege.values()]}
        if self.risiko is not None:
            daten[RISIKO] = self.risiko
        return daten


# --- Hilfen -------------------------------------------------------------------


def _eintrag(buch: Buch, eintrag_id: str) -> dict:
    eintrag = buch.eintraege.get(eintrag_id)
    if eintrag is None:
        raise fehler(EINTRAG_UNBEKANNT, "entry")
    return eintrag


def _termin_pruefen(eintrag: dict, datum: date) -> None:
    if not termine.hat_termin(eintrag, datum):
        raise fehler(TERMIN_UNBEKANNT, "date")


def _neuer_eintrag(kennung: str, werte: Werte) -> dict:
    return {
        ID: kennung,
        FAHRZEUG: werte.fahrzeug,
        ABFAHRT: werte.abfahrt,
        DAUER: werte.dauer_min,
        WIEDERHOLUNG: werte.wiederholung,
        STRECKE: werte.strecke_km,
        FAHRER: werte.fahrer,
        LADESTAND: werte.ladestand,
        BIS: None,
        AUSNAHMEN: {},
    }


def _ausnahme(werte: Werte) -> dict:
    return {ABFAHRT: werte.abfahrt, DAUER: werte.dauer_min, STRECKE: werte.strecke_km,
            FAHRER: werte.fahrer, LADESTAND: werte.ladestand}


def _mit_ausnahme(eintrag: dict, datum: date, werte: dict | None) -> dict:
    """Eine Kopie mit der Ausnahme am Datum. None sagt den Termin ab."""
    neu = copy.deepcopy(eintrag)
    neu[AUSNAHMEN][datum.isoformat()] = werte
    return neu


def _beendet(eintrag: dict, datum: date) -> dict:
    """Eine Kopie, deren Serie vor datum endet, ohne die Ausnahmen ab dort."""
    neu = copy.deepcopy(eintrag)
    neu[BIS] = datum.isoformat()
    neu[AUSNAHMEN] = {tag: werte for tag, werte in eintrag[AUSNAHMEN].items() if tag < datum.isoformat()}
    return neu


def _datum(text: str) -> date:
    return date.fromisoformat(text[:10])


def _anwenden(
    buch: Buch,
    aenderungen: dict[str, dict | None],
    neue_id: Callable[[], str],
    zu_schritt: str | None = None,
) -> str:
    """Setzt die Eintraege und haelt fest, wie sie vorher waren. Gibt den Schritt zurueck.

    Mit zu_schritt gehoert die Aenderung zu einem frueheren Schritt: das
    Absagen nach dem Speichern eines Termins. Rueckgaengig nimmt dann beides
    zurueck. Ist der Schritt nicht mehr da, etwa nach einem Neustart, wird
    es ein eigener.
    """
    schritt = next((s for s in buch.schritte if s.kennung == zu_schritt), None)
    if schritt is None:
        schritt = Schritt(neue_id(), {}, {})
        buch.schritte.append(schritt)  # der 51. verdraengt den ersten
    for eintrag_id, neu in aenderungen.items():
        if eintrag_id not in schritt.vorher:
            schritt.vorher[eintrag_id] = copy.deepcopy(buch.eintraege.get(eintrag_id))
        if neu is None:
            buch.eintraege.pop(eintrag_id, None)
        else:
            buch.eintraege[eintrag_id] = neu
        schritt.nachher[eintrag_id] = copy.deepcopy(neu)
    return schritt.kennung


# --- Die Operationen, Spec Abschnitte 2.1 und 2.2 ------------------------------


def anlegen(buch: Buch, werte: Werte, neue_id: Callable[[], str]) -> tuple[str, list[str]]:
    """Ein neuer Eintrag. Gibt (Schritt, [Eintrag]) zurueck."""
    eintrag = _neuer_eintrag(neue_id(), werte)
    return _anwenden(buch, {eintrag[ID]: eintrag}, neue_id), [eintrag[ID]]


def aendern(
    buch: Buch,
    eintrag_id: str,
    datum: date,
    umfang: str | None,
    werte: Werte,
    neue_id: Callable[[], str],
) -> tuple[str, list[str]]:
    """Aendert den Termin am Datum. Gibt (Schritt, Eintraege) zurueck.

    Die Eintraege sind die, die der Schritt angelegt oder geaendert hat; der
    mit den neuen Werten steht vorn. Ein einmaliger Termin kennt keinen
    Umfang, ohne Umfang gilt this.
    """
    eintrag = _eintrag(buch, eintrag_id)
    _termin_pruefen(eintrag, datum)
    if eintrag[WIEDERHOLUNG] == EINMALIG:
        neu = _neuer_eintrag(eintrag_id, werte)
        return _anwenden(buch, {eintrag_id: neu}, neue_id), [eintrag_id]

    umfang = umfang or DIESER
    regel_neu = werte.wiederholung != eintrag[WIEDERHOLUNG]
    tag_neu = _datum(werte.abfahrt) != datum

    if umfang == DIESER:
        if regel_neu:
            raise fehler(UMFANG_UNZULAESSIG, "scope")
        if werte.fahrzeug != eintrag[FAHRZEUG]:
            # Anderes Fahrzeug: hier absagen, dort einmalig anlegen.
            einmalig = _neuer_eintrag(neue_id(), replace(werte, wiederholung=EINMALIG))
            aenderungen = {einmalig[ID]: einmalig, eintrag_id: _mit_ausnahme(eintrag, datum, None)}
            return _anwenden(buch, aenderungen, neue_id), [einmalig[ID], eintrag_id]
        aenderungen = {eintrag_id: _mit_ausnahme(eintrag, datum, _ausnahme(werte))}
        return _anwenden(buch, aenderungen, neue_id), [eintrag_id]

    if umfang == FOLGENDE and datum != termine.erster_termin(eintrag):
        # Die Serie endet vor dem Datum, ab ihm beginnt ein neuer Eintrag.
        folge = _neuer_eintrag(neue_id(), werte)
        folge[BIS] = eintrag[BIS]
        if not (regel_neu or tag_neu):
            # Die Ausnahmen danach wandern mit. Die am Datum selbst nicht: der
            # Termin traegt jetzt die neuen Werte.
            folge[AUSNAHMEN] = {
                tag: copy.deepcopy(w) for tag, w in eintrag[AUSNAHMEN].items() if tag > datum.isoformat()}
        aenderungen = {folge[ID]: folge, eintrag_id: _beendet(eintrag, datum)}
        return _anwenden(buch, aenderungen, neue_id), [folge[ID], eintrag_id]

    # ALLE, oder FOLGENDE am ersten Termin: neue Werte fuer die Serie. Ein
    # verschobenes Datum verschiebt ihren Beginn um dieselben Tage.
    verschiebung = _datum(werte.abfahrt) - datum
    neu = _neuer_eintrag(eintrag_id, werte)
    neu[ABFAHRT] = (_datum(eintrag[ABFAHRT]) + verschiebung).isoformat() + werte.abfahrt[10:]
    if eintrag[BIS] is not None:
        neu[BIS] = (date.fromisoformat(eintrag[BIS]) + verschiebung).isoformat()
    if not (regel_neu or tag_neu):
        neu[AUSNAHMEN] = {
            tag: copy.deepcopy(w) for tag, w in eintrag[AUSNAHMEN].items() if tag != datum.isoformat()}
    return _anwenden(buch, {eintrag_id: neu}, neue_id), [eintrag_id]


def loeschen(
    buch: Buch, eintrag_id: str, datum: date, umfang: str | None, neue_id: Callable[[], str]
) -> str:
    """Loescht den Termin am Datum im Umfang. Gibt den Schritt zurueck."""
    eintrag = _eintrag(buch, eintrag_id)
    _termin_pruefen(eintrag, datum)
    umfang = umfang or DIESER
    if eintrag[WIEDERHOLUNG] == EINMALIG or umfang == ALLE:
        return _anwenden(buch, {eintrag_id: None}, neue_id)
    if umfang == DIESER:
        return _anwenden(buch, {eintrag_id: _mit_ausnahme(eintrag, datum, None)}, neue_id)
    if datum == termine.erster_termin(eintrag):
        return _anwenden(buch, {eintrag_id: None}, neue_id)
    return _anwenden(buch, {eintrag_id: _beendet(eintrag, datum)}, neue_id)


def absagen(
    buch: Buch,
    liste: list[tuple[str, date]],
    zu_schritt: str | None,
    neue_id: Callable[[], str],
) -> str:
    """Sagt Termine ab: bei einer Serie eine Ausnahme, ein einmaliger wird geloescht.

    Nennt der Aufruf den Schritt des Speicherns davor, gehoert das Absagen
    zu ihm (Spec Abschnitt 2.2).
    """
    arbeit: dict[str, dict | None] = {}
    for eintrag_id, datum in liste:
        eintrag = arbeit[eintrag_id] if eintrag_id in arbeit else buch.eintraege.get(eintrag_id)
        if eintrag is None:
            raise fehler(EINTRAG_UNBEKANNT, "entry")
        _termin_pruefen(eintrag, datum)
        arbeit[eintrag_id] = None if eintrag[WIEDERHOLUNG] == EINMALIG else _mit_ausnahme(eintrag, datum, None)
    return _anwenden(buch, arbeit, neue_id, zu_schritt)


def rueckgaengig(buch: Buch, kennung: str) -> None:
    """Stellt die Eintraege des Schritts her, wie sie vor ihm waren.

    Nur solange jeder davon noch so ist, wie der Schritt ihn hinterliess.
    Danach ist der Schritt verbraucht.
    """
    schritt = next((s for s in buch.schritte if s.kennung == kennung), None)
    if schritt is None or any(
        buch.eintraege.get(eintrag_id) != nachher for eintrag_id, nachher in schritt.nachher.items()
    ):
        raise fehler(RUECKGAENGIG_UNMOEGLICH, "step")
    for eintrag_id, vorher in schritt.vorher.items():
        if vorher is None:
            buch.eintraege.pop(eintrag_id, None)
        else:
            buch.eintraege[eintrag_id] = copy.deepcopy(vorher)
    buch.schritte.remove(schritt)


def fahrzeuge_bereinigen(buch: Buch, fahrzeuge: set[str]) -> bool:
    """Entfernt die Eintraege geloeschter Fahrzeuge. Kein Schritt. True, wenn einer ging."""
    weg = [eintrag_id for eintrag_id, e in buch.eintraege.items() if e[FAHRZEUG] not in fahrzeuge]
    for eintrag_id in weg:
        del buch.eintraege[eintrag_id]
    return bool(weg)


def schritt_bekannt(buch: Buch, kennung: str) -> bool:
    return any(s.kennung == kennung for s in buch.schritte)

