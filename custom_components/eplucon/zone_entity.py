from __future__ import annotations

import logging
from typing import Optional

from dacite import from_dict
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .eplucon_api.DTO.DeviceDTO import DeviceDTO
from .eplucon_api.DTO.ZoneDTO import ZoneDTO

_LOGGER = logging.getLogger(__name__)


class EpluconZoneEntity(CoordinatorEntity):
    """Base for entities backed by a single zone of a zones controller.

    Each zone is modelled as its own HA device (a room / control panel),
    linked to the controller module via ``via_device``.
    """

    def __init__(self, coordinator, device: DeviceDTO, zone: ZoneDTO, entity_description) -> None:
        super().__init__(coordinator)
        self._module_id = device.id
        self._module_index = device.account_module_index
        self._zone_id = zone.id
        self._zone_name = zone.name
        self.entity_description = entity_description
        self._attr_name = entity_description.name
        self._attr_unique_id = f"{device.id}_zone_{zone.id}_{entity_description.key}"

        _LOGGER.debug(
            "Created zone entity %s with unique_id %s",
            self._attr_name,
            self._attr_unique_id,
        )

    @property
    def zone(self) -> Optional[ZoneDTO]:
        """Return the current ZoneDTO from the latest coordinator data."""
        for device in self.coordinator.data:
            if isinstance(device, dict):
                device = from_dict(data_class=DeviceDTO, data=device)
            if device.id != self._module_id or not device.zones:
                continue
            for zone in device.zones:
                if zone.id == self._zone_id:
                    return zone
        return None

    @property
    def device_info(self) -> dict:
        """Return per-zone device info, linked to the controller module."""
        return {
            "identifiers": {(DOMAIN, f"{self._module_index}_zone_{self._zone_id}")},
            "name": self._zone_name,
            "manufacturer": MANUFACTURER,
            "model": "Zone control panel",
            "via_device": (DOMAIN, self._module_index),
        }
