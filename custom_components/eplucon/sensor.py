from __future__ import annotations

import logging
from dacite import from_dict
from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.typing import StateType
from typing import Any

from .const import DOMAIN, MANUFACTURER, SENSORS, EpluconSensorEntityDescription

from .eplucon_api.DTO.DeviceDTO import DeviceDTO

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
        hass: HomeAssistant,
        entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Eplucon sensor based on a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    await coordinator.async_config_entry_first_refresh()
    devices = coordinator.data

    list_device_dto = []
    for device in devices:
        if isinstance(device, dict):
            device = from_dict(data_class=DeviceDTO, data=device)
        list_device_dto.append(device)

    entities = []
    for device in list_device_dto:
        for description in SENSORS:
            if description.exists_fn(device):
                entities.append(EpluconSensorEntity(coordinator, device, description))

    _LOGGER.debug("Adding %d sensor entities", len(entities))
    async_add_entities(entities)


class EpluconSensorEntity(CoordinatorEntity, SensorEntity):
    """Representation of an Eplucon sensor with detailed logging."""

    entity_description: SensorEntityDescription

    def __init__(self, coordinator, device: DeviceDTO, entity_description: SensorEntityDescription) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.device = device
        self.entity_description = entity_description
        self._attr_name = f"{entity_description.name}"
        self._attr_unique_id = f"{device.id}_{entity_description.key}"

        _LOGGER.debug("Created sensor entity %s with unique_id %s", self._attr_name, self._attr_unique_id)

    @property
    def device_info(self) -> dict:
        """Return device info for HA device registry."""
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
                        "Sensor %s value changed: %s -> %s",
                        self.name, old_value, new_value
                    )
                self.device = updated_device
                break

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        value = self.entity_description.value_fn(self.device)
        #_LOGGER.debug("Sensor %s native_value: %s", self.name, value)
        return value


    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator and log sensor value."""
        self._update_device_data()
        value = self.native_value
        #_LOGGER.debug(f"Sensor {self.name} updated value: {value}")
        super()._handle_coordinator_update()
