"""Coordinator to manage Loxone connectivity and state updates."""

from __future__ import annotations

import logging
from typing import Any, Dict

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send

from loxone_api import LoxoneClient, LoxoneControl, LoxoneState
from loxone_api.const import DEFAULT_STRUCT_PATH

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
            status, payload = await self.client._get_json(DEFAULT_STRUCT_PATH)
        except Exception as err:
            _LOGGER.error("Unable to fetch Loxone structure: %s", err)
            return {}

        if status != 200:
            _LOGGER.error("Loxone structure request failed with HTTP %s", status)
            return {}

        structure = payload.get("LL", {}).get("value", payload)
        if not isinstance(structure, dict):
            _LOGGER.error("Unexpected structure payload: %s", structure)
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
