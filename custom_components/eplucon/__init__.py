from __future__ import annotations

import logging
import time
import asyncio
import dataclasses
from datetime import timedelta
from typing import Dict

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import device_registry

from dacite import from_dict

from .const import (
    DOMAIN,
    PLATFORMS,
    EPLUCON_PORTAL_URL,
    MANUFACTURER,
    SUPPORTED_TYPES,
    HEAT_PUMP_TYPES,
    ZONE_CONTROLLER_TYPES,
)
from .eplucon_api.eplucon_client import (
    EpluconApi,
    ApiError,
    DeviceDTO,
    BASE_URL,
)

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = timedelta(seconds=30)


# ----------------------------
# Helper functions
# ----------------------------

def is_valid_realtime_info(info) -> bool:
    """Return False if payload is clearly invalid (disconnect / zero dump)."""
    if info is None or info.common is None:
        return False

    # Pick a few stable indicators that should never ALL be zero
    indicators = [
        info.common.indoor_temperature,
        info.common.outdoor_temperature,
        info.common.operating_hours,
    ]

    return any(v not in (None, 0) for v in indicators)


async def fetch_with_retry(func, *args, retries=3, delay=2):
    """Retry wrapper for API calls."""
    for attempt in range(1, retries + 1):
        try:
            return await func(*args)
        except Exception as err:
            if attempt == retries:
                raise
            _LOGGER.warning(
                "API call %s failed (%s), retry %d/%d",
                func.__name__,
                err,
                attempt,
                retries,
            )
            await asyncio.sleep(delay)


async def device_dict_to_dto(device: DeviceDTO | dict) -> DeviceDTO:
    """Ensure device is DeviceDTO."""
    if isinstance(device, dict):
        device = from_dict(data_class=DeviceDTO, data=device)
    return device


async def _update_heat_pump(client, device: DeviceDTO, hass: HomeAssistant) -> DeviceDTO:
    """Fetch heat pump realtime + heatloading data, with last-good fallback."""
    realtime_info = await fetch_with_retry(client.get_realtime_info, device.id)
    _LOGGER.debug("Realtime info for %s: %s", device.id, realtime_info)

    heatloading_status = await fetch_with_retry(
        client.get_heatpump_heatloading_status, device.id
    )
    _LOGGER.debug("Heatloading status for %s: %s", device.id, heatloading_status)

    # Validate before overwriting
    if is_valid_realtime_info(realtime_info):
        device.realtime_info = realtime_info
        device.heatloading_status = heatloading_status
        hass.data[DOMAIN]["last_good_devices"][device.id] = device
    else:
        _LOGGER.warning(
            "Invalid realtime data for device %s, keeping last known values",
            device.id,
        )
        last_good = hass.data[DOMAIN]["last_good_devices"].get(device.id)
        if last_good:
            device = last_good

    return device


async def _update_zone_controller(client, device: DeviceDTO, hass: HomeAssistant) -> DeviceDTO:
    """Fetch the regulation zones for a zones_system_controller module."""
    zones = await fetch_with_retry(client.get_zones, device.id)
    _LOGGER.debug("Fetched %d zones for %s", len(zones or []), device.id)

    if zones:
        device.zones = zones
        hass.data[DOMAIN]["last_good_devices"][device.id] = device
    else:
        last_good = hass.data[DOMAIN]["last_good_devices"].get(device.id)
        if last_good:
            _LOGGER.warning(
                "No zones returned for controller %s, keeping last known values",
                device.id,
            )
            device = last_good
        else:
            # Entities are built at platform setup, so with nothing to fall
            # back on this controller gets no zone entities at all until the
            # integration is reloaded. Say so rather than finish setup quietly.
            _LOGGER.warning(
                "No zones returned for controller %s and no previously known "
                "zones; no zone entities will be created until the integration "
                "is reloaded",
                device.id,
            )

    return device


def _device_id(device) -> object:
    """Return the module id from a stored dict or a DeviceDTO."""
    return device["id"] if isinstance(device, dict) else device.id


async def _ensure_supported_devices(hass: HomeAssistant, entry: ConfigEntry, client) -> None:
    """Merge in supported modules missing from the stored config entry.

    Older versions only stored heat_pump modules, so zone controllers added
    to an account (or supported by a newer release) never appeared. Re-fetch
    the module list at setup and add any supported module we don't have yet.
    """
    try:
        fetched = await client.get_devices()
    except Exception:  # network/API hiccup: keep the stored list, try again next start
        _LOGGER.warning("Could not refresh Eplucon module list at setup", exc_info=True)
        return

    existing = list(entry.data.get("devices", []))
    existing_ids = {_device_id(d) for d in existing}

    missing = [
        dataclasses.asdict(dev)
        for dev in fetched
        if dev.type in SUPPORTED_TYPES and dev.id not in existing_ids
    ]

    if not missing:
        return

    _LOGGER.info(
        "Adding %d newly supported Eplucon module(s) to the config entry: %s",
        len(missing),
        [(d["id"], d["type"]) for d in missing],
    )
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, "devices": existing + missing}
    )


# ----------------------------
# Setup entry
# ----------------------------

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Eplucon from a config entry."""
    api_token = entry.data["api_token"]
    api_endpoint = entry.data.get("api_endpoint", BASE_URL)

    session = async_get_clientsession(hass)
    client = EpluconApi(api_token, api_endpoint, session)

    # Store last known good devices
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault("last_good_devices", {})

    # Pick up modules (e.g. zone controllers) not present in an older entry.
    await _ensure_supported_devices(hass, entry, client)
    devices = entry.data["devices"]

    await register_devices(devices, entry, hass)

    async def async_update_data() -> list[DeviceDTO]:
        start = time.monotonic()
        updated_devices: list[DeviceDTO] = []

        try:
            for entry_device in entry.data["devices"]:
                device = await device_dict_to_dto(entry_device)

                _LOGGER.debug(
                    "Updating device %s (%s, type=%s)",
                    device.name,
                    device.id,
                    device.type,
                )

                if device.type in HEAT_PUMP_TYPES:
                    device = await _update_heat_pump(client, device, hass)
                elif device.type in ZONE_CONTROLLER_TYPES:
                    device = await _update_zone_controller(client, device, hass)
                else:
                    continue

                updated_devices.append(device)

            _LOGGER.debug(
                "Finished fetching Eplucon devices data in %.3f seconds (success: True)",
                time.monotonic() - start,
            )
            return updated_devices

        except ApiError as err:
            _LOGGER.error("Eplucon API error: %s", err)
            raise

        except Exception:
            _LOGGER.exception("Unexpected error while updating Eplucon data")
            raise

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="Eplucon devices",
        update_method=async_update_data,
        update_interval=UPDATE_INTERVAL,
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


# ----------------------------
# Device registry
# ----------------------------

async def register_devices(devices, entry, hass):
    registry = device_registry.async_get(hass)

    for device in devices:
        device = await device_dict_to_dto(device)

        registry.async_get_or_create(
            configuration_url=EPLUCON_PORTAL_URL,
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, device.account_module_index)},
            manufacturer=MANUFACTURER,
            suggested_area="Utility Room",
            name=device.name,
            model=device.type,
        )


# ----------------------------
# Unload
# ----------------------------

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, PLATFORMS
    )

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    return unload_ok
