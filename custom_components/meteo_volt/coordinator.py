"""DataUpdateCoordinator for Meteo-Volt."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MeteoVoltApiClient
from .const import DOMAIN, UPDATE_INTERVAL_SECONDS

_LOGGER = logging.getLogger(__name__)


class MeteoVoltDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Meteo-Volt data."""

    def __init__(self, hass: HomeAssistant, client: MeteoVoltApiClient) -> None:
        """Initialize."""
        self.client = client
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL_SECONDS),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from API."""
        try:
            data = await self.client.async_get_predictions(self.hass)
            return data
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err
