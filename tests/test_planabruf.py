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

PROD_URL = "https://meteo-volt-main-ca19f82.zuplo.app/v1/prediction"

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


def _auswerten(status, antwort, retry_after=None, abruf=None, jetzt=0.0):
    """antwort ist ein Dokument oder schon ein Koerper in Bytes."""
    abruf = abruf or planabruf.PlanAbruf(PROD_URL)
    koerper = antwort if isinstance(antwort, bytes) else json.dumps(antwort).encode("utf-8")
    return abruf.nach_antwort(status, retry_after, koerper, jetzt)


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
    (PROD_URL, "https://meteo-volt-main-ca19f82.zuplo.app/v1/plan"),
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


# --- Nachtraege aus der Review -----------------------------------------------


def test_tief_verschachtelter_koerper_ergibt_die_klasse_des_status():
    """json.loads wirft bei tiefer Verschachtelung RecursionError, und das ist
    kein ValueError. Spec Abschnitt 8: nie eine andere Ausnahme."""
    with pytest.raises(planabruf.PlanNichtVerfuegbar):
        _auswerten(502, b"[" * 100000)
    with pytest.raises(planabruf.PlanNichtVerfuegbar):
        _auswerten(200, b"[" * 100000)


def test_die_meldung_rundet_die_restpause_auf():
    """Abnahmeschritt 5 liest diese Zahl. 0,4 s Rest sind noch gesperrt und
    duerfen nicht als 'Pause 0 s' erscheinen."""
    assert "Pause 1 s" in str(planabruf.PlanRateLimit(retry_after=0.4))


def test_ein_unendlicher_header_zaehlt_wie_keiner():
    """400 Ziffern sind fuer isdigit() eine Zahl und fuer float() unendlich.
    Eine Pause, die nie ablaeuft, ist keine -- also wie ein fehlender Header."""
    with pytest.raises(planabruf.PlanRateLimit) as info:
        _auswerten(429, b"", retry_after="9" * 400)
    assert info.value.retry_after == 60


def test_eine_200_ohne_json_setzt_die_pause_trotzdem_zurueck():
    abruf = planabruf.PlanAbruf(PROD_URL)
    with pytest.raises(planabruf.PlanRateLimit):
        _auswerten(429, b"", abruf=abruf, jetzt=0.0)
    with pytest.raises(planabruf.PlanNichtVerfuegbar):
        _auswerten(200, b"<html></html>", abruf=abruf, jetzt=1.0)

    abruf.vor_dem_senden(1.0)  # frei
    with pytest.raises(planabruf.PlanRateLimit) as info:
        _auswerten(429, b"", abruf=abruf, jetzt=1.0)
    assert info.value.retry_after == 60


def test_ein_429_mit_header_zaehlt_fuer_die_verdopplung_mit():
    """Spec Abschnitt 4: gezaehlt wird jeder 429, auch einer mit Header."""
    abruf = planabruf.PlanAbruf(PROD_URL)
    with pytest.raises(planabruf.PlanRateLimit) as info:
        _auswerten(429, b"", retry_after="39", abruf=abruf)
    assert info.value.retry_after == 39
    with pytest.raises(planabruf.PlanRateLimit) as info:
        _auswerten(429, b"", abruf=abruf)
    assert info.value.retry_after == 120


def test_die_verdoppelte_pause_sperrt_wirklich():
    """Die Verdopplung am Senden pruefen, nicht nur am Rueckgabewert."""
    abruf = planabruf.PlanAbruf(PROD_URL)
    for _ in range(2):
        with pytest.raises(planabruf.PlanRateLimit):
            _auswerten(429, b"", abruf=abruf, jetzt=0.0)
    with pytest.raises(planabruf.PlanRateLimit):
        abruf.vor_dem_senden(119.0)
    abruf.vor_dem_senden(120.0)  # frei
