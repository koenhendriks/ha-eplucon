import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client

from .const import DOMAIN
from .eplucon_api.eplucon_client import EpluconApi

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Eplucon device from a config entry."""
    devices = entry.data.get("devices", "Empty")

    _LOGGER.debug(f"Eplucon init with devices from entry: {devices}")

    # await hass.config_entries.async_forward_entry_setups(entry, ["coordinator"])
    return True
