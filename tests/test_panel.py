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


# --- Die Module ohne Home Assistant ------------------------------------------------------

# Geladen ueber ein Paket, dessen __init__.py NICHT laeuft -- die zieht homeassistant
# herein. termine.py und panel.py importieren Home Assistant nicht beim Laden.
_PAKET = "meteo_volt_c3"


def _modul(name: str):
    if _PAKET not in sys.modules:
        paket = types.ModuleType(_PAKET)
        paket.__path__ = [str(INTEGRATION)]
        sys.modules[_PAKET] = paket
    return importlib.import_module(f"{_PAKET}.{name}")


IMPORT = re.compile(r"""^\s*(?:import|export)\b[^'"]*?\bfrom\s+['"](\.[^'"]+)['"]""", re.MULTILINE)


def test_jeder_relative_import_im_frontend_hat_ein_ziel():
    """Ein vertippter Modulname fiele sonst erst im Browser auf, und das Panel bliebe leer."""
    gefunden = 0
    for datei in sorted(FRONTEND.glob("*.js")):
        for ziel in IMPORT.findall(datei.read_text(encoding="utf-8")):
            gefunden += 1
            assert (datei.parent / ziel).resolve().is_file(), f"{datei.name}: {ziel} fehlt"
    assert gefunden, "kein Import gefunden; prueft der Test noch etwas?"


# Gegenprobe: das Panel rollt aus wie termine.py, in Europe/Berlin mit Zeitumstellung.
FAELLE = [
    # (Abfahrt, Dauer in min, Wiederholung, von, bis)
    ("2026-09-16T08:00:00", 600, "once", "2026-09-14T00:00:00", "2026-10-12T00:00:00"),
    ("2026-09-16T08:00:00", 600, "daily", "2026-09-14T00:00:00", "2026-09-30T00:00:00"),
    ("2026-09-19T08:00:00", 600, "weekdays", "2026-09-14T00:00:00", "2026-10-12T00:00:00"),
    ("2026-09-16T19:00:00", 150, "weekly", "2026-09-20T00:00:00", "2026-11-20T00:00:00"),
    ("2026-09-16T07:30:00", 60, "monthly", "2026-09-01T00:00:00", "2027-09-01T00:00:00"),
    ("2026-09-30T07:30:00", 60, "monthly", "2026-09-01T00:00:00", "2027-09-01T00:00:00"),
    ("2026-09-28T07:30:00", 60, "monthly", "2026-09-01T00:00:00", "2027-09-01T00:00:00"),
    ("2028-02-29T10:00:00", 120, "yearly", "2028-01-01T00:00:00", "2034-01-01T00:00:00"),
    ("2026-03-28T02:30:00", 60, "daily", "2026-03-27T00:00:00", "2026-03-31T00:00:00"),
    ("2026-10-24T02:30:00", 60, "daily", "2026-10-23T00:00:00", "2026-10-27T00:00:00"),
    ("2026-10-24T22:00:00", 480, "daily", "2026-10-24T00:00:00", "2026-10-27T00:00:00"),
    ("2026-09-14T20:00:00", 2940, "weekly", "2026-09-16T12:00:00", "2026-09-30T12:00:00"),
]

SKRIPT = """
import { ausrollen } from %s;
import { zuMs } from %s;
let text = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', (teil) => { text += teil; });
process.stdin.on('end', () => {
  const tz = 'Europe/Berlin';
  const aus = JSON.parse(text).map(([abfahrt, dauerMin, regel, von, bis]) =>
    ausrollen({ abfahrt, dauerMin, regel }, tz, zuMs(von, tz), zuMs(bis, tz))
      .map((t) => [t.datum, t.abfahrt, t.rueckkehr]));
  process.stdout.write(JSON.stringify(aus));
});
"""


def test_das_panel_rollt_aus_wie_termine_py():
    termine = _modul("termine")
    berlin = ZoneInfo("Europe/Berlin")
    ms = lambda zeitpunkt: round(zeitpunkt.timestamp() * 1000)  # noqa: E731
    erwartet = []
    for abfahrt, dauer, wiederholung, von, bis in FAELLE:
        eintrag = {
            "id": "e1", "vehicle": "v1", "departure": abfahrt, "duration_min": dauer, "repeat": wiederholung,
            "distance_km": 1, "driver": None, "soc": None, "until": None, "exceptions": {},
        }
        liste = termine.termine_von(eintrag, berlin, termine.lokal(von, berlin), termine.lokal(bis, berlin))
        erwartet.append([[t.datum.isoformat(), ms(t.abfahrt), ms(t.rueckkehr)] for t in liste])
    assert all(erwartet), "ein Fall ohne Termin prueft nichts"
    skript = SKRIPT % (
        json.dumps((FRONTEND / "wiederholung.js").as_uri()), json.dumps((FRONTEND / "zeit.js").as_uri()))
    lauf = subprocess.run(
        [_node(), "--input-type=module", "-e", skript], input=json.dumps(FAELLE),
        capture_output=True, text=True, encoding="utf-8", cwd=WURZEL,
    )
    assert lauf.returncode == 0, lauf.stderr[-4000:]
    assert json.loads(lauf.stdout) == erwartet


# --- Anmeldung, Spec Abschnitte 2 und 3 --------------------------------------------------


def test_die_parameter_der_anmeldung():
    panel = _modul("panel")
    assert panel.parameter("1.1.0-beta.10") == {
        "frontend_url_path": "meteo-volt",
        "webcomponent_name": "meteo-volt-panel",
        "sidebar_title": "Meteo-Volt",
        "sidebar_icon": "mdi:lightning-bolt",
        "module_url": "/meteo_volt_panel/1.1.0-beta.10/meteo-volt-panel.js",
        "embed_iframe": False,
        "require_admin": False,
    }
    assert panel.adresse("1.1.0-beta.10") == "/meteo_volt_panel/1.1.0-beta.10"
    assert panel.VERZEICHNIS == FRONTEND
    assert panel.ANGEMELDET != panel.DOMAIN, "nicht unter hass.data[DOMAIN]: das lesen die sechs Sensoren"


def test_das_element_liegt_dort_wo_die_adresse_hinzeigt():
    panel = _modul("panel")
    element = FRONTEND / f"{panel.ELEMENT}.js"
    assert element.is_file()
    assert f"customElements.define('{panel.ELEMENT}'" in element.read_text(encoding="utf-8")
