"""Die Ausgabe-Entitaeten ohne Home Assistant.

Dieses Modul importiert bewusst NICHTS aus Home Assistant und nichts aus
aiohttp -- wie standort.py, auf dem es aufbaut. Hier steht, was C6
entscheidet: welche Werte die acht Entitaeten eines Fahrzeugs tragen, wann
"Jetzt laden" am gemessenen Ladestand abschaltet, wie die
Ladegeschwindigkeit gegen den Plan gemessen wird und wann das Issue kommt
und geht. fahrzeugausgabe.py
verdrahtet das mit Home Assistant und entscheidet selbst nichts.

Spec: meteo-volt-brain/docs/features/C6-ausgabe-entitaeten/spec.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from . import standort
from .const import ISSUE_LANGSAMER, ISSUE_SCHNELLER

# --- Die Entitaeten, Spec Abschnitt 2 ---------------------------------------
# Zugleich translation_key und Ende der unique_id.

JETZT_LADEN = "charge_now"
LADELEISTUNG = "charge_now_kw"
NAECHSTER_LADESTART = "next_charge_start"
ENERGIE = "total_kwh"
KOSTEN = "total_cost"
LADESTAND_PLANENDE = "soc_end_pct"
ERFUELLBAR = "feasible"
LADEPLAN = "plan"

BINAERSENSOREN = (JETZT_LADEN, ERFUELLBAR)
SENSOREN = (LADELEISTUNG, NAECHSTER_LADESTART, ENERGIE, KOSTEN, LADESTAND_PLANENDE, LADEPLAN)

# --- Der Zustand des Ladeplans, Spec Abschnitt 2.2 --------------------------
# Die Gruende aus ausgelassen gehen vor: sie sagen, was der Nutzer tun kann.

AKTUELL = "aktuell"
KEIN_PLAN = "kein_plan"
GRUENDE = (
    standort.GRUND_KEIN_LADEPUNKT,
    standort.GRUND_LADEPUNKT_GELOESCHT,
    standort.GRUND_LADESTAND,
)
ZUSTAENDE = (*GRUENDE, AKTUELL, KEIN_PLAN)

# --- Die Attribute, Spec Abschnitt 2.3 --------------------------------------
# Keins davon geht in den Recorder (Abschnitt 3).

QUELLE = "quelle"
ZIEL_ERREICHT = "ziel_erreicht"
VIOLATIONS = "violations"
SLOTS = "slots"
INTERVALS = "intervals"
WARNINGS = "warnings"
FEHLER = "fehler"

# --- Grenzen, Spec Abschnitte 5 und 6 ---------------------------------------

# Dieselbe Grenze wie soc_stale im Plan-Dienst. Ein aelterer Ladestand stoppt nicht.
FRISCH = timedelta(minutes=30)
# Gemessen am 2026-09-10: darunter erzeugt die Messung allein mehr als 5 %.
BEWERTEN_AB = timedelta(hours=2)
TOLERANZ = 0.05
MIN_PUNKTE = 3

# Wo ein Einschalten in der Messung steht, Spec Abschnitt 6. None heisst,
# Jetzt laden ist aus.
WARTET = "wartet"  # auf den ersten Anstieg
ZAEHLT = "zaehlt"
GEFALLEN = "gefallen"  # bis zum naechsten Einschalten zaehlt nichts


@dataclass(frozen=True)
class Abgleich:
    """Die laufende Messung der Ladegeschwindigkeit. Spec Abschnitt 6.

    Die Zeitachse ist die Ladezeit in Sekunden: Pausen zaehlen nicht mit.
    punkte traegt (einschalten, ladezeit_s, ladestand). Jedes Einschalten
    zaehlt hoch und bekommt in der Regression einen eigenen
    Achsenabschnitt -- wird das Auto zwischen zwei Bloecken gefahren, aendert
    das nur die Hoehe, nicht die Steigung.

    phase ist WARTET, ZAEHLT, GEFALLEN oder None. vorig ist beim Warten der
    letzte frische Ladestand. seit steht nur, solange Ladezeit laeuft.
    """

    ladezeit_s: float = 0.0
    geplant_pp: float = 0.0
    punkte: tuple[tuple[int, float, float], ...] = ()
    einschalten: int = 0
    seit: datetime | None = None
    rate: float | None = None
    phase: str | None = None
    vorig: float | None = None


@dataclass(frozen=True)
class Zustand:
    """Was von einer Auswertung eines Fahrzeugs zur naechsten bleibt.

    daten sind die Daten des Fahrzeugs bei der letzten Auswertung, vor der
    ersten None.
    """

    gesperrt_bis: datetime | None = None
    abgleich: Abgleich = field(default_factory=Abgleich)
    daten: dict | None = None


@dataclass(frozen=True)
class Bewertung:
    """Gemessene und geplante Rate in Prozentpunkten je Stunde."""

    gemessen: float
    geplant: float

    @property
    def abweichung(self) -> float:
        return self.gemessen / self.geplant - 1

    @property
    def ausserhalb(self) -> bool:
        # Als Differenz, nicht als Quotient: 105 / 100 - 1 ergibt in Gleitkomma
        # 0.05000000000000004, und genau 5 % laege dann schon ausserhalb.
        return abs(self.gemessen - self.geplant) > TOLERANZ * self.geplant


@dataclass(frozen=True)
class Auswertung:
    """Das Ergebnis einer Auswertung. Spec Abschnitt 4.

    werte und attribute sind nach den Schluesseln aus Abschnitt 2 geordnet.
    naechste ist, wann spaetestens neu ausgewertet wird. bewertung steht nur,
    wenn in dieser Auswertung eine Messung bewertet wurde. issue ist ANLEGEN,
    ENTFERNEN oder None, wenn das Issue bleibt, wie es ist.
    """

    werte: dict
    attribute: dict
    naechste: datetime
    zustand: Zustand
    bewertung: Bewertung | None = None
    issue: str | None = None


def auswerten(
    stand: standort.Planstand,
    fahrzeug_id: str,
    jetzt: datetime,
    soc_pct: float | None,
    gemeldet: datetime | None,
    zustand: Zustand,
    daten: dict,
) -> Auswertung:
    """Eine Auswertung fuer ein Fahrzeug. Spec Abschnitte 2 bis 6.

    soc_pct ist der Ladestand nach standort.ladestand_lesen, gemeldet sein
    last_reported. zustand kommt aus der vorigen Auswertung, daten sind die
    Daten aus dem Subentry des Fahrzeugs.
    """
    gilt = standort.was_gilt(stand, fahrzeug_id, jetzt, soc_pct)
    mit_plan = gilt["quelle"] == standort.QUELLE_PLAN
    frisch = soc_pct is not None and gemeldet is not None and jetzt - gemeldet <= FRISCH
    fahrzeugplan, block = _plan_und_block(stand, fahrzeug_id, gilt) if mit_plan else (None, None)

    laden, kw = gilt["charge_now"], gilt["charge_now_kw"]
    gesperrt_bis = zustand.gesperrt_bis
    if gesperrt_bis is not None and jetzt >= gesperrt_bis:
        gesperrt_bis = None
    if block is not None:
        ende, ziel = block
        # Abschnitt 5, Regeln 1 und 3: nur ein frischer Ladestand stoppt.
        if gesperrt_bis is None and frisch and soc_pct >= ziel:
            gesperrt_bis = ende
        # Regel 2: die Sperre haelt bis zum Blockende, auch gegen einen neuen Plan.
        if gesperrt_bis is not None:
            laden, kw = False, 0.0

    # Abschnitt 6: aendern sich die Daten des Fahrzeugs, beginnt die Messung
    # neu, und das Issue geht. Das prueft jede Auswertung, gleich aus welchem Anlass.
    geaendert = zustand.daten is not None and daten != zustand.daten
    rate = _geplante_rate(stand, fahrzeug_id, kw) if mit_plan and laden else None
    abgleich, bewertung = abgleichen(
        Abgleich() if geaendert else zustand.abgleich, jetzt, rate, soc_pct if frisch else None
    )

    return Auswertung(
        werte=_werte(stand, fahrzeug_id, gilt, fahrzeugplan, laden, kw),
        attribute=_attribute(stand, fahrzeug_id, gilt, fahrzeugplan, mit_plan and gesperrt_bis is not None),
        naechste=_naechste(stand, jetzt, gilt["current_slot_end"]),
        zustand=Zustand(gesperrt_bis=gesperrt_bis, abgleich=abgleich, daten=daten),
        bewertung=bewertung,
        issue=_issue(bewertung, geaendert),
    )


def _plan_und_block(
    stand: standort.Planstand, fahrzeug_id: str, gilt: dict
) -> tuple[dict | None, tuple[datetime, float] | None]:
    """Der Fahrzeugplan und, wenn gerade geladen wird, Ende und Ziel des Blocks.

    Der Plan-Client prueft eine 200 nicht gegen das Schema (C7-Spec
    Abschnitt 5). Fehlt dem Plan etwas, gibt es keinen Stopp am Ladestand,
    und die Planwerte bleiben unbekannt.
    """
    try:
        fahrzeugplan = next(
            fp for fp in stand.plan["vehicles"] if fp.get("id") == fahrzeug_id
        )
        if not gilt["charge_now"]:
            return fahrzeugplan, None
        return fahrzeugplan, _block(
            fahrzeugplan["slots"], gilt["current_slot_end"], stand.plan["slot_minutes"]
        )
    except (AttributeError, KeyError, StopIteration, TypeError, ValueError):
        return None, None


def _block(slots: list[dict], slot_ende: datetime, slot_minutes: int) -> tuple[datetime, float]:
    """Ende und Ziel des Ladeblocks, dessen laufender Slot bei slot_ende endet.

    Ein Block ist eine lueckenlose Folge von Ladeslots (A0-Spec 3.10), sein
    Ziel das soc_end_pct seines letzten Slots.
    """
    schritt = timedelta(minutes=slot_minutes)
    index = next(
        i for i, slot in enumerate(slots)
        if datetime.fromisoformat(slot["t"]) + schritt == slot_ende
    )
    while index + 1 < len(slots) and slots[index + 1]["charge"]:
        index += 1
    return datetime.fromisoformat(slots[index]["t"]) + schritt, float(slots[index]["soc_end_pct"])


def _geplante_rate(stand: standort.Planstand, fahrzeug_id: str, kw: float) -> float | None:
    """charge_now_kw x eta / Kapazitaet x 100, in Prozentpunkten je Stunde.

    eta und Kapazitaet kommen aus dem zuletzt gebauten Request.
    """
    for fahrzeug in (stand.anfrage or {}).get("vehicles", []):
        if fahrzeug.get("id") == fahrzeug_id:
            try:
                return kw * fahrzeug["efficiency_curve"][0]["eta"] / fahrzeug["capacity_kwh"] * 100
            except (IndexError, KeyError, TypeError, ZeroDivisionError):
                return None
    return None


def abgleichen(
    alt: Abgleich, jetzt: datetime, rate: float | None, soc: float | None
) -> tuple[Abgleich, Bewertung | None]:
    """Fuehrt die Messung um eine Auswertung weiter. Spec Abschnitt 6.

    rate ist die geplante Rate, solange Jetzt laden aus dem Plan an ist, sonst
    None. soc ist der Ladestand, wenn er frisch ist, sonst None. Ein
    Einschalten zaehlt erst ab seinem ersten Anstieg: ab da laeuft seine
    Ladezeit, und Messpunkte sind dieser Ladestand und jeder hoehere danach,
    auch der, der das Ziel erreicht und damit abschaltet. Faellt der
    Ladestand, zaehlt bis zum naechsten Einschalten nichts mehr.
    """
    aktiv = rate is not None
    ladezeit, geplant = alt.ladezeit_s, alt.geplant_pp
    if alt.seit is not None:
        dauer = max(0.0, (jetzt - alt.seit).total_seconds())
        ladezeit += dauer
        geplant += alt.rate * dauer / 3600
    einschalten, phase, vorig, punkte = alt.einschalten, alt.phase, alt.vorig, alt.punkte
    if aktiv and phase is None:
        einschalten, phase, vorig = einschalten + 1, WARTET, soc
    elif soc is not None and phase == WARTET:
        if vorig is not None and soc > vorig:
            punkte, phase, vorig = (*punkte, (einschalten, ladezeit, soc)), ZAEHLT, None
        else:
            vorig = soc
    elif soc is not None and phase == ZAEHLT:
        if soc > punkte[-1][2]:
            punkte = (*punkte, (einschalten, ladezeit, soc))
        elif soc < punkte[-1][2]:
            phase = GEFALLEN
    if not aktiv:
        phase = None
    zaehlt = phase == ZAEHLT
    neu = Abgleich(ladezeit, geplant, punkte, einschalten,
                   jetzt if zaehlt else None, rate if zaehlt else None, phase, vorig)
    if ladezeit < BEWERTEN_AB.total_seconds():
        return neu, None
    # Bewertet, die Messung beginnt neu. Laedt das Auto weiter, beginnt sie wie
    # nach einem Einschalten: der naechste Punkt ist die naechste Aenderung.
    if zaehlt:
        naechste_messung = Abgleich(einschalten=einschalten + 1, phase=WARTET, vorig=soc)
    else:
        naechste_messung = Abgleich(einschalten=einschalten, phase=phase)
    return naechste_messung, bewerten(neu)


def bewerten(abgleich: Abgleich) -> Bewertung | None:
    """Die gemeinsame Steigung mit eigenem Achsenabschnitt je Einschalten.

    None heisst nicht bewertet: weniger als MIN_PUNKTE verwertbare Punkte,
    das sind Punkte eines Einschaltens mit mindestens zwei.
    """
    gruppen: dict[int, list[tuple[float, float]]] = {}
    for einschalten, ladezeit, soc in abgleich.punkte:
        gruppen.setdefault(einschalten, []).append((ladezeit, soc))
    zaehler = nenner = 0.0
    verwertbar = 0
    for punkte in gruppen.values():
        if len(punkte) < 2:
            continue
        verwertbar += len(punkte)
        mitte_t = sum(t for t, _ in punkte) / len(punkte)
        mitte_soc = sum(s for _, s in punkte) / len(punkte)
        zaehler += sum((t - mitte_t) * (s - mitte_soc) for t, s in punkte)
        nenner += sum((t - mitte_t) ** 2 for t, _ in punkte)
    if verwertbar < MIN_PUNKTE or nenner <= 0 or abgleich.geplant_pp <= 0:
        return None
    return Bewertung(
        gemessen=zaehler / nenner * 3600,
        geplant=abgleich.geplant_pp / abgleich.ladezeit_s * 3600,
    )


def _werte(
    stand: standort.Planstand,
    fahrzeug_id: str,
    gilt: dict,
    fahrzeugplan: dict | None,
    laden: bool,
    kw: float,
) -> dict:
    """Die Zustaende der acht Entitaeten. Spec Abschnitte 2, 2.1 und 2.2."""
    grund = stand.ausgelassen.get(fahrzeug_id)
    if grund in GRUENDE:
        plan = grund
    elif fahrzeugplan is not None:
        plan = AKTUELL
    else:
        plan = KEIN_PLAN
    fp = fahrzeugplan or {}
    return {
        JETZT_LADEN: laden,
        LADELEISTUNG: kw,
        NAECHSTER_LADESTART: gilt["next_charge_start"],
        ENERGIE: fp.get("total_kwh"),
        # A0-Spec 3.2: mit Netzentgelt, wenn der Plan es liefert.
        KOSTEN: fp.get("total_cost_incl_fees_eur", fp.get("total_cost_eur")),
        LADESTAND_PLANENDE: fp.get("soc_end_pct"),
        ERFUELLBAR: fp.get("feasible"),
        LADEPLAN: plan,
    }


def _attribute(
    stand: standort.Planstand,
    fahrzeug_id: str,
    gilt: dict,
    fahrzeugplan: dict | None,
    ziel_erreicht: bool,
) -> dict:
    """Die Attribute je Entitaet. Spec Abschnitt 2.3."""
    fehler = None if stand.fehler is None else f"{type(stand.fehler).__name__}: {stand.fehler}"
    attribute = {
        JETZT_LADEN: {QUELLE: gilt["quelle"], ZIEL_ERREICHT: ziel_erreicht},
        ERFUELLBAR: {},
        LADEPLAN: {FEHLER: fehler},
    }
    if fahrzeugplan is not None:
        attribute[ERFUELLBAR] = {VIOLATIONS: fahrzeugplan.get("violations", [])}
        attribute[LADEPLAN] = {
            SLOTS: fahrzeugplan.get("slots", []),
            INTERVALS: fahrzeugplan.get("intervals", []),
            WARNINGS: _warnungen(stand.plan, fahrzeug_id),
            FEHLER: fehler,
        }
    return attribute


def _warnungen(plan: dict, fahrzeug_id: str) -> list[dict]:
    """Die Warnungen, die dieses Fahrzeug nennen oder gar keins."""
    return [w for w in plan.get("warnings") or [] if _nennt(w, fahrzeug_id)]


def _nennt(warnung: dict, fahrzeug_id: str) -> bool:
    if "vehicle_id" in warnung:
        return warnung["vehicle_id"] == fahrzeug_id
    if "vehicle_ids" in warnung:
        return fahrzeug_id in warnung["vehicle_ids"]
    return True


def _naechste(stand: standort.Planstand, jetzt: datetime, slot_ende: datetime) -> datetime:
    """Die Slotgrenze, oder 12 h nach Empfang, wenn das frueher kommt. Spec Abschnitt 4."""
    if stand.erhalten_um is not None:
        veraltet = stand.erhalten_um + standort.VERALTET_NACH
        if jetzt < veraltet < slot_ende:
            return veraltet
    return slot_ende


# --- Das Issue, Spec Abschnitt 6 --------------------------------------------

ANLEGEN = "anlegen"
ENTFERNEN = "entfernen"


def _issue(bewertung: Bewertung | None, geaendert: bool) -> str | None:
    """Ueber 5 % anlegen. Hoechstens 5 % und geaenderte Daten nehmen es zurueck."""
    if bewertung is not None:
        return ANLEGEN if bewertung.ausserhalb else ENTFERNEN
    return ENTFERNEN if geaendert else None


def issue_uebersetzung(bewertung: Bewertung) -> str:
    return ISSUE_SCHNELLER if bewertung.abweichung > 0 else ISSUE_LANGSAMER


def issue_platzhalter(bewertung: Bewertung, fahrzeug: str, sprache: str) -> dict[str, str]:
    """Zahlen mit einer Nachkommastelle, Dezimalzeichen nach der Sprache."""
    deutsch = (sprache or "en").split("-")[0].lower() == "de"

    def zahl(wert: float) -> str:
        text = f"{wert:.1f}"
        return text.replace(".", ",") if deutsch else text

    return {
        "fahrzeug": fahrzeug,
        "gemessen": zahl(bewertung.gemessen),
        "geplant": zahl(bewertung.geplant),
        "abweichung": str(round(abs(bewertung.abweichung) * 100)),
    }
