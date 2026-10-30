"""DataUpdateCoordinator for Meteo-Volt."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MeteoVoltApiClient
from .const import DOMAIN, REAUTH_GRUND, UPDATE_INTERVAL_SECONDS
from .planabruf import PrognoseFehler

_LOGGER = logging.getLogger(__name__)


def reauth_grund_merken(hass: HomeAssistant, entry_id: str, klasse: str) -> None:
    """Warum der Key abgewiesen wurde. Der Reauth-Dialog liest es.

    Liegt neben hass.data[DOMAIN]: scheitert schon der erste Abruf, gibt es
    dort keinen Eintrag.
    """
    hass.data.setdefault(REAUTH_GRUND, {})[entry_id] = klasse


class MeteoVoltDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Meteo-Volt data."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: MeteoVoltApiClient
    ) -> None:
        """Initialize."""
        self.client = client
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL_SECONDS),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from API."""
        try:
            data = await self.client.async_get_predictions(self.hass)
            return data
        except PrognoseFehler as err:
            if err.key_abgewiesen:
                # Home Assistant stoppt die Abfragen und bietet "Erneut
                # authentifizieren" an.
                reauth_grund_merken(self.hass, self.config_entry.entry_id, err.klasse)
                raise ConfigEntryAuthFailed(f"Key abgewiesen: {err}") from err
            raise UpdateFailed(f"Error communicating with API: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err
