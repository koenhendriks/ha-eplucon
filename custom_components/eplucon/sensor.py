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
    UnitOfTemperature, REVOLUTIONS_PER_MINUTE, UnitOfPressure, UnitOfEnergy, UnitOfTime, UnitOfPower,
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
    value_fn: Callable[[Any], SensorEntityDescription]


# Define the sensor types
SENSORS: tuple[EpluconSensorEntityDescription, ...] = (
    EpluconSensorEntityDescription(
        key="indoor_temperature",
        name="Indoor Temperature",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        value_fn=lambda device: device.realtime_info.common.indoor_temperature,
        exists_fn=lambda device: device.realtime_info is not None,
    ),
    EpluconSensorEntityDescription(
        key="act_vent_rpm",
        name="Act Vent RPM",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        value_fn=lambda device: device.realtime_info.common.act_vent_rpm,
        exists_fn=lambda device: device.realtime_info is not None,
    ),

    EpluconSensorEntityDescription(
        key="brine_circulation_pump",
        name="Brine Circulation Pump",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        value_fn=lambda device: device.realtime_info.common.brine_circulation_pump,
        exists_fn=lambda device: device.realtime_info is not None,
    ),
    EpluconSensorEntityDescription(
        key="brine_in_temperature",
        name="Brine In Temperature",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        value_fn=lambda device: device.realtime_info.common.brine_in_temperature,
        exists_fn=lambda device: device.realtime_info is not None,
    ),
    EpluconSensorEntityDescription(
        key="brine_out_temperature",
        name="Brine Out Temperature",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        value_fn=lambda device: device.realtime_info.common.brine_out_temperature,
        exists_fn=lambda device: device.realtime_info is not None,
    ),
    EpluconSensorEntityDescription(
        key="brine_pressure",
        name="Brine Pressure",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPressure.BAR,
        device_class=SensorDeviceClass.PRESSURE,
        value_fn=lambda device: device.realtime_info.common.brine_pressure,
        exists_fn=lambda device: device.realtime_info is not None,
    ),
    EpluconSensorEntityDescription(
        key="compressor_speed",
        name="Compressor Speed",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        value_fn=lambda device: device.realtime_info.common.compressor_speed,
        exists_fn=lambda device: device.realtime_info is not None,
    ),
    EpluconSensorEntityDescription(
        key="condensation_temperature",
        name="Condensation Temperature",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        value_fn=lambda device: device.realtime_info.common.condensation_temperature,
        exists_fn=lambda device: device.realtime_info is not None,
    ),
    EpluconSensorEntityDescription(
        key="configured_indoor_temperature",
        name="Configured Indoor Temperature",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        value_fn=lambda device: device.realtime_info.common.configured_indoor_temperature,
        exists_fn=lambda device: device.realtime_info is not None,
    ),

    EpluconSensorEntityDescription(
        key="cv_pressure",
        name="CV Pressure",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPressure.BAR,
        device_class=SensorDeviceClass.PRESSURE,
        value_fn=lambda device: device.realtime_info.common.cv_pressure,
        exists_fn=lambda device: device.realtime_info is not None,
    ),
    EpluconSensorEntityDescription(
        key="energy_delivered",
        name="Energy Delivered",
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        value_fn=lambda device: device.realtime_info.common.energy_delivered,
        exists_fn=lambda device: device.realtime_info is not None,
    ),
    EpluconSensorEntityDescription(
        key="energy_usage",
        name="Energy Usage",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        value_fn=lambda device: device.realtime_info.common.energy_usage,
        exists_fn=lambda device: device.realtime_info is not None,
    ),
    EpluconSensorEntityDescription(
        key="evaporation_temperature",
        name="Evaporation Temperature",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        value_fn=lambda device: device.realtime_info.common.evaporation_temperature,
        exists_fn=lambda device: device.realtime_info is not None,
    ),
    EpluconSensorEntityDescription(
        key="export_energy",
        name="Export Energy",
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        value_fn=lambda device: device.realtime_info.common.export_energy,
        exists_fn=lambda device: device.realtime_info is not None,
    ),
    EpluconSensorEntityDescription(
        key="heating_in_temperature",
        name="Heating In Temperature",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        value_fn=lambda device: device.realtime_info.common.heating_in_temperature,
        exists_fn=lambda device: device.realtime_info is not None,
    ),

    EpluconSensorEntityDescription(
        key="heating_out_temperature",
        name="Heating Out Temperature",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        value_fn=lambda device: device.realtime_info.common.heating_out_temperature,
        exists_fn=lambda device: device.realtime_info is not None,
    ),
    EpluconSensorEntityDescription(
        key="import_energy",
        name="Import Energy",
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        value_fn=lambda device: device.realtime_info.common.import_energy,
        exists_fn=lambda device: device.realtime_info is not None,
    ),
    EpluconSensorEntityDescription(
        key="inverter_temperature",
        name="Inverter Temperature",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        value_fn=lambda device: device.realtime_info.common.inverter_temperature,
        exists_fn=lambda device: device.realtime_info is not None,
    ),

    EpluconSensorEntityDescription(
        key="operating_hours",
        name="Operating Hours",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.HOURS,
        device_class=SensorDeviceClass.DURATION,
        value_fn=lambda device: device.realtime_info.common.operating_hours,
        exists_fn=lambda device: device.realtime_info is not None,
    ),

    EpluconSensorEntityDescription(
        key="outdoor_temperature",
        name="Outdoor Temperature",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        value_fn=lambda device: device.realtime_info.common.outdoor_temperature,
        exists_fn=lambda device: device.realtime_info is not None,
    ),
    EpluconSensorEntityDescription(
        key="overheating",
        name="Overheating",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        value_fn=lambda device: device.realtime_info.common.overheating,
        exists_fn=lambda device: device.realtime_info is not None,
    ),

    EpluconSensorEntityDescription(
        key="press_gas_pressure",
        name="Press Gas Pressure",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPressure.BAR,
        device_class=SensorDeviceClass.PRESSURE,
        value_fn=lambda device: device.realtime_info.common.press_gas_pressure,
        exists_fn=lambda device: device.realtime_info is not None,
    ),
    EpluconSensorEntityDescription(
        key="press_gas_temperature",
        name="Press Gas Temperature",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        value_fn=lambda device: device.realtime_info.common.press_gas_temperature,
        exists_fn=lambda device: device.realtime_info is not None,
    ),
    EpluconSensorEntityDescription(
        key="production_circulation_pump",
        name="Production Circulation Pump",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        value_fn=lambda device: device.realtime_info.common.production_circulation_pump,
        exists_fn=lambda device: device.realtime_info is not None,
    ),
    EpluconSensorEntityDescription(
        key="suction_gas_pressure",
        name="Suction Gas Pressure",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPressure.BAR,
        device_class=SensorDeviceClass.PRESSURE,
        value_fn=lambda device: device.realtime_info.common.suction_gas_pressure,
        exists_fn=lambda device: device.realtime_info is not None,
    ),
    EpluconSensorEntityDescription(
        key="suction_gas_temperature",
        name="Suction Gas Temperature",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        value_fn=lambda device: device.realtime_info.common.suction_gas_temperature,
        exists_fn=lambda device: device.realtime_info is not None,
    ),
    EpluconSensorEntityDescription(
        key="total_active_power",
        name="Total Active Power",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        value_fn=lambda device: device.realtime_info.common.total_active_power,
        exists_fn=lambda device: device.realtime_info is not None,
    ),

    EpluconSensorEntityDescription(
        key="ww_temperature",
        name="WW Temperature",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        value_fn=lambda device: device.realtime_info.common.ww_temperature,
        exists_fn=lambda device: device.realtime_info is not None,
    ),
    EpluconSensorEntityDescription(
        key="ww_temperature_configured",
        name="WW Temperature Configured",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        value_fn=lambda device: device.realtime_info.common.ww_temperature_configured,
        exists_fn=lambda device: device.realtime_info is not None,
    )
)


async def async_setup_entry(
        hass: HomeAssistant,
        entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Eplucon sensor based on a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    # Ensure the coordinator has refreshed its data
    await coordinator.async_config_entry_first_refresh()

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
        _LOGGER.debug(f"device received in sensor INIT {device} ")
        self.device = device
        self.entity_description = entity_description
        self._attr_name = f"{device.name} {entity_description.name}"
        self._attr_unique_id = f"{device.id}_{entity_description.key}"
        self._update_device_data()

    def _update_device_data(self):
        """Update the internal data from the coordinator."""
        # Assuming devices are updated in the coordinator data
        for updated_device in self.coordinator.data:
            if updated_device.id == self.device.id:
                self.device = updated_device

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        return self.entity_description.value_fn(self.device)

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        _LOGGER.debug("Getting update from coordinator in sensor.")
        self._update_device_data()
        super()._handle_coordinator_update()
