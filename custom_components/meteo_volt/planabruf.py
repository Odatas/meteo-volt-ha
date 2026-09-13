"""Der Plan-Aufruf ohne Home Assistant.

Dieses Modul importiert bewusst NICHTS aus Home Assistant und nichts aus
aiohttp -- wie stammdaten.py. Beides steckt nicht in den Testabhaengigkeiten.
api.py schickt ab und reicht Status, Retry-After und Koerper herein; was
davor und danach entschieden wird, steht hier und ist gegen die vendorten
Fehlerfixtures pruefbar.

Verzweigt wird nur auf den Statuscode, nie auf `type`. 401 und 429 kommen aus
Zuplos Policies mit Typen aus httpproblems.com, der Rest aus dem Plan-Dienst
oder dem Gateway-Handler. Fehlerkoerper werden deshalb tolerant gelesen:
Zuplos Antworten verletzen plan-error.schema.json.

Die Klassen sagen, was zu tun ist, nicht warum. Ein 404 kann ein unbekanntes
Modell sein oder eine Gateway-Umgebung ohne Plan-Route.

Spec: meteo-volt-brain/docs/features/C7-plan-client/spec.md
"""

from __future__ import annotations

import json
import math

PROGNOSE_PFAD = "/v1/prediction"
PLAN_PFAD = "/v1/plan"

# Ohne brauchbaren Retry-After-Header (A0-Spec 3.9): 60 s, verdoppelt mit
# jedem weiteren 429 seit der letzten 200, hoechstens 15 min.
PAUSE_BASIS_S = 60.0
PAUSE_DECKEL_S = 900.0


class PlanFehler(Exception):
    """Basis aller Plan-Fehler.

    Die Meldung entsteht nur aus Status, title, detail und den drei Feldern je
    Feldfehler. Sie nennt nie einen Wert aus dem Request -- dort stehen
    Ladestand und Fahrzeugdaten (Basiskontrakt 3.7).
    """

    def __init__(
        self,
        *,
        status: int | None = None,
        titel: str | None = None,
        detail: str | None = None,
        feldfehler: tuple[dict, ...] = (),
    ) -> None:
        self.status = status
        self.titel = titel
        self.detail = detail
        self.feldfehler = tuple(feldfehler)
        super().__init__(self._meldung())

    def _meldung(self) -> str:
        teile = [f"Status {self.status}" if self.status is not None else "kein Status"]
        teile += [text for text in (self.titel, self.detail) if text]
        teile += [
            f"{f.get('field', '?')}: {f.get('problem', '?')} "
            f"(erwartet: {f.get('expected', '?')})"
            for f in self.feldfehler
        ]
        return "; ".join(teile)


class PlanNichtAutorisiert(PlanFehler):
    """401, 403. Der Key gilt nicht; ohne den Nutzer aendert sich nichts."""


class PlanRateLimit(PlanFehler):
    """429, und jeder Aufruf waehrend der Sendepause.

    retry_after sind die Sekunden bis zum Ende der Pause.
    """

    def __init__(self, *, retry_after: float, **felder) -> None:
        # Vor super().__init__: die Meldung nennt die Pause.
        self.retry_after = retry_after
        super().__init__(**felder)

    def _meldung(self) -> str:
        # Aufgerundet: 0,4 s Rest sind noch gesperrt und duerfen nicht als
        # "Pause 0 s" erscheinen. retry_after ist immer endlich, siehe
        # _retry_after.
        return f"{super()._meldung()}; Pause {math.ceil(self.retry_after)} s"


class PlanAbgelehnt(PlanFehler):
    """Jeder andere Status unter 500 ausser 200. Dieselbe Anfrage scheitert wieder."""


class PlanNichtVerfuegbar(PlanFehler):
    """500 und hoeher, Verbindungsfehler, Timeout, eine 200 ohne JSON-Objekt.

    Jetzt kein Plan. Spaeter erneut, ohne die Anfrage zu aendern.
    """


def _plan_url(api_url: str) -> str | None:
    """'.../v1/prediction' -> '.../v1/plan', sonst None.

    Aus api_url abgeleitet statt aus einem eigenen Override-Schluessel: sonst
    liefen Dev und Prod still auseinander, sobald const_overwrite.json nur
    einen der beiden nennt.
    """
    basis = api_url.rstrip("/")
    if not basis.endswith(PROGNOSE_PFAD):
        return None
    return basis[: -len(PROGNOSE_PFAD)] + PLAN_PFAD


def _json_objekt(koerper: bytes) -> dict | None:
    """Der Koerper als JSON-Objekt, oder None. Wirft nie."""
    try:
        dokument = json.loads(koerper)
    # ValueError faengt auch JSONDecodeError und UnicodeDecodeError. Tief
    # verschachteltes JSON wirft dagegen RecursionError, und das ist keiner.
    except (ValueError, RecursionError):
        return None
    return dokument if isinstance(dokument, dict) else None


def _text(dokument: dict, schluessel: str) -> str | None:
    wert = dokument.get(schluessel)
    return wert if isinstance(wert, str) else None


