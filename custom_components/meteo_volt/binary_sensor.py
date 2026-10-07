"""Binaersensoren je Fahrzeug: Jetzt laden und Plan erfuellbar.

Home Assistant importiert alle Plattformen eines Eintrags, bevor es eine
einrichtet, und ein Importfehler bricht das Einrichten des ganzen Eintrags ab,
die sechs Sensoren der Prognose eingeschlossen. Die Klassen stehen deshalb in
fahrzeugbinaersensor.py und werden erst hier im try geladen (Spec C6
Abschnitt 8).

Spec: meteo-volt-brain/docs/features/C6-ausgabe-entitaeten/spec.md
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Die Binaersensoren aller Fahrzeuge, auch der spaeter angelegten."""
    try:
        from .fahrzeugbinaersensor import fahrzeugbinaersensoren_anbinden

        fahrzeugbinaersensoren_anbinden(hass, entry, async_add_entities)
    except Exception:  # pylint: disable=broad-except
        _LOGGER.exception("Binaersensoren je Fahrzeug nicht angelegt, die Prognose laeuft weiter")
