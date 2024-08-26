from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN, MANUFACTURER

import logging

from .eplucon_api.DTO.DeviceDTO import DeviceDTO

_LOGGER = logging.getLogger(__name__)


class EpluconDevice:
    def __init__(
            self,
            hass: HomeAssistant,
            entry: ConfigEntry,
            device: DeviceDTO,
    ) -> None:
        _LOGGER.info(
            f"Init EpluconDevice with id '{device.id}'"
        )
        self.device_registry = dr.async_get(hass)
        self.device = self.device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            name=f"Eplucon {device.name}",
            model=f"{device.type}",
            manufacturer=MANUFACTURER,
            identifiers={(DOMAIN, f"Eplucon {device.id}")}
        )
