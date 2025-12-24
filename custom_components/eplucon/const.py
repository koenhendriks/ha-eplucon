from __future__ import annotations
from dataclasses import dataclass
from collections.abc import Callable


from homeassistant.components.binary_sensor import (
    BinarySensorEntityDescription,
    BinarySensorDeviceClass,
)

from homeassistant.components.sensor import (
    SensorEntityDescription,
    SensorDeviceClass,
    SensorStateClass,
)

from homeassistant.const import (
    UnitOfTemperature,
    UnitOfPressure,
    UnitOfEnergy,
    UnitOfTime,
    UnitOfPower,
    REVOLUTIONS_PER_MINUTE,
    PERCENTAGE,
)

from typing import Any


DOMAIN = "eplucon"
MANUFACTURER = "Eplucon"
PLATFORMS = ["sensor", "binary_sensor"]
EPLUCON_PORTAL_URL = "https://portaal.eplucon.nl/"
SUPPORTED_TYPES = ["heat_pump"]



# -------------------------
# Helper functions
# -------------------------

def get_friendly_operation_mode_text(device) -> str:
    try:
        operation_mode = int(device.realtime_info.common.operation_mode)
    except (TypeError, ValueError):
        return "Unavailable"

    return {
        1: "Koeling",
        2: "Verwarming",
        3: "Auto th-TOUCH",
        4: "Auto Wp",
        5: "Haard",
    }.get(operation_mode, "Unknown operation mode")

def get_friendly_heating_mode_text(device) -> str:
    try:
        heating_mode = int(device.realtime_info.common.heating_mode)
    except (TypeError, ValueError):
        return "Unavailable"

    return {
        0: "Off",
        1: "On",
        2: "Emergency operation",
        3: "APX",
    }.get(heating_mode, "Unknown operation mode")

def normalize_on_off(value):
    """Normalize values to 'ON' or 'OFF'."""
    if str(value).upper() in ["1", "ON", "TRUE"]:
        return "ON"
    return "OFF"

def normalize_bool(value) -> bool:
    return str(value).upper() in ["1", "ON", "TRUE"]

