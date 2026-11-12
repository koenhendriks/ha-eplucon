from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .control_entity import SELECTS, EpluconControlEntity, web_coordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = web_coordinator(hass, entry)
    if coordinator is None:
        return
    async_add_entities(
        EpluconControlSelect(coordinator, device, description)
        for device in coordinator.heat_pumps
        for description in SELECTS
    )


class EpluconControlSelect(EpluconControlEntity, SelectEntity):
    def __init__(self, coordinator, device, description) -> None:
        super().__init__(coordinator, device, description)
        self._attr_options = list(description.value_options.values())

    @property
    def current_option(self) -> str | None:
        value = self._control_value
        if value is None:
            return None
        return self.entity_description.value_options.get(int(value))

    async def async_select_option(self, option: str) -> None:
        value = next(
            v for v, o in self.entity_description.value_options.items() if o == option
        )
        await self._async_write(value)
