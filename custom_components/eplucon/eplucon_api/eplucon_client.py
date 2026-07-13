from __future__ import annotations

import aiohttp
import json
import logging
from typing import Any

from .DTO.CommonInfoDTO import CommonInfoDTO
from .DTO.DeviceDTO import DeviceDTO
from .DTO.RealtimeInfoDTO import RealtimeInfoDTO
from .DTO.HeatLoadingDTO import HeatLoadingDTO
from .DTO.ZoneDTO import ZoneDTO

BASE_URL = "https://portaal.eplucon.nl/api/v2"

_LOGGER = logging.getLogger(__package__)


class ApiAuthError(Exception):
    """Authentication failed"""


class ApiError(Exception):
    """Generic API error"""


class EpluconApi:
    """Client to talk to the Eplucon API."""

    def __init__(
        self,
        api_token: str,
        api_endpoint: str | None = None,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        self._base = api_endpoint or BASE_URL

        if session is None:
            raise RuntimeError("aiohttp ClientSession is required")

        self._session = session
        self._headers = {
            "Accept": "application/json",
            "Cache-Control": "no-cache",
            "Authorization": f"Bearer {api_token}",
        }

        _LOGGER.debug(
            "Initialized Eplucon API client (endpoint=%s)",
            self._base,
        )



    async def get_devices(self) -> list[DeviceDTO]:
        url = f"{self._base}/econtrol/modules"
        _LOGGER.debug("Fetching devices list: %s", url)

        async with self._session.get(url, headers=self._headers) as response:
            data = await response.json()

        _LOGGER.debug("Devices raw response: %s", data)
        self._validate_response(data)

        devices: list[DeviceDTO] = []

        for item in data.get("data", []):
            try:
                devices.append(DeviceDTO(**item))
            except Exception:
                _LOGGER.exception("Failed to parse device DTO: %s", item)

        _LOGGER.debug("Parsed %d Eplucon devices", len(devices))
        return devices


    async def get_realtime_info(self, module_id: int) -> RealtimeInfoDTO:
        url = f"{self._base}/econtrol/modules/{module_id}/get_realtime_info"
        _LOGGER.debug("Fetching realtime info for %s: %s", module_id, url)

        async with self._session.get(url, headers=self._headers) as response:
            data = await response.json()

        _LOGGER.debug("Realtime raw response for %s: %s", module_id, data)
        self._validate_response(data)

        common = CommonInfoDTO(**data["data"]["common"])
        heatpump = data["data"].get("heatpump")

        return RealtimeInfoDTO(common=common, heatpump=heatpump)

    async def get_heatpump_heatloading_status(self, module_id: int) -> HeatLoadingDTO:
        url = f"{self._base}/econtrol/modules/{module_id}/heatloading_status"
        _LOGGER.debug("Fetching heatloading status for %s: %s", module_id, url)

        async with self._session.get(url, headers=self._headers) as response:
            data = await response.json()

        _LOGGER.debug("Heatloading raw response for %s: %s", module_id, data)
        self._validate_response(data)

        return HeatLoadingDTO(**data["data"])

    async def get_zones(self, module_id: int) -> list[ZoneDTO]:
        """Fetch the regulation zones / control panels of a zone controller.

        Only valid for modules of type ``zones_system_controller``; other
        module types return HTTP 406. See docs/zones-api.md.
        """
        url = f"{self._base}/econtrol/modules/{module_id}/zones"
        _LOGGER.debug("Fetching zones for %s: %s", module_id, url)

        async with self._session.get(url, headers=self._headers) as response:
            data = await response.json()

        _LOGGER.debug("Zones raw response for %s: %s", module_id, data)
        self._validate_response(data)

        zones: list[ZoneDTO] = []
        for item in data.get("data", []):
            try:
                zones.append(self._parse_zone(item))
            except Exception:
                _LOGGER.exception("Failed to parse zone DTO: %s", item)

        _LOGGER.debug("Parsed %d zones for module %s", len(zones), module_id)
        return zones

    @staticmethod
    def _parse_zone(item: dict) -> ZoneDTO:
        """Build a ZoneDTO from one /zones entry, enriching from raw_data."""
        zone = ZoneDTO(
            id=int(item["id"]),
            name=item.get("name"),
            mode=item.get("mode"),
            set_temperature=item.get("set_temperature"),
            current_temperature=item.get("current_temperature"),
        )

        raw = item.get("raw_data")
        if not raw:
            return zone

        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
        except (ValueError, TypeError):
            _LOGGER.debug("Zone %s has unparseable raw_data", zone.id)
            return zone

        z = parsed.get("zone", {}) if isinstance(parsed, dict) else {}
        flags = z.get("flags", {}) if isinstance(z, dict) else {}

        zone.humidity = z.get("humidity")
        zone.battery_level = z.get("batteryLevel")
        zone.signal_strength = z.get("signalStrength")
        zone.actuators_open = z.get("actuatorsOpen")
        zone.zone_state = z.get("zoneState")
        zone.relay_state = flags.get("relayState")
        zone.algorithm = flags.get("algorithm")

        return zone

    @staticmethod
    def _validate_response(response: Any) -> None:
        if not isinstance(response, dict):
            raise ApiError("Invalid API response type")

        if "auth" not in response:
            raise ApiError("Missing 'auth' field in API response")

        if response["auth"] is not True:
            raise ApiAuthError("Authentication failed")
