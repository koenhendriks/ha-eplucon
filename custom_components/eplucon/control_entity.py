"""Entities that change heat pump settings through the portal website."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.components.select import SelectEntityDescription
from homeassistant.components.switch import SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .eplucon_api.DTO.DeviceDTO import DeviceDTO
from .web_coordinator import EpluconWebCoordinator

# hass.data[DOMAIN][WEB_COORDINATORS][entry_id], present only when the web
# control credentials are set.
WEB_COORDINATORS = "web_coordinators"


def web_coordinator(hass: HomeAssistant, entry: ConfigEntry) -> EpluconWebCoordinator | None:
    return hass.data.get(DOMAIN, {}).get(WEB_COORDINATORS, {}).get(entry.entry_id)


@dataclass(frozen=True, kw_only=True)
class EpluconSelectDescription(SelectEntityDescription):
    # Portal value -> option key (translated in strings.json).
    value_options: dict[int, str]


def _temperature(key: str, name: str, low: float, high: float, step: float = 0.1, *, delta: bool = False):
    # The bounds apply until the portal's dialog reports its own.
    return NumberEntityDescription(
        key=key,
        name=name,
        native_min_value=low,
        native_max_value=high,
        native_step=step,
        mode=NumberMode.BOX,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        # A difference must not be converted like a temperature.
        device_class=None if delta else NumberDeviceClass.TEMPERATURE,
    )


NUMBERS = (
    _temperature("indoor_temperature", "Target Indoor Temperature", 10, 30),
    _temperature("boiler_temperature", "Warm Water Target Temperature", 0, 65, 1),
    _temperature("boiler_temperature_delta", "Warm Water Restart Delta", -99.9, 99.9, delta=True),
    _temperature("stop_heating_above", "Stop Heating Above", -99.9, 99.9),
    _temperature("stop_passive_cooling_below", "Stop Passive Cooling Below", 0, 35),
    _temperature("stop_active_cooling_below", "Stop Active Cooling Below", 0, 35),
)

SWITCHES = (
    SwitchEntityDescription(key="heating_active", name="Heating"),
    SwitchEntityDescription(key="cooling_active", name="Cooling"),
    SwitchEntityDescription(key="warm_water_active", name="Warm Water Production"),
)

SELECTS = (
    EpluconSelectDescription(
        key="heatpump_active",
        name="Heat Pump State",
        translation_key="heatpump_active",
        value_options={0: "off", 1: "on", 2: "emergency", 3: "apx"},
    ),
    EpluconSelectDescription(
        key="heatpump_operation_mode",
        name="Operation Mode",
        translation_key="heatpump_operation_mode",
        value_options={
            1: "cooling",
            2: "heating",
            3: "auto_th_touch",
            4: "auto_heat_pump",
            5: "fireplace",
        },
    ),
    EpluconSelectDescription(
        key="heating_curve_correction",
        name="Heating Curve Correction",
        translation_key="heating_curve_correction",
        value_options={0: "minus_4", 1: "minus_2", 2: "zero", 3: "plus_2", 4: "plus_4"},
    ),
)


def heat_pump_device_info(device: DeviceDTO) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, device.account_module_index)},
        manufacturer=MANUFACTURER,
    )


class EpluconControlEntity(CoordinatorEntity[EpluconWebCoordinator]):
    def __init__(self, coordinator: EpluconWebCoordinator, device: DeviceDTO, description) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._module_index = device.account_module_index
        self._attr_name = description.name
        self._attr_unique_id = f"{device.id}_control_{description.key}"
        self._attr_device_info = heat_pump_device_info(device)

    @property
    def available(self) -> bool:
        return super().available and self._control_value is not None

    @property
    def _control_value(self) -> float | int | None:
        return self.coordinator.value(self._module_index, self.entity_description.key)

    async def _async_write(self, value: float | int) -> None:
        await self.coordinator.async_set_value(
            self._module_index, self.entity_description.key, value
        )
