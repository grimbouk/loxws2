"""Home Assistant integration for the Loxone Miniserver."""

from __future__ import annotations

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.importlib import async_import_module
from homeassistant.helpers.typing import ConfigType

from loxone_api import DEFAULT_PORT, DEFAULT_TLS_PORT, LoxoneClient

from .const import CONF_USE_TLS, CONF_VERIFY_SSL, DOMAIN, PLATFORMS
from .coordinator import LoxoneCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the integration via YAML (not supported)."""

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Loxone from a config entry."""

    hass.data.setdefault(DOMAIN, {})

    _LOGGER.debug(
        "Setting up Loxone client for host %s (port=%s, tls=%s, verify_ssl=%s)",
        entry.data[CONF_HOST],
        entry.data.get(CONF_PORT),
        entry.data.get(CONF_USE_TLS, True),
        entry.data.get(CONF_VERIFY_SSL, True),
    )

    use_tls = entry.data.get(CONF_USE_TLS, True)
    if not use_tls:
        _LOGGER.warning(
            "LoxoneClient currently supports HTTPS only; proceeding with HTTPS settings."
        )

    port = entry.data.get(CONF_PORT) or (DEFAULT_TLS_PORT if use_tls else DEFAULT_PORT)

    client = LoxoneClient(
        host=entry.data[CONF_HOST],
        user=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        port=port,
        verify_tls=entry.data.get(CONF_VERIFY_SSL, True),
    )

    coordinator = LoxoneCoordinator(hass, client)
    try:
        await coordinator.async_setup()
    except Exception as err:
        _LOGGER.error("Unable to initialise Loxone client: %s", err)
        raise ConfigEntryNotReady from err

    hass.data[DOMAIN][entry.entry_id] = coordinator
    await asyncio.gather(
        *(async_import_module(hass, f"{__name__}.{platform}") for platform in PLATFORMS)
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Loxone config entry."""

    coordinator: LoxoneCoordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.async_unload()
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
