"""Sensor platform for Meteo-Volt integration."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo, DeviceEntryType

from .const import DOMAIN, CONF_GRID_FEES
from .coordinator import MeteoVoltDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    coordinator: MeteoVoltDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    grid_fees = entry.data.get(CONF_GRID_FEES, 0.0)

    async_add_entities([
        MeteoVoltForecastSensor(coordinator, entry.entry_id, "q10", "Q10", grid_fees),
        MeteoVoltForecastSensor(coordinator, entry.entry_id, "q50", "Q50", grid_fees),
        MeteoVoltForecastSensor(coordinator, entry.entry_id, "q90", "Q90", grid_fees),
        MeteoVoltStringSensor(coordinator, entry.entry_id, "model", "Model"),
        MeteoVoltTimestampSensor(coordinator, entry.entry_id, "snapshot_time", "Snapshot Time"),
        MeteoVoltTimestampSensor(coordinator, entry.entry_id, "computed_at", "Computed At"),
    ])


class MeteoVoltBaseSensor(CoordinatorEntity, SensorEntity):
    """Base class for Meteo-Volt sensors to provide device info."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: MeteoVoltDataUpdateCoordinator,
        entry_id: str,
        name: str,
        unique_id: str,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._attr_name = name
        self._attr_unique_id = unique_id

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name="Meteo-Volt Dienst",
            manufacturer="Meteo-Volt",
            entry_type=DeviceEntryType.SERVICE,
        )


class MeteoVoltForecastSensor(MeteoVoltBaseSensor):
    """Representation of a Meteo-Volt Forecast Sensor."""

    # The forecast series is far larger than the recorder's 16384-byte limit for
    # state attributes (measured: ~20 KB free, ~46 KB paid, ~91 KB admin).
    # Without this, every update logs a warning and the attributes are dropped
    # from the database anyway. They remain on the live state, which is all that
    # charts and templates read.
    _unrecorded_attributes = frozenset({"forecast"})

    def __init__(
        self,
        coordinator: MeteoVoltDataUpdateCoordinator,
        entry_id: str,
        quantile: str,
        name: str,
        grid_fees: float,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            entry_id,
            name,
            f"meteo_volt_{entry_id}_{quantile}",
        )
        self._quantile = quantile
        self._grid_fees = grid_fees

    @property
    def native_value(self) -> int | str | None:
        """Return the number of slots available or a fallback state."""
        if not self.coordinator.data or "slots" not in self.coordinator.data:
            return None
        return len(self.coordinator.data["slots"])

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return a unit if applicable."""
        return "slots"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes (full forecast with grid fees applied)."""
        attrs = {}
        if self.coordinator.data:
            # Map the full forecast for charting
            forecast = []
            if "slots" in self.coordinator.data:
                for slot in self.coordinator.data["slots"]:
                    val = slot.get(self._quantile)
                    if val is not None:
                        val += self._grid_fees
                    forecast.append({
                        "target_timestamp": slot.get("target_timestamp"),
                        "value": val
                    })
            attrs["forecast"] = forecast
            
        return attrs


class MeteoVoltStringSensor(MeteoVoltBaseSensor):
    """Representation of a string-based sensor (e.g. model)."""

    def __init__(
        self,
        coordinator: MeteoVoltDataUpdateCoordinator,
        entry_id: str,
        key: str,
        name: str,
    ) -> None:
        """Initialize."""
        super().__init__(
            coordinator,
            entry_id,
            name,
            f"meteo_volt_{entry_id}_{key}",
        )
        self._key = key

    @property
    def native_value(self) -> str | None:
        """Return the state."""
        if self.coordinator.data:
            return self.coordinator.data.get(self._key)
        return None


class MeteoVoltTimestampSensor(MeteoVoltBaseSensor):
    """Representation of a timestamp sensor."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(
        self,
        coordinator: MeteoVoltDataUpdateCoordinator,
        entry_id: str,
        key: str,
        name: str,
    ) -> None:
        """Initialize."""
        super().__init__(
            coordinator,
            entry_id,
            name,
            f"meteo_volt_{entry_id}_{key}",
        )
        self._key = key

    @property
    def native_value(self) -> datetime | None:
        """Return the state as datetime."""
        if self.coordinator.data:
            val = self.coordinator.data.get(self._key)
            if val:
                try:
                    return datetime.fromisoformat(val)
                except ValueError:
                    return None
        return None
