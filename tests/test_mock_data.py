"""Tests for the mock data mode of the API client."""

import json

import pytest

from custom_components.eplucon.eplucon_api import eplucon_client
from custom_components.eplucon.eplucon_api.eplucon_client import (
    BASE_URL,
    ApiError,
    EpluconApi,
)


def mock_client():
    """A mocked client; deliberately given no session and a real endpoint."""
    return EpluconApi("token", BASE_URL, use_mock_data=True)


def test_mock_data_needs_no_session():
    assert mock_client()._mock is True


def test_client_is_not_mocked_by_default():
    assert EpluconApi("token", BASE_URL, session=object())._mock is False


def test_an_unmocked_client_still_requires_a_session():
    with pytest.raises(RuntimeError):
        EpluconApi("token", BASE_URL)


# ----------------------------
# The shipped fixtures
# ----------------------------

async def test_mock_devices_are_supported_module_types():
    from custom_components.eplucon.const import SUPPORTED_TYPES

    devices = await mock_client().get_devices()

    assert devices
    assert {device.type for device in devices} <= set(SUPPORTED_TYPES)


async def test_mock_realtime_info_parses():
    api = mock_client()
    device = next(d for d in await api.get_devices() if d.type == "heat_pump")

    info = await api.get_realtime_info(device.id)

    assert info.common.indoor_temperature is not None


async def test_mock_heatloading_status_parses():
    api = mock_client()
    device = next(d for d in await api.get_devices() if d.type == "heat_pump")

    status = await api.get_heatpump_heatloading_status(device.id)

    assert isinstance(status.configurations, dict)


async def test_mock_zones_parse_including_raw_data():
    api = mock_client()
    device = next(
        d for d in await api.get_devices() if d.type == "zones_system_controller"
    )

    zones = await api.get_zones(device.id)

    assert zones
    # raw_data enrichment is where the fixtures are easiest to get wrong.
    assert all(zone.zone_state is not None for zone in zones)


# ----------------------------
# Fixture resolution
# ----------------------------

@pytest.fixture
def fixture_dir(tmp_path, monkeypatch):
    """Serve mocks from a temporary directory instead of the shipped one."""
    monkeypatch.setattr(eplucon_client, "MOCK_DIR", tmp_path)
    return tmp_path


def write_zones(path, name, **extra):
    path.write_text(
        json.dumps(
            {
                "auth": True,
                "error_code": 200,
                "data": [{"id": 1, "name": name}],
                **extra,
            }
        )
    )


async def test_per_module_fixture_wins_over_the_shared_one(fixture_dir):
    write_zones(fixture_dir / "get_zones.json", "Shared")
    write_zones(fixture_dir / "get_zones.42.json", "Per module")

    api = mock_client()

    assert [z.name for z in await api.get_zones(42)] == ["Per module"]
    assert [z.name for z in await api.get_zones(7)] == ["Shared"]


async def test_fixture_http_status_drives_the_406_path(fixture_dir):
    write_zones(fixture_dir / "get_zones.json", "Zone", http_status=406)

    assert await mock_client().get_zones(1) == []


async def test_missing_fixture_reports_the_paths_it_looked_for(fixture_dir):
    with pytest.raises(ApiError) as err:
        await mock_client().get_devices()

    assert "get_devices.json" in str(err.value)


async def test_unparseable_fixture_raises_api_error(fixture_dir):
    (fixture_dir / "get_devices.json").write_text("{not json")

    with pytest.raises(ApiError):
        await mock_client().get_devices()
