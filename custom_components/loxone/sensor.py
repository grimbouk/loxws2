"""Sensor platform for Loxone controls."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import LoxoneCoordinator
from .entity import LoxoneEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: LoxoneCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [
        LoxoneSensor(coordinator, control)
        for control in coordinator.controls.values()
        if control.type.lower() in {"temperature", "sensor", "humidity"}
    ]
    async_add_entities(entities)


class LoxoneSensor(LoxoneEntity, SensorEntity):
    """Representation of a generic Loxone sensor."""

    @property
    def native_value(self):
        return self._current_state()
