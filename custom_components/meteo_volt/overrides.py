"""Optionale Ueberschreibung von Konstanten aus einer Datei.

Zweck: die Integration gegen eine andere API testen koennen, ohne deren
Adresse in das auszuliefern, was ein Nutzer bekommt. Wer testen will, legt
const_overwrite.json neben dieses Modul und startet Home Assistant neu.

    { "api_url": "https://.../v1/prediction" }

Fehlt die Datei -- der Normalfall -- passiert nichts, und es wird auch nichts
protokolliert: eine Meldung bei jedem Start waere Rauschen, und Rauschen, das
man gewohnheitsmaessig uebergeht, macht die Warnungen unten wertlos.

Ist die Datei DA, steht immer eine Zeile im Log, auch im Erfolgsfall. Der
gefaehrliche Zustand ist naemlich nicht der Absturz, sondern die stille
Annahme, man teste gegen Dev, waehrend Prod antwortet. Aus demselben Grund
wird ein unbekannter Schluessel benannt: ein Tippfehler wie "api_ur" fuehrt
sonst lautlos zurueck auf Prod.

Eine unbrauchbare Datei bricht die Integration NICHT ab; sie faellt auf die
hartkodierten Werte zurueck und warnt.

Dieses Modul importiert bewusst NICHTS aus Home Assistant. Nur so laesst es
sich in der Testsuite dieses Repos ueberhaupt laden -- homeassistant steckt
nicht in den Testabhaengigkeiten. Die gesamte Logik liegt deshalb hier, und
die Verdrahtung in __init__.py und config_flow.py bleibt klein genug, um sie
mit dem Auge zu pruefen.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

OVERRIDE_FILE = "const_overwrite.json"

# Bekannte Schluessel. Jeder Wert muss ein nicht-leerer String sein; kaeme
# einmal ein Schluessel mit anderem Typ dazu, braucht diese Stelle eine
# Fallunterscheidung statt eines weiteren Eintrags.
_KNOWN_KEYS = ("api_url",)


def load_overrides(directory: Path | None = None) -> dict[str, str]:
    """Liefert die wirksamen Ueberschreibungen, oder ein leeres dict.

    directory dient den Tests; im Betrieb liegt die Datei neben diesem Modul.
    Es wird nicht zwischengespeichert -- die Datei ist winzig, wird nur beim
    Setup und beim Config-Flow gelesen, und ein Cache braechte nur die Frage,
    warum eine Aenderung nicht wirkt.
    """
    pfad = (directory or Path(__file__).parent) / OVERRIDE_FILE
    if not pfad.is_file():
        return {}

    try:
        daten = json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, ValueError) as fehler:
        _LOGGER.warning(
            "%s ist nicht lesbar (%s) -- die hartkodierten Werte bleiben aktiv",
            OVERRIDE_FILE, fehler,
        )
        return {}

    if not isinstance(daten, dict):
        _LOGGER.warning(
            "%s enthaelt %s statt eines JSON-Objekts -- die hartkodierten "
            "Werte bleiben aktiv",
            OVERRIDE_FILE, type(daten).__name__,
        )
        return {}

    unbekannt = sorted(set(daten) - set(_KNOWN_KEYS))
    if unbekannt:
        _LOGGER.warning(
            "%s nennt unbekannte Schluessel: %s -- bekannt sind: %s. Ein "
            "Tippfehler wirkt hier wie eine fehlende Ueberschreibung",
            OVERRIDE_FILE, ", ".join(unbekannt), ", ".join(_KNOWN_KEYS),
        )

    wirksam: dict[str, str] = {}
    for schluessel in _KNOWN_KEYS:
        if schluessel not in daten:
            continue
        wert = daten[schluessel]
        if not isinstance(wert, str) or not wert.strip():
            _LOGGER.warning(
                "%s: %s ist %r und damit keine brauchbare Angabe -- der "
                "hartkodierte Wert bleibt aktiv",
                OVERRIDE_FILE, schluessel, wert,
            )
            continue
        wirksam[schluessel] = wert.strip()

    if not wirksam:
        _LOGGER.warning(
            "%s ist vorhanden, ergibt aber keine wirksame Ueberschreibung -- "
            "es gelten die hartkodierten Werte",
            OVERRIDE_FILE,
        )
        return {}

    for schluessel, wert in wirksam.items():
        _LOGGER.warning(
            "%s aktiv: %s = %s. Diese Integration spricht NICHT mit der "
            "ausgelieferten Standardadresse",
            OVERRIDE_FILE, schluessel, wert,
        )
    return wirksam
