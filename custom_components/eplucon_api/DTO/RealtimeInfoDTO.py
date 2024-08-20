from dataclasses import dataclass
from typing import List

from eplucon_api.DTO import CommonInfoDTO


@dataclass
class RealtimeInfoDTO:
    common: CommonInfoDTO
    heatpump: List  # I'm always getting an empty list here... the docs say array[string].
