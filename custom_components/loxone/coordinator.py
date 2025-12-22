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
        _LOGGER.debug("async_setup")

        await self.client.__aenter__()
        _LOGGER.debug("Client session initialized")
        
        token = await self.client.authenticate()
        _LOGGER.debug("Authentication successful, JWT: %s...", token[:24] if len(token) > 24 else token)
        _LOGGER.debug("Client JWT property: %s", self.client.jwt[:24] if self.client.jwt and len(self.client.jwt) > 24 else self.client.jwt)
        
        self.controls = await self._load_controls()

    async def async_unload(self) -> None:
        """Close the client connection."""
        _LOGGER.debug("async_unload")

        await self.client.__aexit__(None, None, None)

    async def async_send_command(
        self, control_uuid: str, command: str, value: Any | None = None
    ) -> None:
        """Send a control command using the jdev endpoint."""
        _LOGGER.debug("async_send_command")

        ctrl: LoxoneControl | None = self.controls.get(control_uuid)
        details = ctrl.details if ctrl else {}

        # Resolve action path robustly to avoid parent duplication
        if "/" in control_uuid:
            # Already composite; trust the provided path
            action_uuid = control_uuid
        else:
            parent_uuid = details.get("parent_uuid")
            subcontrol_id = details.get("subcontrol_id")
            if parent_uuid and subcontrol_id:
                action_uuid = f"{parent_uuid}/{subcontrol_id}"
            else:
                action_uuid = (ctrl.states.get("uuidAction") if ctrl else None) or control_uuid

        if value is None:
            path = f"sps/io/{action_uuid}/{command}"
        else:
            path = f"sps/io/{action_uuid}/{command}/{value}"

        _LOGGER.debug("Sending command to %s (resolved %s): %s/%s (value=%s)", control_uuid, action_uuid, command, value, value)
        
        try:
            payload = await self.client.jdev_get(path)
            _LOGGER.debug("Command response: %s", payload)
            
            # Check if the command was successful (handle both 'code' and 'Code')
            ll = payload.get("LL", {})
            ll_code = ll.get("code") or ll.get("Code")
            if ll_code not in ("200", 200):
                _LOGGER.warning(
                    "Command %s/%s failed with code %s: %s",
                    command, value, ll_code, payload
                )
        except Exception as err:
            _LOGGER.error("Failed to send command %s/%s: %s", command, value, err)
            raise
        
        # Fetch updated state immediately after command
        try:
            await self.async_update_state(control_uuid)
        except Exception as err:
            _LOGGER.warning("Failed to fetch updated state for %s: %s", control_uuid, err)

    async def async_update_state(self, control_uuid: str) -> Any:
        """Fetch and cache the current state for a control."""
        _LOGGER.debug("async_update_state")

        ctrl: LoxoneControl | None = self.controls.get(control_uuid)
        details = ctrl.details if ctrl else {}

        # Resolve read path robustly to avoid parent duplication
        if "/" in control_uuid:
            read_uuid = control_uuid
        else:
            parent_uuid = details.get("parent_uuid")
            subcontrol_id = details.get("subcontrol_id")
            if parent_uuid and subcontrol_id:
                read_uuid = f"{parent_uuid}/{subcontrol_id}"
            else:
                read_uuid = (ctrl.states.get("uuidAction") if ctrl else None) or control_uuid

        try:
            payload = await self.client.jdev_get(f"sps/io/{read_uuid}")
        except Exception as err:
            _LOGGER.warning(
                "Unable to refresh state for control %s: %s", control_uuid, err
            )
            return self.states.get(control_uuid)

        value = payload.get("LL", {}).get("value", payload)
        self.states[control_uuid] = value
        
        # Notify Home Assistant that state has changed
        async_dispatcher_send(
            self.hass,
            f"{DOMAIN}_state_update",
            LoxoneState(control_uuid=control_uuid, state="", value=value)
        )
        
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
        _LOGGER.debug("_load_controls")

        try:
            structure = await self.client.load_structure()
        except Exception as err:
            _LOGGER.error("Unable to fetch Loxone structure: %s", err)
            return {}

        rooms = {
            room_uuid: room_data.get("name")
            for room_uuid, room_data in (structure.get("rooms") or {}).items()
        }
        
        # Pre-create Home Assistant areas for each Loxone room
        await self._create_areas(list(rooms.values()))
        
        categories = {
            cat_uuid: cat_data.get("name")
            for cat_uuid, cat_data in (structure.get("cats") or {}).items()
        }

        controls: Dict[str, LoxoneControl] = {}
        for control_uuid, control in (structure.get("controls") or {}).items():
            if not isinstance(control, dict):
                continue

            # Parent/top-level control
            parent = LoxoneControl(
                uuid=control_uuid,
                name=control.get("name") or control_uuid,
                type=control.get("type") or "",
                room=rooms.get(control.get("room")),
                category=categories.get(control.get("cat")),
                states=control.get("states") or {},
                details=control.get("details") or {},
            )
            controls[control_uuid] = parent

            # Subcontrols (e.g., LightControllerV2 outputs, moods, etc.)
            sub_controls = control.get("subControls") or {}
            # Handle dict keyed by UUID or list of subcontrol dicts
            if isinstance(sub_controls, dict):
                iterable = sub_controls.items()
            elif isinstance(sub_controls, list):
                # Convert list to (uuid, data) pairs when possible
                iterable = (
                    (
                        sc.get("uuid") or sc.get("id") or sc.get("UUID") or "",
                        sc,
                    )
                    for sc in sub_controls
                    if isinstance(sc, dict)
                )
            else:
                iterable = []

            for sc_uuid, sc_data in iterable:
                if not sc_uuid or not isinstance(sc_data, dict):
                    continue
                name = sc_data.get("name") or sc_uuid
                # Prefix with parent name for clarity
                full_name = f"{parent.name} - {name}" if parent.name else name
                # Store subcontrol with composite UUID (parent/subcontrol_id) for proper lookup
                composite_uuid = f"{control_uuid}/{sc_uuid}"
                sc = LoxoneControl(
                    uuid=composite_uuid,
                    name=full_name,
                    type=(sc_data.get("type") or sc_data.get("typeName") or ""),
                    room=parent.room,
                    category=parent.category,
                    states=sc_data.get("states") or {},
                    details={
                        **(sc_data.get("details") or {}),
                        "parent_uuid": control_uuid,
                        "subcontrol_id": sc_uuid,
                    },
                )
                controls[composite_uuid] = sc

        return controls

    async def _create_areas(self, room_names: list) -> None:
        """Pre-create Home Assistant areas for Loxone rooms."""
        area_registry = self.hass.data.get("area_registry")
        if not area_registry:
            return

        for room_name in room_names:
            if not room_name:
                continue
            # Check if area already exists
            if area_registry.async_get_area_by_name(room_name):
                continue
            # Create new area
            area_registry.async_create(room_name)
