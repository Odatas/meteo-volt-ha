"""Prueft das Panel: die Tests unter Node, Dateien, Ausrollen wie C3, Anmeldung. Spec C8 Abschnitt 11.

Die Logik des Panels ist JavaScript. Ihre Tests liegen unter tests/panel und
laufen mit node --test; dieser Test startet sie, damit sie im Gate stehen.
Fehlt Node oder ist es zu alt, scheitert er laut, statt gruen zu werden.

Was dieser Test NICHT sieht: Home Assistant. Ob das Panel angemeldet und
ausgeliefert wird, ob der Browser es laedt und wie es aussieht, zeigen die
Vorschau unter tests/panel/vorschau.html und die Abnahme.
"""

import importlib
import json
import re
import shutil
import subprocess
import sys
import types
from pathlib import Path
from zoneinfo import ZoneInfo

WURZEL = Path(__file__).resolve().parents[1]
INTEGRATION = WURZEL / "custom_components" / "meteo_volt"
FRONTEND = INTEGRATION / "frontend"
PANEL_TESTS = WURZEL / "tests" / "panel"
NODE_MINDESTENS = (22, 12)


def _node() -> str:
    node = shutil.which("node")
    assert node, "Node fehlt. Die Tests des Panels brauchen Node 22.12 oder neuer (https://nodejs.org)."
    version = subprocess.run([node, "--version"], capture_output=True, text=True, check=True).stdout.strip()
    teile = tuple(int(x) for x in version.lstrip("v").split(".")[:2])
    assert teile >= NODE_MINDESTENS, f"Node {version} ist zu alt, gebraucht wird 22.12 oder neuer."
    return node


def test_die_tests_des_panels_laufen_unter_node():
    dateien = sorted(str(pfad) for pfad in PANEL_TESTS.glob("*.test.mjs"))
    assert dateien, "keine Tests unter tests/panel; prueft der Test noch etwas?"
    lauf = subprocess.run(
        [_node(), "--test", "--test-reporter=tap", *dateien],
        capture_output=True, text=True, encoding="utf-8", cwd=WURZEL,
    )
    bericht = lauf.stdout + lauf.stderr
    assert lauf.returncode == 0, bericht[-6000:]
    anzahl = re.search(r"^# tests (\d+)$", lauf.stdout, re.MULTILINE)
    assert anzahl and int(anzahl.group(1)) > 0, bericht[-2000:]
    assert re.search(r"^# fail 0$", lauf.stdout, re.MULTILINE), bericht[-6000:]


def test_im_frontend_steht_nichts_aus_dem_netz():
    """Spec Abschnitt 3: keine Schrift, kein CDN, keine Bibliothek."""
    dateien = sorted(FRONTEND.glob("*.js"))
    assert dateien, "kein Modul unter frontend/; prueft der Test noch etwas?"
    for datei in dateien:
        assert not re.search(r"https?://", datei.read_text(encoding="utf-8")), datei.name
