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

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


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

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
