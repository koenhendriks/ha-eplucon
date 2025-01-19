from dataclasses import dataclass


@dataclass
class HeatLoadingDTO:
    heatloading_active: bool
    configurations: dict[str, bool]
