"""Prueft die Verdrahtung von C6, C3 und C8 am Quelltext. Spec C6 Abschnitt 8, C3 Abschnitt 8, C8 Abschnitt 2.

__init__.py, sensor.py und binary_sensor.py importieren Home Assistant und
lassen sich hier nicht laden. Die Fehler, um die es geht, stehen aber im AST.
Was im Lauf passiert, sieht nur die Abnahme.
"""

import ast
from pathlib import Path

import pytest

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


# Die Module von C6, C3 und C8. Jedes andere Modul laedt sie nur im try.
C6 = {"ausgabe", "fahrzeugausgabe", "fahrzeugsensor", "fahrzeugbinaersensor"}
C3 = {"termine", "pruefungen", "terminbuch", "terminanfrage", "ansicht",
      "terminverwaltung", "aktionen", "terminwebsocket"}
C8 = {"panel"}


def _importe(knoten: ast.AST, im_try: bool = False):
    """Jeder Import, und ob der Rumpf eines try ihn umschliesst."""
    for feld, wert in ast.iter_fields(knoten):
        geschuetzt = im_try or (isinstance(knoten, ast.Try) and feld == "body")
        for kind in wert if isinstance(wert, list) else [wert]:
            if isinstance(kind, (ast.Import, ast.ImportFrom)):
                yield kind, geschuetzt
            elif isinstance(kind, ast.AST):
                yield from _importe(kind, geschuetzt)


def _laedt(knoten: ast.Import | ast.ImportFrom, gruppe: set[str]) -> bool:
    if not isinstance(knoten, ast.ImportFrom) or knoten.level != 1:
        return False
    if knoten.module is None:  # from . import ausgabe
        return any(alias.name in gruppe for alias in knoten.names)
    return knoten.module.split(".")[0] in gruppe


@pytest.mark.parametrize(("name", "gruppe"), [("C6", C6), ("C3", C3), ("C8", C8)])
def test_die_module_werden_ausserhalb_ihrer_gruppe_nur_im_try_importiert(name, gruppe):
    """Home Assistant 2026.4.1 importiert alle Plattformen, bevor es eine einrichtet.

    Ein Importfehler bricht dann das Einrichten des ganzen Eintrags ab, die
    sechs Sensoren der Prognose eingeschlossen. Im try steht er nur im Log.
    Fuer C3 verlangt das die C3-Spec Abschnitt 8 auch ohne Plattform, fuer
    das Panel die C8-Spec Abschnitt 2.
    """
    importe = [
        (f"{datei}:{knoten.lineno}", geschuetzt)
        for datei, baum in _module() if datei.removesuffix(".py") not in gruppe
        for knoten, geschuetzt in _importe(baum) if _laedt(knoten, gruppe)
    ]
    assert importe, f"kein Import von {name} gefunden; prueft der Test noch etwas?"
    assert [stelle for stelle, geschuetzt in importe if not geschuetzt] == []


# --- C9R: die Markierungen erreichen Request, Panel und Bereinigung ------------------------


def _methode(datei: str, name: str) -> ast.AST:
    baum = ast.parse((INTEGRATION / datei).read_text(encoding="utf-8"))
    return next(k for k in ast.walk(baum)
                if isinstance(k, (ast.FunctionDef, ast.AsyncFunctionDef)) and k.name == name)


def _ruft(methode: ast.AST, ziel: str) -> list[ast.Call]:
    return [k for k in ast.walk(methode) if isinstance(k, ast.Call)
            and isinstance(k.func, ast.Attribute) and k.func.attr == ziel]


def _traegt_ignoriert(aufruf: ast.Call) -> bool:
    return any(ast.unparse(arg) == "self.buch.ignoriert" for arg in aufruf.args)


@pytest.mark.parametrize(("methode", "ziel"), [("fragmente", "fragmente"), ("termine_im_fenster", "termine_ansicht")])
def test_die_ignorierten_termine_gehen_in_request_und_panel(methode, ziel):
    """C9R-Spec Abschnitte 2 und 5. Fehlt das Argument, ist der Knopf wirkungslos und kein Test rot."""
    aufrufe = _ruft(_methode("terminverwaltung.py", methode), ziel)
    assert aufrufe and all(_traegt_ignoriert(a) for a in aufrufe)


@pytest.mark.parametrize("methode", ["async_starten", "_nach_schritt"])
def test_start_und_jeder_schritt_bereinigen_die_markierungen(methode):
    """C9R-Spec Abschnitt 2: nach jedem Schritt, jedem Umschalten und beim Start."""
    assert _ruft(_methode("terminverwaltung.py", methode), "ignoriert_bereinigen")


def test_umschalten_laeuft_ueber_nach_schritt():
    """Speichern, Meldung an das Panel, Neuplanen und Bereinigen haengen an _nach_schritt."""
    assert _ruft(_methode("terminverwaltung.py", "async_ignorieren"), "_nach_schritt")


# --- C9Z: eine Heimkehr setzt dieselbe Markierung ---------------------------------------


def test_die_standorte_der_fahrzeuge_werden_beobachtet():
    """C9Z-Spec Abschnitt 8.2. Ohne sie im Abo meldet ein device_tracker nie eine Heimkehr."""
    quelle = ast.unparse(_methode("terminverwaltung.py", "_zustaende_bestellen"))
    assert "stammdaten.standorte_von(fahrzeuge)" in quelle
    assert "set(self._standorte)" in quelle


def test_ein_zustandswechsel_von_person_oder_standort_prueft_die_heimkehr():
    methode = _methode("terminverwaltung.py", "_zustand_geaendert")
    assert _ruft(methode, "heimgekehrt")
    quelle = ast.unparse(methode)
    assert "in self._personen" in quelle and "in self._standorte" in quelle


def test_die_heimkehr_geht_ueber_dieselbe_markierung_und_nach_schritt():
    methode = _methode("terminverwaltung.py", "_async_heimkehr")
    for ziel in ("heimkehr_von", "ignorieren", "_nach_schritt", "heimkehr_ereignisse", "async_fire"):
        assert _ruft(methode, ziel), ziel
    assert "self._standorte" in ast.unparse(_ruft(methode, "heimkehr_von")[0])
