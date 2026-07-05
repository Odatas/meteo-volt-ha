"""API Client for Meteo-Volt."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import API_URL

_LOGGER = logging.getLogger(__name__)


class MeteoVoltApiClient:
    """API Client for Meteo-Volt predictions."""

    def __init__(self, api_token: str) -> None:
        """Initialize API client."""
        self._api_token = api_token

    async def async_get_predictions(self, hass: HomeAssistant) -> dict[str, Any]:
        """Get prediction data from the API."""
        session = async_get_clientsession(hass)
        
        headers = {
            "Authorization": f"Bearer {self._api_token}",
            "Accept": "application/json",
        }

        async with session.get(API_URL, headers=headers) as response:
            if response.status == 401 or response.status == 403:
                raise Exception("Unauthorized. Please check your API token.")
            
            response.raise_for_status()
            data = await response.json()
            return data
