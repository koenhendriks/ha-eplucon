from dataclasses import dataclass
from typing import List
from .CommonInfoDTO import CommonInfoDTO


@dataclass
class RealtimeInfoDTO:
    common: CommonInfoDTO
    heatpump: List  # I'm always getting an empty list here... the Eplucon API docs say array[string].

    @staticmethod
    def from_dict(data: dict) -> 'RealtimeInfoDTO':
        common_info = CommonInfoDTO.from_dict(data.get("common"))
        heatpump = data.get("heatpump", [])
        return RealtimeInfoDTO(common=common_info, heatpump=heatpump)
