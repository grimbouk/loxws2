"""Light platform for Loxone controls."""

from __future__ import annotations

import logging

from homeassistant.components.light import ATTR_BRIGHTNESS, ATTR_RGB_COLOR, ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import LoxoneEntity
from .coordinator import LoxoneCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: LoxoneCoordinator = hass.data[DOMAIN][entry.entry_id]
    
    # Supported Loxone light device types
    light_types = {
        "lightcontrollerv2",
        "colorpickerv2",
        "dimmer",
        "switch",
    }
    
    entities = []

    # Group subcontrols under LightControllerV2 by parent and name to merge duplicates (e.g., Pendant)
    parent_children: dict[str, list] = {}
    for control in coordinator.controls.values():
        details = control.details or {}
        parent_uuid = details.get("parent_uuid")
        if parent_uuid:
            parent_children.setdefault(parent_uuid, []).append(control)

    # Keep track of subcontrols that are merged to avoid adding them individually
    merged_subcontrol_uuids: set[str] = set()

    # Create grouped entities for LightControllerV2 parents
    for parent in (c for c in coordinator.controls.values() if (c.type or "").lower() == "lightcontrollerv2"):
        children = parent_children.get(parent.uuid, [])
        if not children:
            continue

        # Group children by display name (after the parent prefix)
        name_groups: dict[str, list] = {}
        for child in children:
            # Child names are in format "<parent> - <name>", extract the part after the hyphen
            base_name = child.name
            if parent.name and base_name.startswith(parent.name + " - "):
                base_name = base_name[len(parent.name) + 3 :]
            norm = base_name.strip().lower()
            name_groups.setdefault(norm, []).append(child)

        for norm_name, group in name_groups.items():
            if len(group) > 1:
                # Merge duplicate-named subcontrols into a single grouped entity
                _LOGGER.debug("Merging %d subcontrols under '%s' of parent %s", len(group), norm_name, parent.uuid)
                entities.append(LoxoneGroupedLight(coordinator, parent, group))
                merged_subcontrol_uuids.update(c.uuid for c in group)

    # Add remaining lights (skip merged duplicates)
    for control in coordinator.controls.values():
        if control.uuid in merged_subcontrol_uuids:
            continue
        if control.type.lower() in light_types:
            # Use color picker entity for ColorPickerV2, standard light for others
            _LOGGER.debug("Adding Loxone light entity for control %s of type %s", control.uuid, control.type)
            if control.type.lower() == "colorpickerv2":
                entities.append(LoxoneColorLight(coordinator, control))
            else:
                entities.append(LoxoneLight(coordinator, control))
    async_add_entities(entities)


class LoxoneLight(LoxoneEntity, LightEntity):
    """Representation of a Loxone light."""

    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_color_mode = ColorMode.BRIGHTNESS

    @property
    def is_on(self) -> bool:
        value = self._current_state()
        return bool(value) if value is not None else False

    @property
    def brightness(self) -> int | None:
        value = self._current_state()
        if value is None or value == "":
            return None
        try:
            # Loxone expresses dimmer values as 0-100
            float_val = float(value)
            return int(float_val * 2.55) if float_val <= 100 else int(float_val)
        except (ValueError, TypeError):
            return None

    async def async_turn_on(self, **kwargs) -> None:
        _LOGGER.debug("async_turn_on")

        brightness = kwargs.get(ATTR_BRIGHTNESS)
        if brightness is not None:
            value = round(brightness / 2.55, 1)
            _LOGGER.debug(
                "Turning on %s with brightness %s (HA scale 0-255) -> %.1f (Loxone scale 0-100)",
                self.control.uuid, brightness, value
            )
            await self.coordinator.async_send_command(
                self.control.uuid, "setValue", value
            )
        else:
            _LOGGER.debug("Turning on %s without brightness", self.control.uuid)
            await self.coordinator.async_send_command(self.control.uuid, "on")

    async def async_turn_off(self, **kwargs) -> None:
        _LOGGER.debug("async_turn_off")
        _LOGGER.debug("Turning off %s", self.control.uuid)
        await self.coordinator.async_send_command(self.control.uuid, "off")


