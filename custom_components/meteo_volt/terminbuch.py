"""Der Inhalt des Terminspeichers und seine Schritte, ohne Home Assistant.

Dieses Modul importiert bewusst NICHTS aus Home Assistant und nichts aus
aiohttp. Hier steht, was Anlegen, Aendern, Loeschen, Absagen und
Rueckgaengig mit den Eintraegen tun: Serien, Ausnahmen, Umfang.

Jeder schreibende Aufruf ist ein Schritt mit einer Kennung. Rueckgaengig
stellt die Eintraege des Schritts her, wie sie vor ihm waren, solange sie
seitdem niemand anders geaendert hat. Die Schritte liegen nur im Speicher,
die letzten 50 je Standort. Das Risiko ist kein Schritt, das Ignorieren
eines laufenden Termins (C9R) auch nicht. Speichern, Signale
und neu planen macht terminverwaltung.py.

Jede Operation prueft zuerst und aendert dann: scheitert sie, bleibt das
Buch, wie es war.

Spec: meteo-volt-brain/docs/features/C3-konfig-entitaeten/spec.md, Abschnitte 2.1, 2.2 und 3
      meteo-volt-brain/docs/features/C9-termine-im-alltag/spec.md, Abschnitte 2, 3 und 8
"""

from __future__ import annotations

import copy
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, tzinfo

from . import termine
from .pruefungen import (
    EINTRAG_UNBEKANNT,
    RUECKGAENGIG_UNMOEGLICH,
    TERMIN_LAEUFT_NICHT,
    TERMIN_UNBEKANNT,
    UMFANG_UNZULAESSIG,
    Werte,
    fehler,
)
from .termine import (
    ABFAHRT, AUSNAHMEN, BIS, DAUER, EINMALIG, FAHRER, FAHRZEUG, ID, LADESTAND, SICHERN, STRECKE,
    WIEDERHOLUNG,
)

# --- Umfang, Spec Abschnitt 2.1 ---------------------------------------------

DIESER = "this"
FOLGENDE = "following"
ALLE = "all"
UMFAENGE = (DIESER, FOLGENDE, ALLE)

MAX_SCHRITTE = 50

# Der Store, Spec Abschnitt 3
RISIKO = "risk"
EINTRAEGE = "entries"
IGNORIERT = "ignored"  # C9R-Spec Abschnitt 3

# C9Z-Spec Abschnitt 8.3: nur in den letzten 30 % eines Termins. Fest, siehe Karte C14.
HEIMKEHR_AB_ANTEIL = 0.7
ZU_HAUSE = "home"
KEIN_ZUSTAND = ("unavailable", "unknown")


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
        # Die ignorierten Termine als (Eintrag, Datum). Sie liegen neben den
        # Eintraegen, damit Umschalten kein Rueckgaengig eines Schritts bricht.
        self.ignoriert: set[tuple[str, date]] = {
            (paar["entry"], date.fromisoformat(paar["date"])) for paar in daten.get(IGNORIERT, [])}
        self.schritte: deque[Schritt] = deque(maxlen=MAX_SCHRITTE) if schritte is None else schritte

    def speicherform(self) -> dict:
        """Was in den Store geht. Risiko und ignorierte Termine nur, wenn es sie gibt."""
        daten: dict = {EINTRAEGE: [copy.deepcopy(eintrag) for eintrag in self.eintraege.values()]}
        if self.risiko is not None:
            daten[RISIKO] = self.risiko
        if self.ignoriert:
            daten[IGNORIERT] = [
                {"entry": eintrag_id, "date": datum.isoformat()} for eintrag_id, datum in sorted(self.ignoriert)]
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
        SICHERN: werte.sichern,
        BIS: None,
        AUSNAHMEN: {},
    }


def _ausnahme(werte: Werte) -> dict:
    return {ABFAHRT: werte.abfahrt, DAUER: werte.dauer_min, STRECKE: werte.strecke_km,
            FAHRER: werte.fahrer, LADESTAND: werte.ladestand, SICHERN: werte.sichern}


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


