from dataclasses import dataclass

@dataclass
class DeviceDTO:
    id: int
    account_module_index: str
    name: str
    type: str
