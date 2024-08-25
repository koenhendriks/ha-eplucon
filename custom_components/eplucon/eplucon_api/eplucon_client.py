from __future__ import annotations

import aiohttp
import logging
from typing import Any, Optional

from .DTO.CommonInfoDTO import CommonInfoDTO
from .DTO.DeviceDTO import DeviceDTO
from .DTO.RealtimeInfoDTO import RealtimeInfoDTO

BASE_URL = "https://portaal.eplucon.nl/api/v2"
_LOGGER: logging.Logger = logging.getLogger(__package__)


class ApiAuthError(Exception):
    pass


class ApiError(Exception):
    pass


class EpluconApi:
    """Client to talk to Eplucon API"""

    def __init__(self, api_token: str, session: Optional[aiohttp.ClientSession] = None) -> None:
        self._base = BASE_URL
        self._session = session or aiohttp.ClientSession()
        self._headers = {
            "Accept": "application/json",
            "Cache-Control": "no-cache",
            "Authorization": f"Bearer {api_token}"
        }

        _LOGGER.debug("Initialize Eplucon API client")

    async def get_devices(self) -> list[DeviceDTO]:
        url = f"{self._base}/econtrol/modules"
        _LOGGER.debug(f"Eplucon Get devices {url}")
        async with self._session.get(url, headers=self._headers) as response:
            devices = await response.json()
            self.validate_response(devices)
            data = devices.get('data', [])
            return [DeviceDTO(**device) for device in data]

    async def get_realtime_info(self, module_id: int) -> RealtimeInfoDTO:
        url = f"{self._base}/econtrol/modules/{module_id}/get_realtime_info"
        _LOGGER.debug(f"Eplucon Get realtime info for {module_id}: {url}")

        async with self._session.get(url, headers=self._headers) as response:
            data = await response.json()
            self.validate_response(data)

            common_info = CommonInfoDTO(**data['data']['common'])
            heatpump_info = data['data']['heatpump']  # Not sure what this could be
            realtime_info = RealtimeInfoDTO(common=common_info, heatpump=heatpump_info)

            return realtime_info

    @staticmethod
    def validate_response(response: Any) -> None:
        if 'auth' not in response:
            raise ApiError('Error from Eplucon API, expecting auth key in response.')

        if not response['auth']:
            raise ApiAuthError("Authentication failed: Please check the given API key.")
