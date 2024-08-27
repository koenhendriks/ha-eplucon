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
    inverter_temperature: int
    compressor_speed: int
    suction_gas_temperature: Union[float, str]
    suction_gas_pressure: Union[float, str]
    press_gas_temperature: Union[float, str]
    press_gas_pressure: Union[float, str]
    overheating: Union[float, str]
    position_expansion_ventil: int
    total_active_power: int
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

    @staticmethod
    def from_dict(data: dict) -> 'CommonInfoDTO':
        return CommonInfoDTO(
            spf=data.get("spf"),
            indoor_temperature=data.get("indoor_temperature"),
            outdoor_temperature=data.get("outdoor_temperature"),
            brine_in_temperature=data.get("brine_in_temperature"),
            brine_out_temperature=data.get("brine_out_temperature"),
            configured_indoor_temperature=data.get("configured_indoor_temperature"),
            heating_in_temperature=data.get("heating_in_temperature"),
            heating_out_temperature=data.get("heating_out_temperature"),
            energy_usage=data.get("energy_usage"),
            energy_delivered=data.get("energy_delivered"),
            import_energy=data.get("import_energy"),
            export_energy=data.get("export_energy"),
            ww_temperature=data.get("ww_temperature"),
            ww_temperature_configured=data.get("ww_temperature_configured"),
            brine_pressure=data.get("brine_pressure"),
            cv_pressure=data.get("cv_pressure"),
            evaporation_temperature=data.get("evaporation_temperature"),
            condensation_temperature=data.get("condensation_temperature"),
            inverter_temperature=data.get("inverter_temperature"),
            compressor_speed=data.get("compressor_speed"),
            suction_gas_temperature=data.get("suction_gas_temperature"),
            suction_gas_pressure=data.get("suction_gas_pressure"),
            press_gas_temperature=data.get("press_gas_temperature"),
            press_gas_pressure=data.get("press_gas_pressure"),
            overheating=data.get("overheating"),
            position_expansion_ventil=data.get("position_expansion_ventil"),
            total_active_power=data.get("total_active_power"),
            number_of_starts=data.get("number_of_starts"),
            operating_hours=data.get("operating_hours"),
            operation_mode=data.get("operation_mode"),
            heating_mode=data.get("heating_mode"),
            dg1=data.get("dg1"),
            sg2=data.get("sg2"),
            sg3=data.get("sg3"),
            sg4=data.get("sg4"),
            warmwater=data.get("warmwater"),
            brine_circulation_pump=data.get("brine_circulation_pump"),
            production_circulation_pump=data.get("production_circulation_pump"),
            act_vent_rpm=data.get("act_vent_rpm"),
            alarm_active=data.get("alarm_active"),
            active_requests_ww=data.get("active_requests_ww"),
            current_heating_pump_state=data.get("current_heating_pump_state"),
            current_heating_state=data.get("current_heating_state")
        )
