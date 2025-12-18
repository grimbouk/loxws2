"""Cover platform for Loxone controls."""

from __future__ import annotations

from homeassistant.components.cover import CoverEntity, CoverEntityFeature
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
        LoxoneCover(coordinator, control)
        for control in coordinator.controls.values()
        if control.type.lower() in {"gate", "door", "jalousie", "cover"}
    ]
    async_add_entities(entities)


class LoxoneCover(LoxoneEntity, CoverEntity):
    """Representation of a Loxone cover."""

    _attr_supported_features = (
        CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
    )

    @property
    def is_closed(self) -> bool | None:
        value = self._current_state()
        if value is None:
            return None
        return float(value) <= 0

    async def async_open_cover(self, **kwargs) -> None:
        await self.coordinator.client.send_control_command(self.control.uuid, "open")

    async def async_close_cover(self, **kwargs) -> None:
        await self.coordinator.client.send_control_command(self.control.uuid, "close")

    async def async_stop_cover(self, **kwargs) -> None:
        await self.coordinator.client.send_control_command(self.control.uuid, "stop")
