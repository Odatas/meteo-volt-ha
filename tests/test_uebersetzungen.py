"""Prueft, dass jedes Subentry-Feld in beiden Sprachen beschriftet ist.

Ohne Home Assistant laesst sich am Config-Flow fast nichts pruefen. Das hier
geht: die Feldnamen stehen in stammdaten.py, die Beschriftungen in den
Sprachdateien, und ein Feld ohne Beschriftung erscheint dem Nutzer als roher
Schluessel.

Was dieser Test NICHT sieht: ob HA die Datei ueberhaupt laedt, ob
data_description gerendert wird und ob eine Beschriftung inhaltlich passt.
"""

import importlib.util
import json
from pathlib import Path

import pytest

WURZEL = Path(__file__).resolve().parents[1]
INTEGRATION = WURZEL / "custom_components" / "meteo_volt"
UEBERSETZUNGEN = INTEGRATION / "translations"

_SPEC = importlib.util.spec_from_file_location(
    "meteo_volt_stammdaten", INTEGRATION / "stammdaten.py")
stammdaten = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(stammdaten)

SPRACHEN = ("de", "en")


def _laden(sprache: str) -> dict:
    return json.loads((UEBERSETZUNGEN / f"{sprache}.json").read_text(encoding="utf-8"))


def _schluesselbaum(knoten, praefix: str = "") -> set[str]:
    """Alle Blattpfade eines verschachtelten dict."""
    pfade = set()
    for schluessel, wert in knoten.items():
        pfad = f"{praefix}.{schluessel}" if praefix else schluessel
        if isinstance(wert, dict):
            pfade |= _schluesselbaum(wert, pfad)
        else:
            pfade.add(pfad)
    return pfade


def test_beide_sprachdateien_sind_da():
    """Eigene Existenzpruefung: die parametrisierten Tests unten wuerden bei
    einer fehlenden Datei mit einem Fehler abbrechen, der nach Tippfehler im
    Test aussieht statt nach fehlender Uebersetzung."""
    for sprache in SPRACHEN:
        assert (UEBERSETZUNGEN / f"{sprache}.json").is_file(), sprache


@pytest.mark.parametrize("sprache", SPRACHEN)
@pytest.mark.parametrize(
    ("typ", "felder"),
    [
        (stammdaten.TYP_LADEPUNKT, stammdaten.LADEPUNKT_FELDER),
        (stammdaten.TYP_FAHRZEUG, stammdaten.FAHRZEUG_FELDER),
    ],
)
@pytest.mark.parametrize("schritt", ["user", "reconfigure"])
def test_jedes_feld_hat_eine_beschriftung(sprache, typ, felder, schritt):
    daten = _laden(sprache)["config_subentries"][typ]["step"][schritt]["data"]
    fehlend = sorted(set(felder) - set(daten))
    assert not fehlend, f"{sprache}/{typ}/{schritt}: ohne Beschriftung: {fehlend}"


@pytest.mark.parametrize("sprache", SPRACHEN)
@pytest.mark.parametrize(
    ("typ", "felder"),
    [
        (stammdaten.TYP_LADEPUNKT, stammdaten.LADEPUNKT_FELDER),
        (stammdaten.TYP_FAHRZEUG, stammdaten.FAHRZEUG_FELDER),
    ],
)
@pytest.mark.parametrize("schritt", ["user", "reconfigure"])
def test_keine_beschriftung_ohne_feld(sprache, typ, felder, schritt):
    """Die Gegenrichtung, und die stillere von beiden: ein umbenanntes Feld
    laesst seine alte Beschriftung stehen, wo sie nie wieder jemand sieht."""
    daten = _laden(sprache)["config_subentries"][typ]["step"][schritt]["data"]
    verwaist = sorted(set(daten) - set(felder))
    assert not verwaist, f"{sprache}/{typ}/{schritt}: ohne Feld: {verwaist}"


def test_der_battery_guard_hat_seinen_hinweis():
    """Abschnitt 4 der Spec: die Rolle des Guards soll sichtbar sein, nicht
    aus dem Verhalten erschlossen werden muessen."""
    for sprache in SPRACHEN:
        schritte = _laden(sprache)["config_subentries"][
            stammdaten.TYP_FAHRZEUG]["step"]
        for schritt in ("user", "reconfigure"):
            hinweise = schritte[schritt]["data_description"]
            assert stammdaten.FELD_SOC_MIN in hinweise, f"{sprache}/{schritt}"
            assert stammdaten.FELD_SOC_MAX in hinweise, f"{sprache}/{schritt}"


def test_beide_sprachen_haben_denselben_schluesselbaum():
    """Faengt den haeufigsten Fall: ein Schluessel wird in einer Sprache
    ergaenzt und in der anderen vergessen."""
    de = _schluesselbaum(_laden("de"))
    en = _schluesselbaum(_laden("en"))
    assert de == en, (
        f"nur de: {sorted(de - en)}; nur en: {sorted(en - de)}")
