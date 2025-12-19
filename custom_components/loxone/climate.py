"""Climate platform for Loxone controls."""

from __future__ import annotations

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, TEMP_CELSIUS
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
        LoxoneClimate(coordinator, control)
        for control in coordinator.controls.values()
        if control.type.lower() in {"climate", "heating", "roomcontroller"}
    ]
    async_add_entities(entities)


class LoxoneClimate(LoxoneEntity, ClimateEntity):
    """Representation of a Loxone climate controller."""

    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.COOL, HVACMode.OFF]
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_temperature_unit = TEMP_CELSIUS

    @property
    def current_temperature(self):
        return self._current_state()

    @property
    def target_temperature(self):
        return self.control.details.get("defaultSetpoint") or self._current_state()

    async def async_set_temperature(self, **kwargs) -> None:
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return
        await self.coordinator.async_send_command(
            self.control.uuid, "setTemperature", temp
        )

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        await self.coordinator.async_send_command(
            self.control.uuid, "setMode", hvac_mode.value
        )
