"""Die Websocket-Befehle fuer das Panel. Spec C3 Abschnitt 6.

Jeder Nutzer darf lesen: kein Befehl verlangt Admin-Rechte. Jeder nimmt
optional config_entry; ohne meint er den zuerst geladenen Standort. Den
Inhalt baut ansicht.py, hier wird nur gelesen und geschickt.

meteo_volt/subscribe meldet appointments, site, plan, planning und prices,
jeweils nur den Namen. Das Panel liest danach neu.

Geladen wird dieses Modul nur im try (Spec Abschnitt 8). Das Verhalten
sieht kein automatischer Test, nur die Abnahme.

Spec: meteo-volt-brain/docs/features/C3-konfig-entitaeten/spec.md, Abschnitt 6
"""

from __future__ import annotations

from datetime import datetime

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from . import pruefungen, termine
from .const import DOMAIN
from .terminverwaltung import SIGNAL_PANEL, Terminverwaltung, nach_geraet, nach_standort

REGISTRIERT = f"{DOMAIN}_websocket"


def _standort(hass: HomeAssistant, connection, msg: dict) -> Terminverwaltung | None:
    verwaltung = nach_standort(hass, msg.get("config_entry"))
    if verwaltung is None:
        connection.send_error(msg["id"], websocket_api.ERR_NOT_FOUND, "Kein Meteo-Volt-Standort mit Terminen")
    return verwaltung


def _fahrzeug(hass: HomeAssistant, connection, msg: dict, verwaltung: Terminverwaltung) -> str | None:
    """Die subentry_id zur Geraete-ID, oder None nach einer Fehlermeldung."""
    try:
        anderer, fahrzeug_id = nach_geraet(hass, msg.get("vehicle"))
    except pruefungen.Terminfehler:
        anderer = None
    if anderer is not verwaltung:
        connection.send_error(msg["id"], pruefungen.FAHRZEUG_UNBEKANNT, "Kein Fahrzeug dieses Standorts")
        return None
    return fahrzeug_id


def _zeitpunkt(text: str, verwaltung: Terminverwaltung) -> datetime | None:
    """ISO 8601. Ohne Offset gilt die Zeitzone von Home Assistant."""
    try:
        zeitpunkt = datetime.fromisoformat(text)
    except ValueError:
        return None
    return zeitpunkt if zeitpunkt.tzinfo is not None else termine.lokal(text, verwaltung.zeitzone())


@websocket_api.websocket_command(
    {vol.Required("type"): "meteo_volt/site", vol.Optional("config_entry"): str})
@callback
def ws_standort(hass: HomeAssistant, connection, msg: dict) -> None:
    if (verwaltung := _standort(hass, connection, msg)) is not None:
        connection.send_result(msg["id"], verwaltung.standort())


@websocket_api.websocket_command({
    vol.Required("type"): "meteo_volt/appointments",
    vol.Required("start"): str,
    vol.Required("end"): str,
    vol.Optional("vehicle"): str,
    vol.Optional("config_entry"): str,
})
@callback
def ws_termine(hass: HomeAssistant, connection, msg: dict) -> None:
    if (verwaltung := _standort(hass, connection, msg)) is None:
        return
    start, ende = _zeitpunkt(msg["start"], verwaltung), _zeitpunkt(msg["end"], verwaltung)
    if start is None or ende is None:
        connection.send_error(msg["id"], websocket_api.ERR_INVALID_FORMAT, "start und end sind ISO 8601")
        return
    fahrzeug_id = None
    if msg.get("vehicle") is not None and (fahrzeug_id := _fahrzeug(hass, connection, msg, verwaltung)) is None:
        return
    connection.send_result(msg["id"], verwaltung.termine_im_fenster(start, ende, fahrzeug_id))


@websocket_api.websocket_command({
    vol.Required("type"): "meteo_volt/plan",
    vol.Required("vehicle"): str,
    vol.Optional("config_entry"): str,
})
@callback
def ws_plan(hass: HomeAssistant, connection, msg: dict) -> None:
    if (verwaltung := _standort(hass, connection, msg)) is None:
        return
    if (fahrzeug_id := _fahrzeug(hass, connection, msg, verwaltung)) is None:
        return
    connection.send_result(msg["id"], verwaltung.plan(fahrzeug_id))


@websocket_api.websocket_command(
    {vol.Required("type"): "meteo_volt/prices", vol.Optional("config_entry"): str})
@callback
def ws_preise(hass: HomeAssistant, connection, msg: dict) -> None:
    if (verwaltung := _standort(hass, connection, msg)) is not None:
        connection.send_result(msg["id"], verwaltung.preise())


@websocket_api.websocket_command(
    {vol.Required("type"): "meteo_volt/subscribe", vol.Optional("config_entry"): str})
@callback
def ws_abonnieren(hass: HomeAssistant, connection, msg: dict) -> None:
    """Eine Meldung je Aenderung, auch die anderer Nutzer. Ueberlebt das Neuladen des Eintrags."""
    if (verwaltung := _standort(hass, connection, msg)) is None:
        return

    @callback
    def melden(meldung: str) -> None:
        connection.send_message(websocket_api.event_message(msg["id"], meldung))

    connection.subscriptions[msg["id"]] = async_dispatcher_connect(
        hass, SIGNAL_PANEL.format(verwaltung.entry.entry_id), melden)
    connection.send_result(msg["id"])


@callback
def async_websocket_registrieren(hass: HomeAssistant) -> None:
    """Einmal je Home-Assistant-Lauf."""
    if hass.data.get(REGISTRIERT):
        return
    hass.data[REGISTRIERT] = True
    for befehl in (ws_standort, ws_termine, ws_plan, ws_preise, ws_abonnieren):
        websocket_api.async_register_command(hass, befehl)
