from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import (
    UnitOfTemperature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.typing import StateType
from typing import Any

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass(kw_only=True)
class EpluconSensorEntityDescription(SensorEntityDescription):
    """Describes an Eplucon sensor entity."""

    exists_fn: Callable[[Any], bool] = lambda _: True
    value_fn: Callable[[Any], StateType]


# Define the sensor types
SENSORS: tuple[EpluconSensorEntityDescription, ...] = (
    EpluconSensorEntityDescription(
        key="indoor_temperature",
        name="Indoor Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device: device.realtime_info.common.indoor_temperature,
        exists_fn=lambda device: device.realtime_info is not None,
    ),
)


async def async_setup_entry(
        hass: HomeAssistant,
        entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Eplucon sensor based on a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    devices = coordinator.data

    async_add_entities(
        EpluconSensorEntity(coordinator, device, description)
        for device in devices
        for description in SENSORS
        if description.exists_fn(device)
    )


class EpluconSensorEntity(CoordinatorEntity, SensorEntity):
    """Representation of an Eplucon sensor."""

    entity_description: EpluconSensorEntityDescription

    def __init__(
            self, coordinator, device, entity_description: EpluconSensorEntityDescription
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.device = device
        self.entity_description = entity_description
        self._attr_name = f"{device.name} {entity_description.name}"
        self._attr_unique_id = f"{device.id}_{entity_description.key}"

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        return self.entity_description.value_fn(self.device)
