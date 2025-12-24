from __future__ import annotations

import logging
from dacite import from_dict
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, BINARY_SENSORS
from .eplucon_api.DTO.DeviceDTO import DeviceDTO

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:

    coordinator = hass.data[DOMAIN][entry.entry_id]

    await coordinator.async_config_entry_first_refresh()

    entities: list[EpluconBinarySensorEntity] = []

    for device in coordinator.data:
        if isinstance(device, dict):
            device = from_dict(DeviceDTO, device)

        for description in BINARY_SENSORS:
            if description.exists_fn and not description.exists_fn(device):
                continue

            entities.append(
                EpluconBinarySensorEntity(coordinator, device, description)
            )

    _LOGGER.debug("Adding %d binary sensor entities", len(entities))
    async_add_entities(entities)


class EpluconBinarySensorEntity(CoordinatorEntity, BinarySensorEntity):

    def __init__(self, coordinator, device, description):

        super().__init__(coordinator)
        self.device = device
        self.entity_description = description
        self._attr_name = description.name
        self._attr_unique_id = f"{device.id}_{description.key}"

        _LOGGER.debug("Created binary sensor entity %s with unique_id %s", self._attr_name, self._attr_unique_id)


    @property
    def device_info(self):
        return {
            "manufacturer": MANUFACTURER,
            "identifiers": {(DOMAIN, self.device.account_module_index)},
        }


    def _update_device_data(self):
        """Update internal device data from coordinator."""
        for updated_device in self.coordinator.data:
            if isinstance(updated_device, dict):
                updated_device = from_dict(data_class=DeviceDTO, data=updated_device)
            if updated_device.id == self.device.id:
                old_value = self.entity_description.value_fn(self.device)
                new_value = self.entity_description.value_fn(updated_device)
                if old_value != new_value:
                    _LOGGER.debug(
                        "Binary Sensor %s value changed: %s -> %s",
                        self.name, old_value, new_value
                    )
                self.device = updated_device
                break


    @property
    def is_on(self) -> bool:
        value = self.entity_description.value_fn(self.device)
        return bool(value)

    def _handle_coordinator_update(self) -> None:
        for updated_device in self.coordinator.data:
            if isinstance(updated_device, dict):
                updated_device = from_dict(DeviceDTO, updated_device)

            if updated_device.id == self.device.id:
                self.device = updated_device
                break

        super()._handle_coordinator_update()
