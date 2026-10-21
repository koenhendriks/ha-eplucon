"""Tests for riding out portal outages on the last known values (issue #41)."""

import functools
import json
import shutil
import types
from datetime import timedelta

import pytest
from homeassistant.const import CONF_SCAN_INTERVAL
from pytest_homeassistant_custom_component.common import MockConfigEntry

import custom_components.eplucon as eplucon
from custom_components.eplucon.const import (
    CONF_API_ENDPOINT,
    CONF_API_TOKEN,
    CONF_DEVELOPER_OPTIONS,
    CONF_USE_MOCK_DATA,
    DOMAIN,
)
from custom_components.eplucon.eplucon_api import eplucon_client
from custom_components.eplucon.eplucon_api.eplucon_client import BASE_URL

INVALID_ACCOUNT = {"auth": True, "message": "Invalid account", "error_code": 400}


class Clock:
    def __init__(self):
        self.now = 1000.0

    def monotonic(self):
        return self.now


@pytest.fixture
def fixture_dir(tmp_path, monkeypatch):
    """Serve a copy of the shipped mocks, so a test can break one."""
    shutil.copytree(eplucon_client.MOCK_DIR, tmp_path, dirs_exist_ok=True)
    monkeypatch.setattr(eplucon_client, "MOCK_DIR", tmp_path)
    return tmp_path


@pytest.fixture
def clock(monkeypatch):
    """Drive the outage timer without touching the event loop's clock."""
    clock = Clock()
    monkeypatch.setattr(eplucon, "time", types.SimpleNamespace(monotonic=clock.monotonic))
    return clock


@pytest.fixture(autouse=True)
def no_retries(monkeypatch):
    monkeypatch.setattr(
        eplucon,
        "fetch_with_retry",
        functools.partial(eplucon.fetch_with_retry, retries=1),
    )


async def set_up(hass, **data):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_API_TOKEN: "token",
            CONF_API_ENDPOINT: BASE_URL,
            CONF_USE_MOCK_DATA: True,
            "devices": [],
            **data,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry, hass.data[DOMAIN][entry.entry_id]


def break_realtime_info(fixture_dir, body=INVALID_ACCOUNT):
    (fixture_dir / "get_realtime_info.json").write_text(json.dumps(body))


async def test_a_short_outage_keeps_the_last_values(hass, fixture_dir, clock):
    _, coordinator = await set_up(hass)
    last_good = coordinator.data

    break_realtime_info(fixture_dir)
    await coordinator.async_refresh()
    clock.now += eplucon.STALE_DATA_GRACE.total_seconds() - 1
    await coordinator.async_refresh()

    assert coordinator.last_update_success is True
    assert coordinator.data is last_good


async def test_entities_go_unavailable_once_the_grace_period_is_over(
    hass, fixture_dir, clock
):
    _, coordinator = await set_up(hass)

    break_realtime_info(fixture_dir)
    await coordinator.async_refresh()
    clock.now += eplucon.STALE_DATA_GRACE.total_seconds()
    await coordinator.async_refresh()

    assert coordinator.last_update_success is False
    assert "Invalid account" in str(coordinator.last_exception)


async def test_recovery_starts_a_fresh_grace_period(hass, fixture_dir, clock):
    _, coordinator = await set_up(hass)
    good_fixture = (fixture_dir / "get_realtime_info.json").read_text()

    break_realtime_info(fixture_dir)
    await coordinator.async_refresh()
    clock.now += eplucon.STALE_DATA_GRACE.total_seconds() - 1

    (fixture_dir / "get_realtime_info.json").write_text(good_fixture)
    await coordinator.async_refresh()

    break_realtime_info(fixture_dir)
    clock.now += 60
    await coordinator.async_refresh()

    assert coordinator.last_update_success is True


async def test_an_auth_failure_is_not_ridden_out(hass, fixture_dir, clock):
    _, coordinator = await set_up(hass)

    break_realtime_info(fixture_dir, {"auth": False})
    await coordinator.async_refresh()

    assert coordinator.last_update_success is False


async def test_setup_without_previous_values_still_fails(hass, fixture_dir, clock):
    break_realtime_info(fixture_dir)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_API_TOKEN: "token",
            CONF_API_ENDPOINT: BASE_URL,
            CONF_USE_MOCK_DATA: True,
            "devices": [],
        },
    )
    entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(entry.entry_id)


async def test_update_interval_comes_from_the_entry(hass, fixture_dir):
    _, coordinator = await set_up(hass, **{CONF_SCAN_INTERVAL: 120})

    assert coordinator.update_interval == timedelta(seconds=120)


async def test_changing_the_interval_in_the_options_applies_it(hass, fixture_dir):
    entry, _ = await set_up(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_API_TOKEN: "token",
            CONF_API_ENDPOINT: BASE_URL,
            CONF_SCAN_INTERVAL: 300,
            CONF_DEVELOPER_OPTIONS: {CONF_USE_MOCK_DATA: True},
        },
    )
    await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN][entry.entry_id]
    assert entry.data[CONF_SCAN_INTERVAL] == 300
    assert coordinator.update_interval == timedelta(seconds=300)
