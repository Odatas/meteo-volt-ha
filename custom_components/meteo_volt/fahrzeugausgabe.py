"""Die Ausgabe je Fahrzeug in Home Assistant: Ausloeser, Timer, Issue.

Was C6 entscheidet, steht in ausgabe.py und ist dort ohne Home Assistant
geprueft. Hier steht nur die Verdrahtung: wann ein Fahrzeug ausgewertet wird,
wie seine Entitaeten davon erfahren, wann das Abweichungs-Issue kommt und geht
und wie Entitaeten fuer spaeter angelegte Fahrzeuge entstehen. Das sieht kein
automatischer Test, nur die Abnahme.

Spec: meteo-volt-brain/docs/features/C6-ausgabe-entitaeten/spec.md
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity, EntityDescription
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import (
    async_track_point_in_utc_time,
    async_track_state_change_event,
)
from homeassistant.util import dt as dt_util

from . import ausgabe, stammdaten, standort
from .const import DOMAIN, ISSUE_ABWEICHUNG
from .plankoordinator import MeteoVoltPlanKoordinator

# hass.data[AUSGABEN][entry_id]. Nicht unter hass.data[DOMAIN]: das lesen die
# sechs Sensoren (Bestandsschutz Auflage 5).
AUSGABEN = f"{DOMAIN}_ausgaben"


class Fahrzeugausgabe:
    """Wertet ein Fahrzeug aus und meldet es seinen Entitaeten. Spec Abschnitt 4."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        koordinator: MeteoVoltPlanKoordinator,
        fahrzeug_id: str,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.koordinator = koordinator
        self.fahrzeug_id = fahrzeug_id
        self.auswertung: ausgabe.Auswertung | None = None
        self._zustand = ausgabe.Zustand()
        self._daten: dict | None = None
        self._zuhoerer: list[Callable[[], None]] = []
        self._koordinator_abmelden: CALLBACK_TYPE | None = None
        self._ladestand: tuple[str, CALLBACK_TYPE] | None = None
        self._timer: CALLBACK_TYPE | None = None

    @property
    def device_info(self) -> DeviceInfo:
        """Spec Abschnitt 7. Den Namen schreibt Home Assistant nur beim Anlegen."""
        subentry = self.entry.subentries.get(self.fahrzeug_id)
        return DeviceInfo(
            identifiers={(DOMAIN, self.fahrzeug_id)},
            name=None if subentry is None else subentry.title,
            manufacturer="Meteo-Volt",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def _issue_id(self) -> str:
        return f"{ISSUE_ABWEICHUNG}_{self.fahrzeug_id}"

    @callback
    def async_starten(self) -> None:
        self._koordinator_abmelden = self.koordinator.async_add_listener(self._koordinator_meldet)
        self._auswerten()

    @callback
    def async_beenden(self) -> None:
        """Timer, Listener und Issue gehen mit dem Fahrzeug oder dem Eintrag."""
        if self._koordinator_abmelden is not None:
            self._koordinator_abmelden()
            self._koordinator_abmelden = None
        self._ladestand_abmelden()
        self._timer_absagen()
        ir.async_delete_issue(self.hass, DOMAIN, self._issue_id)

    @callback
    def async_zuhoeren(self, zuhoerer: Callable[[], None]) -> CALLBACK_TYPE:
        self._zuhoerer.append(zuhoerer)

        @callback
        def abmelden() -> None:
            self._zuhoerer.remove(zuhoerer)

        return abmelden

    # --- Anlaesse, Spec Abschnitt 4 ------------------------------------------

    @callback
    def _koordinator_meldet(self) -> None:
        daten = self._fahrzeugdaten()
        if daten is None:
            return  # geloescht; Fahrzeugausgaben raeumt auf
        if self._daten is not None and daten != self._daten:
            # Spec Abschnitt 6: aendern sich die Daten des Fahrzeugs, beginnt
            # die Messung neu, und das Issue geht.
            self._zustand = replace(self._zustand, abgleich=ausgabe.Abgleich())
            ir.async_delete_issue(self.hass, DOMAIN, self._issue_id)
        self._auswerten()

    @callback
    def _ladestand_meldet(self, _event: Event[EventStateChangedData]) -> None:
        self._auswerten()

    @callback
    def _timer_meldet(self, _jetzt: datetime) -> None:
        self._timer = None
        self._auswerten()

    # --- Die Auswertung --------------------------------------------------------

    @callback
    def _auswerten(self) -> None:
        daten = self._fahrzeugdaten()
        if daten is None:
            return
        self._daten = daten
        entitaet = daten.get(stammdaten.FELD_SOC_ENTITAET)
        self._ladestand_anmelden(entitaet)
        zustand = self.hass.states.get(entitaet) if entitaet else None
        self.auswertung = ausgabe.auswerten(
            self.koordinator.data,
            self.fahrzeug_id,
            dt_util.utcnow(),
            None if zustand is None else standort.ladestand_lesen(zustand.state),
            None if zustand is None else zustand.last_reported,
            self._zustand,
        )
        self._zustand = self.auswertung.zustand
        if self.auswertung.bewertung is not None:
            self._issue(self.auswertung.bewertung)
        self._timer_absagen()
        self._timer = async_track_point_in_utc_time(
            self.hass, self._timer_meldet, self.auswertung.naechste
        )
        for zuhoerer in list(self._zuhoerer):
            zuhoerer()

    @callback
    def _issue(self, bewertung: ausgabe.Bewertung) -> None:
        """Spec Abschnitt 6: ueber 5 % anlegen, sonst entfernen."""
        if not bewertung.ausserhalb:
            ir.async_delete_issue(self.hass, DOMAIN, self._issue_id)
            return
        subentry = self.entry.subentries.get(self.fahrzeug_id)
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            self._issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=ausgabe.issue_uebersetzung(bewertung),
            translation_placeholders=ausgabe.issue_platzhalter(
                bewertung,
                self.fahrzeug_id if subentry is None else subentry.title,
                self.hass.config.language,
            ),
        )

    # --- Hilfen -----------------------------------------------------------------

    def _fahrzeugdaten(self) -> dict | None:
        subentry = self.entry.subentries.get(self.fahrzeug_id)
        return None if subentry is None else dict(subentry.data)

    @callback
    def _ladestand_anmelden(self, entitaet: str | None) -> None:
        """Spec Abschnitt 4: bei der alten Ladestand-Entitaet ab, bei der neuen an."""
        if self._ladestand is not None and self._ladestand[0] == entitaet:
            return
        self._ladestand_abmelden()
        if entitaet:
            self._ladestand = (
                entitaet,
                async_track_state_change_event(self.hass, [entitaet], self._ladestand_meldet),
            )

    @callback
    def _ladestand_abmelden(self) -> None:
        if self._ladestand is not None:
            self._ladestand[1]()
            self._ladestand = None

    @callback
    def _timer_absagen(self) -> None:
        if self._timer is not None:
            self._timer()
            self._timer = None


