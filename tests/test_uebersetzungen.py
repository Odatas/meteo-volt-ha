"""Prueft, dass jedes Subentry-Feld dort beschriftet ist, wo HA nachsieht.

Ohne Home Assistant laesst sich am Config-Flow fast nichts pruefen. Das hier
geht: die Feldnamen und ihre Abschnitte stehen in stammdaten.py, die
Beschriftungen in den Sprachdateien, und ein Feld ohne Beschriftung erscheint
dem Nutzer als roher Schluessel.

**Der Pfad ist der Punkt.** Ein Feld in einer section sucht HA unter

    step.<schritt>.sections.<abschnitt>.data.<feld>

und nicht flach unter step.<schritt>.data. Die erste Fassung dieses Tests las
die flache Seite und wurde gruen, waehrend zehn von elf Fahrzeugfeldern in der
Oberflaeche als roher Schluessel gestanden haetten. Deshalb laeuft er jetzt
ueber LADEPUNKT_AUFBAU/FAHRZEUG_AUFBAU -- dieselbe Quelle, aus der auch das
Formular seine sections baut.

Beleg: home-assistant/frontend, src/dialogs/config-flow/show-dialog-config-flow.ts

    const prefix = options?.path?.[0] ? `sections.${options.path[0]}.` : "";

Was dieser Test NICHT sieht: ob HA die Datei ueberhaupt laedt, ob
data_description ueberhaupt gerendert wird, ob eine Beschriftung inhaltlich
passt, und ob das Formular die Abschnitte wirklich so baut wie der Aufbau es
vorgibt -- Letzteres kann nur die manuelle Abnahme.
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
SCHRITTE = ("user", "reconfigure")

TYPEN = (
    (stammdaten.TYP_LADEPUNKT, stammdaten.LADEPUNKT_AUFBAU),
    (stammdaten.TYP_FAHRZEUG, stammdaten.FAHRZEUG_AUFBAU),
)


def _laden(sprache: str) -> dict:
    return json.loads((UEBERSETZUNGEN / f"{sprache}.json").read_text(encoding="utf-8"))


def _schritt(sprache: str, typ: str, schritt: str) -> dict:
    return _laden(sprache)["config_subentries"][typ]["step"][schritt]


def _beschriftungen(schritt: dict, abschnitt: str | None, block: str) -> dict:
    """Der Block, in dem HA die Beschriftung eines Feldes sucht.

    block ist "data" oder "data_description". abschnitt None ist die oberste
    Ebene, dort ohne sections-Praefix.
    """
    if abschnitt is None:
        return schritt.get(block, {})
    return schritt.get("sections", {}).get(abschnitt, {}).get(block, {})


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


def test_der_aufbau_ist_nicht_leer():
    """Die Tests unten leiten alles aus dem Aufbau ab. Waere er leer, liefen
    sie ueber null Felder und blieben vakuos gruen."""
    assert len(stammdaten.LADEPUNKT_FELDER) >= 5
    assert len(stammdaten.FAHRZEUG_FELDER) >= 11


@pytest.mark.parametrize("sprache", SPRACHEN)
@pytest.mark.parametrize(("typ", "aufbau"), TYPEN)
@pytest.mark.parametrize("schritt", SCHRITTE)
def test_jedes_feld_ist_an_seinem_pfad_beschriftet(sprache, typ, aufbau, schritt):
    daten = _schritt(sprache, typ, schritt)
    fehlend = []
    for abschnitt, felder in aufbau.items():
        vorhanden = _beschriftungen(daten, abschnitt, "data")
        for feld in felder:
            if feld not in vorhanden:
                ort = "data" if abschnitt is None else f"sections.{abschnitt}.data"
                fehlend.append(f"{ort}.{feld}")
    assert not fehlend, f"{sprache}/{typ}/{schritt}: ohne Beschriftung: {fehlend}"


@pytest.mark.parametrize("sprache", SPRACHEN)
@pytest.mark.parametrize(("typ", "aufbau"), TYPEN)
@pytest.mark.parametrize("schritt", SCHRITTE)
def test_keine_beschriftung_ohne_feld(sprache, typ, aufbau, schritt):
    """Die Gegenrichtung, und die stillere von beiden: eine Beschriftung am
    falschen Pfad wird von HA nie gefunden und faellt sonst niemandem auf.
    Genau so lag die erste Fassung -- alle Felder flach, alle unsichtbar."""
    daten = _schritt(sprache, typ, schritt)
    verwaist = []
    for abschnitt, felder in aufbau.items():
        for block in ("data", "data_description"):
            vorhanden = _beschriftungen(daten, abschnitt, block)
            for schluessel in set(vorhanden) - set(felder):
                ort = block if abschnitt is None else f"sections.{abschnitt}.{block}"
                verwaist.append(f"{ort}.{schluessel}")
    assert not verwaist, f"{sprache}/{typ}/{schritt}: ohne Feld: {sorted(verwaist)}"


@pytest.mark.parametrize("sprache", SPRACHEN)
@pytest.mark.parametrize(("typ", "aufbau"), TYPEN)
@pytest.mark.parametrize("schritt", SCHRITTE)
def test_die_abschnitte_heissen_wie_im_aufbau(sprache, typ, aufbau, schritt):
    """Ein im Code umbenannter Abschnitt laesst HA seine Ueberschrift nicht
    mehr finden -- und mit ihr keine einzige Beschriftung darunter."""
    daten = _schritt(sprache, typ, schritt)
    erwartet = set(stammdaten.abschnitte_von(aufbau))
    vorhanden = set(daten.get("sections", {}))
    assert erwartet == vorhanden, (
        f"{sprache}/{typ}/{schritt}: nur im Aufbau: {sorted(erwartet - vorhanden)}; "
        f"nur in der Uebersetzung: {sorted(vorhanden - erwartet)}")


def test_der_battery_guard_hat_seinen_hinweis():
    """Abschnitt 4 der Spec: die Rolle des Guards soll sichtbar sein, nicht
    aus dem Verhalten erschlossen werden muessen. Der Hinweis unter
    soc_min_pct ist zugleich die Kostenwarnung."""
    for sprache in SPRACHEN:
        for schritt in SCHRITTE:
            daten = _schritt(sprache, stammdaten.TYP_FAHRZEUG, schritt)
            hinweise = _beschriftungen(
                daten, stammdaten.ABSCHNITT_GUARD, "data_description")
            assert stammdaten.FELD_SOC_MIN in hinweise, f"{sprache}/{schritt}"
            assert stammdaten.FELD_SOC_MAX in hinweise, f"{sprache}/{schritt}"


def test_beide_sprachen_haben_denselben_schluesselbaum():
    """Faengt den haeufigsten Fall: ein Schluessel wird in einer Sprache
    ergaenzt und in der anderen vergessen."""
    de = _schluesselbaum(_laden("de"))
    en = _schluesselbaum(_laden("en"))
    assert de == en, (
        f"nur de: {sorted(de - en)}; nur en: {sorted(en - de)}")
