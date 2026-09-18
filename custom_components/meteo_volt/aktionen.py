"""Die Actions der Termine in Home Assistant. Spec C3 Abschnitt 5.

Registriert einmal je Home-Assistant-Lauf unter meteo_volt. Jeder Nutzer
darf sie aufrufen, auch ohne Admin-Rechte. Die Felder stehen in
pruefungen.AKTIONEN und sind im Schema optional; geprueft wird in
pruefungen.py und terminbuch.py, damit jede Meldung aus Spec Abschnitt 2.3
uebersetzt ankommt: als ServiceValidationError mit dem Schluessel als
translation_key. Warnungen stehen in der Antwort.

Geladen wird dieses Modul nur im try (Spec Abschnitt 8). Das Verhalten
sieht kein automatischer Test, nur die Abnahme.

Spec: meteo-volt-brain/docs/features/C3-konfig-entitaeten/spec.md, Abschnitt 5
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import date

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from . import pruefungen, terminbuch, termine
from .const import DOMAIN
from .terminverwaltung import Terminverwaltung, nach_eintrag, nach_geraet, nach_schritt, nach_standort

_TEXT = vol.Any(None, cv.string)
_ZAHL = vol.Any(None, vol.Coerce(float))

# Die Pruefung der Form. Was Spec Abschnitt 2.3 meldet, prueft das Backend.
_FELDER = {
    "vehicle": _TEXT,
    "departure": _TEXT,
    "return": _TEXT,
    "repeat": vol.Any(None, vol.In(termine.WIEDERHOLUNGEN)),
    "distance_km": _ZAHL,
    "driver": _TEXT,
    "soc": _ZAHL,
    "entry": _TEXT,
    "date": _TEXT,
    "scope": vol.Any(None, vol.In(terminbuch.UMFAENGE)),
    "appointments": vol.Any(None, [{vol.Optional("entry"): _TEXT, vol.Optional("date"): _TEXT}]),
    "step": _TEXT,
    # Fuer das Risiko gibt es keinen Schluessel in 2.3: die Form prueft es ganz.
    "risk": vol.All(vol.Coerce(int), vol.In([1, 2, 3])),
    "config_entry": _TEXT,
}
_PFLICHT = {"risk"}


def _schema(aktion: str) -> vol.Schema:
    return vol.Schema({
        (vol.Required if feld in _PFLICHT else vol.Optional)(feld): _FELDER[feld]
        for feld in pruefungen.AKTIONEN[aktion]
    })


def _datum(text: str | None) -> date:
    try:
        return date.fromisoformat(text or "")
    except ValueError:
        raise pruefungen.fehler(pruefungen.TERMIN_UNBEKANNT, "date") from None


def _standort(hass: HomeAssistant, entry_id: str | None) -> Terminverwaltung:
    verwaltung = nach_standort(hass, entry_id)
    if verwaltung is None:
        raise HomeAssistantError("Kein Meteo-Volt-Standort mit Terminen geladen")
    return verwaltung


# --- Die sieben Actions --------------------------------------------------------


async def _anlegen(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    verwaltung, fahrzeug_id = nach_geraet(hass, call.data.get("vehicle"))
    return await verwaltung.async_anlegen(fahrzeug_id, dict(call.data))


async def _aendern(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    # Die Reihenfolge der Meldungen: Eintrag, Datum, Fahrzeug, Felder, Umfang.
    verwaltung = nach_eintrag(hass, call.data.get("entry"))
    datum = _datum(call.data.get("date"))
    if not termine.hat_termin(verwaltung.buch.eintraege[call.data["entry"]], datum):
        raise pruefungen.fehler(pruefungen.TERMIN_UNBEKANNT, "date")
    anderer, fahrzeug_id = nach_geraet(hass, call.data.get("vehicle"))
    if anderer is not verwaltung:
        raise pruefungen.fehler(pruefungen.FAHRZEUG_UNBEKANNT, "vehicle")
    return await verwaltung.async_aendern(
        call.data["entry"], datum, call.data.get("scope"), fahrzeug_id, dict(call.data))


async def _loeschen(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    verwaltung = nach_eintrag(hass, call.data.get("entry"))
    return await verwaltung.async_loeschen(
        call.data["entry"], _datum(call.data.get("date")), call.data.get("scope"))


async def _absagen(hass: HomeAssistant, call: ServiceCall) -> ServiceResponse:
    angaben = call.data.get("appointments") or []
    if not angaben:
        raise pruefungen.fehler(pruefungen.EINTRAG_UNBEKANNT, "entry")
    verwaltung = nach_eintrag(hass, angaben[0].get("entry"))
    liste = [(termin.get("entry"), _datum(termin.get("date"))) for termin in angaben]
    return await verwaltung.async_absagen(liste, call.data.get("step"))


async def _rueckgaengig(hass: HomeAssistant, call: ServiceCall) -> None:
    schritt = call.data.get("step")
    await nach_schritt(hass, schritt).async_rueckgaengig(schritt)


async def _risiko(hass: HomeAssistant, call: ServiceCall) -> None:
    await _standort(hass, call.data.get("config_entry")).async_risiko_setzen(call.data["risk"])


async def _neu_planen(hass: HomeAssistant, call: ServiceCall) -> None:
    await _standort(hass, call.data.get("config_entry")).async_neu_planen()


_AKTIONEN: dict[str, tuple[Callable[[HomeAssistant, ServiceCall], Awaitable], SupportsResponse]] = {
    "create_appointment": (_anlegen, SupportsResponse.OPTIONAL),
    "update_appointment": (_aendern, SupportsResponse.OPTIONAL),
    "delete_appointment": (_loeschen, SupportsResponse.OPTIONAL),
    "cancel_appointments": (_absagen, SupportsResponse.OPTIONAL),
    "undo": (_rueckgaengig, SupportsResponse.NONE),
    "set_risk": (_risiko, SupportsResponse.NONE),
    "replan": (_neu_planen, SupportsResponse.NONE),
}


def _uebersetzt(
    hass: HomeAssistant, ablauf: Callable[[HomeAssistant, ServiceCall], Awaitable]
) -> Callable[[ServiceCall], Awaitable]:
    """Aus einem Terminfehler wird ein ServiceValidationError mit dem Schluessel."""

    async def aufrufen(call: ServiceCall) -> ServiceResponse:
        try:
            return await ablauf(hass, call)
        except pruefungen.Terminfehler as fehler:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key=fehler.meldung.schluessel,
                translation_placeholders=fehler.meldung.platzhalter or None,
            ) from None

    return aufrufen


@callback
def async_aktionen_registrieren(hass: HomeAssistant) -> None:
    """Einmal je Home-Assistant-Lauf. Ohne geladenen Standort melden sie das."""
    if hass.services.has_service(DOMAIN, "create_appointment"):
        return
    for aktion, (ablauf, antwort) in _AKTIONEN.items():
        hass.services.async_register(
            DOMAIN, aktion, _uebersetzt(hass, ablauf), schema=_schema(aktion), supports_response=antwort)
