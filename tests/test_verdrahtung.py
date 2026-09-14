"""Prueft die Verdrahtung von C6 am Quelltext. Spec C6 Abschnitt 8.

__init__.py, sensor.py und binary_sensor.py importieren Home Assistant und
lassen sich hier nicht laden. Die Fehler, um die es geht, stehen aber im AST.
Was im Lauf passiert, sieht nur die Abnahme.
"""

import ast
from pathlib import Path

INTEGRATION = Path(__file__).resolve().parents[1] / "custom_components" / "meteo_volt"


def _module() -> list[tuple[str, ast.Module]]:
    return [(pfad.name, ast.parse(pfad.read_text(encoding="utf-8")))
            for pfad in sorted(INTEGRATION.glob("*.py"))]


def test_kein_rueckruf_fuers_entladen_ist_eine_lambda():
    """Home Assistant 2026.4.1 macht aus jedem Rueckgabewert ausser None einen Task.

    Eine lambda gibt immer ihren Ausdruck zurueck. Ist der keine Coroutine,
    scheitert das Entladen, und nach dem Neuladen bleiben die sechs Sensoren
    bis zum Neustart nicht verfuegbar.
    """
    aufrufe, mit_lambda = 0, []
    for name, baum in _module():
        for knoten in ast.walk(baum):
            if not (isinstance(knoten, ast.Call) and isinstance(knoten.func, ast.Attribute)
                    and knoten.func.attr == "async_on_unload"):
                continue
            aufrufe += 1
            if any(isinstance(argument, ast.Lambda) for argument in knoten.args):
                mit_lambda.append(f"{name}:{knoten.lineno}")
    assert aufrufe, "kein Aufruf von async_on_unload gefunden; prueft der Test noch etwas?"
    assert mit_lambda == []
