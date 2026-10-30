"""Der Plan-Aufruf ohne Home Assistant.

Dieses Modul importiert bewusst NICHTS aus Home Assistant und nichts aus
aiohttp -- wie stammdaten.py. Beides steckt nicht in den Testabhaengigkeiten.
api.py schickt ab und reicht Status, Retry-After und Koerper herein; was
davor und danach entschieden wird, steht hier und ist gegen die vendorten
Fehlerfixtures pruefbar.

Verzweigt wird nach der Fehlerart, dem letzten Teil von `type` unter
PROBLEM_BASE. Ohne Art oder bei einer unbekannten zaehlt der Statuscode: Zuplo
antwortet mit Typen aus httpproblems.com, und eine neue Art greift erst, wenn
sie hier eingetragen ist. Fehlerkoerper werden deshalb tolerant gelesen.

Dieselbe Einordnung gilt fuer die Prognose und den Config-Flow
(prognose_fehler, flow_fehler).

Die Klassen sagen, was zu tun ist, nicht warum. Ein 404 kann ein unbekanntes
Modell sein oder eine Gateway-Umgebung ohne Plan-Route.

Spec: meteo-volt-brain/docs/features/C7-plan-client/spec.md
"""

from __future__ import annotations

import json
import math

PROGNOSE_PFAD = "/v1/prediction"
PLAN_PFAD = "/v1/plan"

PROBLEM_BASE = "https://api.meteo-volt.de/problems/"
HEADER_ANFRAGE_ID = "X-Request-Id"

# Die Klassen der Einordnung. Was jede ausloest, steht bei ihren Nutzern:
# PlanAbruf.nach_antwort, prognose_fehler, flow_fehler.
KEY_ABGEWIESEN = "key_abgewiesen"
KEY_GESPERRT = "key_gesperrt"
# Nur nach Status: 401 oder 403 ohne bekannte Art.
NICHT_AUTORISIERT = "nicht_autorisiert"
TARIF = "tarif"
ABGELEHNT = "abgelehnt"
RATE_LIMIT = "rate_limit"
NICHT_VERFUEGBAR = "nicht_verfuegbar"

# Die Arten, die diese Integration kennt. Arten, die nur das Dashboard
# bekommt (token-*, reauth-required, email-unverified, limit-reached), fehlen
# mit Absicht: Erreicht eine davon die Integration, zaehlt der Status.
ARTEN = {
    "key-missing": KEY_ABGEWIESEN,
    "key-invalid": KEY_ABGEWIESEN,
    "key-locked": KEY_GESPERRT,
    "tier-not-allowed": TARIF,
    "not-found": ABGELEHNT,
    "invalid-request": ABGELEHNT,
    "headers-too-large": ABGELEHNT,
    "rate-limited": RATE_LIMIT,
    "unavailable": NICHT_VERFUEGBAR,
    "internal-error": NICHT_VERFUEGBAR,
}

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
        art: str | None = None,
        anfrage_id: str | None = None,
    ) -> None:
        self.status = status
        self.titel = titel
        self.detail = detail
        self.feldfehler = tuple(feldfehler)
        self.art = art
        self.anfrage_id = anfrage_id
        super().__init__(self._meldung())

    def _meldung(self) -> str:
        teile = [f"Status {self.status}" if self.status is not None else "kein Status"]
        if self.art:
            teile.append(f"Art {self.art}")
        if self.anfrage_id:
            teile.append(f"Anfrage-ID {self.anfrage_id}")
        teile += [text for text in (self.titel, self.detail) if text]
        teile += [
            f"{f.get('field', '?')}: {f.get('problem', '?')} "
            f"(erwartet: {f.get('expected', '?')})"
            for f in self.feldfehler
        ]
        return "; ".join(teile)


class PlanNichtAutorisiert(PlanFehler):
    """401, 403. Der Key gilt nicht; ohne den Nutzer aendert sich nichts."""


class PlanKeyAbgewiesen(PlanNichtAutorisiert):
    """Das Gateway nennt den Key fehlend oder ungueltig. Der Nutzer traegt einen neuen ein."""


class PlanKeyGesperrt(PlanKeyAbgewiesen):
    """Den Key gibt es, er ist gesperrt."""


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


