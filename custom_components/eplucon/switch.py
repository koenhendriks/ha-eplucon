from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .control_entity import SWITCHES, EpluconControlEntity, web_coordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = web_coordinator(hass, entry)
    if coordinator is None:
        return
    async_add_entities(
        EpluconControlSwitch(coordinator, device, description)
        for device in coordinator.heat_pumps
        for description in SWITCHES
    )


class EpluconControlSwitch(EpluconControlEntity, SwitchEntity):
    @property
    def is_on(self) -> bool | None:
        value = self._control_value
        return None if value is None else bool(value)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_write(1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_write(0)
