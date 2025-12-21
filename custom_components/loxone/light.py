"""Light platform for Loxone controls."""

from __future__ import annotations

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import LoxoneEntity
from .coordinator import LoxoneCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: LoxoneCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [
        LoxoneLight(coordinator, control)
        for control in coordinator.controls.values()
        if control.type.lower().startswith("light")
    ]
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
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        if brightness is not None:
            value = round(brightness / 2.55, 1)
            await self.coordinator.async_send_command(
                self.control.uuid, "setValue", value
            )
        else:
            await self.coordinator.async_send_command(self.control.uuid, "on")

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_send_command(self.control.uuid, "off")
