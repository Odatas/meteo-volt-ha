"""Prueft das Laden von const_overwrite.json.

Bewusst schmal gehalten. Die echte Abnahme ist ein Lauf in einer
Home-Assistant-Umgebung; was hier steht, sind die Faelle, die sich ohne HA
ehrlich pruefen lassen -- echte Dateien, echte Funktion, keine Mocks.
"""

import ast
import importlib.util
import json
import logging
from pathlib import Path

import pytest

INTEGRATION = Path(__file__).resolve().parents[1] / "custom_components" / "meteo_volt"

# Per Pfad geladen, NICHT als custom_components.meteo_volt.overrides: das Paket
# zu importieren zieht dessen __init__.py und damit homeassistant herein, das in
# den Testabhaengigkeiten nicht steckt. Der Ladeweg ist zugleich die schaerfste
# Fassung der Auflage "overrides.py hat keine HA-Importe" -- bekaeme das Modul je
# einen, scheitert schon dieser Import.
_SPEC = importlib.util.spec_from_file_location(
    "meteo_volt_overrides", INTEGRATION / "overrides.py")
overrides = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(overrides)

DEV_URL = "https://dev.example/v1/prediction"


def _write(directory: Path, inhalt) -> None:
    (directory / overrides.OVERRIDE_FILE).write_text(
        inhalt if isinstance(inhalt, str) else json.dumps(inhalt),
        encoding="utf-8",
    )


def test_missing_file_yields_nothing_and_stays_quiet(tmp_path, caplog):
    """Der Normalfall bei jedem Nutzer. Eine Meldung bei jedem Start waere
    Rauschen -- und Rauschen, das man gewohnheitsmaessig uebergeht, macht die
    Warnungen unten wertlos."""
    with caplog.at_level(logging.DEBUG):
        assert overrides.load_overrides(tmp_path) == {}
    assert caplog.records == []


def test_valid_file_overrides_and_names_the_url(tmp_path, caplog):
    """Auch der Erfolgsfall wird protokolliert: der gefaehrliche Zustand ist
    nicht der Absturz, sondern die stille Annahme, man teste gegen Dev,
    waehrend Prod antwortet."""
    _write(tmp_path, {"api_url": DEV_URL})
    with caplog.at_level(logging.WARNING):
        assert overrides.load_overrides(tmp_path) == {"api_url": DEV_URL}
    assert any(DEV_URL in r.message for r in caplog.records)


@pytest.mark.parametrize("inhalt", [
    "{ das ist kein JSON",   # kaputt
    '["api_url"]',           # gueltiges JSON, aber kein Objekt
    "{}",                    # Objekt ohne den Schluessel
    '{"api_url": 42}',       # falscher Typ
    '{"api_url": "   "}',    # leer nach dem Trimmen
])
def test_unusable_content_falls_back_and_warns(tmp_path, caplog, inhalt):
    _write(tmp_path, inhalt)
    with caplog.at_level(logging.WARNING):
        assert overrides.load_overrides(tmp_path) == {}
    assert caplog.records, f"{inhalt!r} darf nicht lautlos durchgehen"


def test_unknown_key_is_named_and_valid_ones_survive(tmp_path, caplog):
    """Zweck dieser Warnung: ein Tippfehler wie api_ur wuerde sonst lautlos
    dazu fuehren, dass gegen Prod getestet wird."""
    _write(tmp_path, {"api_url": DEV_URL, "api_ur": "https://tippfehler"})
    with caplog.at_level(logging.WARNING):
        assert overrides.load_overrides(tmp_path) == {"api_url": DEV_URL}
    assert any("api_ur" in r.message for r in caplog.records)


# --- Verdrahtung: nicht ausfuehrbar, deshalb am Quelltext geprueft ---------
#
# api.py, __init__.py und config_flow.py importieren Home Assistant und lassen
# sich hier nicht laden. Der Fehlerfall, um den es geht, ist aber strukturell
# und am AST sichtbar: eine der beiden Aufrufstellen wird ergaenzt, die andere
# vergessen -- dann richtet der Config-Flow gegen die eine Umgebung ein,
# waehrend der Coordinator die andere pollt.

def test_every_client_construction_passes_an_api_url():
    gefunden = 0
    for pfad in sorted(INTEGRATION.glob("*.py")):
        baum = ast.parse(pfad.read_text(encoding="utf-8"))
        for k in ast.walk(baum):
            if not (isinstance(k, ast.Call) and isinstance(k.func, ast.Name)
                    and k.func.id == "MeteoVoltApiClient"):
                continue
            gefunden += 1
            assert "api_url" in {s.arg for s in k.keywords if s.arg}, (
                f"{pfad.name}:{k.lineno} baut MeteoVoltApiClient ohne api_url "
                "-- diese Stelle wuerde die Ueberschreibung ignorieren"
            )
    assert gefunden >= 2, (
        f"nur {gefunden} Konstruktion(en) gefunden; erwartet werden zwei "
        "(async_setup_entry und der Config-Flow)"
    )