def normalize_number(value):
    """Normalize numeric values safely."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0




# ------------------------------------------------------------------------------------
# Sensor definitions
# ------------------------------------------------------------------------------------

@dataclass(kw_only=True)
class EpluconSensorEntityDescription(SensorEntityDescription):
    key: str
    name: str
    value_fn: Callable[[Any], Any]
    exists_fn: Callable[[Any], bool] = lambda _: True


@dataclass(kw_only=True)
class EpluconBinarySensorEntityDescription(BinarySensorEntityDescription):
    key: str
    name: str
    value_fn: Callable[[Any], bool] | None = None
    exists_fn: Callable[[Any], bool] = lambda _: True




RAW_SENSOR_DEFS = [
    # Numeric sensors
    {"key": "indoor_temperature", "name": "Indoor Temperature", "attr": "indoor_temperature", "unit": UnitOfTemperature.CELSIUS, "state_class": SensorStateClass.MEASUREMENT},
    {"key": "outdoor_temperature", "name": "Outdoor Temperature", "attr": "outdoor_temperature", "unit": UnitOfTemperature.CELSIUS, "state_class": SensorStateClass.MEASUREMENT},
    {"key": "brine_in_temperature", "name": "Brine In Temperature", "attr": "brine_in_temperature", "unit": UnitOfTemperature.CELSIUS, "state_class": SensorStateClass.MEASUREMENT},
    {"key": "brine_out_temperature", "name": "Brine Out Temperature", "attr": "brine_out_temperature", "unit": UnitOfTemperature.CELSIUS, "state_class": SensorStateClass.MEASUREMENT},
    {"key": "configured_indoor_temperature", "name": "Configured Indoor Temperature", "attr": "configured_indoor_temperature", "unit": UnitOfTemperature.CELSIUS, "state_class": SensorStateClass.MEASUREMENT},
    {"key": "heating_in_temperature", "name": "Heating In Temperature", "attr": "heating_in_temperature", "unit": UnitOfTemperature.CELSIUS, "state_class": SensorStateClass.MEASUREMENT},
    {"key": "heating_out_temperature", "name": "Heating Out Temperature", "attr": "heating_out_temperature", "unit": UnitOfTemperature.CELSIUS, "state_class": SensorStateClass.MEASUREMENT},
    {"key": "ww_temperature", "name": "WW Temperature", "attr": "ww_temperature", "unit": UnitOfTemperature.CELSIUS, "state_class": SensorStateClass.MEASUREMENT},
    {"key": "ww_temperature_configured", "name": "WW Temperature Configured", "attr": "ww_temperature_configured", "unit": UnitOfTemperature.CELSIUS, "state_class": SensorStateClass.MEASUREMENT},
    {"key": "brine_pressure", "name": "Brine Pressure", "attr": "brine_pressure", "unit": UnitOfPressure.BAR, "state_class": SensorStateClass.MEASUREMENT},
    {"key": "cv_pressure", "name": "CV Pressure", "attr": "cv_pressure", "unit": UnitOfPressure.BAR, "state_class": SensorStateClass.MEASUREMENT},
    {"key": "suction_gas_pressure", "name": "Suction Gas Pressure", "attr": "suction_gas_pressure", "unit": UnitOfPressure.BAR, "state_class": SensorStateClass.MEASUREMENT},
    {"key": "press_gas_pressure", "name": "Press Gas Pressure", "attr": "press_gas_pressure", "unit": UnitOfPressure.BAR, "state_class": SensorStateClass.MEASUREMENT},
    {"key": "suction_gas_temperature", "name": "Suction Gas Temperature", "attr": "suction_gas_temperature", "unit": UnitOfTemperature.CELSIUS, "state_class": SensorStateClass.MEASUREMENT},
    {"key": "press_gas_temperature", "name": "Press Gas Temperature", "attr": "press_gas_temperature", "unit": UnitOfTemperature.CELSIUS, "state_class": SensorStateClass.MEASUREMENT},
    {"key": "condensation_temperature", "name": "Condensation Temperature", "attr": "condensation_temperature", "unit": UnitOfTemperature.CELSIUS, "state_class": SensorStateClass.MEASUREMENT},
    {"key": "evaporation_temperature", "name": "Evaporation Temperature", "attr": "evaporation_temperature", "unit": UnitOfTemperature.CELSIUS, "state_class": SensorStateClass.MEASUREMENT},
    {"key": "inverter_temperature", "name": "Inverter Temperature", "attr": "inverter_temperature", "unit": UnitOfTemperature.CELSIUS, "state_class": SensorStateClass.MEASUREMENT},
    {"key": "compressor_speed", "name": "Compressor Speed", "attr": "compressor_speed", "unit": REVOLUTIONS_PER_MINUTE, "state_class": SensorStateClass.MEASUREMENT},
    {"key": "brine_circulation_pump", "name": "Brine Circulation Pump", "attr": "brine_circulation_pump", "unit": PERCENTAGE, "state_class": SensorStateClass.MEASUREMENT},
    {"key": "production_circulation_pump", "name": "Production Circulation Pump", "attr": "production_circulation_pump", "unit": PERCENTAGE, "state_class": SensorStateClass.MEASUREMENT},
    {"key": "act_vent_rpm", "name": "Act Vent RPM", "attr": "act_vent_rpm", "unit": REVOLUTIONS_PER_MINUTE, "state_class": SensorStateClass.MEASUREMENT},
    {"key": "total_active_power", "name": "Total Active Power", "attr": "total_active_power", "unit": UnitOfPower.KILO_WATT, "state_class": SensorStateClass.MEASUREMENT},
    {"key": "energy_usage", "name": "Energy Usage", "attr": "energy_usage", "unit": UnitOfEnergy.KILO_WATT_HOUR, "state_class": SensorStateClass.TOTAL_INCREASING},
    {"key": "energy_delivered", "name": "Energy Delivered", "attr": "energy_delivered", "unit": UnitOfEnergy.KILO_WATT_HOUR, "state_class": SensorStateClass.TOTAL_INCREASING},
    {"key": "import_energy", "name": "Import Energy", "attr": "import_energy", "unit": UnitOfEnergy.KILO_WATT_HOUR, "state_class": SensorStateClass.TOTAL_INCREASING},
    {"key": "export_energy", "name": "Export Energy", "attr": "export_energy", "unit": UnitOfEnergy.KILO_WATT_HOUR, "state_class": SensorStateClass.TOTAL_INCREASING},
    {"key": "spf", "name": "Seasonal Performance Factor (SPF)", "attr": "spf", "state_class": SensorStateClass.MEASUREMENT},
    {"key": "overheating", "name": "Overheating", "attr": "overheating", "unit": UnitOfTemperature.CELSIUS, "state_class": SensorStateClass.MEASUREMENT},
    {"key": "position_expansion_ventil", "name": "Position Expansion Ventil", "attr": "position_expansion_ventil", "unit": PERCENTAGE, "state_class": SensorStateClass.MEASUREMENT},
    {"key": "number_of_starts", "name": "Number of Starts", "attr": "number_of_starts", "state_class": SensorStateClass.TOTAL_INCREASING},
    {"key": "operating_hours", "name": "Operating Hours", "attr": "operating_hours", "unit": UnitOfTime.HOURS, "state_class": SensorStateClass.MEASUREMENT},
]

# ON/OFF sensors
ONOFF_SENSOR_DEFS = [
    {"key": "dg1", "name": "Direct Outlet (DG1)", "attr": "dg1", "device_class": BinarySensorDeviceClass.RUNNING},
    {"key": "sg2", "name": "Mixture Outlet (SG2)", "attr": "sg2", "device_class": BinarySensorDeviceClass.RUNNING},
    {"key": "sg3", "name": "Mixture Outlet (SG3)", "attr": "sg3", "device_class": BinarySensorDeviceClass.RUNNING},
    {"key": "sg4", "name": "Mixture Outlet (SG4)", "attr": "sg4", "device_class": BinarySensorDeviceClass.RUNNING},
    {"key": "warmwater", "name": "Warm Water", "attr": "warmwater", "device_class": None},
    {"key": "alarm_active", "name": "Alarm Active", "attr": "alarm_active", "device_class": BinarySensorDeviceClass.PROBLEM},
    {"key": "current_heating_pump_state", "name": "Current Heating Pump State", "attr": "current_heating_pump_state", "device_class": None},
    {"key": "current_heating_state", "name": "Current Heating State", "attr": "current_heating_state", "device_class": BinarySensorDeviceClass.HEAT},
    {"key": "active_requests_ww", "name": "Active WW request", "attr": "active_requests_ww", "device_class": None},
]

# Heatloading status sensors
HEATLOADING_SENSOR_DEFS = [
    {"key": "heatloading_active", "name": "Heatloading Active", "attr": "heatloading_active", "device_class": None, "value_fn": lambda d: d.heatloading_status.heatloading_active, "exists_fn": lambda d: d.heatloading_status is not None,},
    {"key": "domestic_hot_water", "name": "Domestic Hot Water", "attr": "domestic_hot_water", "device_class": None, "value_fn": lambda d: d.heatloading_status.configurations.get("domestic_hot_water"), "exists_fn": lambda d: (d.heatloading_status is not None and d.heatloading_status.configurations is not None and "domestic_hot_water" in d.heatloading_status.configurations),},
    {"key": "heatloading_for_heating", "name": "Heatloading for Heating", "attr": "heatloading_for_heating", "device_class": None, "value_fn": lambda d: d.heatloading_status.configurations.get("heatloading_for_heating"), "exists_fn": lambda d: (d.heatloading_status is not None and d.heatloading_status.configurations is not None and "heatloading_for_heating" in d.heatloading_status.configurations),},
]

# Friendly text sensors
FRIENDLY_TEXT_SENSOR_DEFS = [
    {"key": "operation_mode_text", "name": "Operation Mode Text", "value_fn": get_friendly_operation_mode_text},
    {"key": "heating_mode_text", "name": "Heating Mode Text", "value_fn": get_friendly_heating_mode_text},
]

# ----------------------
# Combine all sensors
# ----------------------

sensor_list = []
binary_sensor_list = []

# Numeric sensors
for s in RAW_SENSOR_DEFS:
    attr = s["attr"]
    sensor_list.append(
        EpluconSensorEntityDescription(
            key=s["key"],
            name=s["name"],
            device_class=s.get("device_class"),
            native_unit_of_measurement=s.get("unit"),
            state_class=s.get("state_class"),
            value_fn=lambda device, attr=attr: normalize_number(
                getattr(getattr(device.realtime_info, "common", {}), attr, None)
            ),
            exists_fn=lambda device, attr=attr: getattr(getattr(device.realtime_info, "common", {}), attr, None) is not None,
        )
    )

# ON/OFF sensors
for s in ONOFF_SENSOR_DEFS:
    attr = s["attr"]
    binary_sensor_list.append(
        EpluconBinarySensorEntityDescription(
            key=s["key"],
            name=s["name"],
            device_class=s.get("device_class"),
            value_fn=lambda device, attr=attr: normalize_bool(
                getattr(getattr(device.realtime_info, "common", {}), attr, "OFF")
            ),
            exists_fn=lambda device, attr=attr: getattr(getattr(device.realtime_info, "common", {}), attr, None) is not None,
        )
    )

# Heatloading sensors
for s in HEATLOADING_SENSOR_DEFS:
    attr = s["attr"]
    binary_sensor_list.append(
        EpluconBinarySensorEntityDescription(
            key=s["key"],
            name=s["name"],
            device_class=s.get("device_class"),
            value_fn=s.get("value_fn"),
            exists_fn=s.get("exists_fn"),
        )
    )

# Friendly text sensors
for s in FRIENDLY_TEXT_SENSOR_DEFS:
    value_fn = s["value_fn"]
    sensor_list.append(
        EpluconSensorEntityDescription(
            key=s["key"],
            name=s["name"],
            device_class=SensorDeviceClass.ENUM,
            value_fn=value_fn,
            exists_fn=lambda device: getattr(device.realtime_info, "common", None) is not None,
        )
    )

SENSORS = tuple(sensor_list)
BINARY_SENSORS = tuple(binary_sensor_list)
