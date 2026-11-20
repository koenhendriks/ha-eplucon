from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional
from .RealtimeInfoDTO import RealtimeInfoDTO
from .HeatLoadingDTO import HeatLoadingDTO
from .ZoneDTO import ZoneDTO


@dataclass
class DeviceDTO:
    id: int
    account_module_index: str
    name: str
    type: str
    realtime_info: Optional[RealtimeInfoDTO] = None
    heatloading_status: Optional[HeatLoadingDTO] = None
    zones: Optional[List[ZoneDTO]] = None


STORED_DEVICE_FIELDS = ("id", "account_module_index", "name", "type")


def stored_device(device: DeviceDTO | dict) -> dict:
    """Return the part of a module that belongs in the config entry.

    Only the module's identity: realtime values or zones stored with it are
    stale by the next start, and the API sometimes sends values (such as a
    null operation_mode) that the DTOs don't allow.
    """
    if isinstance(device, dict):
        return {field: device.get(field) for field in STORED_DEVICE_FIELDS}
    return {field: getattr(device, field) for field in STORED_DEVICE_FIELDS}
