"""Der Standort-Koordinator in Home Assistant: Ausloeser, Buendelung, Timer.

Was C5 entscheidet, steht in standort.py und ist dort ohne Home Assistant
geprueft. Hier steht nur die Verdrahtung: welche Ereignisse einen Plan
ausloesen, dass nur ein Aufruf zur Zeit laeuft, wann nachgeholt wird und wann
das Repair-Issue kommt. Das sieht kein automatischer Test, nur die Abnahme.

Der Grundtakt laeuft nicht ueber update_interval: DataUpdateCoordinator
taktet nur, solange er Listener hat, und C5 legt keine Entitaet an. Den Takt
haelt deshalb ein eigener Timer.

Spec: meteo-volt-brain/docs/features/C5-standort-koordinator/spec.md
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.event import (
    async_call_later,
    async_track_point_in_utc_time,
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from . import stammdaten, standort
from .api import MeteoVoltApiClient
from .const import DOMAIN, ISSUE_PLAN_VERALTET
from .planabruf import PlanFehler

_LOGGER = logging.getLogger(__name__)


class MeteoVoltPlanKoordinator(DataUpdateCoordinator[standort.Planstand]):
    """Ein Koordinator je Eintrag, also je Standort. Spec C5 Abschnitt 9.

    data ist immer ein Planstand, nie None. Ein PlanFehler macht den
    Koordinator nicht unavailable, er steht in data.fehler.
    """

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: MeteoVoltApiClient
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_plan",
            update_interval=None,
            # Spec Abschnitt 6: der erste Ausloeser geht sofort raus, weitere
            # binnen 30 s ergeben einen einzigen Request am Ende der 30 s.
            request_refresh_debouncer=Debouncer(
                hass, _LOGGER, cooldown=standort.BUENDELN_S, immediate=True
            ),
        )
        self.client = client
        self.data = standort.Planstand()
        # Der Plan-Client haelt gleichzeitige Aufrufe nicht auseinander
        # (C7-Spec Abschnitt 4). Die Dev-Action umgeht die Buendelung, diese
        # Sperre nicht.
        self._sperre = asyncio.Lock()
        self._ausloeser: set[str] = set()
        self._takt = standort.WEITER_IM_GRUNDTAKT
        self._letzte_fehlerklasse: str | None = None
        self._subentries = self._subentry_abbild()
        # Ab hier zaehlt das Repair-Issue, solange kein Plan kam: der Start,
        # oder das erste Fahrzeug, wenn es spaeter angelegt wird.
        self._seit = dt_util.utcnow()
        self._nachholen_abbrechen: Callable[[], None] | None = None
        self._issue_abbrechen: Callable[[], None] | None = None
        self._entitaeten_abbrechen: list[Callable[[], None]] = []

    # --- Start und Ende ---------------------------------------------------

    @callback
    def async_starten(self) -> None:
        """Verdrahtet Ausloeser und Timer und kehrt sofort zurueck."""
        entry = self.config_entry
        entry.async_on_unload(self._aufraeumen)
        entry.async_on_unload(entry.add_update_listener(self._eintrag_geaendert))
        entry.async_on_unload(
            async_track_time_interval(
                self.hass,
                self._grundtakt,
                standort.GRUNDTAKT,
                name=f"{DOMAIN} Grundtakt",
                cancel_on_shutdown=True,
            )
        )
        # Startet Home Assistant, dann erst, wenn es gestartet ist: vorher
        # fehlen die Ladestaende anderer Integrationen noch. Beim Neuladen des
        # Eintrags laeuft das sofort.
        entry.async_on_unload(async_at_started(self.hass, self._beim_start))
        self._entitaeten_anmelden()
        self._issue_pruefung_planen()

    @callback
    def _aufraeumen(self) -> None:
        self._nachholen_absagen()
        if self._issue_abbrechen is not None:
            self._issue_abbrechen()
            self._issue_abbrechen = None
        self._entitaeten_abmelden()
        ir.async_delete_issue(self.hass, DOMAIN, self._issue_id)

    # --- Ausloeser, Spec Abschnitt 6 ----------------------------------------

    @callback
    def _ausloesen(self, kennung: str) -> None:
        """Merkt die Kennung fuer das Debug-Log und fordert gebuendelt an."""
        self._ausloeser.add(kennung)
        self.config_entry.async_create_background_task(
            self.hass, self.async_request_refresh(), name=f"{DOMAIN} Plan {kennung}"
        )

    @callback
    def _beim_start(self, _hass: HomeAssistant) -> None:
        self._ausloesen("start")

    @callback
    def _grundtakt(self, jetzt: datetime) -> None:
        # Spec Abschnitt 7: nach abgelehnt nur der Herzschlag, nach einem
        # Key-Fehler nichts.
        kennung = standort.takt_ausloeser(self._takt, self.data.letzter_versuch_um, jetzt)
        if kennung is not None:
            self._ausloesen(kennung)

    async def _eintrag_geaendert(self, _hass: HomeAssistant, _entry: ConfigEntry) -> None:
        """Nur geaenderte Subentries zaehlen.

        Eine Aenderung am Haupteintrag laedt den Eintrag ohnehin neu (S2). Hier
        wird nicht neu geladen: das holte jedes Mal die Prognose mit, und die
        Sensoren wuerden kurz unavailable.
        """
        abbild = self._subentry_abbild()
        if abbild == self._subentries:
            return
        hatte_fahrzeuge = self._hat_fahrzeuge(self._subentries)
        self._subentries = abbild
        if not self._hat_fahrzeuge(abbild):
            ir.async_delete_issue(self.hass, DOMAIN, self._issue_id)
        elif not hatte_fahrzeuge:
            self._seit = dt_util.utcnow()
        self._issue_pruefung_planen()
        self._entitaeten_anmelden()
        self._ausloesen("subentry")

    @callback
    def _stecker_geaendert(self, event: Event[EventStateChangedData]) -> None:
        # Spec Abschnitt 6: nur off -> on ist Einstecken. Aus unavailable oder
        # beim Start aus dem Nichts nicht -- sonst ginge beim Start ein Request
        # vor start raus, und eine flatternde Cloud-Entitaet loeste staendig aus.
        neu, alt = event.data["new_state"], event.data["old_state"]
        if neu is not None and alt is not None and alt.state == "off" and neu.state == "on":
            self._ausloesen("stecker")

    @callback
    def _ladestand_geaendert(self, event: Event[EventStateChangedData]) -> None:
        """Nur fuer ein Fahrzeug, das wegen seines Ladestands fehlt."""
        neu = event.data["new_state"]
        if neu is None or standort.ladestand_lesen(neu.state) is None:
            return
        for fahrzeug_id, daten in self._subentries_vom_typ(stammdaten.TYP_FAHRZEUG):
            if (
                daten.get(stammdaten.FELD_SOC_ENTITAET) == event.data["entity_id"]
                and self.data.ausgelassen.get(fahrzeug_id) == standort.GRUND_LADESTAND
            ):
                self._ausloesen("ladestand")
                return

    @callback
    def _nachholen(self, _jetzt: datetime) -> None:
        self._nachholen_abbrechen = None
        self._ausloesen("nachholen")

    async def async_jetzt_planen(self) -> standort.Planstand:
        """Fuer die Dev-Action: sofort, ohne Buendelung, nie an der Sendepause vorbei."""
        self._ausloeser.add("dev")
        await self.async_refresh()
        return self.data

    # --- Der Lauf ----------------------------------------------------------

    async def _async_update_data(self) -> standort.Planstand:
        """Ein Lauf. Wirft nie fuer einen PlanFehler, der steht im Planstand."""
        async with self._sperre:
            kennung = ",".join(sorted(self._ausloeser)) or "grundtakt"
            # Spec Abschnitt 7: ein Nachholversuch, der selbst scheitert, plant
            # keinen weiteren.
            nur_nachholen = self._ausloeser == {"nachholen"}
            self._ausloeser.clear()
            # Spec Abschnitt 7: ein Nachholversuch entfaellt, wenn vorher ein
            # anderer Aufruf kommt.
            self._nachholen_absagen()
            if self._takt == standort.STOPP:
                # Spec Abschnitt 7: nach einem Key-Fehler geht nichts mehr raus,
                # bis ein neuer Key den Eintrag neu laedt oder HA neu startet.
                _LOGGER.debug("Plan %s: gestoppt nach einem Key-Fehler, nichts gesendet", kennung)
                return self.data

            anfrage, ausgelassen = standort.anfrage_bauen(
                self._subentries_vom_typ(stammdaten.TYP_LADEPUNKT),
                self._subentries_vom_typ(stammdaten.TYP_FAHRZEUG),
                self._messungen(),
                dict(self.config_entry.data),
                self.hass.config.time_zone,
            )
            stand = replace(self.data, anfrage=anfrage, ausgelassen=ausgelassen)
            if anfrage is None:
                # Spec Abschnitt 3: kein Request, der gehaltene Plan bleibt.
                _LOGGER.debug("Plan %s: kein planbares Fahrzeug, nichts gesendet", kennung)
                return stand

            versuch_um = dt_util.utcnow()
            try:
                plan = await self.client.async_create_plan(self.hass, anfrage)
            except PlanFehler as fehler:
                stand = replace(stand, fehler=fehler, letzter_versuch_um=versuch_um)
            else:
                stand = replace(
                    stand,
                    plan=plan,
                    erhalten_um=dt_util.utcnow(),
                    fehler=None,
                    letzter_versuch_um=versuch_um,
                )
            # Kennung und Ergebnisklasse, nie Inhalt: im Request stehen
            # Ladestaende (Basiskontrakt 3.7).
            _LOGGER.debug(
                "Plan %s: %s",
                kennung,
                "erhalten" if stand.fehler is None else type(stand.fehler).__name__,
            )
            self._nach_dem_aufruf(stand, nur_nachholen)
            return stand

    @callback
    def _nach_dem_aufruf(self, stand: standort.Planstand, nur_nachholen: bool) -> None:
        art, sekunden = standort.naechster_versuch(stand.fehler, nur_nachholen)
        # Ein Nachholversuch laeuft neben dem Grundtakt, er ersetzt ihn nicht.
        self._takt = standort.WEITER_IM_GRUNDTAKT if art == standort.NACHHOLEN else art
        if art == standort.NACHHOLEN:
            self._nachholen_abbrechen = async_call_later(self.hass, sekunden, self._nachholen)

        klasse = None if stand.fehler is None else type(stand.fehler).__name__
        if klasse is not None and klasse != self._letzte_fehlerklasse:
            # Spec Abschnitt 7: einmal, wenn er auftritt oder die Klasse wechselt.
            _LOGGER.warning(
                "Kein neuer Ladeplan: %s: %s%s",
                klasse,
                stand.fehler,
                " -- gestoppt bis zu einem neuen API-Key oder einem Neustart"
                if art == standort.STOPP
                else "",
            )
        self._letzte_fehlerklasse = klasse

        if stand.fehler is None:
            ir.async_delete_issue(self.hass, DOMAIN, self._issue_id)
            self._issue_pruefung_planen(stand)
        else:
            # Spec Abschnitt 8: jeder weitere Fehlschlag schreibt den Text neu.
            self._issue_anlegen_wenn_faellig(stand, dt_util.utcnow())

    @callback
    def _nachholen_absagen(self) -> None:
        if self._nachholen_abbrechen is not None:
            self._nachholen_abbrechen()
            self._nachholen_abbrechen = None

    # --- Repair-Issue, Spec Abschnitt 8 -------------------------------------

    @property
    def _issue_id(self) -> str:
        return f"{ISSUE_PLAN_VERALTET}_{self.config_entry.entry_id}"

    @callback
    def _issue_pruefung_planen(self, stand: standort.Planstand | None = None) -> None:
        """Das Issue haengt an der Uhr, nicht am naechsten Versuch.

        Nach abgelehnt pausiert der Grundtakt. Ein Issue, das erst beim
        naechsten Versuch geprueft wuerde, kaeme dann nie.
        """
        if self._issue_abbrechen is not None:
            self._issue_abbrechen()
        faellig_um = standort.issue_pruefen_um(stand or self.data, self._seit)
        self._issue_abbrechen = async_track_point_in_utc_time(
            self.hass, self._issue_pruefen, faellig_um
        )

    @callback
    def _issue_pruefen(self, jetzt: datetime) -> None:
        self._issue_abbrechen = None
        self._issue_anlegen_wenn_faellig(self.data, jetzt)

    @callback
    def _issue_anlegen_wenn_faellig(self, stand: standort.Planstand, jetzt: datetime) -> None:
        """Legt das Issue an oder ersetzt seinen Text, wenn es faellig ist."""
        hat_fahrzeuge = self._hat_fahrzeuge(self._subentries)
        if standort.issue_faellig(stand, self._seit, jetzt, hat_fahrzeuge):
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                self._issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key=ISSUE_PLAN_VERALTET,
                translation_placeholders={"fehler": standort.issue_text(stand)},
            )

    # --- Lesen aus Home Assistant --------------------------------------------

    def _subentries_vom_typ(self, typ: str) -> list[tuple[str, dict]]:
        """(subentry_id, data) in Anlagereihenfolge."""
        return [
            (subentry.subentry_id, dict(subentry.data))
            for subentry in self.config_entry.subentries.values()
            if subentry.subentry_type == typ
        ]

    def _subentry_abbild(self) -> dict[str, tuple[str, dict]]:
        return {
            subentry.subentry_id: (subentry.subentry_type, dict(subentry.data))
            for subentry in self.config_entry.subentries.values()
        }

    @staticmethod
    def _hat_fahrzeuge(abbild: dict[str, tuple[str, dict]]) -> bool:
        return any(typ == stammdaten.TYP_FAHRZEUG for typ, _ in abbild.values())

    def _messungen(self) -> dict[str, standort.Messung | None]:
        """Die Ladestand-Entitaet je Fahrzeug, None wenn sie fehlt."""
        messungen: dict[str, standort.Messung | None] = {}
        for fahrzeug_id, daten in self._subentries_vom_typ(stammdaten.TYP_FAHRZEUG):
            zustand = self.hass.states.get(daten.get(stammdaten.FELD_SOC_ENTITAET) or "")
            messungen[fahrzeug_id] = (
                None
                if zustand is None
                # last_reported, nicht last_changed (Spec C5 Abschnitt 3): ein gleichbleibender
                # Ladestand, den die Integration neu meldet, gilt als frisch.
                else standort.Messung(zustand=zustand.state, gemeldet=zustand.last_reported)
            )
        return messungen

    def was_gilt_jetzt(self) -> dict[str, dict]:
        """Fuer die Dev-Action: was je Fahrzeug gerade gilt, mit dem aktuellen Ladestand."""
        jetzt = dt_util.utcnow()
        return {
            fahrzeug_id: standort.was_gilt(
                self.data,
                fahrzeug_id,
                jetzt,
                standort.ladestand_lesen(None if messung is None else messung.zustand),
            )
            for fahrzeug_id, messung in self._messungen().items()
        }

    @callback
    def _entitaeten_anmelden(self) -> None:
        """Angesteckt- und Ladestand-Entitaeten aller Fahrzeuge, neu angemeldet."""
        self._entitaeten_abmelden()
        fahrzeuge = [daten for _, daten in self._subentries_vom_typ(stammdaten.TYP_FAHRZEUG)]
        for feld, reaktion in (
            (stammdaten.FELD_ANGESTECKT, self._stecker_geaendert),
            (stammdaten.FELD_SOC_ENTITAET, self._ladestand_geaendert),
        ):
            entitaeten = sorted({daten[feld] for daten in fahrzeuge if daten.get(feld)})
            if entitaeten:
                self._entitaeten_abbrechen.append(
                    async_track_state_change_event(self.hass, entitaeten, reaktion)
                )

    @callback
    def _entitaeten_abmelden(self) -> None:
        while self._entitaeten_abbrechen:
            self._entitaeten_abbrechen.pop()()
