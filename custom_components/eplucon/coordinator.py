from datetime import timedelta
import logging
from homeassistant.config_entries import ConfigEntry
from typing import Callable

from device import EpluconDevice

_LOGGER = logging.getLogger(__name__)

import async_timeout

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import callback, HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed, _DataT,
)

from .const import DOMAIN


async def async_setup_entry(
        hass: HomeAssistant,
        entry: ConfigEntry,
        async_add_entities: Callable
) -> None:
    # assuming API object stored here by __init__.py
    eplucon_api = hass.data[DOMAIN][entry.entry_id]
    coordinator = EpluconCoordinator(hass, eplucon_api)

    await coordinator.async_config_entry_first_refresh()

    async_add_entities(
        MyEntity(coordinator, idx) for idx, ent in enumerate(coordinator.data)
    )


class EpluconCoordinator(DataUpdateCoordinator):
    """Eplucon coordinator."""

    def __init__(self, hass: HomeAssistant, eplucon_api) -> None:
        """Initialize my coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="Eplucon Heat Pump",
            update_interval=timedelta(seconds=30),
            always_update=True
        )
        self.eplucon_api = eplucon_api
        self._device: EpluconDevice | None = None

    async def _async_setup(self) -> None:
        """Set up the coordinator

        This is the place to set up your coordinator,
        or to load data, that only needs to be loaded once.

        This method will be called automatically during
        coordinator.async_config_entry_first_refresh.
        """
        self._device = await self.eplucon_api.get_device()

    async def _async_update_data(self)  -> _DataT:
        """Fetch data from API endpoint.

        This is the place to pre-process the data to lookup tables
        so entities can quickly look up their data.
        """
        try:
            # Note: asyncio.TimeoutError and aiohttp.ClientError are already
            # handled by the data update coordinator.
            async with async_timeout.timeout(10):
                return await self.eplucon_api.fetch_data()
        except ApiAuthError as err:
            # Raising ConfigEntryAuthFailed will cancel future updates
            # and start a config flow with SOURCE_REAUTH (async_step_reauth)
            raise ConfigEntryAuthFailed from err
        except ApiError as err:
            raise UpdateFailed(f"Error communicating with API: {err}")


class MyEntity(CoordinatorEntity, SensorEntity):
    """An entity using CoordinatorEntity.

    The CoordinatorEntity class provides:
      should_poll
      async_update
      async_added_to_hass
      available

    """

    _attr_should_poll = True

    def __init__(self, coordinator, idx):
        """Pass coordinator to CoordinatorEntity."""
        super().__init__(coordinator, context=idx)
        self.idx = idx

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_is_on = self.coordinator.data[self.idx]["state"]
        self.async_write_ha_state()
