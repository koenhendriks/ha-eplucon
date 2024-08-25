from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN, MANUFACTURER

import logging

_LOGGER = logging.getLogger(__name__)


class EpluconDevice:
    def __init__(
            self,
            hass: HomeAssistant,
            entry: ConfigEntry,
            module_id: str,
    ) -> None:
        _LOGGER.info(
            f"Init EpluconDevice with id '{module_id}'"
        )
        self.device_registry = dr.async_get(hass)
        self.device = self.device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            connections={(DOMAIN, hub.config.identifier())},
            name=f"Eplucon device {module_id}",
            model="Heat Pump",
            manufacturer=MANUFACTURER,
            identifiers={(DOMAIN, f"Eplucon {module_id}")}
        )
