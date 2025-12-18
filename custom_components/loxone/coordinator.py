"""Coordinator to manage Loxone connectivity and state updates."""

from __future__ import annotations

import logging
from typing import Any, Dict

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send

from loxone_api import LoxoneClient, LoxoneState

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class LoxoneCoordinator:
    """Manage Loxone client lifecycle and state updates."""

    def __init__(self, hass: HomeAssistant, client: LoxoneClient) -> None:
        self.hass = hass
        self.client = client
        self.controls: Dict[str, Any] = {}
        self.states: Dict[str, Any] = {}

    async def async_setup(self) -> None:
        """Initialise client and register callbacks."""

        self.controls = await self.client.async_start()
        self.client.register_callback(self._handle_state)

    async def async_unload(self) -> None:
        """Close the client connection."""

        await self.client.async_stop()

    @callback
    def _handle_state(self, state: LoxoneState) -> None:
        """Handle updates coming from the websocket."""

        self.states[state.control_uuid] = state.value
        async_dispatcher_send(self.hass, f"{DOMAIN}_state_update", state)

    def get_state(self, uuid: str) -> Any:
        """Return cached value for a control."""

        return self.states.get(uuid)
