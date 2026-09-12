"""Config flow for Meteo-Volt integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries, data_entry_flow
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector

from . import stammdaten
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

    # VERSION bleibt 1. Subentries kommen additiv: ein bestehender Eintrag
    # ohne sie ist gueltig, entry.subentries ist dann leer. Eine Migration
    # ohne Datenaenderung waere Risiko ohne Gegenwert -- Bestandsschutz
    # Auflage 4.

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Die zwei Stammdaten-Typen unter dem bestehenden Eintrag."""
        return {
            stammdaten.TYP_LADEPUNKT: LadepunktSubentryFlow,
            stammdaten.TYP_FAHRZEUG: FahrzeugSubentryFlow,
        }

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


def _formular(
    aufbau: dict,
    bauplan: dict,
    eingeklappt: frozenset = frozenset(),
    weglassen: frozenset = frozenset(),
) -> vol.Schema:
    """Baut ein Formular aus dem Aufbau in stammdaten.py.

    Damit gibt es EINE Quelle fuer die Zuordnung Feld -> Abschnitt: dieselbe,
    gegen die tests/test_uebersetzungen.py die Sprachdateien prueft, und
    dieselbe, unter der Home Assistant die Beschriftungen sucht
    (step.<schritt>.sections.<abschnitt>.data.<feld>).

    Diese Zuordnung ein zweites Mal von Hand zu fuehren war der Fehler der
    ersten Fassung. Ein Feld im Aufbau ohne Eintrag im Bauplan ist hier ein
    KeyError beim Formularbau -- laut, nicht still.

    bauplan bildet Feldname auf (Marker, Validator) ab. weglassen nennt die
    Felder, die dieses Mal nicht erscheinen sollen; das ist eine Entscheidung
    des Aufrufers und steht deshalb ausdruecklich da.
    """
    felder: dict = {}
    for abschnitt, namen in aufbau.items():
        inhalt = {
            bauplan[name][0]: bauplan[name][1]
            for name in namen
            if name not in weglassen
        }
        if abschnitt is None:
            felder.update(inhalt)
        elif inhalt:
            felder[vol.Required(abschnitt)] = data_entry_flow.section(
                vol.Schema(inhalt), {"collapsed": abschnitt in eingeklappt})
    return vol.Schema(felder)


def _vorhandene_titel(entry: ConfigEntry, typ: str) -> list[str]:
    """Die Titel aller Subentries eines Typs, fuer die Namensvergabe."""
    return [
        subentry.title
        for subentry in entry.subentries.values()
        if subentry.subentry_type == typ
    ]


def _titel_bestimmen(
    flow: ConfigSubentryFlow,
    typ: str,
    daten: dict[str, Any],
    bisher: str | None = None,
) -> str:
    """Der eingetippte Name, sonst der bisherige, sonst eine Nummer.

    Nimmt den Namen aus daten HERAUS: er ist der Titel des Subentries und
    nicht eines seiner Felder. Stuenden beide da, gingen sie beim naechsten
    Umbenennen auseinander.

    Beide Flows teilen sich diese Funktion. _get_entry ist die dokumentierte
    API von ConfigSubentryFlow, auch wenn der Unterstrich anderes nahelegt.
    """
    name = str(daten.pop(stammdaten.FELD_NAME, "") or "").strip()
    if name:
        return name
    if bisher:
        return bisher
    return stammdaten.naechster_name(
        _vorhandene_titel(flow._get_entry(), typ),
        typ,
        flow.hass.config.language,
    )


