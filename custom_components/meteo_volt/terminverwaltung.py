"""Die Termine in Home Assistant: Store, Schritte, Meldungen an das Panel, neu planen.

Was C3 entscheidet, steht in termine.py, pruefungen.py, terminbuch.py,
terminanfrage.py und ansicht.py und ist dort ohne Home Assistant geprueft.
Hier steht nur die Verdrahtung: der Store je Standort, die Schritte im
Speicher, die Meldungen an das Panel und die Ausloeser an C5. Das sieht kein
automatischer Test, nur die Abnahme.

Geladen wird dieses Modul nur im try (Spec Abschnitt 8): scheitert es,
laufen Prognose, Plan und die Entitaeten aus C6 weiter, und C5 plant ohne
Termine.

Spec: meteo-volt-brain/docs/features/C3-konfig-entitaeten/spec.md, Abschnitte 3 bis 8
"""

from __future__ import annotations

import uuid
from collections import deque
from datetime import date, datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send
from homeassistant.helpers.event import (
    async_track_state_added_domain,
    async_track_state_change_event,
    async_track_state_removed_domain,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from . import (
    ansicht, ladereserve, pruefungen, stammdaten, standort, terminanfrage, terminbuch, termine,
)
from .const import CONF_GRID_FEES, DOMAIN, SIGNAL_PLANUNG
from .plankoordinator import MeteoVoltPlanKoordinator

# hass.data[VERWALTUNGEN][entry_id]. Nicht unter hass.data[DOMAIN]: das lesen
# die sechs Sensoren (Bestandsschutz Auflage 5).
VERWALTUNGEN = f"{DOMAIN}_termine"
# hass.data[SCHRITTE][entry_id]: die Schritte ueberleben das Neuladen eines
# Eintrags, nicht den Neustart (Spec Abschnitt 2.2).
SCHRITTE = f"{DOMAIN}_schritte"

SPEICHER_VERSION = 1

# Meldungen an das Panel, Spec Abschnitt 6. Nutzlast ist der Name, ohne Inhalt.
SIGNAL_PANEL = f"{DOMAIN}_panel_{{}}"
TERMINE = "appointments"
STANDORT = "site"
PLAN = "plan"
PLANUNG = "planning"
PREISE = "prices"

# Die Entitaeten aus C6, aus denen meteo_volt/plan liest (C6-Spec Abschnitt 9).
C6_WERTE = (("binary_sensor", "charge_now"), ("sensor", "charge_now_kw"), ("sensor", "next_charge_start"))


def speicher_schluessel(entry_id: str) -> str:
    """Spec Abschnitt 3: ein Store je Standort."""
    return f"{DOMAIN}.termine.{entry_id}"


def _neue_id() -> str:
    """Ohne '/': die IDs im Request setzen sich daraus zusammen (Spec Abschnitt 4)."""
    return uuid.uuid4().hex


class Terminverwaltung:
    """Die Termine eines Standorts."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, koordinator: MeteoVoltPlanKoordinator
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.koordinator = koordinator
        self.buch = terminbuch.Buch()
        self._store: Store = Store(hass, SPEICHER_VERSION, speicher_schluessel(entry.entry_id))
        self._fahrzeuge: set[str] = set()
        self._soc_entitaeten: set[str] = set()
        self._c6_entitaeten: set[str] = set()
        self._personen: set[str] = set()
        self._zustaende_abmelden: CALLBACK_TYPE | None = None

    # --- Start ------------------------------------------------------------------

    async def async_starten(self) -> None:
        schritte = self.hass.data.setdefault(SCHRITTE, {}).setdefault(
            self.entry.entry_id, deque(maxlen=terminbuch.MAX_SCHRITTE))
        # Ohne Datei None: wer nie einen Termin anlegt und nie das Risiko setzt,
        # hat keine (Spec Abschnitt 3). Sie entsteht mit dem ersten Schreiben.
        self.buch = terminbuch.Buch(await self._store.async_load(), schritte)
        self._fahrzeuge = set(self.fahrzeugdaten())
        # Verschwand ein Fahrzeug, waehrend C3 nicht lief, gehen seine Termine jetzt.
        if terminbuch.fahrzeuge_bereinigen(self.buch, self._fahrzeuge):
            await self._speichern()

        entry = self.entry
        entry.async_on_unload(entry.add_update_listener(self._eintrag_geaendert))
        entry.async_on_unload(self.koordinator.async_add_listener(self._plan_geaendert))
        entry.async_on_unload(async_dispatcher_connect(
            self.hass, SIGNAL_PLANUNG.format(entry.entry_id), self._planung_geaendert))
        prognose = self.hass.data.get(DOMAIN, {}).get(entry.entry_id)
        if prognose is not None:
            # Der Rueckruf sendet nur ein Signal und kann die sechs Sensoren
            # nicht aufhalten: der Dispatcher faengt, was dahinter scheitert.
            entry.async_on_unload(prognose.async_add_listener(self._preise_geaendert))
        entry.async_on_unload(async_track_state_added_domain(self.hass, "person", self._person_geaendert))
        entry.async_on_unload(async_track_state_removed_domain(self.hass, "person", self._person_geaendert))
        entry.async_on_unload(self.hass.bus.async_listen(
            er.EVENT_ENTITY_REGISTRY_UPDATED, self._register_geaendert))
        entry.async_on_unload(self._zustaende_abbestellen)
        self._zustaende_bestellen()
        # Zuletzt: erst ab hier traegt jeder Request die Termine.
        self.koordinator.termine_quelle = self.fragmente

    # --- Aus Home Assistant lesen --------------------------------------------------

    def fahrzeugdaten(self) -> dict[str, dict]:
        """subentry_id -> data, in Anlagereihenfolge."""
        return {
            subentry_id: dict(subentry.data)
            for subentry_id, subentry in self.entry.subentries.items()
            if subentry.subentry_type == stammdaten.TYP_FAHRZEUG
        }

    def _titel(self) -> dict[str, str]:
        return {subentry_id: self.entry.subentries[subentry_id].title for subentry_id in self.fahrzeugdaten()}

    def _fahrzeugwerte(self) -> dict[str, ladereserve.Fahrzeugwerte]:
        """Je Fahrzeug, was die Rechnung hinter dem Haken braucht. Spec C10 Abschnitt 2."""
        return {
            fid: ladereserve.Fahrzeugwerte(
                soc_min_pct=float(daten[stammdaten.FELD_SOC_MIN]),
                capacity_kwh=float(daten[stammdaten.FELD_KAPAZITAET]),
                consumption_kwh_per_100km=float(daten[stammdaten.FELD_VERBRAUCH]),
            )
            for fid, daten in self.fahrzeugdaten().items()
        }

    def _soc_min(self) -> dict[str, float]:
        return {fid: werte.soc_min_pct for fid, werte in self._fahrzeugwerte().items()}

    def geraete(self) -> dict[str, str]:
        """subentry_id -> Geraete-ID, fuer jedes Fahrzeug mit Geraet aus C6 (C6-Spec Abschnitt 7)."""
        register = dr.async_get(self.hass)
        geraete = {}
        for fahrzeug_id in self.fahrzeugdaten():
            geraet = register.async_get_device(identifiers={(DOMAIN, fahrzeug_id)})
            if geraet is not None:
                geraete[fahrzeug_id] = geraet.id
        return geraete

    def personen(self) -> dict[str, str]:
        return {zustand.entity_id: zustand.name for zustand in self.hass.states.async_all("person")}

    @property
    def risiko(self) -> int:
        return terminanfrage.RISIKO_VORGABE if self.buch.risiko is None else self.buch.risiko

    @staticmethod
    def zeitzone():
        return dt_util.get_default_time_zone()

    # --- Fuer C5, Spec Abschnitt 4 ------------------------------------------------------

    @callback
    def fragmente(self, stand: standort.Planstand, jetzt: datetime) -> tuple[dict[str, dict], int]:
        bis = terminanfrage.ausrollen_bis(stand.plan, jetzt)
        auswahl = termine.ausrollen(list(self.buch.eintraege.values()), self.zeitzone(), jetzt, bis)
        return terminanfrage.fragmente(auswahl, self._fahrzeugwerte(), jetzt), self.risiko

    # --- Schreiben, Spec Abschnitt 5 --------------------------------------------------------

    async def async_anlegen(self, fahrzeug_id: str, felder: dict) -> dict:
        jetzt = dt_util.utcnow()
        werte = pruefungen.werte_pruefen(felder, fahrzeug_id, jetzt, self.zeitzone())
        schritt, eintraege = terminbuch.anlegen(self.buch, werte, _neue_id)
        await self._nach_schritt()
        return {"step": schritt, "entry": eintraege[0], "warnings": self._warnungen(werte, eintraege[0], jetzt)}

    async def async_aendern(
        self, eintrag_id: str, datum: date, umfang: str | None, fahrzeug_id: str, felder: dict
    ) -> dict:
        eintrag = self.buch.eintraege[eintrag_id]
        if not termine.hat_termin(eintrag, datum):
            raise pruefungen.fehler(pruefungen.TERMIN_UNBEKANNT, "date")
        jetzt = dt_util.utcnow()
        # Fehlt repeat, bleibt die Wiederholung. once waere hier eine stille Aenderung.
        # Fehlt keep_min_soc, bleibt der Haken dieses Termins -- aus der Ausnahme,
        # wenn es eine gibt, sonst aus dem Eintrag (C10-Spec Abschnitt 8).
        vorher = termine.termin_am(eintrag, datum, self.zeitzone())
        werte = pruefungen.werte_pruefen(
            felder, fahrzeug_id, jetzt, self.zeitzone(), eintrag[termine.WIEDERHOLUNG],
            vorgabe_sichern=vorher.sichern)
        schritt, eintraege = terminbuch.aendern(self.buch, eintrag_id, datum, umfang, werte, _neue_id)
        await self._nach_schritt()
        return {"step": schritt, "entries": eintraege, "warnings": self._warnungen(werte, eintraege[0], jetzt)}

    async def async_loeschen(self, eintrag_id: str, datum: date, umfang: str | None) -> dict:
        schritt = terminbuch.loeschen(self.buch, eintrag_id, datum, umfang, _neue_id)
        await self._nach_schritt()
        return {"step": schritt}

    async def async_absagen(self, liste: list[tuple[str, date]], zu_schritt: str | None) -> dict:
        schritt = terminbuch.absagen(self.buch, liste, zu_schritt, _neue_id)
        await self._nach_schritt()
        return {"step": schritt}

    async def async_rueckgaengig(self, schritt: str) -> None:
        terminbuch.rueckgaengig(self.buch, schritt)
        await self._nach_schritt()

    async def async_risiko_setzen(self, risiko: int) -> None:
        """Das Risiko ist kein Schritt (Spec Abschnitt 2.2)."""
        self.buch.risiko = risiko
        await self._speichern()
        self._melden(STANDORT)
        self.koordinator.risiko_geaendert()

    async def async_neu_planen(self) -> None:
        vorher = self.koordinator.data
        nachher = await self.koordinator.async_neu_planen()
        meldung = pruefungen.neu_planen_pruefen(vorher, nachher)
        if meldung is not None:
            raise pruefungen.Terminfehler(meldung)

    async def _nach_schritt(self) -> None:
        await self._speichern()
        self._melden(TERMINE)
        self.koordinator.termine_geaendert()

    async def _speichern(self) -> None:
        """Sofort, nicht verzoegert (Spec Abschnitt 3)."""
        await self._store.async_save(self.buch.speicherform())

    def _warnungen(self, werte: pruefungen.Werte, eintrag_id: str, jetzt: datetime) -> list[dict]:
        meldungen = pruefungen.warnungen(
            werte, eintrag_id, list(self.buch.eintraege.values()), self.zeitzone(), jetzt,
            self._fahrzeugwerte()[werte.fahrzeug], self.personen(), self._titel(), self.hass.config.language)
        return [meldung.als_dict() for meldung in meldungen]

    # --- Lesen, Spec Abschnitt 6 ----------------------------------------------------------

    def standort(self) -> dict:
        geraete = self.geraete()
        fahrzeuge = []
        for fahrzeug_id, daten in self.fahrzeugdaten().items():
            if fahrzeug_id not in geraete:
                continue  # ohne Geraet aus C6 laesst es sich nicht ansprechen
            zustand = self.hass.states.get(daten.get(stammdaten.FELD_SOC_ENTITAET) or "")
            fahrzeuge.append({
                "vehicle": geraete[fahrzeug_id],
                "title": self.entry.subentries[fahrzeug_id].title,
                "soc_min_pct": float(daten[stammdaten.FELD_SOC_MIN]),
                "soc_max_pct": float(daten[stammdaten.FELD_SOC_MAX]),
                "max_charge_kw": float(daten[stammdaten.FELD_MAX_LADELEISTUNG]),
                # C10 rechnet den gesicherten Ladestand im Panel mit; ohne die
                # beiden Werte kann es weder Hinweiszeile noch Warnung zeigen.
                "capacity_kwh": float(daten[stammdaten.FELD_KAPAZITAET]),
                "consumption_kwh_per_100km": float(daten[stammdaten.FELD_VERBRAUCH]),
                "soc_pct": standort.ladestand_lesen(None if zustand is None else zustand.state),
            })
        netzentgelt = self.entry.data.get(CONF_GRID_FEES)
        return {
            "risk": self.risiko,
            # Wie in C5: ein negativer Wert aus einem alten Eintrag zaehlt als keiner.
            "grid_fees": None if netzentgelt is None or float(netzentgelt) < 0 else float(netzentgelt),
            "vehicles": fahrzeuge,
            "persons": [{"entity_id": eid, "name": name} for eid, name in self.personen().items()],
        }

    def termine_im_fenster(self, start: datetime, ende: datetime, fahrzeug_id: str | None) -> list[dict]:
        """Die Termine, deren Rueckkehr nach start und deren Abfahrt vor ende liegt."""
        tz = self.zeitzone()
        eintraege = list(self.buch.eintraege.values())
        auswahl = termine.ausrollen(eintraege, tz, start, ende, fahrzeug_id)
        umfeld: list[termine.Termin] = []
        if auswahl:
            # Die Hinweise brauchen alle Termine aller Fahrzeuge, die einen der
            # gewaehlten ueberschneiden koennten, auch ausserhalb des Fensters.
            von = min((t.abfahrt for t in auswahl), key=termine.utc)
            bis = max((t.rueckkehr for t in auswahl), key=termine.utc)
            umfeld = termine.ausrollen(eintraege, tz, von, bis)
        return ansicht.termine_ansicht(
            auswahl, umfeld, self.koordinator.data, dt_util.utcnow(), self._soc_min(), self.geraete(),
            set(self.personen()))

    def plan(self, fahrzeug_id: str) -> dict:
        register = er.async_get(self.hass)
        werte = {}
        for plattform, schluessel in C6_WERTE:
            entity_id = register.async_get_entity_id(plattform, DOMAIN, f"{DOMAIN}_{fahrzeug_id}_{schluessel}")
            zustand = self.hass.states.get(entity_id) if entity_id else None
            werte[schluessel] = ansicht.c6_wert(schluessel, None if zustand is None else zustand.state, self.zeitzone())
        return ansicht.fahrzeugplan(self.koordinator.data, fahrzeug_id, werte, self.koordinator.plant)

    def preise(self) -> dict:
        prognose = self.hass.data.get(DOMAIN, {}).get(self.entry.entry_id)
        return ansicht.preise(None if prognose is None else prognose.data, dt_util.utcnow())

    # --- Meldungen an das Panel, Spec Abschnitt 6 --------------------------------------

    @callback
    def _melden(self, meldung: str) -> None:
        async_dispatcher_send(self.hass, SIGNAL_PANEL.format(self.entry.entry_id), meldung)

    async def _eintrag_geaendert(self, _hass: HomeAssistant, _entry: ConfigEntry) -> None:
        """Spec Abschnitt 7: ein geloeschtes Fahrzeug nimmt seine Termine mit."""
        fahrzeuge = set(self.fahrzeugdaten())
        if fahrzeuge != self._fahrzeuge:
            self._fahrzeuge = fahrzeuge
            if terminbuch.fahrzeuge_bereinigen(self.buch, fahrzeuge):
                await self._speichern()
                self._melden(TERMINE)
        self._zustaende_bestellen()
        self._melden(STANDORT)

    @callback
    def _plan_geaendert(self) -> None:
        self._melden(PLAN)

    @callback
    def _planung_geaendert(self, _plant: bool) -> None:
        self._melden(PLANUNG)

    @callback
    def _preise_geaendert(self) -> None:
        self._melden(PREISE)

    @callback
    def _person_geaendert(self, _event: Event) -> None:
        """Eine Person kam oder ging: neu beobachten, damit auch ihr Name zaehlt."""
        self._zustaende_bestellen()
        self._melden(STANDORT)

    @callback
    def _register_geaendert(self, event: Event) -> None:
        """Legt C6 die Entitaeten eines Fahrzeugs an, werden sie ab jetzt beobachtet.

        Mit ihnen entsteht das Geraet, und erst mit ihm steht das Fahrzeug in site.
        """
        if event.data.get("action") not in ("create", "remove", "update"):
            return
        vorher = self._c6_entitaeten
        self._zustaende_bestellen()
        if self._c6_entitaeten != vorher:
            self._melden(STANDORT)
            self._melden(PLAN)

    @callback
    def _zustaende_bestellen(self) -> None:
        """Ladestand-Entitaeten und Personen melden site, die drei Entitaeten aus C6 plan."""
        self._zustaende_abbestellen()
        register = er.async_get(self.hass)
        fahrzeuge = self.fahrzeugdaten()
        self._soc_entitaeten = {
            daten[stammdaten.FELD_SOC_ENTITAET] for daten in fahrzeuge.values()
            if daten.get(stammdaten.FELD_SOC_ENTITAET)
        }
        self._personen = set(self.hass.states.async_entity_ids("person"))
        self._c6_entitaeten = set()
        for fahrzeug_id in fahrzeuge:
            for plattform, schluessel in C6_WERTE:
                entity_id = register.async_get_entity_id(plattform, DOMAIN, f"{DOMAIN}_{fahrzeug_id}_{schluessel}")
                if entity_id:
                    self._c6_entitaeten.add(entity_id)
        alle = sorted(self._soc_entitaeten | self._c6_entitaeten | self._personen)
        if alle:
            self._zustaende_abmelden = async_track_state_change_event(self.hass, alle, self._zustand_geaendert)

    @callback
    def _zustaende_abbestellen(self) -> None:
        if self._zustaende_abmelden is not None:
            self._zustaende_abmelden()
            self._zustaende_abmelden = None

    @callback
    def _zustand_geaendert(self, event: Event[EventStateChangedData]) -> None:
        entity_id = event.data["entity_id"]
        if entity_id in self._soc_entitaeten:
            self._melden(STANDORT)
        if entity_id in self._c6_entitaeten:
            self._melden(PLAN)
        if entity_id in self._personen:
            # Nur ein neuer Name aendert site, nicht wer gerade zu Hause ist.
            alt, neu = event.data["old_state"], event.data["new_state"]
            if alt is None or neu is None or alt.name != neu.name:
                self._melden(STANDORT)


# --- Start, Standorte, Ende ----------------------------------------------------------------


async def async_termine_starten(
    hass: HomeAssistant, entry: ConfigEntry, koordinator: MeteoVoltPlanKoordinator
) -> None:
    verwaltung = Terminverwaltung(hass, entry, koordinator)
    await verwaltung.async_starten()
    hass.data.setdefault(VERWALTUNGEN, {})[entry.entry_id] = verwaltung

    def vergessen() -> None:
        # Ohne Rueckgabewert: aus jedem ausser None macht Home Assistant einen
        # Task, und das Entladen scheiterte (C6-Spec Abschnitt 8).
        hass.data[VERWALTUNGEN].pop(entry.entry_id, None)
        koordinator.termine_quelle = None

    entry.async_on_unload(vergessen)


async def async_speicher_entfernen(hass: HomeAssistant, entry_id: str) -> None:
    """Spec Abschnitt 3: entfernt der Nutzer die Integration, geht der Store mit."""
    await Store(hass, SPEICHER_VERSION, speicher_schluessel(entry_id)).async_remove()
    hass.data.get(SCHRITTE, {}).pop(entry_id, None)


def verwaltungen(hass: HomeAssistant) -> dict[str, Terminverwaltung]:
    return hass.data.get(VERWALTUNGEN, {})


def nach_geraet(hass: HomeAssistant, geraet_id: str | None) -> tuple[Terminverwaltung, str]:
    """Standort und subentry_id zur Geraete-ID eines Fahrzeugs, sonst fahrzeug_unbekannt."""
    geraet = dr.async_get(hass).async_get(geraet_id) if geraet_id else None
    alle = verwaltungen(hass)
    entry_id, fahrzeug_id = pruefungen.fahrzeug_aus_geraet(
        set() if geraet is None else set(geraet.identifiers), DOMAIN,
        {eid: set(verwaltung.fahrzeugdaten()) for eid, verwaltung in alle.items()})
    return alle[entry_id], fahrzeug_id


def nach_eintrag(hass: HomeAssistant, eintrag_id: str | None) -> Terminverwaltung:
    for verwaltung in verwaltungen(hass).values():
        if eintrag_id in verwaltung.buch.eintraege:
            return verwaltung
    raise pruefungen.fehler(pruefungen.EINTRAG_UNBEKANNT, "entry")


def nach_schritt(hass: HomeAssistant, schritt: str | None) -> Terminverwaltung:
    for verwaltung in verwaltungen(hass).values():
        if terminbuch.schritt_bekannt(verwaltung.buch, schritt or ""):
            return verwaltung
    raise pruefungen.fehler(pruefungen.RUECKGAENGIG_UNMOEGLICH, "step")


def nach_standort(hass: HomeAssistant, entry_id: str | None) -> Terminverwaltung | None:
    """Ohne config_entry der zuerst geladene Standort, wie bei der Dev-Action.

    In der Reihenfolge der Eintraege, nicht in der von hass.data: nach dem
    Neuladen eines Standorts stuende der sonst hinten.
    """
    alle = verwaltungen(hass)
    if entry_id is not None:
        return alle.get(entry_id)
    for eintrag in hass.config_entries.async_loaded_entries(DOMAIN):
        if eintrag.entry_id in alle:
            return alle[eintrag.entry_id]
    return None
