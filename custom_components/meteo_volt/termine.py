"""Termine ohne Home Assistant: wann ein Eintrag stattfindet.

Dieses Modul importiert bewusst NICHTS aus Home Assistant und nichts aus
aiohttp -- wie standort.py. Hier steht, wie ein Eintrag aus dem Store zu
Terminen wird: Wiederholung, Ausnahmen, Ende der Serie, Zeitumstellung.
Was daraus im Request wird, steht in terminanfrage.py, was das Panel liest,
in ansicht.py.

Ein Eintrag ist ein einmaliger Termin oder eine Serie. Ein Termin ist ein
Vorkommen darin, erkannt an Eintrag und Datum seiner urspruenglichen
Abfahrt. Uhrzeiten gelten lokal in der Zeitzone von Home Assistant.
Gespeichert werden Abfahrt und Dauer; die Rueckkehr ist die Abfahrt plus
Dauer als verstrichene Zeit, also in UTC gerechnet.

Spec: meteo-volt-brain/docs/features/C3-konfig-entitaeten/spec.md, Abschnitte 2 und 3
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone, tzinfo

# --- Wiederholung, Spec Abschnitt 2 -----------------------------------------

EINMALIG = "once"
TAEGLICH = "daily"
WERKTAGS = "weekdays"
WOECHENTLICH = "weekly"
MONATLICH = "monthly"
JAEHRLICH = "yearly"
WIEDERHOLUNGEN = (EINMALIG, TAEGLICH, WERKTAGS, WOECHENTLICH, MONATLICH, JAEHRLICH)

# Der Abstand einer Serie. Dauert ein Termin so lange oder laenger, ist das
# dauer_zu_lang (Spec Abschnitt 2.3).
ABSTAND = {
    TAEGLICH: timedelta(hours=24),
    WERKTAGS: timedelta(hours=24),
    WOECHENTLICH: timedelta(days=7),
    MONATLICH: timedelta(days=28),
    JAEHRLICH: timedelta(days=365),
}

# --- Ein Eintrag im Store, Spec Abschnitt 3 ---------------------------------

ID = "id"
FAHRZEUG = "vehicle"
ABFAHRT = "departure"  # lokal, ISO 8601 ohne Offset
DAUER = "duration_min"
WIEDERHOLUNG = "repeat"
STRECKE = "distance_km"
FAHRER = "driver"
LADESTAND = "soc"
SICHERN = "keep_min_soc"  # der Haken "Min-SoC sichern", Spec C10 Abschnitt 3
BIS = "until"  # lokales Datum, ab dem die Serie endet, oder None
AUSNAHMEN = "exceptions"  # Datum -> None (abgesagt) oder die Werte unten

AUSNAHME_FELDER = (ABFAHRT, DAUER, STRECKE, FAHRER, LADESTAND, SICHERN)


def sichern_von(werte: dict) -> bool:
    """Der Haken eines Eintrags oder einer Ausnahme; fehlt er, ist er nicht gesetzt.

    Ein Eintrag aus der Zeit vor C10 traegt das Feld nicht und plant weiter
    wie bisher (C10-Spec Abschnitt 8). Kein Default True: das aenderte den
    Plan bestehender Termine, ohne dass jemand etwas angefasst haette.
    """
    return bool(werte.get(SICHERN, False))


@dataclass(frozen=True)
class Termin:
    """Ein Vorkommen eines Eintrags."""

    eintrag: str
    datum: date  # der urspruenglichen Abfahrt, lokal
    fahrzeug: str  # subentry_id
    abfahrt: datetime  # mit Zeitzone
    rueckkehr: datetime  # mit Zeitzone
    strecke_km: int
    fahrer: str | None
    ladestand: float | None
    wiederholung: str
    geaendert: bool  # eine geaenderte Ausnahme
    sichern: bool  # der Haken "Min-SoC sichern", Spec C10 Abschnitt 3


def lokal(text: str, tz: tzinfo) -> datetime:
    """'2026-09-21T08:00:00' als Zeitpunkt in tz.

    fold=0 wie beim Planer in _entry_moments: eine Uhrzeit, die es am Tag der
    Umstellung nicht gibt, liegt eine Stunde spaeter; eine, die es zweimal
    gibt, gilt beim ersten Mal. Der Weg ueber UTC schreibt die Uhrzeit
    danach richtig: aus 02:30 wird 03:30.
    """
    zeitpunkt = datetime.fromisoformat(text).replace(tzinfo=tz, fold=0)
    return zeitpunkt.astimezone(timezone.utc).astimezone(tz)


def plus_dauer(abfahrt: datetime, dauer_min: int, tz: tzinfo) -> datetime:
    """Die Rueckkehr: Abfahrt plus Dauer als verstrichene Zeit.

    Nicht abfahrt + timedelta: Python rechnet mit Zeitzone auf der Wanduhr,
    und eine Fahrt ueber die Zeitumstellung dauerte eine Stunde laenger
    oder kuerzer als jede andere.
    """
    return (abfahrt.astimezone(timezone.utc) + timedelta(minutes=dauer_min)).astimezone(tz)


def utc(zeitpunkt: datetime) -> datetime:
    """Fuer jeden Vergleich und jede Differenz.

    Tragen zwei Zeitpunkte dasselbe tzinfo, vergleicht und subtrahiert Python
    sie auf der Wanduhr, ohne fold. Ueber die Umstellung ist das falsch.
    """
    return zeitpunkt.astimezone(timezone.utc)


def dauer_min(abfahrt: datetime, rueckkehr: datetime) -> int:
    """Die verstrichenen Minuten zwischen zwei Zeitpunkten mit Zeitzone."""
    return math.floor((utc(rueckkehr) - utc(abfahrt)).total_seconds() / 60)


# --- Die Daten einer Serie ---------------------------------------------------


def _start(eintrag: dict) -> date:
    return date.fromisoformat(eintrag[ABFAHRT][:10])


def _nter_wochentag(jahr: int, monat: int, wochentag: int, n: int) -> date:
    """Der n-te Wochentag im Monat. n = 5 heisst: der letzte."""
    if n >= 5:
        naechster = date(jahr + 1, 1, 1) if monat == 12 else date(jahr, monat + 1, 1)
        letzter = naechster - timedelta(days=1)
        return letzter - timedelta(days=(letzter.weekday() - wochentag) % 7)
    erster = date(jahr, monat, 1)
    return erster + timedelta(days=(wochentag - erster.weekday()) % 7 + 7 * (n - 1))


def regeldaten(eintrag: dict, ab: date, bis: date) -> Iterator[date]:
    """Die Daten der regulaeren Termine von ab bis bis, beide eingeschlossen.

    Regulaer heisst: nach der Wiederholung, vor until, abgesagt oder nicht.
    """
    start = _start(eintrag)
    if eintrag.get(BIS) is not None:
        bis = min(bis, date.fromisoformat(eintrag[BIS]) - timedelta(days=1))
    art = eintrag[WIEDERHOLUNG]
    if art == EINMALIG:
        if ab <= start <= bis:
            yield start
        return
    tag = max(start, ab)
    if art in (TAEGLICH, WERKTAGS):
        while tag <= bis:
            if art == TAEGLICH or tag.weekday() < 5:
                yield tag
            tag += timedelta(days=1)
    elif art == WOECHENTLICH:
        tag += timedelta(days=-(tag - start).days % 7)
        while tag <= bis:
            yield tag
            tag += timedelta(days=7)
    elif art == MONATLICH:
        # n = ceil(Tag / 7). Ab dem 29. ist das 5 und heisst "am letzten".
        n = math.ceil(start.day / 7)
        jahr, monat = tag.year, tag.month
        while True:
            kandidat = _nter_wochentag(jahr, monat, start.weekday(), n)
            if kandidat > bis:
                return
            if kandidat >= tag:
                yield kandidat
            jahr, monat = (jahr + 1, 1) if monat == 12 else (jahr, monat + 1)
    elif art == JAEHRLICH:
        for jahr in range(tag.year, bis.year + 1):
            try:
                kandidat = start.replace(year=jahr)
            except ValueError:
                continue  # der 29. Februar gibt es nur im Schaltjahr
            if tag <= kandidat <= bis:
                yield kandidat
    else:
        raise ValueError(f"unbekannte Wiederholung: {art}")


def ist_regeldatum(eintrag: dict, datum: date) -> bool:
    return next(regeldaten(eintrag, datum, datum), None) is not None


def hat_termin(eintrag: dict, datum: date) -> bool:
    """Ob der Eintrag an diesem Datum einen Termin hat, der nicht abgesagt ist."""
    ausnahmen = eintrag.get(AUSNAHMEN) or {}
    abgesagt = datum.isoformat() in ausnahmen and ausnahmen[datum.isoformat()] is None
    return ist_regeldatum(eintrag, datum) and not abgesagt


def erster_termin(eintrag: dict) -> date | None:
    """Das Datum des ersten Termins, der nicht abgesagt ist. Werktags ab einem Samstag der Montag.

    Spec Abschnitt 2.1: an ihm wirkt following wie all. Ein abgesagter zaehlt
    nicht, sonst bliebe nach following am ersten sichtbaren ein Eintrag ohne
    sichtbaren Termin zurueck. Die Suche endet: Ausnahmen gibt es endlich viele.
    """
    ausnahmen = eintrag.get(AUSNAHMEN) or {}
    for datum in regeldaten(eintrag, _start(eintrag), date.max):
        tag = datum.isoformat()
        if not (tag in ausnahmen and ausnahmen[tag] is None):
            return datum
    return None


# --- Termine ----------------------------------------------------------------


def termin_am(eintrag: dict, datum: date, tz: tzinfo) -> Termin | None:
    """Der Termin des Eintrags an diesem Datum, oder None, wenn es keinen gibt."""
    if not hat_termin(eintrag, datum):
        return None
    werte = (eintrag.get(AUSNAHMEN) or {}).get(datum.isoformat())
    if werte is None:
        # SICHERN getrennt: ein Eintrag von vor C10 traegt das Feld nicht,
        # die uebrigen Felder sind Pflicht und sollen laut fehlen.
        werte = {feld: eintrag[feld] for feld in AUSNAHME_FELDER if feld != SICHERN}
        werte[SICHERN] = sichern_von(eintrag)
        werte[ABFAHRT] = datum.isoformat() + eintrag[ABFAHRT][10:]
        geaendert = False
    else:
        geaendert = True
    abfahrt = lokal(werte[ABFAHRT], tz)
    return Termin(
        eintrag=eintrag[ID],
        datum=datum,
        fahrzeug=eintrag[FAHRZEUG],
        abfahrt=abfahrt,
        rueckkehr=plus_dauer(abfahrt, werte[DAUER], tz),
        strecke_km=werte[STRECKE],
        fahrer=werte[FAHRER],
        ladestand=werte[LADESTAND],
        wiederholung=eintrag[WIEDERHOLUNG],
        geaendert=geaendert,
        sichern=sichern_von(werte),
    )


def termine_von(eintrag: dict, tz: tzinfo, von: datetime, bis: datetime) -> list[Termin]:
    """Die Termine eines Eintrags, deren Rueckkehr nach von und deren Abfahrt vor bis liegt.

    Eine geaenderte Ausnahme kann ihren Termin an einen anderen Tag legen, in
    das Fenster hinein oder aus ihm heraus. Ihre Daten zaehlen deshalb immer mit.
    """
    ab = von.astimezone(tz).date() - timedelta(days=eintrag[DAUER] // 1440 + 1)
    daten = set(regeldaten(eintrag, ab, bis.astimezone(tz).date()))
    daten |= {
        date.fromisoformat(tag)
        for tag, werte in (eintrag.get(AUSNAHMEN) or {}).items()
        if werte is not None
    }
    ergebnis = []
    for datum in sorted(daten):
        termin = termin_am(eintrag, datum, tz)
        if termin is not None and utc(termin.rueckkehr) > utc(von) and utc(termin.abfahrt) < utc(bis):
            ergebnis.append(termin)
    return ergebnis


def ausrollen(
    eintraege: list[dict],
    tz: tzinfo,
    von: datetime,
    bis: datetime,
    fahrzeug: str | None = None,
) -> list[Termin]:
    """Alle Termine im Fenster, nach Abfahrt sortiert. fahrzeug filtert."""
    termine = [
        termin
        for eintrag in eintraege
        if fahrzeug is None or eintrag[FAHRZEUG] == fahrzeug
        for termin in termine_von(eintrag, tz, von, bis)
    ]
    return sorted(termine, key=_reihenfolge)


def _reihenfolge(termin: Termin) -> tuple:
    return utc(termin.abfahrt), termin.eintrag, termin.datum


def ueberschneiden(a: Termin, b: Termin) -> bool:
    """Zwei Termine liegen zur selben Zeit. Halboffen: Rueckkehr gleich Abfahrt nicht."""
    return utc(a.abfahrt) < utc(b.rueckkehr) and utc(b.abfahrt) < utc(a.rueckkehr)
