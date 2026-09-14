"""Binaersensoren je Fahrzeug: Jetzt laden und Plan erfuellbar.

Eine neue Plattform. Scheitert ihr Aufbau, beruehrt das die sechs Sensoren
der Prognose nicht (Spec C6 Abschnitt 8).

Spec: meteo-volt-brain/docs/features/C6-ausgabe-entitaeten/spec.md
"""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
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


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Die Binaersensoren aller Fahrzeuge, auch der spaeter angelegten."""
    fahrzeuge_anbinden(hass, entry, async_add_entities, _bauen)
