"""Temporaer: eine Action, die sofort einen Plan ueber den Koordinator holt.

Nur fuer die Entwicklung, und sie fliegt wieder raus: dann gehen diese Datei,
ihr Eintrag in services.yaml sowie Import und Aufruf in __init__.py -- bleibt
der Import stehen, laedt die ganze Integration nicht mehr. Registriert wird
sie nur, wenn const_overwrite.json wirkt (siehe overrides.py) -- ein normaler
Nutzer sieht sie nie.

Keine Felder, keine Uebersetzung, keine Entitaet. Die Antwort zeigt den
Planstand und je Fahrzeug, was gerade gilt. Bis C5 schickte sie einen festen
Request (C7-Spec Abschnitt 7).

Spec: meteo-volt-brain/docs/features/C5-standort-koordinator/spec.md, Abschnitt 10
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN

DEV_ACTION = "dev_plan"


def _json(wert: Any) -> Any:
    """datetime als ISO-Text, rekursiv durch dict und list.

    Die Antwort einer Action muss JSON sein, der Planstand traegt Zeitpunkte.
    """
    if isinstance(wert, datetime):
        return wert.isoformat()
    if isinstance(wert, dict):
        return {schluessel: _json(inhalt) for schluessel, inhalt in wert.items()}
    if isinstance(wert, list):
        return [_json(inhalt) for inhalt in wert]
    return wert


def async_dev_action_registrieren(hass: HomeAssistant) -> None:
    """Registriert meteo_volt.dev_plan, einmal je Home-Assistant-Lauf."""
    if hass.services.has_service(DOMAIN, DEV_ACTION):
        return

    async def _plan_holen(call: ServiceCall) -> ServiceResponse:
        koordinatoren = [
            eintrag.runtime_data
            for eintrag in hass.config_entries.async_loaded_entries(DOMAIN)
            if getattr(eintrag, "runtime_data", None) is not None
        ]
        if not koordinatoren:
            raise HomeAssistantError("Kein Standort-Koordinator geladen")
        koordinator = koordinatoren[0]
        stand = await koordinator.async_jetzt_planen()
        fehler = None
        if stand.fehler is not None:
            fehler = {"klasse": type(stand.fehler).__name__, "meldung": str(stand.fehler)}
        return _json(
            {
                "anfrage": stand.anfrage,
                "ausgelassen": stand.ausgelassen,
                "plan": stand.plan,
                "erhalten_um": stand.erhalten_um,
                "fehler": fehler,
                "letzter_versuch_um": stand.letzter_versuch_um,
                "jetzt": koordinator.was_gilt_jetzt(),
            }
        )

    hass.services.async_register(
        DOMAIN, DEV_ACTION, _plan_holen, supports_response=SupportsResponse.ONLY
    )