def _angezeigt(eintrag: dict, datum: date) -> date:
    """Das Datum, das der Termin zeigt: bei einer geaenderten Ausnahme ihre Abfahrt."""
    werte = eintrag[AUSNAHMEN].get(datum.isoformat())
    return datum if werte is None else _datum(werte[ABFAHRT])


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

    # FOLGENDE: die Serie endet vor dem Datum, ab ihm beginnt ein neuer
    # Eintrag. Am ersten Termin wirkt es wie ALLE: neue Werte fuer die Serie.
    folgende = umfang == FOLGENDE and datum != termine.erster_termin(eintrag)
    neu = _neuer_eintrag(neue_id() if folgende else eintrag_id, werte)
    if regel_neu:
        # Eine neue Wiederholung beginnt am Termin aus dem Formular, ohne die
        # Ausnahmen der alten.
        tag = _datum(werte.abfahrt)
        neu[BIS] = eintrag[BIS]
    else:
        # Verschoben ist das Datum gegen das, das der Termin zeigt; entschieden
        # am 2026-09-19. Um dieselben Tage wandern die uebrigen Termine.
        verschiebung = _datum(werte.abfahrt) - _angezeigt(eintrag, datum)
        tag = datum + verschiebung
        anker = datum if folgende else _datum(eintrag[ABFAHRT])
        neu[ABFAHRT] = (anker + verschiebung).isoformat() + werte.abfahrt[10:]
        if eintrag[BIS] is not None:
            neu[BIS] = (date.fromisoformat(eintrag[BIS]) + verschiebung).isoformat()
        if not verschiebung:
            # Ohne neuen Tag bleiben die Ausnahmen, bei FOLGENDE die danach.
            neu[AUSNAHMEN] = {
                t: copy.deepcopy(w) for t, w in eintrag[AUSNAHMEN].items()
                if t != datum.isoformat() and (t > datum.isoformat() or not folgende)}

    # Der bearbeitete Termin steht so da wie im Formular: als Ausnahme, wenn er
    # einzeln verlegt war; als einmaliger Termin, wenn die Serie keinen Platz
    # fuer ihn hat, etwa werktags auf einen Samstag gelegt.
    aenderungen: dict[str, dict | None] = {neu[ID]: neu}
    if not termine.ist_regeldatum(neu, tag):
        einmalig = _neuer_eintrag(neue_id(), replace(werte, wiederholung=EINMALIG))
        aenderungen[einmalig[ID]] = einmalig
    elif _datum(werte.abfahrt) != tag:
        neu[AUSNAHMEN][tag.isoformat()] = _ausnahme(werte)
    if folgende:
        aenderungen[eintrag_id] = _beendet(eintrag, datum)
    return _anwenden(buch, aenderungen, neue_id), list(aenderungen)


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


def ignorieren(
    buch: Buch, eintrag_id: str, datum: date, ignoriert: bool | None, jetzt: datetime, tz: tzinfo
) -> None:
    """Ignoriert den Termin am Datum oder beachtet ihn wieder. C9R-Spec Abschnitte 2 und 4.

    None heisst ignorieren, wie ein fehlendes ignored an der Action. Ignorieren
    geht nur, solange er laeuft. Beachten geht immer und tut ohne Markierung nichts.
    """
    _termin_pruefen(_eintrag(buch, eintrag_id), datum)
    if ignoriert is False:
        buch.ignoriert.discard((eintrag_id, datum))
        return
    if not termine.laeuft(termine.termin_am(buch.eintraege[eintrag_id], datum, tz), jetzt):
        raise fehler(TERMIN_LAEUFT_NICHT, "date")
    buch.ignoriert.add((eintrag_id, datum))


def ignoriert_bereinigen(buch: Buch, jetzt: datetime, tz: tzinfo) -> bool:
    """Entfernt jede Markierung, deren Termin gerade nicht laeuft. True, wenn eine ging.

    Vorbei, geloescht, abgesagt oder verschoben: ein Termin, der spaeter
    wieder laeuft, wird dann beachtet (C9R-Spec Abschnitt 2).
    """
    weg = set()
    for eintrag_id, datum in buch.ignoriert:
        eintrag = buch.eintraege.get(eintrag_id)
        termin = None if eintrag is None else termine.termin_am(eintrag, datum, tz)
        if termin is None or not termine.laeuft(termin, jetzt):
            weg.add((eintrag_id, datum))
    buch.ignoriert -= weg
    return bool(weg)


