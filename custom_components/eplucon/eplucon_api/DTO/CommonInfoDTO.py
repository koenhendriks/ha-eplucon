from dataclasses import dataclass
from typing import Optional, Union


@dataclass
class CommonInfoDTO:
    spf: Union[float, str]
    indoor_temperature: Union[float, str]
    outdoor_temperature: Union[float, str]
    brine_in_temperature: Union[float, str]
    brine_out_temperature: Union[float, str]
    configured_indoor_temperature: Union[float, str]
    heating_in_temperature: Union[float, str]
    heating_out_temperature: Union[float, str]
    energy_usage: int
    energy_delivered: int
    import_energy: int
    export_energy: int
    ww_temperature: Union[float, str]
    ww_temperature_configured: float
    brine_pressure: Union[float, str]
    cv_pressure: Union[float, str]
    evaporation_temperature: Union[float, str]
    condensation_temperature: Union[float, str]
    inverter_temperature: Union[float, str]
    compressor_speed: int
    suction_gas_temperature: Union[float, str]
    suction_gas_pressure: Union[float, str]
    press_gas_temperature: Union[float, str]
    press_gas_pressure: Union[float, str]
    overheating: Union[float, str]
    position_expansion_ventil: int
    total_active_power: Union[float, str]
    number_of_starts: int
    operating_hours: int
    operation_mode: int
    heating_mode: int
    dg1: str
    sg2: Optional[str]
    sg3: str
    sg4: Optional[str]
    warmwater: int
    brine_circulation_pump: Union[float, str]
    production_circulation_pump: Union[float, str]
    act_vent_rpm: Union[float, str]
    alarm_active: bool
    active_requests_ww: str
    current_heating_pump_state: int
    current_heating_state: int
