"""Prueft, wie jede Fehlerart aus dem Kontrakt eingeordnet wird.

Je Art: die Klasse des Plan-Fehlers, die Reaktion der Prognose und der
Fehlerschluessel im Formular. Die Dokumente sind die vendorten Beispiele des
Fehlerformats, eines je Art. Dazu ein Koerper ohne Art und eine unbekannte Art:
dort zaehlt der Status wie bisher.

Was dieser Test NICHT sieht: Home Assistant selbst, also die Karte "Erneut
authentifizieren", den Hinweis zum Tarif und den Reauth-Dialog. Das deckt die
Abnahme auf der Instanz.
"""

import importlib.util
import json
from pathlib import Path

import jsonschema
import pytest

WURZEL = Path(__file__).resolve().parents[1]
INTEGRATION = WURZEL / "custom_components" / "meteo_volt"
Q1 = WURZEL / "tests" / "fixtures" / "contract" / "q1"

# Per Pfad geladen: das Paket zu importieren zoege Home Assistant herein.
_SPEC = importlib.util.spec_from_file_location(
    "meteo_volt_planabruf_arten", INTEGRATION / "planabruf.py")
planabruf = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(planabruf)

URL = "https://api.example/v1/prediction"

# Reaktion der Prognose: "reauth", "update_failed" oder None. None heisst: keine
# bekannte Art, die Prognose wirft wie bisher nach dem Status.
REAUTH, FEHLGESCHLAGEN = "reauth", "update_failed"
UNGUELTIG, GESPERRT, VERBINDUNG = "invalid_auth", "key_locked", "cannot_connect"

# Art -> (Plan-Klasse, Prognose, Formular). Formular None heisst: wie bisher
# nach dem Status, 401 und 403 sind invalid_auth.
ERWARTET = {
    "key-missing": (planabruf.PlanKeyAbgewiesen, REAUTH, UNGUELTIG),
    "key-invalid": (planabruf.PlanKeyAbgewiesen, REAUTH, UNGUELTIG),
    "key-locked": (planabruf.PlanKeyGesperrt, REAUTH, GESPERRT),
    "tier-not-allowed": (planabruf.PlanTarifErlaubtNicht, FEHLGESCHLAGEN, UNGUELTIG),
    "not-found": (planabruf.PlanAbgelehnt, FEHLGESCHLAGEN, VERBINDUNG),
    "invalid-request": (planabruf.PlanAbgelehnt, FEHLGESCHLAGEN, VERBINDUNG),
    "headers-too-large": (planabruf.PlanAbgelehnt, FEHLGESCHLAGEN, VERBINDUNG),
    "rate-limited": (planabruf.PlanRateLimit, FEHLGESCHLAGEN, VERBINDUNG),
    "unavailable": (planabruf.PlanNichtVerfuegbar, FEHLGESCHLAGEN, VERBINDUNG),
    "internal-error": (planabruf.PlanNichtVerfuegbar, FEHLGESCHLAGEN, VERBINDUNG),
    # Nur am Eingang Dashboard. Erreicht eine davon die Integration, zaehlt
    # der Status.
    "token-missing": (planabruf.PlanNichtAutorisiert, None, None),
    "token-expired": (planabruf.PlanNichtAutorisiert, None, None),
    "token-invalid": (planabruf.PlanNichtAutorisiert, None, None),
    "reauth-required": (planabruf.PlanNichtAutorisiert, None, None),
    "email-unverified": (planabruf.PlanNichtAutorisiert, None, None),
    "limit-reached": (planabruf.PlanAbgelehnt, None, None),
}


def _dokument(art: str) -> dict:
    return json.loads((Q1 / f"{art}.problem.json").read_text(encoding="utf-8"))


def _plan(status: int, koerper: bytes, anfrage_id: str | None = None):
    abruf = planabruf.PlanAbruf(URL)
    return abruf.nach_antwort(status, None, koerper, 0.0, anfrage_id=anfrage_id)


def _prognose(fehler) -> str | None:
    if fehler is None:
        return None
    return REAUTH if fehler.key_abgewiesen else FEHLGESCHLAGEN


def test_jede_art_hat_ein_beispiel_und_eine_erwartung():
    """Eine neue Art im Kontrakt faellt hier auf, bevor sie lautlos am Status landet."""
    vorhanden = sorted(p.name.removesuffix(".problem.json") for p in Q1.glob("*.problem.json"))
    assert vorhanden == sorted(ERWARTET)


