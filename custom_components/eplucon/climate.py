from __future__ import annotations

import time
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
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .control_entity import heat_pump_device_info, web_coordinator
from .eplucon_api.DTO.DeviceDTO import DeviceDTO
from .eplucon_api.DTO.ZoneDTO import ZoneDTO
from .eplucon_api.web_control import ControlState, zone_key
from .web_coordinator import EpluconWebCoordinator
from .zone_entity import EpluconZoneEntity, zones_of

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
    entities: list[ClimateEntity] = [
        EpluconClimate(coordinator, api_coordinator, device)
        for device in coordinator.heat_pumps
    ]

    # The zones come from the API, like the zone sensors: a zone the API
    # didn't report at setup gets its thermostat after a reload.
    entities.extend(
        EpluconZoneClimate(api_coordinator, coordinator, device, zone)
        for device, zone in zones_of(api_coordinator.data)
    )
    async_add_entities(entities)


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


ZONE_CLIMATE = EntityDescription(key="climate", name=None)

# The portal's zone form: 5-35 °C in tenths of a degree. The form's own bounds
# apply once web control has read it.
ZONE_MIN_TEMP = 5.0
ZONE_MAX_TEMP = 35.0
ZONE_TEMP_STEP = 0.1


class EpluconZoneClimate(EpluconZoneEntity, ClimateEntity):
    """A zone's control panel as a thermostat.

    Readings come from the API every update interval, the setpoint is written
    through web control. Writing it puts the zone on a constant temperature,
    as the portal's own "Constante temperatuur" dialog does, overriding the
    zone's schedule. The zone heats or cools as the heat pump does: its HVAC
    mode only reports that and can't be changed here.

    The readings stay available while web control is down; only setting the
    target is refused then.
    """

    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_target_temperature_step = ZONE_TEMP_STEP

    def __init__(
        self,
        api_coordinator,
        web: EpluconWebCoordinator,
        device: DeviceDTO,
        zone: ZoneDTO,
    ) -> None:
        super().__init__(api_coordinator, device, zone, ZONE_CLIMATE)
        self._web = web
        self._key = zone_key(zone.id)
        # This zone's target as each source last reported it, and when that
        # changed: the target comes from the source that changed last. Only a
        # change counts. Both coordinators tell every entity about every update
        # (a write to another zone, or the API repeating its last data during
        # an outage), which says nothing new about this zone.
        self._api_seen: float | None = None
        self._web_seen: float | int | None = None
        self._api_at = 0.0
        self._web_at = 0.0

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # What there is at the start is no change from either source.
        self._api_seen = self._api_target()
        self._web_seen = self._web_value()
        self.async_on_remove(self._web.async_add_listener(self._handle_web_update))

    @staticmethod
    def _changed(seen, value) -> bool:
        """Whether a source's new value is a change of the zone's target.

        Losing a source (None) or getting it back says nothing about the
        target: after a portal outage the zones page may still show what it
        had before, while the API has followed a change made meanwhile.
        """
        return seen is not None and value is not None and seen != value

    @callback
    def _handle_coordinator_update(self) -> None:
        reported = self._api_target()
        if self._changed(self._api_seen, reported):
            self._api_at = time.monotonic()
        self._api_seen = reported
        super()._handle_coordinator_update()

    @callback
    def _handle_web_update(self) -> None:
        value = self._web_value()
        if self._changed(self._web_seen, value):
            self._web_at = time.monotonic()
        self._web_seen = value
        self.async_write_ha_state()

    def _api_target(self) -> float | None:
        zone = self.zone
        return None if zone is None else self._number(zone.set_temperature)

    def _web_value(self) -> float | int | None:
        state = self._web_state()
        return None if state is None else state.value

    def _web_state(self) -> ControlState | None:
        """The zone's form as web control last read it, if web control works."""
        if not self._web.last_update_success:
            return None
        return self._web.state(self._module_index, self._key)

    @staticmethod
    def _number(value) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @property
    def native_current_temperature(self) -> float | None:
        zone = self.zone
        return None if zone is None else self._number(zone.current_temperature)

    @property
    def current_humidity(self) -> float | None:
        zone = self.zone
        return None if zone is None else self._number(zone.humidity)

    @property
    def native_target_temperature(self) -> float | None:
        reported = self._api_target()
        value = self._web_value()
        if value is None:
            return reported
        # While a write waits for the portal to report it, web control holds
        # the value sent. Otherwise the target is whichever source changed
        # last: a write, or a change on the control panel the API reported.
        if (
            reported is None
            or self._web.is_pending(self._module_index, self._key)
            or self._web_at > self._api_at
        ):
            return value / 10
        return reported

    def _bound(self, attr: str, default: float) -> float:
        state = self._web_state()
        value = getattr(state, attr, None) if state is not None else None
        return default if value is None else value / 10

    @property
    def min_temp(self) -> float:
        return self._bound("min", ZONE_MIN_TEMP)

    @property
    def max_temp(self) -> float:
        return self._bound("max", ZONE_MAX_TEMP)

    @property
    def hvac_mode(self) -> HVACMode:
        zone = self.zone
        if zone is not None and str(zone.algorithm).lower() == "cooling":
            return HVACMode.COOL
        return HVACMode.HEAT

    @property
    def hvac_modes(self) -> list[HVACMode]:
        return [self.hvac_mode]

    @property
    def hvac_action(self) -> HVACAction | None:
        zone = self.zone
        if zone is None or zone.relay_state is None:
            return None
        if str(zone.relay_state).lower() != "on":
            return HVACAction.IDLE
        return HVACAction.COOLING if self.hvac_mode == HVACMode.COOL else HVACAction.HEATING

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode != self.hvac_mode:
            raise ServiceValidationError(
                "A zone heats or cools as the heat pump does; change the heat "
                "pump's operation mode instead"
            )

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        if self._web_state() is None:
            raise HomeAssistantError(
                "Eplucon web control can't read this zone from the portal at the "
                "moment, so its target temperature can't be set"
            )
        target = round(float(temperature), 1)
        await self._web.async_set_value(self._module_index, self._key, round(target * 10))


# Home Assistant 2026.11 reads the native_* names and warns about the old ones;
# older releases only know the old ones. Drop this once 2026.11 is the minimum.
if not hasattr(ClimateEntity, "native_target_temperature"):
    for _cls in (EpluconClimate, EpluconZoneClimate):
        _cls._attr_temperature_unit = UnitOfTemperature.CELSIUS
        _cls.current_temperature = property(lambda self: self.native_current_temperature)
        _cls.target_temperature = property(lambda self: self.native_target_temperature)
