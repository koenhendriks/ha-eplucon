"""The config entry stores only each module's identity, never API data."""

import json
import shutil

import pytest
from homeassistant.config_entries import ConfigEntryState
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.eplucon.const import (
    CONF_API_ENDPOINT,
    CONF_API_TOKEN,
    CONF_DEVELOPER_OPTIONS,
    CONF_USE_MOCK_DATA,
    DOMAIN,
)
from custom_components.eplucon.eplucon_api import eplucon_client
from custom_components.eplucon.eplucon_api.eplucon_client import BASE_URL

from .test_config_flow import MOCK_MODULES

HEAT_PUMP = MOCK_MODULES[0]


@pytest.fixture
def fixture_dir(tmp_path, monkeypatch):
    """Serve a copy of the shipped mocks, so a test can change one."""
    shutil.copytree(eplucon_client.MOCK_DIR, tmp_path, dirs_exist_ok=True)
    monkeypatch.setattr(eplucon_client, "MOCK_DIR", tmp_path)
    return tmp_path


def realtime_snapshot(**common):
    realtime = json.loads((eplucon_client.MOCK_DIR / "get_realtime_info.json").read_text())
    realtime["data"]["common"].update(common)
    return realtime


async def set_up(hass, devices):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_API_TOKEN: "token",
            CONF_API_ENDPOINT: BASE_URL,
            CONF_USE_MOCK_DATA: True,
            "devices": devices,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry, hass.data[DOMAIN][entry.entry_id]


def heat_pump(coordinator):
    return next(d for d in coordinator.data if d.id == HEAT_PUMP["id"])


async def test_setup_survives_null_operation_mode_in_stored_device(hass):
    """Older versions stored a realtime snapshot, which may hold a null."""
    snapshot = realtime_snapshot(operation_mode=None)["data"]

    await set_up(hass, [{**HEAT_PUMP, "realtime_info": snapshot}])


async def test_setup_drops_the_stored_snapshot_from_the_entry(hass):
    snapshot = realtime_snapshot()["data"]

    entry, _ = await set_up(hass, [{**HEAT_PUMP, "realtime_info": snapshot}])

    assert entry.data["devices"] == MOCK_MODULES


async def test_a_stored_snapshot_is_never_shown_as_current(hass, fixture_dir):
    """With no valid refresh yet, the values are unknown, not days old."""
    (fixture_dir / "get_realtime_info.json").write_text(
        json.dumps(
            realtime_snapshot(
                indoor_temperature=0, outdoor_temperature=0, operating_hours=0
            )
        )
    )
    snapshot = realtime_snapshot(indoor_temperature=21.5)["data"]

    _, coordinator = await set_up(hass, [{**HEAT_PUMP, "realtime_info": snapshot}])

    assert heat_pump(coordinator).realtime_info is None


async def test_refreshes_after_saving_the_options_stay_out_of_the_entry(hass):
    """The refresh filled in the objects the options flow had stored."""
    entry, _ = await set_up(hass, MOCK_MODULES)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_API_TOKEN: "token",
            CONF_API_ENDPOINT: BASE_URL,
            CONF_DEVELOPER_OPTIONS: {CONF_USE_MOCK_DATA: True},
        },
    )
    await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.async_refresh()

    assert entry.state is ConfigEntryState.LOADED
    assert heat_pump(coordinator).realtime_info is not None
    assert entry.data["devices"] == MOCK_MODULES