class LoxoneColorLight(LoxoneLight):
    """Representation of a Loxone ColorPickerV2 light with RGB support."""

    # Per Home Assistant requirements, do not mix RGB with BRIGHTNESS.
    # RGB implies brightness support when provided.
    _attr_supported_color_modes = {ColorMode.RGB}
    _attr_color_mode = ColorMode.RGB

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        """Return the RGB color value."""
        value = self._current_state()
        if value is None or value == "":
            return None
        
        try:
            # Loxone stores color as a hex string like "FF0000" for red
            hex_color = str(value).strip()
            if len(hex_color) == 6:
                r = int(hex_color[0:2], 16)
                g = int(hex_color[2:4], 16)
                b = int(hex_color[4:6], 16)
                return (r, g, b)
        except (ValueError, TypeError, AttributeError):
            _LOGGER.debug("Failed to parse color value: %s", value)
        
        return None

    async def async_turn_on(self, **kwargs) -> None:
        _LOGGER.debug("async_turn_on")
        """Turn on the light with optional brightness and RGB color."""
        rgb = kwargs.get(ATTR_RGB_COLOR)
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        
        # If RGB color is specified, send it
        if rgb is not None:
            # Convert RGB to hex string for Loxone (RRGGBB format)
            hex_color = f"{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"
            _LOGGER.debug(
                "Turning on %s with RGB %s -> %s",
                self.control.uuid, rgb, hex_color
            )
            await self.coordinator.async_send_command(
                self.control.uuid, "setColor", hex_color
            )
        # Otherwise use brightness if specified
        elif brightness is not None:
            value = round(brightness / 2.55, 1)
            _LOGGER.debug(
                "Turning on %s with brightness %s (HA scale 0-255) -> %.1f (Loxone scale 0-100)",
                self.control.uuid, brightness, value
            )
            await self.coordinator.async_send_command(
                self.control.uuid, "setValue", value
            )
        else:
            _LOGGER.debug("Turning on %s without brightness or color", self.control.uuid)
            await self.coordinator.async_send_command(self.control.uuid, "on")


class LoxoneGroupedLight(LoxoneEntity, LightEntity):
    """A grouped light representing multiple subcontrols with the same name under one LightControllerV2."""

    def __init__(self, coordinator: LoxoneCoordinator, parent_control, subcontrols: list):
        # Use the first subcontrol name (already includes parent prefix) for display
        super().__init__(coordinator, subcontrols[0])
        self.parent = parent_control
        self.subcontrols = subcontrols

        # Determine capabilities: prefer RGB, else BRIGHTNESS, else ON/OFF
        types = { (c.type or "").lower() for c in subcontrols }
        if "colorpickerv2" in types:
            self._attr_supported_color_modes = {ColorMode.RGB}
            self._attr_color_mode = ColorMode.RGB
        elif "dimmer" in types:
            self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}
            self._attr_color_mode = ColorMode.BRIGHTNESS
        else:
            self._attr_supported_color_modes = {ColorMode.ONOFF}
            self._attr_color_mode = ColorMode.ONOFF

    def _first_of_type(self, t: str):
        for c in self.subcontrols:
            if (c.type or "").lower() == t:
                return c
        return None

    @property
    def is_on(self) -> bool:
        # Consider on if any subcontrol reports a truthy state
        for c in self.subcontrols:
            val = self.coordinator.get_state(c.uuid)
            if val:
                return True
        return False

    @property
    def brightness(self) -> int | None:
        if ColorMode.BRIGHTNESS not in getattr(self, "_attr_supported_color_modes", set()):
            return None
        dimmer = self._first_of_type("dimmer")
        if not dimmer:
            return None
        value = self.coordinator.get_state(dimmer.uuid)
        if value is None or value == "":
            return None
        try:
            float_val = float(value)
            return int(float_val * 2.55) if float_val <= 100 else int(float_val)
        except (ValueError, TypeError):
            return None

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        if ColorMode.RGB not in getattr(self, "_attr_supported_color_modes", set()):
            return None
        color = self._first_of_type("colorpickerv2")
        if not color:
            return None
        value = self.coordinator.get_state(color.uuid)
        if value is None or value == "":
            return None
        try:
            hex_color = str(value).strip()
            if len(hex_color) == 6:
                r = int(hex_color[0:2], 16)
                g = int(hex_color[2:4], 16)
                b = int(hex_color[4:6], 16)
                return (r, g, b)
        except (ValueError, TypeError, AttributeError):
            _LOGGER.debug("Failed to parse grouped color value: %s", value)
        return None

    async def async_turn_on(self, **kwargs) -> None:
        _LOGGER.debug("async_turn_on")
        rgb = kwargs.get(ATTR_RGB_COLOR)
        brightness = kwargs.get(ATTR_BRIGHTNESS)

        # Apply color to all colorpickerv2 subcontrols
        if rgb is not None and ColorMode.RGB in getattr(self, "_attr_supported_color_modes", set()):
            hex_color = f"{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"
            for c in self.subcontrols:
                if (c.type or "").lower() == "colorpickerv2":
                    await self.coordinator.async_send_command(c.uuid, "setColor", hex_color)
            return

        # Apply brightness to all dimmer subcontrols
        if brightness is not None and ColorMode.BRIGHTNESS in getattr(self, "_attr_supported_color_modes", set()):
            value = round(brightness / 2.55, 1)
            for c in self.subcontrols:
                if (c.type or "").lower() == "dimmer":
                    await self.coordinator.async_send_command(c.uuid, "setValue", value)
            return

        # Fallback: turn on all switch-like subcontrols
        for c in self.subcontrols:
            await self.coordinator.async_send_command(c.uuid, "on")

    async def async_turn_off(self, **kwargs) -> None:
        _LOGGER.debug("async_turn_off")
        for c in self.subcontrols:
            await self.coordinator.async_send_command(c.uuid, "off")
