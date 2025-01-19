from dataclasses import dataclass
from typing import Optional
from .RealtimeInfoDTO import RealtimeInfoDTO
from .HeatLoadingDTO import HeatLoadingDTO


@dataclass
class DeviceDTO:
    id: int
    account_module_index: str
    name: str
    type: str
    realtime_info: Optional[RealtimeInfoDTO] = None
    heatloading_status: Optional[HeatLoadingDTO] = None
