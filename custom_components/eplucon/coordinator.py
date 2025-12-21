from datetime import timedelta
import logging
import async_timeout
from typing import Callable


from homeassistant.config_entries import ConfigEntry
from homeassistant.components.sensor import SensorEntity
from homeassistant.core import callback, HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
    _DataT,
)

from .const import DOMAIN
from .eplucon_api.eplucon_client import ApiAuthError, ApiError
from .device import EpluconDevice

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: Callable,
) -> None:
    """Set up Eplucon sensors via config entry with logging."""
    eplucon_api = hass.data[DOMAIN][entry.entry_id]
    coordinator = EpluconCoordinator(hass, eplucon_api)

    # Optional one-time setup
    if hasattr(coordinator, "_async_setup"):
        await coordinator._async_setup()

    await coordinator.async_config_entry_first_refresh()

    _LOGGER.debug("Setting up sensor entities from coordinator data:")
    for idx, data in enumerate(coordinator.data):
        _LOGGER.debug("Sensor idx %d initial data: %s", idx, data)

    async_add_entities(
        MyEntity(coordinator, idx) for idx, _ in enumerate(coordinator.data)
    )


class EpluconCoordinator(DataUpdateCoordinator):
    """Coordinator to fetch data from Eplucon API with logging."""

    def __init__(self, hass: HomeAssistant, eplucon_api) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="Eplucon Coordinator",
            update_interval=timedelta(seconds=30),
            always_update=True,
        )
        self.eplucon_api = eplucon_api
        self._device: EpluconDevice | None = None

    async def _async_setup(self) -> None:
        """Optional one-time setup: fetch devices."""
        self._device = await self.eplucon_api.get_devices()
        _LOGGER.debug("Fetched %d devices during setup", len(self._device))

    async def _async_update_data(self) -> _DataT:
        """Fetch data from API and log results."""
        try:
            async with async_timeout.timeout(10):
                data = await self.eplucon_api.fetch_data()
                _LOGGER.debug("Coordinator fetched data: %s", data)
                return data
        except ApiAuthError as err:
            _LOGGER.error("Authentication failed during data fetch: %s", err)
            raise ConfigEntryAuthFailed from err
        except ApiError as err:
            _LOGGER.error("API error during data fetch: %s", err)
            raise UpdateFailed(f"Error communicating with API: {err}")
        except Exception as err:
            _LOGGER.exception("Unexpected error fetching Eplucon data: %s", err)
            raise UpdateFailed(f"Unexpected error: {err}")


class MyEntity(CoordinatorEntity, SensorEntity):
    """Sensor entity using the coordinator, with logging."""

    _attr_should_poll = False

    def __init__(self, coordinator: EpluconCoordinator, idx: int) -> None:
        super().__init__(coordinator, context=idx)
        self.idx = idx

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update the sensor state when coordinator data changes."""
        try:
            value = self.coordinator.data[self.idx].get("state")
            _LOGGER.debug(
                "Updating sensor idx %d with new value: %s", self.idx, value
            )
            self._attr_native_value = value
            self.async_write_ha_state()
        except IndexError:
            _LOGGER.warning("Coordinator data missing for sensor idx %d", self.idx)
        except KeyError:
            _LOGGER.warning("Coordinator data missing 'state' for idx %d", self.idx)
