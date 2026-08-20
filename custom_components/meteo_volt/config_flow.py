"""Config flow for Meteo-Volt integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN, CONF_API_TOKEN, CONF_GRID_FEES, API_URL
from .overrides import load_overrides
from .api import MeteoVoltApiClient

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_TOKEN): str,
        vol.Optional(CONF_GRID_FEES, default=0.0): vol.Coerce(float),
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    # Auch hier aufloesen, nicht nur in async_setup_entry: der Config-Flow
    # validiert den Token gegen die API. Griffe die Ueberschreibung nur an
    # einer Stelle, richtete man gegen die eine Umgebung ein und pollte die
    # andere.
    overrides = await hass.async_add_executor_job(load_overrides)
    client = MeteoVoltApiClient(
        data[CONF_API_TOKEN], api_url=overrides.get("api_url", API_URL)
    )
    
    try:
        await client.async_get_predictions(hass)
    except Exception as err:
        _LOGGER.error("Error authenticating with Meteo-Volt API: %s", err)
        raise InvalidAuth from err

    # Return info that you want to store in the config entry.
    return {"title": "Meteo-Volt"}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Meteo-Volt."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            # Prevent multiple configuration of the same token
            await self.async_set_unique_id(user_input[CONF_API_TOKEN])
            self._abort_if_unique_id_configured()

            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
