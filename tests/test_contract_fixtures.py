"""Prueft die vendorten Kontrakt-Fixtures gegen die vendorten Schemas.

Faengt eine halbfertige Kopie, auch ohne Brain-Checkout. Der volle
Drift-Vergleich gegen den Brain-Stand steht in
meteo-volt-brain/scripts/check_contract_drift.py.
"""

import json
from pathlib import Path

import jsonschema
import pytest

CONTRACT = Path(__file__).parent / "fixtures" / "contract"


def _load(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in payload.items() if k != "x-meteo-volt-contract"}


REQUEST_SCHEMA = _load(CONTRACT / "plan-request.schema.json")
RESPONSE_SCHEMA = _load(CONTRACT / "plan-response.schema.json")
ERROR_SCHEMA = _load(CONTRACT / "plan-error.schema.json")


def _names() -> list[str]:
    return sorted(p.name.split(".")[0] for p in CONTRACT.glob("*.request.json"))


def _error_paths() -> list[Path]:
    return sorted((CONTRACT / "errors").glob("*.problem.json"))


def test_fixtures_were_vendored():
    assert _names(), "keine Fixtures gefunden; export_contract.py --to-ha ausfuehren"


def test_error_fixtures_were_vendored():
    """Eigene Existenzpruefung: die parametrisierten Error-Tests unten wuerden
    bei einem leeren errors/-Verzeichnis sonst lautlos null Tests sammeln
    und damit vakuos gruen bleiben, statt den Ausfall zu melden."""
    assert _error_paths(), "keine Error-Fixtures gefunden; errors/ fehlt oder ist leer"


@pytest.mark.parametrize("name", _names())
def test_request_matches_schema(name):
    jsonschema.validate(_load(CONTRACT / f"{name}.request.json"), REQUEST_SCHEMA)


@pytest.mark.parametrize("name", _names())
def test_response_matches_schema(name):
    jsonschema.validate(_load(CONTRACT / f"{name}.response.json"), RESPONSE_SCHEMA)


@pytest.mark.parametrize("path", _error_paths(), ids=lambda p: p.name)
def test_error_matches_schema(path):
    jsonschema.validate(_load(path), ERROR_SCHEMA)


def test_mock_can_answer_every_request():
    """Der Mock-Server aus C5 paart Request und Response ueber den Namen."""
    for name in _names():
        assert (CONTRACT / f"{name}.response.json").exists(), name


def test_no_response_without_a_request():
    """Gegenrichtung zu oben, und die wichtigere von beiden.

    Saemtliche Tests hier leiten ihre Namensliste aus den *.request.json ab.
    Eine Response ohne zugehoerigen Request wuerde deshalb von keinem einzigen
    Test angefasst: nie gegen das Schema geprueft, nie als fehlend gemeldet.
    Sie kaeme lautlos mit und wuerde erst auffallen, wenn jemand den
    Mock-Server damit fuettert.
    """
    orphans = sorted(
        p.name
        for p in CONTRACT.glob("*.response.json")
        if not (CONTRACT / f"{p.name.split('.')[0]}.request.json").exists()
    )
    assert not orphans, f"Response ohne Request: {orphans}"


def test_every_error_case_has_both_halves():
    """Gleiche Paarung eine Ebene tiefer, in beide Richtungen."""
    errors = CONTRACT / "errors"
    problems = {p.name.split(".")[0] for p in errors.glob("*.problem.json")}
    requests = {p.name.split(".")[0] for p in errors.glob("*.request.json")}
    assert problems == requests, (
        f"nur .problem.json: {sorted(problems - requests)}; "
        f"nur .request.json: {sorted(requests - problems)}"
    )
