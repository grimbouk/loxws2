"""Scene platform for Loxone controls."""

from __future__ import annotations

from homeassistant.components.scene import Scene
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
        LoxoneScene(coordinator, control)
        for control in coordinator.controls.values()
        if control.type.lower() in {"scene", "mood"}
    ]
    async_add_entities(entities)


class LoxoneScene(LoxoneEntity, Scene):
    """Representation of a Loxone scene."""

    async def async_activate(self, **kwargs) -> None:
        await self.coordinator.async_send_command(self.control.uuid, "activate")
