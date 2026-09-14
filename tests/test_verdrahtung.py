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


# Die Module von C6. Jedes andere Modul laedt sie nur im try.
C6 = {"ausgabe", "fahrzeugausgabe", "fahrzeugsensor", "fahrzeugbinaersensor"}


def _importe(knoten: ast.AST, im_try: bool = False):
    """Jeder Import, und ob der Rumpf eines try ihn umschliesst."""
    for feld, wert in ast.iter_fields(knoten):
        geschuetzt = im_try or (isinstance(knoten, ast.Try) and feld == "body")
        for kind in wert if isinstance(wert, list) else [wert]:
            if isinstance(kind, (ast.Import, ast.ImportFrom)):
                yield kind, geschuetzt
            elif isinstance(kind, ast.AST):
                yield from _importe(kind, geschuetzt)


def _laedt_c6(knoten: ast.Import | ast.ImportFrom) -> bool:
    if not isinstance(knoten, ast.ImportFrom) or knoten.level != 1:
        return False
    if knoten.module is None:  # from . import ausgabe
        return any(alias.name in C6 for alias in knoten.names)
    return knoten.module.split(".")[0] in C6


def test_c6_wird_ausserhalb_von_c6_nur_im_try_importiert():
    """Home Assistant 2026.4.1 importiert alle Plattformen, bevor es eine einrichtet.

    Ein Importfehler bricht dann das Einrichten des ganzen Eintrags ab, die
    sechs Sensoren der Prognose eingeschlossen. Im try steht er nur im Log.
    """
    importe = [
        (f"{name}:{knoten.lineno}", geschuetzt)
        for name, baum in _module() if name.removesuffix(".py") not in C6
        for knoten, geschuetzt in _importe(baum) if _laedt_c6(knoten)
    ]
    assert importe, "kein Import von C6 gefunden; prueft der Test noch etwas?"
    assert [stelle for stelle, geschuetzt in importe if not geschuetzt] == []
