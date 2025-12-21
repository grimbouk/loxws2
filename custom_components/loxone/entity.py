"""Base entity definitions for Loxone controls."""

from __future__ import annotations

from typing import Any, Callable

from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from loxone_api import LoxoneControl, LoxoneState

from .const import DOMAIN
from .coordinator import LoxoneCoordinator


class LoxoneEntity(Entity):
    """Representation of a Loxone control as a Home Assistant entity."""

    _attr_should_poll = True

    def __init__(self, coordinator: LoxoneCoordinator, control: LoxoneControl) -> None:
        self.coordinator = coordinator
        self.control = control
        self._unsub: Callable[[], None] | None = None
        self._attr_unique_id = control.uuid
        # Include room in entity name for clarity if available
        if control.room:
            self._attr_name = f"{control.room} - {control.name}"
        else:
            self._attr_name = control.name

    async def async_added_to_hass(self) -> None:
        @callback
        def handle_event(state: LoxoneState) -> None:
            if state.control_uuid == self.control.uuid:
                self.async_write_ha_state()

        self._unsub = async_dispatcher_connect(
            self.hass, f"{DOMAIN}_state_update", handle_event
        )

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

    async def async_update(self) -> None:
        """Poll the latest state when websocket updates are unavailable."""

        await self.coordinator.async_update_state(self.control.uuid)

    @property
    def available(self) -> bool:
        return True

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"room": self.control.room, "category": self.control.category}

    @property
    def suggested_area(self) -> str | None:
        """Suggest Home Assistant area based on Loxone room."""
        return self.control.room

    def _current_state(self) -> Any:
        return self.coordinator.get_state(self.control.uuid)