class Fahrzeugausgaben:
    """Die Auswertungen aller Fahrzeuge eines Eintrags."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, koordinator: MeteoVoltPlanKoordinator
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.koordinator = koordinator
        self._ausgaben: dict[str, Fahrzeugausgabe] = {}

    @callback
    def async_starten(self) -> None:
        self.entry.async_on_unload(self.koordinator.async_add_listener(self._aufraeumen))
        self.entry.async_on_unload(self._alle_beenden)

    def fahrzeug_ids(self) -> list[str]:
        return [
            subentry.subentry_id
            for subentry in self.entry.subentries.values()
            if subentry.subentry_type == stammdaten.TYP_FAHRZEUG
        ]

    @callback
    def fuer(self, fahrzeug_id: str) -> Fahrzeugausgabe:
        if fahrzeug_id not in self._ausgaben:
            neu = Fahrzeugausgabe(self.hass, self.entry, self.koordinator, fahrzeug_id)
            self._ausgaben[fahrzeug_id] = neu
            neu.async_starten()
        return self._ausgaben[fahrzeug_id]

    @callback
    def _aufraeumen(self) -> None:
        """Spec Abschnitt 7: ein geloeschtes Fahrzeug beendet Timer, Listener und Issue."""
        for fahrzeug_id in list(self._ausgaben):
            if fahrzeug_id not in self.entry.subentries:
                self._ausgaben.pop(fahrzeug_id).async_beenden()

    @callback
    def _alle_beenden(self) -> None:
        for fahrzeugausgabe in self._ausgaben.values():
            fahrzeugausgabe.async_beenden()
        self._ausgaben.clear()


class FahrzeugEntitaet(Entity):
    """Eine der acht Entitaeten eines Fahrzeugs. Traegt die letzte Auswertung."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, fahrzeugausgabe: Fahrzeugausgabe, beschreibung: EntityDescription) -> None:
        self.entity_description = beschreibung
        self._fahrzeugausgabe = fahrzeugausgabe
        # Spec Abschnitt 2: meteo_volt_{subentry_id}_{schluessel}
        self._attr_unique_id = f"{DOMAIN}_{fahrzeugausgabe.fahrzeug_id}_{beschreibung.key}"
        self._attr_device_info = fahrzeugausgabe.device_info

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._fahrzeugausgabe.async_zuhoeren(self.async_write_ha_state))

    @property
    def _wert(self):
        auswertung = self._fahrzeugausgabe.auswertung
        return None if auswertung is None else auswertung.werte[self.entity_description.key]

    @property
    def extra_state_attributes(self) -> dict | None:
        auswertung = self._fahrzeugausgabe.auswertung
        if auswertung is None:
            return None
        return auswertung.attribute.get(self.entity_description.key) or None


@callback
def fahrzeuge_anbinden(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
    bauen: Callable[[Fahrzeugausgabe], list[Entity]],
) -> None:
    """Legt die Entitaeten jedes Fahrzeugs an, jetzt und fuer spaeter angelegte.

    Spec Abschnitt 7: ohne Neuladen des Eintrags. C5 loest bei einem neuen
    Fahrzeug einen Lauf aus, und danach meldet sich der Koordinator hier.
    Ohne Koordinator entsteht keine Entitaet (Abschnitt 8).
    """
    ausgaben: Fahrzeugausgaben | None = hass.data.get(AUSGABEN, {}).get(entry.entry_id)
    if ausgaben is None:
        return
    angelegt: set[str] = set()

    @callback
    def anlegen() -> None:
        vorhanden = ausgaben.fahrzeug_ids()
        angelegt.intersection_update(vorhanden)
        for fahrzeug_id in vorhanden:
            if fahrzeug_id not in angelegt:
                angelegt.add(fahrzeug_id)
                async_add_entities(
                    bauen(ausgaben.fuer(fahrzeug_id)), config_subentry_id=fahrzeug_id
                )

    anlegen()
    entry.async_on_unload(ausgaben.koordinator.async_add_listener(anlegen))