def heimgekehrt(alt: str | None, neu: str | None) -> bool:
    """Ein echter Wechsel nach home. C9Z-Spec Abschnitt 8.3, Punkt 1.

    Nicht aus home, nicht aus unavailable oder unknown und nicht ohne alten
    Zustand: sonst loesten der Start und eine flatternde Cloud-Entitaet aus.
    """
    return neu == ZU_HAUSE and alt is not None and alt != ZU_HAUSE and alt not in KEIN_ZUSTAND


def heimkehr(
    buch: Buch, tz: tzinfo, jetzt: datetime, fahrzeug: str | None = None, fahrer: str | None = None
) -> list[tuple[str, date]]:
    """Die Termine, die eine Heimkehr ignoriert. C9Z-Spec Abschnitt 8.3, Punkte 2 bis 4.

    fahrzeug: die subentry_id, deren Standort heimkam. fahrer: die Person, die
    heimkam. Ohne beide keine. Nur laufende Termine in ihren letzten 30 %, die
    noch nicht ignoriert sind.
    """
    if fahrzeug is None and fahrer is None:
        return []
    ergebnis = []
    # Ein Termin, der jetzt laeuft, hat Rueckkehr nach jetzt und Abfahrt bis jetzt.
    for termin in termine.ausrollen(list(buch.eintraege.values()), tz, jetzt, jetzt + timedelta(microseconds=1)):
        if (fahrzeug is not None and termin.fahrzeug != fahrzeug) or (fahrer is not None and termin.fahrer != fahrer):
            continue
        if not termine.laeuft(termin, jetzt) or (termin.eintrag, termin.datum) in buch.ignoriert:
            continue
        ab = termine.utc(termin.abfahrt) + (termine.utc(termin.rueckkehr) - termine.utc(termin.abfahrt)) * HEIMKEHR_AB_ANTEIL
        if termine.utc(jetzt) >= ab:
            ergebnis.append((termin.eintrag, termin.datum))
    return ergebnis


def heimkehr_von(
    buch: Buch, tz: tzinfo, jetzt: datetime, quelle: str, standorte: dict[str, set[str]]
) -> list[tuple[str, date]]:
    """Die Termine, die die Heimkehr dieser Quelle ignoriert. C9Z-Spec Abschnitt 8.3, Punkt 2.

    Ein Standort trifft die Termine seiner Fahrzeuge, jede andere Quelle ist eine
    Person und trifft die Termine, die sie als Fahrer tragen.
    """
    if quelle not in standorte:
        return heimkehr(buch, tz, jetzt, fahrer=quelle)
    treffer: list[tuple[str, date]] = []
    for fahrzeug in sorted(standorte[quelle]):
        treffer += heimkehr(buch, tz, jetzt, fahrzeug=fahrzeug)
    return treffer


def heimkehr_ereignisse(
    buch: Buch, treffer: list[tuple[str, date]], geraete: dict[str, str], quelle: str
) -> list[dict]:
    """Die Daten von meteo_volt_trip_ignored je Termin. C9Z-Spec Abschnitt 8.4.

    vehicle ist die Geraete-ID aus C6, nicht die subentry_id.
    """
    return [
        {"entry": eintrag_id, "date": datum.isoformat(),
         "vehicle": geraete.get((buch.eintraege.get(eintrag_id) or {}).get(FAHRZEUG)), "source": quelle}
        for eintrag_id, datum in treffer
    ]


def fahrzeuge_bereinigen(buch: Buch, fahrzeuge: set[str]) -> bool:
    """Entfernt die Eintraege geloeschter Fahrzeuge. Kein Schritt. True, wenn einer ging.

    Die Schritte, die einen davon beruehren, gehen mit (Spec Abschnitt 2.2).
    Sonst holte Rueckgaengig einen schon geloeschten Termin eines geloeschten
    Fahrzeugs zurueck.
    """
    def fremd(eintrag: dict | None) -> bool:
        return eintrag is not None and eintrag[FAHRZEUG] not in fahrzeuge

    for schritt in list(buch.schritte):
        if any(fremd(e) for e in (*schritt.vorher.values(), *schritt.nachher.values())):
            buch.schritte.remove(schritt)
    weg = [eintrag_id for eintrag_id, e in buch.eintraege.items() if fremd(e)]
    for eintrag_id in weg:
        del buch.eintraege[eintrag_id]
    return bool(weg)


def schritt_bekannt(buch: Buch, kennung: str) -> bool:
    return any(s.kennung == kennung for s in buch.schritte)

