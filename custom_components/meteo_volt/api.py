"""API Client for Meteo-Volt."""
from __future__ import annotations

import logging
import time
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import API_URL
from .planabruf import PlanAbruf, PlanNichtVerfuegbar

_LOGGER = logging.getLogger(__name__)

# Spec C7 Abschnitt 5: das Gateway antwortet nach 10 s selbst mit 504. Diese
# 30 s greifen nur, wenn auch das Gateway nicht antwortet.
PLAN_TIMEOUT = aiohttp.ClientTimeout(total=30)


class MeteoVoltApiClient:
    """API Client for Meteo-Volt predictions."""

    def __init__(self, api_token: str, api_url: str = API_URL) -> None:
        """Initialize API client.

        Die URL wird uebergeben statt aus der Modulkonstante gezogen: nur so
        koennen beide Aufrufstellen -- async_setup_entry und der Config-Flow --
        dieselbe aufgeloeste Adresse benutzen, wenn const_overwrite.json eine
        andere nennt (siehe overrides.py). Der Default haelt den Normalfall
        unveraendert.
        """
        self._api_token = api_token
        self._api_url = api_url
        # Plan-URL und Sendepause aus R14. Je Client, also je Config-Entry und
        # damit je Key -- siehe planabruf.py.
        self._plan = PlanAbruf(api_url)

    async def async_get_predictions(self, hass: HomeAssistant) -> dict[str, Any]:
        """Get prediction data from the API."""
        session = async_get_clientsession(hass)
        
        headers = {
            "Authorization": f"Bearer {self._api_token}",
            "Accept": "application/json",
        }

        async with session.get(self._api_url, headers=headers) as response:
            if response.status == 401 or response.status == 403:
                raise Exception("Unauthorized. Please check your API token.")
            
            response.raise_for_status()
            data = await response.json()
            return data

    async def async_create_plan(
        self, hass: HomeAssistant, anfrage: dict[str, Any]
    ) -> dict[str, Any]:
        """POST /v1/plan. Liefert den Plan oder wirft einen PlanFehler.

        Hier wird nur geschickt. Was davor und danach entschieden wird --
        Sendepause, Plan-URL, Fehlerklasse -- steht in planabruf.py, weil es
        dort ohne Home Assistant pruefbar ist.

        Weder anfrage noch der Antwortkoerper gehen ins Log: dort stehen
        Ladestand und Fahrzeugdaten.
        """
        self._plan.vor_dem_senden(time.monotonic())

        session = async_get_clientsession(hass)
        headers = {
            "Authorization": f"Bearer {self._api_token}",
            "Accept": "application/json, application/problem+json",
        }
        try:
            async with session.post(
                self._plan.url,
                json=anfrage,
                headers=headers,
                timeout=PLAN_TIMEOUT,
                # Keine Weiterleitung: der Koerper traegt Ladestaende und geht
                # nur an die konfigurierte Adresse.
                allow_redirects=False,
            ) as response:
                status = response.status
                retry_after = response.headers.get("Retry-After")
                koerper = await response.read()
        except (aiohttp.ClientError, TimeoutError) as err:
            # Der Typ genuegt zur Diagnose und nennt keine Adresse.
            raise PlanNichtVerfuegbar(detail=type(err).__name__) from err

        return self._plan.nach_antwort(status, retry_after, koerper, time.monotonic())
