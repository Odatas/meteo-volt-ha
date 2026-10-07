"""Die Sensoren je Fahrzeug, fuer sensor.py.

Ein eigenes Modul, damit sensor.py es erst nach den sechs Sensoren der
Prognose laedt: scheitert schon der Import, laufen die sechs weiter
(Spec C6 Abschnitt 8).

Spec: meteo-volt-brain/docs/features/C6-ausgabe-entitaeten/spec.md
"""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ausgabe
from .fahrzeugausgabe import FahrzeugEntitaet, Fahrzeugausgabe, fahrzeuge_anbinden

# Spec Abschnitt 2. Keine state_class: Planwerte sind keine Zaehler, und mit
# state_class landeten sie in Langzeitstatistik und Energie-Dashboard.
BESCHREIBUNGEN = (
    SensorEntityDescription(
        key=ausgabe.LADELEISTUNG,
        translation_key=ausgabe.LADELEISTUNG,
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
    ),
    SensorEntityDescription(
        key=ausgabe.NAECHSTER_LADESTART,
        translation_key=ausgabe.NAECHSTER_LADESTART,
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    SensorEntityDescription(
        key=ausgabe.ENERGIE,
        translation_key=ausgabe.ENERGIE,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    ),
    SensorEntityDescription(
        key=ausgabe.KOSTEN,
        translation_key=ausgabe.KOSTEN,
        device_class=SensorDeviceClass.MONETARY,
        # MONETARY verlangt den ISO-4217-Code, nicht das Zeichen.
        native_unit_of_measurement="EUR",
    ),
    SensorEntityDescription(
        key=ausgabe.LADESTAND_PLANENDE,
        translation_key=ausgabe.LADESTAND_PLANENDE,
        # Keine Geraeteklasse battery: sonst sammelten Batterie-Karten eine Prognose ein.
        native_unit_of_measurement=PERCENTAGE,
    ),
    SensorEntityDescription(
        key=ausgabe.LADEPLAN,
        translation_key=ausgabe.LADEPLAN,
        device_class=SensorDeviceClass.ENUM,
        options=list(ausgabe.ZUSTAENDE),
    ),
)


class FahrzeugSensor(FahrzeugEntitaet, SensorEntity):
    """Spec Abschnitt 2. Kein Attribut geht in den Recorder (Abschnitt 3)."""

    _unrecorded_attributes = frozenset(
        {ausgabe.SLOTS, ausgabe.INTERVALS, ausgabe.WARNINGS, ausgabe.FEHLER}
    )

    @property
    def native_value(self):
        return self._wert


def _bauen(fahrzeugausgabe: Fahrzeugausgabe) -> list[FahrzeugSensor]:
    return [FahrzeugSensor(fahrzeugausgabe, b) for b in BESCHREIBUNGEN]


@callback
def fahrzeugsensoren_anbinden(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Die Sensoren aller Fahrzeuge, auch der spaeter angelegten."""
    fahrzeuge_anbinden(hass, entry, async_add_entities, _bauen)
