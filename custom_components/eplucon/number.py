from __future__ import annotations

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .control_entity import NUMBERS, EpluconControlEntity, web_coordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = web_coordinator(hass, entry)
    if coordinator is None:
        return
    async_add_entities(
        EpluconControlNumber(coordinator, device, description)
        for device in coordinator.heat_pumps
        for description in NUMBERS
    )


class EpluconControlNumber(EpluconControlEntity, NumberEntity):
    @property
    def native_value(self) -> float | None:
        value = self._control_value
        return None if value is None else float(value)

    def _bound(self, attr: str, default: float) -> float:
        state = self.coordinator.state(self._module_index, self.entity_description.key)
        value = getattr(state, attr, None) if state is not None else None
        return default if value is None else value

    @property
    def native_min_value(self) -> float:
        return self._bound("min", self.entity_description.native_min_value)

    @property
    def native_max_value(self) -> float:
        return self._bound("max", self.entity_description.native_max_value)

    @property
    def native_step(self) -> float:
        return self._bound("step", self.entity_description.native_step)

    async def async_set_native_value(self, value: float) -> None:
        await self._async_write(value)
