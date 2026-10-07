"""Das Panel in der Seitenleiste: anmelden und ausliefern. Spec C8 Abschnitte 2 und 3.

Home Assistant liefert das Verzeichnis frontend/ unter einer Adresse mit der
Version aus manifest.json aus. Browser halten die Dateien einen Monat; mit
der Version im Pfad ist jede Beta eine neue Adresse.

Die Imports aus Home Assistant stehen in den Funktionen: So laesst sich
parameter() ohne Home Assistant pruefen (tests/test_panel.py). Geladen wird
dieses Modul nur im try (Spec Abschnitt 2); scheitert es, laufen Prognose,
Plan, die Entitaeten aus C6 und C3 weiter. Anmelden und Ausliefern sieht
kein automatischer Test, nur die Abnahme.

Spec: meteo-volt-brain/docs/features/C8-panel/spec.md, Abschnitte 2 und 3
"""

from __future__ import annotations

from pathlib import Path

from .const import DOMAIN

URL_PFAD = "meteo-volt"
ELEMENT = "meteo-volt-panel"
AUSLIEFERUNG = "/meteo_volt_panel"
VERZEICHNIS = Path(__file__).parent / "frontend"

# hass.data, nicht unter hass.data[DOMAIN]: das lesen die sechs Sensoren.
ANGEMELDET = f"{DOMAIN}_panel"
AUSGELIEFERT = f"{DOMAIN}_panel_ausgeliefert"


def adresse(version: str) -> str:
    """Wo Home Assistant das Verzeichnis frontend/ ausliefert."""
    return f"{AUSLIEFERUNG}/{version}"


def parameter(version: str) -> dict:
    """Was panel_custom.async_register_panel bekommt, Spec Abschnitt 2."""
    return {
        "frontend_url_path": URL_PFAD,
        "webcomponent_name": ELEMENT,
        "sidebar_title": "Meteo-Volt",
        "sidebar_icon": "mdi:lightning-bolt",
        "module_url": f"{adresse(version)}/{ELEMENT}.js",
        "embed_iframe": False,
        "require_admin": False,
    }


async def async_panel_anmelden(hass) -> None:
    """Beim Einrichten eines Eintrags, wenn das Panel noch nicht steht.

    Die statische Route einmal je Lauf: abmelden laesst sie sich nicht.
    """
    if hass.data.get(ANGEMELDET):
        return
    from homeassistant.components import panel_custom
    from homeassistant.components.http import StaticPathConfig
    from homeassistant.loader import async_get_integration

    version = str((await async_get_integration(hass, DOMAIN)).version)
    if not hass.data.get(AUSGELIEFERT):
        await hass.http.async_register_static_paths(
            [StaticPathConfig(adresse(version), str(VERZEICHNIS), True)])
        hass.data[AUSGELIEFERT] = True
    await panel_custom.async_register_panel(hass, **parameter(version))
    hass.data[ANGEMELDET] = True


def panel_abmelden(hass, entry_id: str) -> None:
    """In async_remove_entry: wenn danach kein Eintrag der Integration uebrig ist."""
    if not hass.data.get(ANGEMELDET):
        return
    if any(eintrag.entry_id != entry_id for eintrag in hass.config_entries.async_entries(DOMAIN)):
        return
    from homeassistant.components import frontend

    frontend.async_remove_panel(hass, URL_PFAD, warn_if_unknown=False)
    hass.data[ANGEMELDET] = False
