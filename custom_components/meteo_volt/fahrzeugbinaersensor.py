"""Die Binaersensoren je Fahrzeug, fuer binary_sensor.py.

Ein eigenes Modul, damit binary_sensor.py es erst im try laedt: scheitert
schon der Import, laufen die sechs Sensoren der Prognose weiter (Spec C6
Abschnitt 8).

Spec: meteo-volt-brain/docs/features/C6-ausgabe-entitaeten/spec.md
"""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ausgabe
from .fahrzeugausgabe import FahrzeugEntitaet, Fahrzeugausgabe, fahrzeuge_anbinden

BESCHREIBUNGEN = (
    BinarySensorEntityDescription(key=ausgabe.JETZT_LADEN, translation_key=ausgabe.JETZT_LADEN),
    BinarySensorEntityDescription(key=ausgabe.ERFUELLBAR, translation_key=ausgabe.ERFUELLBAR),
)


class FahrzeugBinaersensor(FahrzeugEntitaet, BinarySensorEntity):
    """Spec Abschnitt 2. Kein Attribut geht in den Recorder (Abschnitt 3)."""

    _unrecorded_attributes = frozenset(
        {ausgabe.QUELLE, ausgabe.ZIEL_ERREICHT, ausgabe.VIOLATIONS}
    )

    @property
    def is_on(self) -> bool | None:
        return self._wert


def _bauen(fahrzeugausgabe: Fahrzeugausgabe) -> list[FahrzeugBinaersensor]:
    return [FahrzeugBinaersensor(fahrzeugausgabe, b) for b in BESCHREIBUNGEN]


@callback
def fahrzeugbinaersensoren_anbinden(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Die Binaersensoren aller Fahrzeuge, auch der spaeter angelegten."""
    fahrzeuge_anbinden(hass, entry, async_add_entities, _bauen)
