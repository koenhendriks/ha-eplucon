import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client

from const import DOMAIN
from eplucon_api.eplucon_client import EpluconApi

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Button+ from a config entry."""
    _LOGGER.debug(f"Eplucon init got new device entry! {entry.entry_id.title}")

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = EpluconApi('123', aiohttp_client.async_get_clientsession(hass))

    await hass.config_entries.async_forward_entry_setups(entry, ["coordinator"])
    return True