class LadepunktSubentryFlow(ConfigSubentryFlow):
    """Anlegen und Aendern eines Ladepunkts."""

    def _schema(self, vorgabe: dict[str, Any]) -> vol.Schema:
        """Das Formular, vorbelegt aus vorgabe.

        Min. Leistung und Phasen haben einen Kontrakt-Default, den kaum
        jemand aendert. Sie stehen deshalb eingeklappt -- der Wizard fragt
        sonst nach Werten, zu denen ein Erstnutzer nichts sagen kann.
        """
        standard = stammdaten.LADEPUNKT_DEFAULTS
        positiv = vol.All(vol.Coerce(float), vol.Range(min=0, min_included=False))

        def vor(feld: str):
            return vorgabe.get(feld, standard.get(feld))

        bauplan = {
            stammdaten.FELD_NAME: (
                vol.Optional(
                    stammdaten.FELD_NAME,
                    default=vorgabe.get(stammdaten.FELD_NAME, ""),
                ),
                str,
            ),
            stammdaten.FELD_MAX_LEISTUNG: (
                vol.Required(
                    stammdaten.FELD_MAX_LEISTUNG,
                    default=vor(stammdaten.FELD_MAX_LEISTUNG),
                ),
                positiv,
            ),
            stammdaten.FELD_VERFUEGBAR: (
                vol.Required(
                    stammdaten.FELD_VERFUEGBAR,
                    default=vor(stammdaten.FELD_VERFUEGBAR),
                ),
                bool,
            ),
            stammdaten.FELD_MIN_LEISTUNG: (
                vol.Optional(
                    stammdaten.FELD_MIN_LEISTUNG,
                    default=vor(stammdaten.FELD_MIN_LEISTUNG),
                ),
                positiv,
            ),
            stammdaten.FELD_PHASEN: (
                vol.Optional(
                    stammdaten.FELD_PHASEN,
                    default=vor(stammdaten.FELD_PHASEN),
                ),
                vol.In([1, 3]),
            ),
        }
        return _formular(
            stammdaten.LADEPUNKT_AUFBAU,
            bauplan,
            eingeklappt=frozenset({stammdaten.ABSCHNITT_ERWEITERT}),
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Neuen Ladepunkt anlegen."""
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=self._schema({}))

        daten = stammdaten.flach_aus_abschnitten(
            user_input, stammdaten.ABSCHNITTE_LADEPUNKT)
        titel = _titel_bestimmen(self, stammdaten.TYP_LADEPUNKT, daten)
        return self.async_create_entry(title=titel, data=daten)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Bestehenden Ladepunkt aendern."""
        subentry = self._get_reconfigure_subentry()

        if user_input is None:
            # Der Name kommt mit dem bestehenden Titel vorbelegt zurueck,
            # nicht leer: sonst verloere "Wallbox Garage" seinen Namen,
            # sobald jemand nur die Leistung korrigiert.
            vorgabe = dict(subentry.data)
            vorgabe[stammdaten.FELD_NAME] = subentry.title
            return self.async_show_form(
                step_id="reconfigure", data_schema=self._schema(vorgabe))

        daten = stammdaten.flach_aus_abschnitten(
            user_input, stammdaten.ABSCHNITTE_LADEPUNKT)
        titel = _titel_bestimmen(
            self, stammdaten.TYP_LADEPUNKT, daten, bisher=subentry.title)
        return self.async_update_and_abort(
            self._get_entry(), subentry, title=titel, data=daten)


class FahrzeugSubentryFlow(ConfigSubentryFlow):
    """Anlegen und Aendern eines Fahrzeugs."""

    def _ladepunkt_auswahl(self) -> list[selector.SelectOptionDict]:
        """Die angelegten Ladepunkte, Wert ist die subentry_id.

        Der Titel ist nur die Beschriftung: umbenennen darf die Zuordnung
        nicht verlieren, und die Kontrakt-ID ist ohnehin die subentry_id.
        """
        return [
            selector.SelectOptionDict(
                value=subentry.subentry_id, label=subentry.title)
            for subentry in self._get_entry().subentries.values()
            if subentry.subentry_type == stammdaten.TYP_LADEPUNKT
        ]

    def _schema(self, vorgabe: dict[str, Any]) -> vol.Schema:
        """Das Formular, vorbelegt aus vorgabe."""
        standard = stammdaten.FAHRZEUG_DEFAULTS
        prozent = vol.All(vol.Coerce(float), vol.Range(min=0, max=100))
        positiv = vol.All(vol.Coerce(float), vol.Range(min=0, min_included=False))

        def vor(feld: str):
            return vorgabe.get(feld, standard.get(feld))

        def zahl(feld: str, validator, pflicht: bool = True):
            marker = vol.Required if pflicht else vol.Optional
            return (marker(feld, default=vor(feld)), validator)

        def entitaet(feld: str, config, pflicht: bool = False):
            # suggested_value statt default: eine Entitaets-ID hat keine
            # sinnvolle Vorbelegung, und ein default=None waere ein Wert.
            marker = vol.Required if pflicht else vol.Optional
            return (
                marker(feld, description={"suggested_value": vor(feld)}),
                selector.EntitySelector(config),
            )

        bauplan = {
            stammdaten.FELD_NAME: (
                vol.Optional(
                    stammdaten.FELD_NAME,
                    default=vorgabe.get(stammdaten.FELD_NAME, ""),
                ),
                str,
            ),
            stammdaten.FELD_KAPAZITAET: zahl(stammdaten.FELD_KAPAZITAET, positiv),
            stammdaten.FELD_SOC_MIN: zahl(stammdaten.FELD_SOC_MIN, prozent),
            stammdaten.FELD_SOC_MAX: zahl(stammdaten.FELD_SOC_MAX, prozent),
            stammdaten.FELD_MAX_LADELEISTUNG: zahl(
                stammdaten.FELD_MAX_LADELEISTUNG, positiv),
            stammdaten.FELD_VERBRAUCH: zahl(stammdaten.FELD_VERBRAUCH, positiv),
            # Pflicht: ohne Ladestand ist ein Fahrzeug nicht planbar, und das
            # soll beim Anlegen auffallen statt erst im Plan. input_number
            # neben sensor, weil nicht jedes Auto einen Ladestand liefert --
            # wer keinen hat, traegt ihn ueber einen Helfer von Hand nach.
            stammdaten.FELD_SOC_ENTITAET: entitaet(
                stammdaten.FELD_SOC_ENTITAET,
                selector.EntitySelectorConfig(domain=["sensor", "input_number"]),
                pflicht=True,
            ),
            stammdaten.FELD_LADEPUNKT: (
                vol.Optional(
                    stammdaten.FELD_LADEPUNKT,
                    description={"suggested_value": vor(stammdaten.FELD_LADEPUNKT)},
                ),
                selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=self._ladepunkt_auswahl(),
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            ),
            stammdaten.FELD_ANGESTECKT: entitaet(
                stammdaten.FELD_ANGESTECKT,
                selector.EntitySelectorConfig(domain="binary_sensor"),
            ),
            stammdaten.FELD_MIN_LADELEISTUNG: zahl(
                stammdaten.FELD_MIN_LADELEISTUNG, positiv, pflicht=False),
            stammdaten.FELD_WIRKUNGSGRAD: (
                vol.Optional(
                    stammdaten.FELD_WIRKUNGSGRAD,
                    default=vor(stammdaten.FELD_WIRKUNGSGRAD),
                ),
                vol.All(
                    vol.Coerce(float),
                    vol.Range(min=0, max=100, min_included=False),
                ),
            ),
        }

        # Der Ladepunkt erscheint erst, wenn es einen gibt. Eine leere
        # Auswahlliste stellt eine Frage, auf die es keine Antwort gibt.
        weglassen = frozenset()
        if not self._ladepunkt_auswahl():
            weglassen = frozenset({stammdaten.FELD_LADEPUNKT})

        return _formular(
            stammdaten.FAHRZEUG_AUFBAU,
            bauplan,
            eingeklappt=frozenset({stammdaten.ABSCHNITT_ERWEITERT}),
            weglassen=weglassen,
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Neues Fahrzeug anlegen."""
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=self._schema({}))

        daten = stammdaten.flach_aus_abschnitten(
            user_input, stammdaten.ABSCHNITTE_FAHRZEUG)
        if (fehler := stammdaten.soc_grenzen_pruefen(daten)) is not None:
            return self.async_show_form(
                step_id="user", data_schema=self._schema(daten), errors=fehler)

        titel = _titel_bestimmen(self, stammdaten.TYP_FAHRZEUG, daten)
        return self.async_create_entry(title=titel, data=daten)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Bestehendes Fahrzeug aendern."""
        subentry = self._get_reconfigure_subentry()

        if user_input is None:
            vorgabe = dict(subentry.data)
            vorgabe[stammdaten.FELD_NAME] = subentry.title
            return self.async_show_form(
                step_id="reconfigure", data_schema=self._schema(vorgabe))

        daten = stammdaten.flach_aus_abschnitten(
            user_input, stammdaten.ABSCHNITTE_FAHRZEUG)
        if (fehler := stammdaten.soc_grenzen_pruefen(daten)) is not None:
            vorgabe = dict(daten)
            # Nur einsetzen, wenn nichts getippt wurde. Den eingegebenen Namen
            # im Fehlerfall durch den alten zu ersetzen hiesse, dem Nutzer
            # seine Eingabe wegzunehmen, waehrend er einen Fehler korrigiert.
            if not vorgabe.get(stammdaten.FELD_NAME):
                vorgabe[stammdaten.FELD_NAME] = subentry.title
            return self.async_show_form(
                step_id="reconfigure",
                data_schema=self._schema(vorgabe),
                errors=fehler,
            )

        titel = _titel_bestimmen(
            self, stammdaten.TYP_FAHRZEUG, daten, bisher=subentry.title)
        return self.async_update_and_abort(
            self._get_entry(), subentry, title=titel, data=daten)


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
