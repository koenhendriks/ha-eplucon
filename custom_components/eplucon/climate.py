from __future__ import annotations

from typing import Any

from dacite import from_dict

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .control_entity import heat_pump_device_info, web_coordinator
from .eplucon_api.DTO.DeviceDTO import DeviceDTO
from .web_coordinator import EpluconWebCoordinator

# heatpump_active: 0 off, 1 on, 2 emergency operation, 3 APX.
ACTIVE_OFF = 0
ACTIVE_ON = 1

# heatpump_operation_mode values.
MODE_COOLING = 1
MODE_HEATING = 2
MODE_AUTO_TH_TOUCH = 3
MODE_AUTO_HEAT_PUMP = 4
MODE_FIREPLACE = 5

OPERATION_TO_HVAC = {
    MODE_COOLING: HVACMode.COOL,
    MODE_HEATING: HVACMode.HEAT,
    MODE_AUTO_TH_TOUCH: HVACMode.HEAT_COOL,
    MODE_AUTO_HEAT_PUMP: HVACMode.HEAT_COOL,
    MODE_FIREPLACE: HVACMode.HEAT,
}

# Auto th-TOUCH is what the portal offers first for automatic switching.
HVAC_TO_OPERATION = {
    HVACMode.COOL: MODE_COOLING,
    HVACMode.HEAT: MODE_HEATING,
    HVACMode.HEAT_COOL: MODE_AUTO_TH_TOUCH,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = web_coordinator(hass, entry)
    if coordinator is None:
        return
    api_coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        EpluconClimate(coordinator, api_coordinator, device)
        for device in coordinator.heat_pumps
    )


class EpluconClimate(CoordinatorEntity[EpluconWebCoordinator], ClimateEntity):
    """The heat pump as a thermostat: room temperature from the API, the rest via web control."""

    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL, HVACMode.HEAT_COOL]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_target_temperature_step = 0.1
    _attr_min_temp = 10
    _attr_max_temp = 30

    def __init__(self, coordinator: EpluconWebCoordinator, api_coordinator, device: DeviceDTO) -> None:
        super().__init__(coordinator)
        self._api_coordinator = api_coordinator
        self._device = device
        self._module_index = device.account_module_index
        self._attr_name = "Thermostat"
        self._attr_unique_id = f"{device.id}_control_climate"
        self._attr_device_info = heat_pump_device_info(device)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # The room temperature comes from the API every 30 s; follow it too.
        self.async_on_remove(
            self._api_coordinator.async_add_listener(self._handle_coordinator_update)
        )

    def _common(self):
        for device in self._api_coordinator.data or []:
            if isinstance(device, dict):
                device = from_dict(data_class=DeviceDTO, data=device)
            if device.id == self._device.id:
                realtime = device.realtime_info
                return realtime.common if realtime is not None else None
        return None

    def _api_number(self, attr: str) -> float | None:
        common = self._common()
        try:
            return float(getattr(common, attr))
        except (AttributeError, TypeError, ValueError):
            return None

    def _web(self, key: str) -> float | int | None:
        return self.coordinator.value(self._module_index, key)

    def _setting(self, web_key: str, api_attr: str) -> int | None:
        value = self._web(web_key)
        if value is None:
            value = self._api_number(api_attr)
        return None if value is None else int(value)

    @property
    def available(self) -> bool:
        return super().available and self._web("indoor_temperature") is not None

    @property
    def native_current_temperature(self) -> float | None:
        return self._api_number("indoor_temperature")

    @property
    def native_target_temperature(self) -> float | None:
        value = self._web("indoor_temperature")
        if value is None:
            return self._api_number("configured_indoor_temperature")
        return float(value)

    @property
    def hvac_mode(self) -> HVACMode | None:
        active = self._setting("heatpump_active", "heating_mode")
        if active is None:
            return None
        if active == ACTIVE_OFF:
            return HVACMode.OFF
        operation = self._setting("heatpump_operation_mode", "operation_mode")
        return OPERATION_TO_HVAC.get(operation)

    @property
    def hvac_action(self) -> HVACAction | None:
        mode = self.hvac_mode
        if mode is None:
            return None
        if mode == HVACMode.OFF:
            return HVACAction.OFF
        heating = self._api_number("current_heating_state")
        if heating is None:
            return None
        if heating and mode != HVACMode.COOL:
            return HVACAction.HEATING
        return HVACAction.IDLE

    async def async_set_temperature(self, **kwargs: Any) -> None:
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is not None:
            await self.coordinator.async_set_value(
                self._module_index, "indoor_temperature", round(float(temperature), 1)
            )

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            await self.coordinator.async_set_value(
                self._module_index, "heatpump_active", ACTIVE_OFF
            )
            return

        if self._setting("heatpump_active", "heating_mode") == ACTIVE_OFF:
            await self.coordinator.async_set_value(
                self._module_index, "heatpump_active", ACTIVE_ON
            )
        # Fireplace already counts as heating and Auto Wp as automatic: leave
        # an operation mode alone when it already gives the requested mode.
        current = self._setting("heatpump_operation_mode", "operation_mode")
        if OPERATION_TO_HVAC.get(current) != hvac_mode:
            await self.coordinator.async_set_value(
                self._module_index, "heatpump_operation_mode", HVAC_TO_OPERATION[hvac_mode]
            )

    async def async_turn_on(self) -> None:
        await self.coordinator.async_set_value(self._module_index, "heatpump_active", ACTIVE_ON)

    async def async_turn_off(self) -> None:
        await self.coordinator.async_set_value(self._module_index, "heatpump_active", ACTIVE_OFF)


# Home Assistant 2026.11 reads the native_* names and warns about the old ones;
# older releases only know the old ones. Drop this once 2026.11 is the minimum.
if not hasattr(ClimateEntity, "native_target_temperature"):
    EpluconClimate._attr_temperature_unit = UnitOfTemperature.CELSIUS
    EpluconClimate.current_temperature = property(lambda self: self.native_current_temperature)
    EpluconClimate.target_temperature = property(lambda self: self.native_target_temperature)
