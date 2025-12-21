from __future__ import annotations

import aiohttp
import logging
from typing import Any

from .DTO.CommonInfoDTO import CommonInfoDTO
from .DTO.DeviceDTO import DeviceDTO
from .DTO.RealtimeInfoDTO import RealtimeInfoDTO
from .DTO.HeatLoadingDTO import HeatLoadingDTO

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

    @staticmethod
    def _validate_response(response: Any) -> None:
        if not isinstance(response, dict):
            raise ApiError("Invalid API response type")

        if "auth" not in response:
            raise ApiError("Missing 'auth' field in API response")

        if response["auth"] is not True:
            raise ApiAuthError("Authentication failed")
