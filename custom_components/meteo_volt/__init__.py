"""The Meteo-Volt integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .api import MeteoVoltApiClient
from .const import DOMAIN, CONF_API_TOKEN, API_URL
from .overrides import load_overrides
from .coordinator import MeteoVoltDataUpdateCoordinator
from .plankoordinator import MeteoVoltPlanKoordinator
# Temporaer, Spec C7 Abschnitt 7: geht zusammen mit dev.py und dem Aufruf unten.
from .dev import async_dev_action_registrieren

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Meteo-Volt from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    api_token = entry.data[CONF_API_TOKEN]
    # Dateizugriff gehoert nicht in den Event-Loop. Siehe overrides.py: fehlt
    # die Datei -- der Normalfall -- kommt hier ein leeres dict zurueck.
    overrides = await hass.async_add_executor_job(load_overrides)
    client = MeteoVoltApiClient(api_token, api_url=overrides.get("api_url", API_URL))

    coordinator = MeteoVoltDataUpdateCoordinator(hass, client)

    # Fetch initial data so we have data when entities subscribe
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Spec C5 Abschnitt 6: der Standort-Koordinator wartet auf nichts, und
    # scheitert sein Start, laeuft die Prognose trotzdem weiter -- sie hat
    # zahlende Nutzer (Bestandsschutz). Er haengt an runtime_data; hass.data
    # und sensor.py bleiben, wie sie sind.
    try:
        plan_koordinator = MeteoVoltPlanKoordinator(hass, entry, client)
        # Spec C3 Abschnitt 8: vor dem Start, damit schon der erste Request die
        # Termine traegt. Scheitert C3, plant C5 ohne sie.
        await _termine_starten(hass, entry, plan_koordinator)
        plan_koordinator.async_starten()
    except Exception:  # pylint: disable=broad-except
        _LOGGER.exception("Standort-Koordinator nicht gestartet, die Prognose laeuft weiter")
        # None statt eines fehlenden Attributs: C6 darf daran nicht scheitern.
        entry.runtime_data = None
    else:
        entry.runtime_data = plan_koordinator
        _ausgaben_starten(hass, entry, plan_koordinator)

    # Spec C8 Abschnitt 2: das Panel, im try wie C3. Scheitert es, fehlt nur das Panel.
    await _panel_anmelden(hass)

    # Temporaer, Spec C7 Abschnitt 7: nur wenn const_overwrite.json wirkt.
    if overrides:
        async_dev_action_registrieren(hass)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


def _ausgaben_starten(
    hass: HomeAssistant, entry: ConfigEntry, plan_koordinator: MeteoVoltPlanKoordinator
) -> None:
    """Spec C6 Abschnitt 8: die Auswertung je Fahrzeug, fuer beide Plattformen.

    Scheitert sie, fehlen nur die Fahrzeugentitaeten; Prognose und Plan laufen
    weiter. Der Import steht deshalb mit im try.
    """
    try:
        from .fahrzeugausgabe import AUSGABEN, Fahrzeugausgaben

        ausgaben = Fahrzeugausgaben(hass, entry, plan_koordinator)
        ausgaben.async_starten()
    except Exception:  # pylint: disable=broad-except
        _LOGGER.exception("Ausgabe je Fahrzeug nicht gestartet, die Prognose laeuft weiter")
        return
    hass.data.setdefault(AUSGABEN, {})[entry.entry_id] = ausgaben

    def ausgaben_vergessen() -> None:
        # Spec C6 Abschnitt 8: ohne Rueckgabewert. Aus jedem ausser None macht
        # Home Assistant einen Task, und ein anderes Objekt liesse das Entladen
        # scheitern.
        hass.data[AUSGABEN].pop(entry.entry_id, None)

    entry.async_on_unload(ausgaben_vergessen)


async def _termine_starten(
    hass: HomeAssistant, entry: ConfigEntry, plan_koordinator: MeteoVoltPlanKoordinator
) -> None:
    """Spec C3 Abschnitt 8: Store, Actions und Websocket-Befehle nur im try.

    Der Import steht mit im try. Scheitert etwas, laufen Prognose, Plan und die
    Entitaeten aus C6 weiter, und der Request geht ohne Termine raus.
    """
    try:
        from .aktionen import async_aktionen_registrieren
        from .terminverwaltung import async_termine_starten
        from .terminwebsocket import async_websocket_registrieren

        await async_termine_starten(hass, entry, plan_koordinator)
        async_aktionen_registrieren(hass)
        async_websocket_registrieren(hass)
    except Exception:  # pylint: disable=broad-except
        _LOGGER.exception("Termine nicht gestartet, Prognose und Plan laufen weiter")


async def _panel_anmelden(hass: HomeAssistant) -> None:
    """Spec C8 Abschnitt 2: das Panel in der Seitenleiste, nur im try.

    Der Import steht mit im try. Scheitert etwas, laufen Prognose, Plan, die
    Entitaeten aus C6 und die Termine weiter.
    """
    try:
        from .panel import async_panel_anmelden

        await async_panel_anmelden(hass)
    except Exception:  # pylint: disable=broad-except
        _LOGGER.exception("Panel nicht angemeldet, Prognose und Plan laufen weiter")


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Spec C3 Abschnitt 3: entfernt der Nutzer die Integration, geht der Store mit.

    Spec C8 Abschnitt 2: war es der letzte Eintrag, geht auch das Panel.
    """
    try:
        from .terminverwaltung import async_speicher_entfernen

        await async_speicher_entfernen(hass, entry.entry_id)
    except Exception:  # pylint: disable=broad-except
        _LOGGER.exception("Terminspeicher nicht entfernt")
    try:
        from .panel import panel_abmelden

        panel_abmelden(hass, entry.entry_id)
    except Exception:  # pylint: disable=broad-except
        _LOGGER.exception("Panel nicht abgemeldet")


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
