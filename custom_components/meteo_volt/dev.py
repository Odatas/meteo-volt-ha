"""Temporaer: eine Action, die einen festen Plan-Request schickt.

Nur fuer die Entwicklung, und sie fliegt wieder raus: dann gehen diese Datei,
ihr Eintrag in services.yaml und der Aufruf in __init__.py. Registriert wird
sie nur, wenn const_overwrite.json wirkt (siehe overrides.py) -- ein normaler
Nutzer sieht sie nie.

Keine Felder, keine Uebersetzung, keine Entitaet. Die Antwort erscheint in den
Entwicklerwerkzeugen unter der Action, ein PlanFehler als Fehlermeldung.

Spec: meteo-volt-brain/docs/features/C7-plan-client/spec.md, Abschnitt 7
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .planabruf import PlanFehler

DEV_ACTION = "dev_plan"

# Der kleinste Request, der einen echten Plan ergibt: ein Ladepunkt, ein
# Fahrzeug daran angesteckt. Ohne now -- dann gilt die Serverzeit --, ohne
# model und ohne Constraints.
DEV_ANFRAGE = {
    "schema_version": 1,
    "stations": [{"id": "dev-wallbox", "max_power_kw": 11.0}],
    "vehicles": [
        {
            "id": "dev-auto",
            "capacity_kwh": 58.0,
            "soc_pct": 50.0,
            "max_charge_kw": 11.0,
            "efficiency_curve": [{"kw": 11.0, "eta": 0.92}],
            "soc_min_pct": 15.0,
            "soc_max_pct": 80.0,
            "consumption_kwh_per_100km": 19.5,
            "connection": {"station_id": "dev-wallbox"},
            "consumption": {"type": "none"},
        }
    ],
}


def async_dev_action_registrieren(hass: HomeAssistant) -> None:
    """Registriert meteo_volt.dev_plan, einmal je Home-Assistant-Lauf."""
    if hass.services.has_service(DOMAIN, DEV_ACTION):
        return

    async def _plan_holen(call: ServiceCall) -> ServiceResponse:
        koordinatoren = list(hass.data.get(DOMAIN, {}).values())
        if not koordinatoren:
            raise HomeAssistantError("Kein Meteo-Volt-Eintrag geladen")
        try:
            return await koordinatoren[0].client.async_create_plan(hass, DEV_ANFRAGE)
        except PlanFehler as err:
            raise HomeAssistantError(f"{type(err).__name__}: {err}") from err

    hass.services.async_register(
        DOMAIN, DEV_ACTION, _plan_holen, supports_response=SupportsResponse.ONLY
    )