class PlanTarifErlaubtNicht(PlanAbgelehnt):
    """Der Tarif hat keinen Ladeplan, oder es sind mehr Fahrzeuge angelegt, als er erlaubt.

    Ein Upgrade aendert den Key nicht. Der naechste Herzschlag holt den Plan dann
    ohne Zutun.
    """


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


def art_lesen(dokument: dict) -> str | None:
    """Die Art aus `type`, oder None. Wirft nie.

    Nur unter PROBLEM_BASE; Zuplos Typen aus httpproblems.com haben keine Art.
    """
    typ = _text(dokument, "type")
    if typ is None or not typ.startswith(PROBLEM_BASE):
        return None
    art = typ[len(PROBLEM_BASE):]
    return art if art and art.isascii() and all(
        z.islower() or z.isdigit() or z == "-" for z in art) else None


def nach_status(status: int) -> str:
    """Die Klasse ohne bekannte Art."""
    if status in (401, 403):
        return NICHT_AUTORISIERT
    if status == 429:
        return RATE_LIMIT
    if status >= 500:
        return NICHT_VERFUEGBAR
    return ABGELEHNT


def einordnen(status: int, art: str | None) -> str:
    """Die bekannte Art entscheidet, sonst der Status."""
    return ARTEN.get(art or "") or nach_status(status)


class PrognoseFehler(Exception):
    """Die Prognose wurde mit einer bekannten Art abgewiesen.

    Ohne bekannte Art wirft die Prognose wie bisher; diese Klasse gibt es nur,
    wenn die Art etwas anderes verlangt als der Status allein.
    """

    def __init__(
        self, *, klasse: str, status: int, art: str, anfrage_id: str | None = None
    ) -> None:
        self.klasse = klasse
        self.status = status
        self.art = art
        self.anfrage_id = anfrage_id
        teile = [f"Status {status}", f"Art {art}"]
        if anfrage_id:
            teile.append(f"Anfrage-ID {anfrage_id}")
        super().__init__("; ".join(teile))

    @property
    def key_abgewiesen(self) -> bool:
        """Home Assistant soll erneut authentifizieren lassen."""
        return self.klasse in (KEY_ABGEWIESEN, KEY_GESPERRT)


def prognose_fehler(
    status: int, koerper: bytes, anfrage_id: str | None = None
) -> PrognoseFehler | None:
    """Der Fehler einer Prognose-Antwort mit bekannter Art, sonst None."""
    art = art_lesen(_json_objekt(koerper) or {})
    if art not in ARTEN:
        return None
    return PrognoseFehler(
        klasse=ARTEN[art], status=status, art=art, anfrage_id=anfrage_id)


# Einrichten, Neu konfigurieren, Reauth: der Fehlerschluessel im Formular.
FLOW_UNGUELTIG = "invalid_auth"
FLOW_GESPERRT = "key_locked"
FLOW_VERBINDUNG = "cannot_connect"


def flow_fehler(klasse: str) -> str:
    """Der Fehlerschluessel des Formulars fuer eine Klasse."""
    if klasse == KEY_GESPERRT:
        return FLOW_GESPERRT
    if klasse in (KEY_ABGEWIESEN, NICHT_AUTORISIERT, TARIF):
        return FLOW_UNGUELTIG
    return FLOW_VERBINDUNG


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
        self, status: int, retry_after: str | None, koerper: bytes, jetzt: float,
        anfrage_id: str | None = None,
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
        art = art_lesen(problem)
        felder = {
            "status": status,
            "titel": _text(problem, "title"),
            "detail": _text(problem, "detail"),
            "feldfehler": _feldfehler(problem),
            "art": art,
            "anfrage_id": anfrage_id,
        }
        klasse = einordnen(status, art)
        if klasse == RATE_LIMIT:
            dauer = self._pause.nach_429(_retry_after(retry_after), jetzt)
            raise PlanRateLimit(retry_after=dauer, **felder)
        raise _PLAN_KLASSEN[klasse](**felder)


_PLAN_KLASSEN: dict[str, type[PlanFehler]] = {
    KEY_ABGEWIESEN: PlanKeyAbgewiesen,
    KEY_GESPERRT: PlanKeyGesperrt,
    NICHT_AUTORISIERT: PlanNichtAutorisiert,
    TARIF: PlanTarifErlaubtNicht,
    ABGELEHNT: PlanAbgelehnt,
    NICHT_VERFUEGBAR: PlanNichtVerfuegbar,
}
