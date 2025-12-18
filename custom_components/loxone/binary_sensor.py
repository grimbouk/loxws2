"""Binary sensor platform for Loxone controls."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
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
        LoxoneBinarySensor(coordinator, control)
        for control in coordinator.controls.values()
        if control.type.lower() in {"contact", "binarysensor", "motion"}
    ]
    async_add_entities(entities)


class LoxoneBinarySensor(LoxoneEntity, BinarySensorEntity):
    """Representation of a Loxone binary sensor."""

    @property
    def is_on(self) -> bool:
        value = self._current_state()
        return bool(value)
