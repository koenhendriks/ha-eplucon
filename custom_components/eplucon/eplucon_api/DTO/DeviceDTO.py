from dataclasses import dataclass
from typing import Optional
from . import RealtimeInfoDTO

@dataclass
class DeviceDTO:
    id: int
    account_module_index: str
    name: str
    type: str
    realtime_info: Optional[RealtimeInfoDTO] = None

