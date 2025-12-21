"""Coordinator to manage Loxone connectivity and state updates."""

from __future__ import annotations

import logging
from typing import Any, Dict

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send

from loxone_api import LoxoneClient, LoxoneControl, LoxoneState

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

        await self.client.authenticate()
        self.controls = await self._load_controls()

    async def async_unload(self) -> None:
        """Close the client connection."""

        await self.client.close()

    async def async_send_command(
        self, control_uuid: str, command: str, value: Any | None = None
    ) -> None:
        """Send a control command using the jdev endpoint."""

        if value is None:
            path = f"sps/io/{control_uuid}/{command}"
        else:
            path = f"sps/io/{control_uuid}/{command}/{value}"

        await self.client.jdev_get(path)

    async def async_update_state(self, control_uuid: str) -> Any:
        """Fetch and cache the current state for a control."""

        try:
            payload = await self.client.jdev_get(f"sps/io/{control_uuid}")
        except Exception as err:
            _LOGGER.warning(
                "Unable to refresh state for control %s: %s", control_uuid, err
            )
            return self.states.get(control_uuid)

        value = payload.get("LL", {}).get("value", payload)
        self.states[control_uuid] = value
        return value

    @callback
    def _handle_state(self, state: LoxoneState) -> None:
        """Handle updates coming from the websocket."""

        self.states[state.control_uuid] = state.value
        async_dispatcher_send(self.hass, f"{DOMAIN}_state_update", state)

    def get_state(self, uuid: str) -> Any:
        """Return cached value for a control."""

        return self.states.get(uuid)

    async def _load_controls(self) -> Dict[str, LoxoneControl]:
        """Load controls from the LoxAPP3 structure file."""

        try:
            structure = await self.client.load_structure()
        except Exception as err:
            _LOGGER.error("Unable to fetch Loxone structure: %s", err)
            return {}

        rooms = {
            room_uuid: room_data.get("name")
            for room_uuid, room_data in (structure.get("rooms") or {}).items()
        }
        categories = {
            cat_uuid: cat_data.get("name")
            for cat_uuid, cat_data in (structure.get("cats") or {}).items()
        }

        controls: Dict[str, LoxoneControl] = {}
        for control_uuid, control in (structure.get("controls") or {}).items():
            if not isinstance(control, dict):
                continue
            controls[control_uuid] = LoxoneControl(
                uuid=control_uuid,
                name=control.get("name") or control_uuid,
                type=control.get("type") or "",
                room=rooms.get(control.get("room")),
                category=categories.get(control.get("cat")),
                states=control.get("states") or {},
                details=control.get("details") or {},
            )

        return controls
