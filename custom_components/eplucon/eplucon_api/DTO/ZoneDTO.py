from dataclasses import dataclass
from typing import Optional, Union


@dataclass
class ZoneDTO:
    """A single regulation zone / control panel of a zones_system_controller.

    Top-level fields come straight from the /zones API response; the remaining
    fields are extracted from the (double-encoded) ``raw_data`` JSON string.
    See docs/zones-api.md for the full field reference.
    """

    id: int
    name: str
    mode: Optional[str] = None
    set_temperature: Union[float, str, None] = None
    current_temperature: Union[float, str, None] = None

    # Extracted from raw_data.zone
    humidity: Optional[float] = None
    battery_level: Optional[float] = None
    signal_strength: Optional[float] = None
    relay_state: Optional[str] = None        # "on" / "off"
    algorithm: Optional[str] = None          # "heating" / "cooling"
    actuators_open: Optional[int] = None
    zone_state: Optional[str] = None         # e.g. "noAlarm"
