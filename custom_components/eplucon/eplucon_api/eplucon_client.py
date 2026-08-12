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

# The zones endpoint answers 406 "Account is not a zone-controller" for a
# module that has no zones. See docs/zones-api.md section 2.
HTTP_NOT_ACCEPTABLE = 406

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
        # Modules the zones endpoint has already rejected with a 406, so the
        # warning is logged once instead of on every coordinator refresh.
        self._not_a_zone_controller: set[int] = set()
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
            status = response.status
            # This is the first endpoint with a documented non-200 path, and
            # the error body's content type isn't documented, so don't let
            # aiohttp reject it before we can read the message out of it.
            try:
                data = await response.json(content_type=None)
            except (aiohttp.ClientError, ValueError):
                data = None

        _LOGGER.debug(
            "Zones raw response for %s (HTTP %s): %s", module_id, status, data
        )

        message = data.get("message") if isinstance(data, dict) else None
        error_code = self._error_code(data)

        # A 406 is permanent: this module will never have zones. Retrying it
        # or failing the whole coordinator refresh over it would both be
        # disproportionate, so report "no zones" and warn once.
        if HTTP_NOT_ACCEPTABLE in (status, error_code):
            if module_id not in self._not_a_zone_controller:
                self._not_a_zone_controller.add(module_id)
                _LOGGER.warning(
                    "Eplucon module %s does not expose zones, no zone entities "
                    "will be created for it: %s",
                    module_id,
                    message or f"HTTP {HTTP_NOT_ACCEPTABLE} from {url}",
                )
            return []

        if status != 200:
            if status in (401, 403):
                raise ApiAuthError(
                    f"Not authorized to read zones of module {module_id} "
                    f"(HTTP {status})"
                )
            raise ApiError(
                f"Zones request for module {module_id} failed with HTTP {status}"
                + (f": {message}" if message else "")
            )

        self._validate_response(data)

        if error_code is not None and error_code != 200:
            raise ApiError(
                f"Zones request for module {module_id} returned error_code "
                f"{error_code}" + (f": {message}" if message else "")
            )

        items = data.get("data")
        if not isinstance(items, list):
            raise ApiError(
                f"Zones response for module {module_id} has no 'data' list: {items!r}"
            )

        zones: list[ZoneDTO] = []
        for item in items:
            try:
                zones.append(self._parse_zone(item))
            except ValueError as err:
                # An entry we can't identify; no stacktrace needed for it.
                _LOGGER.warning("Skipping unusable zone entry: %s", err)
            except Exception:
                _LOGGER.exception("Failed to parse zone DTO: %s", item)

        _LOGGER.debug("Parsed %d zones for module %s", len(zones), module_id)
        return zones

    @staticmethod
    def _error_code(data: Any) -> int | None:
        """Return the response's error_code as an int, or None if unusable."""
        if not isinstance(data, dict):
            return None

        raw = data.get("error_code")
        if raw is None:
            return None

        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_zone(item: dict) -> ZoneDTO:
        """Build a ZoneDTO from one /zones entry, enriching from raw_data.

        Raises ValueError for an entry that cannot be identified; anything the
        enrichment step can't make sense of is left as None rather than losing
        the top-level fields with it.
        """
        if not isinstance(item, dict):
            raise ValueError(f"zone entry is not an object: {item!r}")

        raw_id = item.get("id")
        if raw_id is None:
            raise ValueError(f"zone entry has no id: {item}")

        try:
            zone_id = int(raw_id)
        except (TypeError, ValueError):
            raise ValueError(
                f"zone entry has a non-numeric id {raw_id!r}: {item}"
            ) from None

        zone = ZoneDTO(
            id=zone_id,
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

        # Both keys can be present with a JSON null, so a `.get(key, {})`
        # default is not enough: check what actually came back.
        z = parsed.get("zone") if isinstance(parsed, dict) else None
        if not isinstance(z, dict):
            z = {}

        flags = z.get("flags")
        if not isinstance(flags, dict):
            flags = {}

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