def _feldfehler(dokument: dict) -> tuple[dict, ...]:
    """Aus errors nur field, problem und expected, und nur als Strings.

    Ein value oder sonst ein Schluessel wird nicht uebernommen -- auch dann
    nicht, wenn eine Antwort ihn entgegen dem Kontrakt traegt.
    """
    eintraege = dokument.get("errors")
    if not isinstance(eintraege, list):
        return ()
    return tuple(
        {k: e[k] for k in ("field", "problem", "expected") if isinstance(e.get(k), str)}
        for e in eintraege
        if isinstance(e, dict)
    )


def _retry_after(wert: str | None) -> float | None:
    """delay-seconds nach RFC 9110, sonst None.

    Ein HTTP-Datum schickt das Gateway nicht; es zaehlt wie ein fehlender
    Header. isascii() steht dabei, weil isdigit() auch '²' durchlaesst. Und
    400 Ziffern sind fuer isdigit() eine Zahl, fuer float() aber unendlich --
    eine Pause, die nie ablaeuft, zaehlt ebenfalls wie keine.
    """
    if wert is None:
        return None
    wert = wert.strip()
    if not (wert.isascii() and wert.isdigit()):
        return None
    zahl = float(wert)
    return zahl if math.isfinite(zahl) else None


class Sendepause:
    """R14: nach einem 429 geht nichts hinaus, bis die Pause abgelaufen ist.

    Die Zeit kommt als Argument -- api.py reicht time.monotonic(), die Tests
    reichen Zahlen. Die Pause lebt nur im Speicher: ein Neustart vergisst sie,
    und der naechste 429 setzt sie neu.

    Mit Header nennt der Server die Pause selbst; Zuplo schickt den Rest des
    laufenden Fensters. Verdoppelt wird deshalb nur ohne brauchbaren Header.
    """

    def __init__(self) -> None:
        self._bis: float | None = None
        self._folge = 0

    def rest(self, jetzt: float) -> float:
        """Sekunden bis zum Ende der Pause, 0 wenn frei."""
        if self._bis is None:
            return 0.0
        return max(0.0, self._bis - jetzt)

    def nach_429(self, retry_after: float | None, jetzt: float) -> float:
        """Setzt die Pause und gibt ihre Dauer zurueck."""
        self._folge += 1
        if retry_after is None:
            # Der Exponent ist gedeckelt: 60 * 2**10 liegt laengst ueber dem
            # Deckel, und ohne Grenze wuerde 2**n irgendwann zu gross fuer float.
            retry_after = min(PAUSE_BASIS_S * 2 ** min(self._folge - 1, 10), PAUSE_DECKEL_S)
        self._bis = jetzt + retry_after
        return retry_after

    def nach_erfolg(self) -> None:
        self._bis = None
        self._folge = 0


class PlanAbruf:
    """Was vor und nach dem Senden entschieden wird. Ohne Netz, ohne Home Assistant.

    Haelt die Sendepause aus R14. Ein PlanAbruf gehoert zu genau einem
    MeteoVoltApiClient, also zu einem Config-Entry und damit zu einem Key.
    Gleichzeitige Aufrufe haelt er nicht auseinander; das tut C5.
    """

    def __init__(self, api_url: str) -> None:
        self.url = _plan_url(api_url)
        self._pause = Sendepause()

    def vor_dem_senden(self, jetzt: float) -> None:
        """Wirft, wenn nicht gesendet werden darf. Sonst nichts."""
        if self.url is None:
            raise PlanAbgelehnt(
                detail=f"api_url endet nicht auf {PROGNOSE_PFAD}; "
                       "die Plan-URL ist nicht ableitbar")
        rest = self._pause.rest(jetzt)
        if rest > 0:
            raise PlanRateLimit(retry_after=rest, detail="Sendepause nach R14, nicht gesendet")

    def nach_antwort(
        self, status: int, retry_after: str | None, koerper: bytes, jetzt: float
    ) -> dict:
        """Eine 200 mit JSON-Objekt kommt unveraendert zurueck, alles andere wirft."""
        if status == 200:
            # Die erste 200 setzt zurueck, auch mit unbrauchbarem Koerper:
            # das Rate-Limit hat sie durchgelassen.
            self._pause.nach_erfolg()
            dokument = _json_objekt(koerper)
            if dokument is None:
                raise PlanNichtVerfuegbar(status=200, detail="Antwort ist kein JSON-Objekt")
            return dokument

        problem = _json_objekt(koerper) or {}
        felder = {
            "status": status,
            "titel": _text(problem, "title"),
            "detail": _text(problem, "detail"),
            "feldfehler": _feldfehler(problem),
        }
        if status == 429:
            dauer = self._pause.nach_429(_retry_after(retry_after), jetzt)
            raise PlanRateLimit(retry_after=dauer, **felder)
        if status in (401, 403):
            raise PlanNichtAutorisiert(**felder)
        if status >= 500:
            raise PlanNichtVerfuegbar(**felder)
        raise PlanAbgelehnt(**felder)
