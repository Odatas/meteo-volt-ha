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

        return vol.Schema(
            {
                vol.Optional(
                    stammdaten.FELD_NAME,
                    default=vorgabe.get(stammdaten.FELD_NAME, ""),
                ): str,
                vol.Required(
                    stammdaten.FELD_MAX_LEISTUNG,
                    default=vor(stammdaten.FELD_MAX_LEISTUNG),
                ): positiv,
                vol.Required(
                    stammdaten.FELD_VERFUEGBAR,
                    default=vor(stammdaten.FELD_VERFUEGBAR),
                ): bool,
                vol.Required(stammdaten.ABSCHNITT_ERWEITERT): data_entry_flow.section(
                    vol.Schema(
                        {
                            vol.Optional(
                                stammdaten.FELD_MIN_LEISTUNG,
                                default=vor(stammdaten.FELD_MIN_LEISTUNG),
                            ): positiv,
                            vol.Optional(
                                stammdaten.FELD_PHASEN,
                                default=vor(stammdaten.FELD_PHASEN),
                            ): vol.In([1, 3]),
                        }
                    ),
                    {"collapsed": True},
                ),
            }
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

        laufzeit: dict = {
            vol.Required(
                stammdaten.FELD_SOC_ENTITAET,
                description={"suggested_value": vor(stammdaten.FELD_SOC_ENTITAET)},
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["sensor", "input_number"])
            ),
        }
        # Das Feld erscheint erst, wenn es einen Ladepunkt gibt. Eine leere
        # Auswahlliste stellt eine Frage, auf die es keine Antwort gibt.
        auswahl = self._ladepunkt_auswahl()
        if auswahl:
            laufzeit[
                vol.Optional(
                    stammdaten.FELD_LADEPUNKT,
                    description={"suggested_value": vor(stammdaten.FELD_LADEPUNKT)},
                )
            ] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=auswahl, mode=selector.SelectSelectorMode.DROPDOWN)
            )
        laufzeit[
            vol.Optional(
                stammdaten.FELD_ANGESTECKT,
                description={"suggested_value": vor(stammdaten.FELD_ANGESTECKT)},
            )
        ] = selector.EntitySelector(
            selector.EntitySelectorConfig(domain="binary_sensor")
        )

        return vol.Schema(
            {
                vol.Optional(
                    stammdaten.FELD_NAME,
                    default=vorgabe.get(stammdaten.FELD_NAME, ""),
                ): str,
                vol.Required(stammdaten.ABSCHNITT_BATTERIE): data_entry_flow.section(
                    vol.Schema(
                        {
                            vol.Required(
                                stammdaten.FELD_KAPAZITAET,
                                default=vor(stammdaten.FELD_KAPAZITAET),
                            ): positiv,
                        }
                    ),
                    {"collapsed": False},
                ),
                vol.Required(stammdaten.ABSCHNITT_GUARD): data_entry_flow.section(
                    vol.Schema(
                        {
                            vol.Required(
                                stammdaten.FELD_SOC_MIN,
                                default=vor(stammdaten.FELD_SOC_MIN),
                            ): prozent,
                            vol.Required(
                                stammdaten.FELD_SOC_MAX,
                                default=vor(stammdaten.FELD_SOC_MAX),
                            ): prozent,
                        }
                    ),
                    {"collapsed": False},
                ),
                vol.Required(stammdaten.ABSCHNITT_LADEN): data_entry_flow.section(
                    vol.Schema(
                        {
                            vol.Required(
                                stammdaten.FELD_MAX_LADELEISTUNG,
                                default=vor(stammdaten.FELD_MAX_LADELEISTUNG),
                            ): positiv,
                        }
                    ),
                    {"collapsed": False},
                ),
                vol.Required(stammdaten.ABSCHNITT_FAHREN): data_entry_flow.section(
                    vol.Schema(
                        {
                            vol.Required(
                                stammdaten.FELD_VERBRAUCH,
                                default=vor(stammdaten.FELD_VERBRAUCH),
                            ): positiv,
                        }
                    ),
                    {"collapsed": False},
                ),
                vol.Required(stammdaten.ABSCHNITT_LAUFZEIT): data_entry_flow.section(
                    vol.Schema(laufzeit), {"collapsed": False},
                ),
                vol.Required(stammdaten.ABSCHNITT_ERWEITERT): data_entry_flow.section(
                    vol.Schema(
                        {
                            vol.Optional(
                                stammdaten.FELD_MIN_LADELEISTUNG,
                                default=vor(stammdaten.FELD_MIN_LADELEISTUNG),
                            ): positiv,
                            vol.Optional(
                                stammdaten.FELD_WIRKUNGSGRAD,
                                default=vor(stammdaten.FELD_WIRKUNGSGRAD),
                            ): vol.All(
                                vol.Coerce(float),
                                vol.Range(min=0, max=100, min_included=False),
                            ),
                        }
                    ),
                    {"collapsed": True},
                ),
            }
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Neues Fahrzeug anlegen."""
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=self._schema({}))

        daten = stammdaten.flach_aus_abschnitten(
            user_input, stammdaten.ABSCHNITTE_FAHRZEUG)
        if (fehler := self._pruefen(daten)) is not None:
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
        if (fehler := self._pruefen(daten)) is not None:
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

    @staticmethod
    def _pruefen(daten: dict[str, Any]) -> dict[str, str] | None:
        """Die eine Bedingung ueber zwei Felder hinweg.

        Voluptuous prueft jedes Feld fuer sich; dass der Boden unter der
        Decke liegt, sieht es nicht.
        """
        if daten[stammdaten.FELD_SOC_MIN] >= daten[stammdaten.FELD_SOC_MAX]:
            return {"base": "soc_range"}
        return None


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
