"""Tests for the naming and availability of zone-backed entities."""

import pytest

from custom_components.eplucon.binary_sensor import EpluconZoneBinarySensorEntity
from custom_components.eplucon.const import (
    DOMAIN,
    ZONE_BINARY_SENSORS,
    ZONE_SENSORS,
)
from custom_components.eplucon.eplucon_api.DTO.DeviceDTO import DeviceDTO
from custom_components.eplucon.eplucon_api.DTO.ZoneDTO import ZoneDTO
from custom_components.eplucon.sensor import EpluconZoneSensorEntity

TEMPERATURE = next(d for d in ZONE_SENSORS if d.key == "zone_temperature")
CALL_FOR_HEAT = next(d for d in ZONE_BINARY_SENSORS if d.key == "zone_relay")


class FakeCoordinator:
    """Enough of a DataUpdateCoordinator for CoordinatorEntity to work with."""

    def __init__(self, data, last_update_success=True):
        self.data = data
        self.last_update_success = last_update_success


def make_zone(zone_id=3073, name="Woonkamer", **overrides):
    return ZoneDTO(
        id=zone_id,
        name=name,
        current_temperature=overrides.pop("current_temperature", 21.5),
        relay_state=overrides.pop("relay_state", "on"),
        **overrides,
    )


def make_device(zones):
    return DeviceDTO(
        id=1, account_module_index="abc123", name="Controller",
        type="zones_system_controller", zones=zones,
    )


def make_sensor(zones, description=TEMPERATURE, zone=None, last_update_success=True):
    device = make_device(zones)
    return EpluconZoneSensorEntity(
        FakeCoordinator([device], last_update_success),
        device,
        zone or zones[0],
        description,
    )


# ----------------------------
# Naming (review item 1)
# ----------------------------

def test_zone_entity_defers_naming_to_the_device():
    """HA prefixes the zone device name onto the entity id only when this is set.

    Without it every zone contributes an entity literally named "Temperature",
    and the registry disambiguates them as _2, _3, ... in API response order.
    """
    entity = make_sensor([make_zone()])

    assert entity.has_entity_name is True
    assert entity.name == "Temperature"
    assert entity.device_info["name"] == "Woonkamer"


def test_zone_entities_are_unique_per_zone():
    zones = [make_zone(3073, "Woonkamer"), make_zone(3074, "Keuken")]

    unique_ids = {
        make_sensor(zones, description, zone).unique_id
        for zone in zones
        for description in (TEMPERATURE, CALL_FOR_HEAT)
    }
    assert len(unique_ids) == 4

    identifiers = [
        make_sensor(zones, TEMPERATURE, zone).device_info["identifiers"]
        for zone in zones
    ]
    assert identifiers == [
        {(DOMAIN, "abc123_zone_3073")},
        {(DOMAIN, "abc123_zone_3074")},
    ]


def test_zone_device_links_back_to_the_controller():
    info = make_sensor([make_zone()]).device_info

    assert info["via_device"] == (DOMAIN, "abc123")


# ----------------------------
# Availability (review item 3)
# ----------------------------

def test_zone_entity_available_when_zone_is_present():
    entity = make_sensor([make_zone()])

    assert entity.available is True
    assert entity.native_value == 21.5


def test_zone_entity_unavailable_when_zone_vanishes():
    """A dropped zone must not read as a valid value."""
    zone = make_zone()
    entity = make_sensor([zone])
    entity.coordinator.data = [make_device([])]

    assert entity.zone is None
    assert entity.available is False


def test_binary_sensor_does_not_report_off_for_a_vanished_zone():
    """The misleading case: 'Call for Heat' off vs. the zone being gone."""
    zone = make_zone(relay_state="on")
    device = make_device([zone])
    entity = EpluconZoneBinarySensorEntity(
        FakeCoordinator([device]), device, zone, CALL_FOR_HEAT
    )

    assert entity.available is True
    assert entity.is_on is True

    entity.coordinator.data = [make_device([])]
    assert entity.available is False


@pytest.mark.parametrize("zones", [[], None])
def test_zone_entity_unavailable_when_controller_has_no_zones(zones):
    entity = make_sensor([make_zone()])
    entity.coordinator.data = [make_device(zones)]

    assert entity.available is False


def test_zone_entity_unavailable_when_the_coordinator_failed():
    """Availability composes with the coordinator's own state."""
    entity = make_sensor([make_zone()], last_update_success=False)

    assert entity.zone is not None
    assert entity.available is False


def test_zone_entity_ignores_other_modules():
    entity = make_sensor([make_zone()])
    other = DeviceDTO(
        id=2, account_module_index="zzz", name="Other",
        type="zones_system_controller", zones=[make_zone()],
    )
    entity.coordinator.data = [other]

    assert entity.available is False