@pytest.mark.parametrize("art", sorted(ERWARTET))
def test_beispiel_passt_zum_schema(art):
    schema = json.loads((Q1 / "problem.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(_dokument(art), schema)


@pytest.mark.parametrize("art", sorted(ERWARTET))
def test_plan_klasse_je_art(art):
    dokument = _dokument(art)
    klasse = ERWARTET[art][0]
    with pytest.raises(planabruf.PlanFehler) as info:
        _plan(dokument["status"], json.dumps(dokument).encode(), anfrage_id="abc-123")
    assert type(info.value) is klasse
    assert info.value.art == art
    # Die Meldung im Log nennt Art, Status und Anfrage-ID.
    assert f"Art {art}" in str(info.value)
    assert f"Status {dokument['status']}" in str(info.value)
    assert "Anfrage-ID abc-123" in str(info.value)


@pytest.mark.parametrize("art", sorted(ERWARTET))
def test_prognose_je_art(art):
    dokument = _dokument(art)
    fehler = planabruf.prognose_fehler(
        dokument["status"], json.dumps(dokument).encode(), "abc-123")
    assert _prognose(fehler) == ERWARTET[art][1]
    if fehler is not None:
        assert "Anfrage-ID abc-123" in str(fehler)


@pytest.mark.parametrize("art", sorted(a for a, e in ERWARTET.items() if e[2] is not None))
def test_formular_je_art(art):
    dokument = _dokument(art)
    fehler = planabruf.prognose_fehler(dokument["status"], json.dumps(dokument).encode())
    assert planabruf.flow_fehler(fehler.klasse) == ERWARTET[art][2]


# --- Ohne Art oder mit unbekannter Art: der Status, wie bisher ---------------


def _zuplo(status: int) -> bytes:
    return json.dumps({
        "type": f"https://httpproblems.com/http-status/{status}",
        "title": "Zuplo", "status": status,
    }).encode()


def _unbekannt(status: int) -> bytes:
    return json.dumps({
        "type": "https://api.meteo-volt.de/problems/quota-exhausted",
        "title": "Neu", "status": status, "detail": "d",
    }).encode()


@pytest.mark.parametrize("koerper", [_zuplo, _unbekannt, lambda _s: b"Payload Too Large"],
                         ids=["zuplo", "unbekannte-art", "klartext"])
@pytest.mark.parametrize("status, klasse", [
    (401, planabruf.PlanNichtAutorisiert),
    (403, planabruf.PlanNichtAutorisiert),
    (404, planabruf.PlanAbgelehnt),
    (413, planabruf.PlanAbgelehnt),
    (429, planabruf.PlanRateLimit),
    (503, planabruf.PlanNichtVerfuegbar),
])
def test_ohne_bekannte_art_zaehlt_der_status(status, klasse, koerper):
    with pytest.raises(planabruf.PlanFehler) as info:
        _plan(status, koerper(status))
    assert type(info.value) is klasse
    assert planabruf.prognose_fehler(status, koerper(status)) is None


@pytest.mark.parametrize("status, schluessel", [
    (401, UNGUELTIG), (403, UNGUELTIG), (404, VERBINDUNG), (413, VERBINDUNG),
    (429, VERBINDUNG), (500, VERBINDUNG),
])
def test_formular_nach_status_wie_bisher(status, schluessel):
    assert planabruf.flow_fehler(planabruf.nach_status(status)) == schluessel


@pytest.mark.parametrize("typ", [
    "https://api.meteo-volt.de/problems/",
    "https://api.meteo-volt.de/problems/Key-Locked",
    "https://api.meteo-volt.de/problems/key-locked/x",
    "https://evil.example/problems/key-locked",
    "http://api.meteo-volt.de/problems/key-locked",
])
def test_nur_eine_saubere_art_unter_unserem_namensraum_zaehlt(typ):
    assert planabruf.art_lesen({"type": typ}) is None


def test_art_bei_falschem_status_entscheidet_die_art():
    """Die Art benennt die Ursache; der Status ist nur der passende nach HTTP."""
    dokument = _dokument("key-locked")
    with pytest.raises(planabruf.PlanKeyGesperrt):
        _plan(401, json.dumps(dokument).encode())


def test_rate_limited_setzt_die_sendepause():
    abruf = planabruf.PlanAbruf(URL)
    with pytest.raises(planabruf.PlanRateLimit):
        abruf.nach_antwort(
            429, "30", json.dumps(_dokument("rate-limited")).encode(), 0.0)
    with pytest.raises(planabruf.PlanRateLimit) as info:
        abruf.vor_dem_senden(10.0)
    assert info.value.retry_after == 20
