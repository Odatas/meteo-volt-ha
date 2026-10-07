# C7 Plan-Client und Fehlerabbildung — Umsetzungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `POST /v1/plan` im API-Client, mit vier Fehlerklassen nach Verhalten, der Sendepause aus R14 und einer temporären Dev-Action, mit der Patrick den Client auf seiner Instanz prüft.

**Architecture:** Alle Entscheidungen — Fehlerklasse, Sendepause, Plan-URL — liegen im neuen Modul `planabruf.py`, das weder Home Assistant noch aiohttp importiert, und sind gegen die vendorten Fehlerfixtures prüfbar. `api.py` bekommt nur den Aufruf `async_create_plan`. Die Dev-Action `meteo_volt.dev_plan` liegt in `dev.py` und wird nur registriert, wenn `const_overwrite.json` wirkt.

**Tech Stack:** Python 3.12 (Venv `.venv`), pytest + jsonschema. Zur Laufzeit Home Assistant 2026.4 und aiohttp — beide nicht in den Testabhängigkeiten.

**Spec:** `meteo-volt-brain/docs/features/C7-plan-client/spec.md`, Branch `c7-plan-client`. Bei Widerspruch gilt die Spec, nicht dieser Plan.

## Global Constraints

- **Branch** ist `c7-plan-client`, im ha-Repo und im Brain. Gemergt wird nach `beta`. **Niemals nach `master` oder `main`.**
- **Die Abnahme macht Patrick** auf seiner Instanz (Abschnitt „Abnahme"). Vorher ist C7 nicht fertig: kein Status `fertig`, kein Merge nach `beta`.
- **Python** ist `.venv/Scripts/python.exe`. Ein blankes `python` ist der Windows-Store-Alias. **Kein Venv-Update**, keine neue Testabhängigkeit.
- **`custom_components/` ist Endnutzer-Code.** HACS paketiert genau dieses Verzeichnis.
- **`planabruf.py` importiert nichts aus Home Assistant und nichts aus aiohttp.** Der Pfad-Import im Test ist die schärfste Fassung dieser Auflage.
- **`async_get_predictions` bleibt Zeichen für Zeichen, wie es ist.** `api.py` wird nur ergänzt (Bestandsschutz).
- **Verzweigt wird nur auf den Statuscode**, nie auf `type` (Spec Abschnitt 2).
- **Weder Request noch Antwortkörper gehen ins Log.** Keine Meldung nennt einen Wert aus dem Request.
- **Keine Entität, kein Gerät.** Das `unique_id`-Schema bleibt unberührt.
- **Die 35 Kontrakt-Artefakte werden nie von Hand geändert** — `tests/fixtures/contract/**` und `contract.lock.json`.
- **Zeilenenden LF am gestagten Blob.** Vor jedem Commit gibt `git diff --cached --name-only | while read f; do git show ":$f" | grep -q $'\r' && echo "CRLF: $f"; done` nichts aus.
- **Commit-Nachrichten** englisch, Imperativ, letzte Zeile `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- **Die Suite ist vor jedem Commit grün:** `.venv/Scripts/python.exe -m pytest -q`. Ausgangsstand: 109 bestandene Tests.

---

## Dateien

| Datei | Verantwortung |
|---|---|
| `custom_components/meteo_volt/planabruf.py` | **neu.** Fehlerklassen, Auswertung der Antwort, Plan-URL, Sendepause. |
| `custom_components/meteo_volt/api.py` | **ergänzt.** `async_create_plan`: Pause prüfen, senden, Antwort an `planabruf` geben. |
| `custom_components/meteo_volt/dev.py` | **neu, temporär.** Die Dev-Action mit festem Minimal-Request. |
| `custom_components/meteo_volt/services.yaml` | **neu, temporär.** Ein Eintrag für die Dev-Action. |
| `custom_components/meteo_volt/__init__.py` | **ergänzt.** Registriert die Dev-Action, wenn `const_overwrite.json` wirkt. |
| `custom_components/meteo_volt/manifest.json` | **geändert.** Version `1.1.0-beta.6`. |
| `tests/test_planabruf.py` | **neu.** Prüft `planabruf.py` gegen die sieben Fehlerfixtures. |

**Was der Gate nicht sieht:** den aiohttp-Aufruf, die Dev-Action und Home Assistant. `tests/test_overrides.py` parst jede `.py`-Datei der Integration und fängt damit Syntaxfehler, aber keine falschen Namen. Dafür gibt es in Task 3 und 4 je eine Einmal-Prüfung, und am Ende die Abnahme.

---

### Task 1: `planabruf.py` — Fehlerklassen, Auswertung, Plan-URL

**Files:**
- Create: `custom_components/meteo_volt/planabruf.py`
- Test: `tests/test_planabruf.py`

**Interfaces:**
- Consumes: `tests/fixtures/contract/errors/*.problem.json`, `tests/fixtures/contract/minimal.response.json`.
- Produces:
  - `PlanFehler(Exception)`, Konstruktor nur mit Schlüsselwörtern `status=None, titel=None, detail=None, feldfehler=()`; Attribute `status: int | None`, `titel: str | None`, `detail: str | None`, `feldfehler: tuple[dict, ...]`.
  - `PlanNichtAutorisiert`, `PlanAbgelehnt`, `PlanNichtVerfuegbar` — Unterklassen ohne Zusatz.
  - `PlanRateLimit(*, retry_after: float, **felder)` mit Attribut `retry_after: float`.
  - `PlanAbruf(api_url: str)` mit `url: str | None` und `nach_antwort(status: int, retry_after: str | None, koerper: bytes) -> dict`. Task 2 hängt `jetzt: float` als viertes Argument an.
  - Konstanten `PROGNOSE_PFAD`, `PLAN_PFAD`, `PAUSE_BASIS_S`.

- [ ] **Step 1: Den Test schreiben**

`tests/test_planabruf.py`:

```python
"""Prueft die Auswertung des Plan-Aufrufs gegen die vendorten Fehlerfixtures.

Die Fixtures zeigen den Wortlaut des Kontrakts, nicht immer die Form, in der
eine Antwort ankommt: 401 und 429 kommen aus Zuplos Policies, mit anderem
type und einem trace-Block. Deshalb laeuft jede Fixture ein zweites Mal in
Zuplos Form und muss dieselbe Klasse ergeben -- verzweigt wird nur auf den
Statuscode (B4-Spec Abschnitt 15).

Was dieser Test NICHT sieht: den aiohttp-Aufruf in api.py, die Dev-Action und
Home Assistant. Das deckt die Abnahme auf der Instanz.
"""

import importlib.util
import json
from pathlib import Path

import pytest

WURZEL = Path(__file__).resolve().parents[1]
INTEGRATION = WURZEL / "custom_components" / "meteo_volt"
CONTRACT = WURZEL / "tests" / "fixtures" / "contract"
FEHLER = CONTRACT / "errors"

# Per Pfad geladen, NICHT als custom_components.meteo_volt.planabruf: das
# Paket zu importieren zieht __init__.py und damit homeassistant herein, das
# in den Testabhaengigkeiten nicht steckt. Der Ladeweg ist zugleich die
# schaerfste Fassung der Auflage "planabruf.py importiert weder Home Assistant
# noch aiohttp" -- bekaeme das Modul einen solchen Import, scheitert schon das.
_SPEC = importlib.util.spec_from_file_location(
    "meteo_volt_planabruf", INTEGRATION / "planabruf.py")
planabruf = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(planabruf)

PROD_URL = "https://meteo-volt-main-55a1407.d2.zuplo.dev/v1/prediction"

# Welche Klasse jede Fehlerfixture ergibt (Spec Abschnitt 3).
ERWARTET = {
    "400_empty_window": planabruf.PlanAbgelehnt,
    "400_naive_timestamp": planabruf.PlanAbgelehnt,
    "400_reserved_id": planabruf.PlanAbgelehnt,
    "400_unknown_schema_version": planabruf.PlanAbgelehnt,
    "404_unknown_model": planabruf.PlanAbgelehnt,
    "429_rate_limited": planabruf.PlanRateLimit,
    "503_no_snapshot": planabruf.PlanNichtVerfuegbar,
}


def _dokument(name: str) -> dict:
    return json.loads((FEHLER / f"{name}.problem.json").read_text(encoding="utf-8"))


def _auswerten(status, antwort, retry_after=None, abruf=None):
    """antwort ist ein Dokument oder schon ein Koerper in Bytes."""
    abruf = abruf or planabruf.PlanAbruf(PROD_URL)
    koerper = antwort if isinstance(antwort, bytes) else json.dumps(antwort).encode("utf-8")
    return abruf.nach_antwort(status, retry_after, koerper)


def test_jede_fehlerfixture_hat_eine_erwartung():
    """Gegenrichtung zur Parametrisierung unten. Eine neue Fixture ohne
    Eintrag in ERWARTET liefe sonst lautlos an jedem Test vorbei, und ein
    leeres errors/ ergaebe null Tests und damit Gruen."""
    vorhanden = sorted(p.name.split(".")[0] for p in FEHLER.glob("*.problem.json"))
    assert vorhanden == sorted(ERWARTET)


@pytest.mark.parametrize("name", sorted(ERWARTET))
def test_fixture_ergibt_ihre_klasse(name):
    dokument = _dokument(name)
    # Passt der Status nicht zum Dateinamen, ist die Fixture kaputt, nicht der Code.
    assert dokument["status"] == int(name.split("_")[0])
    with pytest.raises(ERWARTET[name]) as info:
        _auswerten(dokument["status"], dokument)
    assert info.value.status == dokument["status"]
    assert info.value.titel == dokument["title"]


@pytest.mark.parametrize("name", sorted(ERWARTET))
def test_zuplos_form_ergibt_dieselbe_klasse(name):
    """Derselbe Status in Zuplos Namensraum, mit instance und trace und ohne
    detail -- so, wie ARCHITEKTUR.md die Antworten der Policies beschreibt."""
    status = _dokument(name)["status"]
    zuplo = {
        "type": f"https://httpproblems.com/http-status/{status}",
        "title": "Zuplo",
        "status": status,
        "instance": "/v1/plan",
        "trace": {"requestId": "r", "buildId": "b", "rayId": "c"},
    }
    with pytest.raises(ERWARTET[name]):
        _auswerten(status, zuplo)


@pytest.mark.parametrize("name", sorted(n for n in ERWARTET if n.startswith("400_")))
def test_400er_tragen_die_feldfehler_der_fixture(name):
    dokument = _dokument(name)
    with pytest.raises(planabruf.PlanAbgelehnt) as info:
        _auswerten(400, dokument)
    assert list(info.value.feldfehler) == dokument["errors"]
    assert dokument["errors"][0]["field"] in str(info.value)


@pytest.mark.parametrize("status", [401, 403])
def test_401_und_403_sind_nicht_autorisiert(status):
    zuplo = {
        "type": f"https://httpproblems.com/http-status/{status}",
        "title": "Authorization Failed",
        "status": status,
    }
    with pytest.raises(planabruf.PlanNichtAutorisiert):
        _auswerten(status, zuplo)


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_jeder_5xx_ist_nicht_verfuegbar(status):
    handler = {
        "type": "https://api.meteo-volt.de/problems/upstream-unavailable",
        "title": "Plan service unavailable",
        "status": status,
    }
    with pytest.raises(planabruf.PlanNichtVerfuegbar):
        _auswerten(status, handler)


@pytest.mark.parametrize("koerper", [
    b"", b"<html><body>Sign in</body></html>", b"[1, 2]", b"\xff\xfe\x00",
])
@pytest.mark.parametrize("status, klasse", [
    (403, planabruf.PlanNichtAutorisiert),
    (404, planabruf.PlanAbgelehnt),
    (502, planabruf.PlanNichtVerfuegbar),
])
def test_unlesbarer_koerper_ergibt_die_klasse_des_status(status, klasse, koerper):
    with pytest.raises(klasse) as info:
        _auswerten(status, koerper)
    assert info.value.status == status
    assert info.value.feldfehler == ()


def test_200_liefert_das_dokument_unveraendert():
    """Tolerant out: auch ein Feld, das der Client nicht kennt, bleibt stehen."""
    antwort = json.loads((CONTRACT / "minimal.response.json").read_text(encoding="utf-8"))
    antwort["ein_neues_feld"] = True
    assert _auswerten(200, antwort) == antwort


@pytest.mark.parametrize("koerper", [b"", b"<html></html>", b"[]", b"null"])
def test_200_ohne_json_objekt_ist_nicht_verfuegbar(koerper):
    with pytest.raises(planabruf.PlanNichtVerfuegbar) as info:
        _auswerten(200, koerper)
    assert info.value.status == 200


def test_429_nennt_die_zahl_aus_retry_after():
    with pytest.raises(planabruf.PlanRateLimit) as info:
        _auswerten(429, _dokument("429_rate_limited"), retry_after="39")
    assert info.value.retry_after == 39


@pytest.mark.parametrize("wert", [
    None, "", "abc", "-5", "1.5", "Wed, 21 Oct 2026 07:28:00 GMT", "²",
])
def test_429_ohne_brauchbaren_header_nennt_60_s(wert):
    with pytest.raises(planabruf.PlanRateLimit) as info:
        _auswerten(429, _dokument("429_rate_limited"), retry_after=wert)
    assert info.value.retry_after == 60


def test_ein_value_im_dokument_erreicht_die_meldung_nicht():
    """Basiskontrakt 3.7: nie den eingesandten Wert. Traegt eine Antwort ihn
    trotzdem, geht er weder in die Meldung noch in die Feldfehler."""
    dokument = _dokument("400_naive_timestamp")
    dokument["errors"][0]["value"] = "geheim-47-prozent"
    dokument["value"] = "geheim-fahrprofil"
    with pytest.raises(planabruf.PlanAbgelehnt) as info:
        _auswerten(400, dokument)
    assert "geheim" not in str(info.value)
    assert all(set(f) <= {"field", "problem", "expected"} for f in info.value.feldfehler)


@pytest.mark.parametrize("api_url, plan_url", [
    (PROD_URL, "https://meteo-volt-main-55a1407.d2.zuplo.dev/v1/plan"),
    ("https://dev.example/v1/prediction/", "https://dev.example/v1/plan"),
])
def test_plan_url_aus_api_url(api_url, plan_url):
    assert planabruf.PlanAbruf(api_url).url == plan_url


def test_nicht_ableitbare_url_ergibt_keine_plan_url():
    assert planabruf.PlanAbruf("http://localhost:8080/prognose").url is None


def test_alle_klassen_erben_von_planfehler():
    for klasse in (planabruf.PlanNichtAutorisiert, planabruf.PlanRateLimit,
                   planabruf.PlanAbgelehnt, planabruf.PlanNichtVerfuegbar):
        assert issubclass(klasse, planabruf.PlanFehler)
```

- [ ] **Step 2: Den Test laufen lassen, er muss scheitern**

Run: `.venv/Scripts/python.exe -m pytest tests/test_planabruf.py -q`
Expected: `ERROR tests/test_planabruf.py` mit `FileNotFoundError` für `planabruf.py`.

- [ ] **Step 3: `planabruf.py` schreiben**

`custom_components/meteo_volt/planabruf.py`:

```python
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

PROGNOSE_PFAD = "/v1/prediction"
PLAN_PFAD = "/v1/plan"

# Ohne brauchbaren Retry-After-Header gilt diese Pause (A0-Spec 3.9).
PAUSE_BASIS_S = 60.0


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
        return f"{super()._meldung()}; Pause {self.retry_after:.0f} s"


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
    except ValueError:  # faengt auch JSONDecodeError und UnicodeDecodeError
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
    Header. isascii() steht dabei, weil isdigit() auch '²' durchlaesst.
    """
    if wert is None:
        return None
    wert = wert.strip()
    if not (wert.isascii() and wert.isdigit()):
        return None
    return float(wert)


class PlanAbruf:
    """Was nach dem Senden entschieden wird. Ohne Netz, ohne Home Assistant."""

    def __init__(self, api_url: str) -> None:
        self.url = _plan_url(api_url)

    def nach_antwort(self, status: int, retry_after: str | None, koerper: bytes) -> dict:
        """Eine 200 mit JSON-Objekt kommt unveraendert zurueck, alles andere wirft."""
        if status == 200:
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
            dauer = _retry_after(retry_after)
            raise PlanRateLimit(retry_after=PAUSE_BASIS_S if dauer is None else dauer, **felder)
        if status in (401, 403):
            raise PlanNichtAutorisiert(**felder)
        if status >= 500:
            raise PlanNichtVerfuegbar(**felder)
        raise PlanAbgelehnt(**felder)
```

- [ ] **Step 4: Den Test laufen lassen**

Run: `.venv/Scripts/python.exe -m pytest tests/test_planabruf.py -q`
Expected: `55 passed`

- [ ] **Step 5: Suite und Commit**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: `164 passed`

```bash
git add custom_components/meteo_volt/planabruf.py tests/test_planabruf.py
git diff --cached --name-only | while read f; do git show ":$f" | grep -q $'\r' && echo "CRLF: $f"; done
git commit -F - <<'EOF'
Map every plan response to one of four behaviour classes

The client branches on the status code only: Zuplo's 401 and 429 carry
another type and a trace block, and the error fixtures show the contract's
wording, not what arrives. Bodies are read tolerantly, and no value from the
request reaches a message.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 2: `planabruf.py` — die Sendepause

**Files:**
- Modify: `custom_components/meteo_volt/planabruf.py`
- Test: `tests/test_planabruf.py`

**Interfaces:**
- Consumes: aus Task 1 `PlanAbruf`, `PlanRateLimit`, `PlanAbgelehnt`, `PAUSE_BASIS_S`, `_plan_url`, `_json_objekt`, `_text`, `_feldfehler`, `_retry_after`.
- Produces:
  - `PlanAbruf.vor_dem_senden(jetzt: float) -> None` — wirft `PlanAbgelehnt` ohne Plan-URL, `PlanRateLimit` mit `status=None` während der Pause.
  - `PlanAbruf.nach_antwort(status: int, retry_after: str | None, koerper: bytes, jetzt: float) -> dict`.
  - `Sendepause` mit `rest(jetzt) -> float`, `nach_429(retry_after, jetzt) -> float`, `nach_erfolg() -> None`.
  - Konstante `PAUSE_DECKEL_S = 900.0`.
  - `jetzt` ist ein monotoner Zeitpunkt in Sekunden; `api.py` reicht `time.monotonic()`.

- [ ] **Step 1: Die Tests schreiben**

In `tests/test_planabruf.py` den Helfer `_auswerten` ersetzen durch:

```python
def _auswerten(status, antwort, retry_after=None, abruf=None, jetzt=0.0):
    """antwort ist ein Dokument oder schon ein Koerper in Bytes."""
    abruf = abruf or planabruf.PlanAbruf(PROD_URL)
    koerper = antwort if isinstance(antwort, bytes) else json.dumps(antwort).encode("utf-8")
    return abruf.nach_antwort(status, retry_after, koerper, jetzt)
```

Ans Ende der Datei anhängen:

```python
# --- Die Sendepause (Spec Abschnitt 4) ---------------------------------------


def test_ohne_429_wird_gesendet():
    """Gegenprobe zu allem darunter: ein frischer Abruf sperrt nichts."""
    planabruf.PlanAbruf(PROD_URL).vor_dem_senden(0.0)


def test_retry_after_sperrt_genau_so_lange():
    abruf = planabruf.PlanAbruf(PROD_URL)
    with pytest.raises(planabruf.PlanRateLimit):
        _auswerten(429, _dokument("429_rate_limited"), retry_after="39",
                   abruf=abruf, jetzt=1000.0)

    with pytest.raises(planabruf.PlanRateLimit) as info:
        abruf.vor_dem_senden(1038.0)
    assert info.value.status is None  # nichts gesendet
    assert info.value.retry_after == pytest.approx(1.0)

    abruf.vor_dem_senden(1039.0)  # frei


def test_ohne_header_verdoppelt_bis_15_minuten():
    abruf = planabruf.PlanAbruf(PROD_URL)
    dauern = []
    for _ in range(7):
        with pytest.raises(planabruf.PlanRateLimit) as info:
            _auswerten(429, b"", abruf=abruf)
        dauern.append(info.value.retry_after)
    assert dauern == [60, 120, 240, 480, 900, 900, 900]


def test_andere_fehler_setzen_nicht_zurueck():
    """Nur eine 200 setzt zurueck. Ein 503 dazwischen laesst die Folge stehen."""
    abruf = planabruf.PlanAbruf(PROD_URL)
    with pytest.raises(planabruf.PlanRateLimit):
        _auswerten(429, b"", abruf=abruf)
    with pytest.raises(planabruf.PlanNichtVerfuegbar):
        _auswerten(503, _dokument("503_no_snapshot"), abruf=abruf)
    with pytest.raises(planabruf.PlanRateLimit) as info:
        _auswerten(429, b"", abruf=abruf)
    assert info.value.retry_after == 120


def test_eine_200_setzt_die_pause_zurueck():
    abruf = planabruf.PlanAbruf(PROD_URL)
    for _ in range(3):
        with pytest.raises(planabruf.PlanRateLimit):
            _auswerten(429, b"", abruf=abruf, jetzt=0.0)
    _auswerten(200, {"schema_version": 1}, abruf=abruf, jetzt=10.0)

    abruf.vor_dem_senden(10.0)  # frei, obwohl die Pause bis 240 s lief
    with pytest.raises(planabruf.PlanRateLimit) as info:
        _auswerten(429, b"", abruf=abruf, jetzt=10.0)
    assert info.value.retry_after == 60


def test_nicht_ableitbare_url_lehnt_vor_dem_senden_ab():
    abruf = planabruf.PlanAbruf("http://localhost:8080/prognose")
    with pytest.raises(planabruf.PlanAbgelehnt) as info:
        abruf.vor_dem_senden(0.0)
    assert info.value.status is None
```

- [ ] **Step 2: Die Tests laufen lassen, sie müssen scheitern**

Run: `.venv/Scripts/python.exe -m pytest tests/test_planabruf.py -q`
Expected: FAIL — `TypeError: PlanAbruf.nach_antwort() takes 4 positional arguments but 5 were given` und `AttributeError: 'PlanAbruf' object has no attribute 'vor_dem_senden'`.

- [ ] **Step 3: Die Sendepause bauen**

In `custom_components/meteo_volt/planabruf.py` den Konstantenblock

```python
# Ohne brauchbaren Retry-After-Header gilt diese Pause (A0-Spec 3.9).
PAUSE_BASIS_S = 60.0
```

ersetzen durch:

```python
# Ohne brauchbaren Retry-After-Header (A0-Spec 3.9): 60 s, verdoppelt mit
# jedem weiteren 429 seit der letzten 200, hoechstens 15 min.
PAUSE_BASIS_S = 60.0
PAUSE_DECKEL_S = 900.0
```

Die ganze Klasse `PlanAbruf` ersetzen durch:

```python
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
```

- [ ] **Step 4: Die Tests laufen lassen**

Run: `.venv/Scripts/python.exe -m pytest tests/test_planabruf.py -q`
Expected: `61 passed`

- [ ] **Step 5: Suite und Commit**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: `170 passed`

```bash
git add custom_components/meteo_volt/planabruf.py tests/test_planabruf.py
git diff --cached --name-only | while read f; do git show ":$f" | grep -q $'\r' && echo "CRLF: $f"; done
git commit -F - <<'EOF'
Hold the R14 send pause in the plan client

Retry-After when it is a whole number of seconds, otherwise 60 s doubled
with every 429 since the last 200, capped at 15 min. While the pause runs
nothing is sent, so no trigger can get past it.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 3: `api.py` — `async_create_plan`

**Files:**
- Modify: `custom_components/meteo_volt/api.py`

**Interfaces:**
- Consumes: aus Task 2 `PlanAbruf(api_url)` mit `url`, `vor_dem_senden(jetzt)`, `nach_antwort(status, retry_after, koerper, jetzt)`; `PlanNichtVerfuegbar(detail=...)`.
- Produces: `MeteoVoltApiClient.async_create_plan(hass: HomeAssistant, anfrage: dict[str, Any]) -> dict[str, Any]`, wirft `PlanFehler`. Die zugesagte Oberfläche für `C5` (Spec Abschnitt 6).

`async_get_predictions` wird **nicht** berührt. Drei gezielte Ersetzungen, keine neue Datei.

- [ ] **Step 1: Die Importe ergänzen**

Ersetzen:

```python
import logging
from typing import Any
```

durch:

```python
import logging
import time
from typing import Any
```

Ersetzen:

```python
from .const import API_URL

_LOGGER = logging.getLogger(__name__)
```

durch:

```python
from .const import API_URL
from .planabruf import PlanAbruf, PlanNichtVerfuegbar

_LOGGER = logging.getLogger(__name__)

# Spec C7 Abschnitt 5: das Gateway antwortet nach 10 s selbst mit 504. Diese
# 30 s greifen nur, wenn auch das Gateway nicht antwortet.
PLAN_TIMEOUT = aiohttp.ClientTimeout(total=30)
```

- [ ] **Step 2: Den Abruf im Konstruktor anlegen**

Ersetzen:

```python
        self._api_token = api_token
        self._api_url = api_url
```

durch:

```python
        self._api_token = api_token
        self._api_url = api_url
        # Plan-URL und Sendepause aus R14. Je Client, also je Config-Entry und
        # damit je Key -- siehe planabruf.py.
        self._plan = PlanAbruf(api_url)
```

- [ ] **Step 3: Die Methode anhängen**

Ersetzen:

```python
            data = await response.json()
            return data
```

durch:

```python
            data = await response.json()
            return data

    async def async_create_plan(
        self, hass: HomeAssistant, anfrage: dict[str, Any]
    ) -> dict[str, Any]:
        """POST /v1/plan. Liefert den Plan oder wirft einen PlanFehler.

        Hier wird nur geschickt. Was davor und danach entschieden wird --
        Sendepause, Plan-URL, Fehlerklasse -- steht in planabruf.py, weil es
        dort ohne Home Assistant pruefbar ist.

        Weder anfrage noch der Antwortkoerper gehen ins Log: dort stehen
        Ladestand und Fahrzeugdaten.
        """
        self._plan.vor_dem_senden(time.monotonic())

        session = async_get_clientsession(hass)
        headers = {
            "Authorization": f"Bearer {self._api_token}",
            "Accept": "application/json, application/problem+json",
        }
        try:
            async with session.post(
                self._plan.url,
                json=anfrage,
                headers=headers,
                timeout=PLAN_TIMEOUT,
                # Keine Weiterleitung: der Koerper traegt Ladestaende und geht
                # nur an die konfigurierte Adresse.
                allow_redirects=False,
            ) as response:
                status = response.status
                retry_after = response.headers.get("Retry-After")
                koerper = await response.read()
        except (aiohttp.ClientError, TimeoutError) as err:
            # Der Typ genuegt zur Diagnose und nennt keine Adresse.
            raise PlanNichtVerfuegbar(detail=type(err).__name__) from err

        return self._plan.nach_antwort(status, retry_after, koerper, time.monotonic())
```

- [ ] **Step 4: Einmal-Prüfung — die Namen aus `planabruf` gibt es**

Kein Test im Repo: `api.py` importiert Home Assistant und ist in der Suite nicht ladbar.

```bash
.venv/Scripts/python.exe - <<'EOF'
import ast, importlib.util
from pathlib import Path
paket = Path("custom_components/meteo_volt")
spec = importlib.util.spec_from_file_location("planabruf", paket / "planabruf.py")
planabruf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(planabruf)
for knoten in ast.walk(ast.parse((paket / "api.py").read_text(encoding="utf-8"))):
    if isinstance(knoten, ast.ImportFrom) and knoten.module == "planabruf":
        for name in knoten.names:
            assert hasattr(planabruf, name.name), f"api.py: {name.name} fehlt in planabruf.py"
print("api.py: Importe aus planabruf.py vorhanden")
EOF
```

Expected: `api.py: Importe aus planabruf.py vorhanden`

- [ ] **Step 5: `async_get_predictions` ist unberührt**

Run: `git diff -U0 custom_components/meteo_volt/api.py | grep -E "^-[^-]"`
Expected: keine Ausgabe — die Datei wird nur ergänzt, keine bestehende Zeile fällt weg.

- [ ] **Step 6: Suite und Commit**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: `170 passed` — `test_overrides.py` parst dabei `api.py`.

```bash
git add custom_components/meteo_volt/api.py
git diff --cached --name-only | while read f; do git show ":$f" | grep -q $'\r' && echo "CRLF: $f"; done
git commit -F - <<'EOF'
Add POST /v1/plan to the API client

api.py only sends. The pause, the plan URL and the error class come from
planabruf.py. The timeout sits above the gateway's own 10 s, redirects are
not followed, and nothing from either body reaches the log.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 4: Die Dev-Action

**Files:**
- Create: `custom_components/meteo_volt/dev.py`
- Create: `custom_components/meteo_volt/services.yaml`
- Modify: `custom_components/meteo_volt/__init__.py`

**Interfaces:**
- Consumes: aus Task 3 `MeteoVoltApiClient.async_create_plan(hass, anfrage)`; aus Task 1 `PlanFehler`; `hass.data[DOMAIN][entry_id]` ist der Koordinator mit Attribut `client` (`coordinator.py`); `load_overrides()` liefert `{}` ohne wirksame Überschreibung (`overrides.py`).
- Produces: die Action `meteo_volt.dev_plan` ohne Felder, `SupportsResponse.ONLY`. Temporär — Entfernen heißt `dev.py` und `services.yaml` löschen und den Aufruf in `__init__.py` streichen.

- [ ] **Step 1: `dev.py` schreiben**

`custom_components/meteo_volt/dev.py`:

```python
"""Temporaer: eine Action, die einen festen Plan-Request schickt.

Nur fuer die Entwicklung, und sie fliegt wieder raus: dann gehen diese Datei,
ihr Eintrag in services.yaml und der Aufruf in __init__.py. Registriert wird
sie nur, wenn const_overwrite.json wirkt (siehe overrides.py) -- ein normaler
Nutzer sieht sie nie.

Keine Felder, keine Uebersetzung, keine Entitaet. Die Antwort erscheint in den
Entwicklerwerkzeugen unter der Action, ein PlanFehler als Fehlermeldung.

Spec: meteo-volt-brain/docs/features/C7-plan-client/spec.md, Abschnitt 7
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .planabruf import PlanFehler

DEV_ACTION = "dev_plan"

# Der kleinste Request, der einen echten Plan ergibt: ein Ladepunkt, ein
# Fahrzeug daran angesteckt. Ohne now -- dann gilt die Serverzeit --, ohne
# model und ohne Constraints.
DEV_ANFRAGE = {
    "schema_version": 1,
    "stations": [{"id": "dev-wallbox", "max_power_kw": 11.0}],
    "vehicles": [
        {
            "id": "dev-auto",
            "capacity_kwh": 58.0,
            "soc_pct": 50.0,
            "max_charge_kw": 11.0,
            "efficiency_curve": [{"kw": 11.0, "eta": 0.92}],
            "soc_min_pct": 15.0,
            "soc_max_pct": 80.0,
            "consumption_kwh_per_100km": 19.5,
            "connection": {"station_id": "dev-wallbox"},
            "consumption": {"type": "none"},
        }
    ],
}


def async_dev_action_registrieren(hass: HomeAssistant) -> None:
    """Registriert meteo_volt.dev_plan, einmal je Home-Assistant-Lauf."""
    if hass.services.has_service(DOMAIN, DEV_ACTION):
        return

    async def _plan_holen(call: ServiceCall) -> ServiceResponse:
        koordinatoren = list(hass.data.get(DOMAIN, {}).values())
        if not koordinatoren:
            raise HomeAssistantError("Kein Meteo-Volt-Eintrag geladen")
        try:
            return await koordinatoren[0].client.async_create_plan(hass, DEV_ANFRAGE)
        except PlanFehler as err:
            raise HomeAssistantError(f"{type(err).__name__}: {err}") from err

    hass.services.async_register(
        DOMAIN, DEV_ACTION, _plan_holen, supports_response=SupportsResponse.ONLY
    )
```

- [ ] **Step 2: `services.yaml` schreiben**

`custom_components/meteo_volt/services.yaml`:

```yaml
# Temporaer. Gehoert zur Dev-Action in dev.py und geht mit ihr.
# Ohne diese Datei warnt Home Assistant bei jedem Laden der
# Action-Beschreibungen: "Unable to find services.yaml".
dev_plan:
  name: Dev-Plan
  description: Temporaer. Schickt einen festen Plan-Request und zeigt die Antwort.
```

- [ ] **Step 3: Die Action in `__init__.py` registrieren**

Ersetzen:

```python
from .coordinator import MeteoVoltDataUpdateCoordinator
```

durch:

```python
from .coordinator import MeteoVoltDataUpdateCoordinator
from .dev import async_dev_action_registrieren
```

Ersetzen:

```python
    hass.data[DOMAIN][entry.entry_id] = coordinator
```

durch:

```python
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Temporaer, Spec C7 Abschnitt 7: nur wenn const_overwrite.json wirkt.
    if overrides:
        async_dev_action_registrieren(hass)
```

- [ ] **Step 4: Einmal-Prüfung — Request kontraktkonform, Namen vorhanden**

```bash
.venv/Scripts/python.exe - <<'EOF'
import ast, importlib.util, json
from pathlib import Path
import jsonschema
paket = Path("custom_components/meteo_volt")
baum = ast.parse((paket / "dev.py").read_text(encoding="utf-8"))
anfrage = next(ast.literal_eval(k.value) for k in baum.body
               if isinstance(k, ast.Assign) and getattr(k.targets[0], "id", "") == "DEV_ANFRAGE")
schema = json.loads(Path("tests/fixtures/contract/plan-request.schema.json").read_text(encoding="utf-8"))
schema.pop("x-meteo-volt-contract", None)
jsonschema.validate(anfrage, schema)
spec = importlib.util.spec_from_file_location("planabruf", paket / "planabruf.py")
planabruf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(planabruf)
for datei in ("api.py", "dev.py"):
    for knoten in ast.walk(ast.parse((paket / datei).read_text(encoding="utf-8"))):
        if isinstance(knoten, ast.ImportFrom) and knoten.module == "planabruf":
            for name in knoten.names:
                assert hasattr(planabruf, name.name), f"{datei}: {name.name} fehlt"
print("DEV_ANFRAGE kontraktkonform, Importe vorhanden")
EOF
```

Expected: `DEV_ANFRAGE kontraktkonform, Importe vorhanden`

- [ ] **Step 5: Suite und Commit**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: `170 passed` — `test_overrides.py` parst dabei `dev.py` und `__init__.py`.

```bash
git add custom_components/meteo_volt/dev.py custom_components/meteo_volt/services.yaml custom_components/meteo_volt/__init__.py
git diff --cached --name-only | while read f; do git show ":$f" | grep -q $'\r' && echo "CRLF: $f"; done
git commit -F - <<'EOF'
Add a temporary dev action that sends a fixed plan request

meteo_volt.dev_plan exists only while const_overwrite.json takes effect, so
no user sees it. It lets the acceptance on the instance reach the real
gateway: a plan, a 429 with its Retry-After, the pause, a 404 where the
route is missing. It goes again later with its services.yaml entry and the
call in __init__.py.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 5: Die Beta

**Files:**
- Modify: `custom_components/meteo_volt/manifest.json`

**Interfaces:**
- Consumes: den Stand nach Task 4.
- Produces: den Prerelease `1.1.0-beta.6` auf dem Commit dieses Tasks.

Die Regeln stehen in `CLAUDE.md`, Abschnitt „Betas gehen über HACS". `gh` ist auf diesem Rechner nicht installiert — das Release entsteht in der GitHub-Oberfläche.

- [ ] **Step 1: Die Version setzen**

In `custom_components/meteo_volt/manifest.json` ersetzen:

```json
  "version": "1.1.0-beta.5"
```

durch:

```json
  "version": "1.1.0-beta.6"
```

- [ ] **Step 2: Suite, Kontrakt, Commit**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: `170 passed`

Run: `.venv/Scripts/python.exe scripts/check_contract.py`
Expected: `Kontrakt in sync (35 Dateien geprueft)`

```bash
git add custom_components/meteo_volt/manifest.json
git diff --cached --name-only | while read f; do git show ":$f" | grep -q $'\r' && echo "CRLF: $f"; done
git commit -F - <<'EOF'
Number this beta 1.1.0-beta.6

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

- [ ] **Step 3: Patrick fragen, dann pushen**

Erst nach seinem Ja:

```bash
git ls-remote origin refs/tags/1.1.0-beta.6
git push -u origin c7-plan-client
git rev-parse HEAD
```

Expected: die erste Zeile gibt nichts aus (der Tag ist neu), der Push geht durch, die letzte Zeile nennt den Commit für das Release.

- [ ] **Step 4: Patrick legt das Prerelease an**

In GitHub unter Releases: Tag `1.1.0-beta.6` — GitHub muss ihn als **neu** anzeigen. Target ist der Commit aus Step 3, gewählt unter „Recent commits". „Set as a pre-release" an, „Set as the latest release" aus.

- [ ] **Step 5: Nachmessen**

```bash
git fetch --tags origin
git ls-remote origin refs/tags/1.1.0-beta.6
git show 1.1.0-beta.6:custom_components/meteo_volt/manifest.json | grep '"version"'
```

Expected: der Tag zeigt auf den Commit aus Step 3, das Manifest im Tag nennt `1.1.0-beta.6`. Stimmt eins nicht: Release samt Tag löschen und neu anlegen, solange niemand die Version installiert hat.

---

## Abnahme — macht Patrick

Auf der eigenen Instanz, mit `1.1.0-beta.6`. Vorher ist C7 nicht fertig.

1. **Beta installieren.** In HACS „Repository-Informationen aktualisieren", `1.1.0-beta.6` herunterladen, Home Assistant neu starten. Ohne eingeschalteten `switch.<name>_pre_release` weist HACS nicht von selbst auf die Beta hin.
2. **Ohne `const_overwrite.json`:** Die Integration startet, die sechs Sensoren laufen. Unter Entwicklerwerkzeuge → Aktionen gibt es `meteo_volt.dev_plan` **nicht**.
3. **Überschreibung anlegen**, erst nach der Installation — ein HACS-Update kann das Verzeichnis ersetzen. Datei `custom_components/meteo_volt/const_overwrite.json` mit `{"api_url": "<Umgebung mit Plan-Route>/v1/prediction"}`, Home Assistant neu starten. Im Log steht `const_overwrite.json aktiv`.
4. **Plan holen:** Entwicklerwerkzeuge → Aktionen → `meteo_volt.dev_plan` → „Aktion ausführen". Die Antwort zeigt einen Plan mit `vehicles` und `slots`.
5. **Rate-Limit:** Die Action schnell hintereinander ausführen. Spätestens der vierte Aufruf binnen einer Minute meldet `PlanRateLimit: Status 429; …; Pause N s`. Ein Aufruf gleich danach meldet `PlanRateLimit: kein Status; Sendepause nach R14, nicht gesendet; Pause M s`, mit M kleiner als N. Nach Ablauf kommt wieder ein Plan.
6. **Fehlende Route:** `api_url` auf `https://meteo-volt-main-55a1407.d2.zuplo.dev/v1/prediction`, neu starten, Action ausführen: `PlanAbgelehnt: Status 404; Not Found`.
7. **Aufräumen:** `const_overwrite.json` löschen, neu starten. Die Action ist weg, die Sensoren laufen.

Gilt der Key in der Umgebung aus Schritt 3 nicht, meldet Schritt 4 `PlanNichtAutorisiert: Status 401`. Das ist dann ein Befund über den Key, nicht über den Client.

## Nach der Abnahme

Erst nach Patricks Ja:

- **Brain**, Branch `c7-plan-client`: in `docs/features/C7-plan-client/feature.md` `status = "spezifiziert"` auf `status = "fertig"`, dann `meteovolt_plan/.venv/Scripts/python.exe scripts/build_docs.py` und das Gate `meteovolt_plan/.venv/Scripts/python.exe scripts/run_tests.py -q`, Commit.
- **Beide Branches nach `beta` mergen**, im Brain und im ha-Repo, jeweils mit `--no-ff`. Pushen erst nach Rückfrage.

## Was dieser Plan nicht baut

| Nicht hier | Wo |
|---|---|
| Den Request aus Subentries bauen, Trigger, Umgang mit dem letzten Plan bei einem Fehler | `C5` |
| Entitäten und Anzeige des Plans | `C6` |
| Das Fehlerverhalten von `async_get_predictions` | bleibt, wie es ist |
| Basiskontrakt 3.7 ohne 500, 502, 504 und die 429-Fixture | `A5`, Punkt `A5E` |
