import logging
from datetime import timedelta
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .eplucon_api.eplucon_client import EpluconApi, ApiError, DeviceDTO
from .const import DOMAIN, PLATFORMS
from dacite import from_dict


_LOGGER = logging.getLogger(__name__)

# Time between data updates
UPDATE_INTERVAL = timedelta(seconds=5)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Eplucon from a config entry."""
    api_token = entry.data["api_token"]

    session = async_get_clientsession(hass)
    client = EpluconApi(api_token, session)

    async def async_update_data() -> list[DeviceDTO]:
        """Fetch Eplucon data from API endpoint."""
        try:
            devices = entry.data["devices"]

            # For each device, fetch the real-time info and combine it with the device data
            for device in devices:
                ##
                # When retrieving given devices from HASS config flow the entry.data["devices"]
                # is type list[DeviceDTO] but on boot this is a list[dict], not sure why and if this is intended,
                # but we will ensure we can parse the correct format here.
                ##
                if isinstance(device, dict):
                    device = from_dict(data_class=DeviceDTO, data=device)

                device_id = device.id
                realtime_info = await client.get_realtime_info(device_id)
                device.realtime_info = realtime_info

            return devices

        except ApiError as err:
            _LOGGER.error(f"Error fetching data from Eplucon API: {err}")
            raise err

    # Set up the coordinator to manage fetching data from the API
    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="Eplucon devices",
        update_method=async_update_data,
        update_interval=UPDATE_INTERVAL,
    )

    # Fetch initial data so we have data when entities subscribe
    await coordinator.async_config_entry_first_refresh()

    # Store the coordinator in hass.data, so it's accessible in other parts of the integration
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # Forward the setup to the sensor platform
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
