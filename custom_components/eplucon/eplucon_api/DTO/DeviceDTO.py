from dataclasses import dataclass
from typing import Optional
from .RealtimeInfoDTO import RealtimeInfoDTO


@dataclass
class DeviceDTO:
    id: int
    account_module_index: str
    name: str
    type: str
    realtime_info: Optional[RealtimeInfoDTO] = None

    @staticmethod
    def from_dict(data: dict) -> 'DeviceDTO':
        realtime_info_data = data.get("realtime_info")
        realtime_info = RealtimeInfoDTO.from_dict(realtime_info_data) if realtime_info_data else None
        return DeviceDTO(
            id=data.get("id"),
            account_module_index=data.get("account_module_index"),
            name=data.get("name"),
            type=data.get("type"),
            realtime_info=realtime_info
        )
