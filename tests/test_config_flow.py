"""Tests for the config flow, in particular the developer tools section."""

from homeassistant import config_entries, data_entry_flow
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.eplucon.config_flow import build_schema, read_use_mock_data
from custom_components.eplucon.const import (
    CONF_API_ENDPOINT,
    CONF_API_TOKEN,
    CONF_DEVELOPER_OPTIONS,
    CONF_USE_MOCK_DATA,
    DOMAIN,
)
from custom_components.eplucon.eplucon_api.eplucon_client import BASE_URL


def test_developer_options_are_off_and_collapsed_by_default():
    schema = build_schema()({CONF_API_TOKEN: "token", CONF_DEVELOPER_OPTIONS: {}})

    assert schema[CONF_API_ENDPOINT] == BASE_URL
    assert schema[CONF_DEVELOPER_OPTIONS] == {CONF_USE_MOCK_DATA: False}


def test_developer_options_section_is_expanded_once_mock_data_is_on():
    """A switch that hides itself again is a switch left on by accident."""
    section = build_schema(use_mock_data=True).schema[CONF_DEVELOPER_OPTIONS]

    assert section.options["collapsed"] is False


def test_read_use_mock_data_tolerates_a_missing_section():
    assert read_use_mock_data({}) is False
    assert read_use_mock_data({CONF_DEVELOPER_OPTIONS: None}) is False
    assert read_use_mock_data({CONF_DEVELOPER_OPTIONS: {CONF_USE_MOCK_DATA: True}}) is True


async def test_flow_with_mock_data_needs_no_working_token(hass):
    """With mock data on, setup completes without the API being reachable."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_API_TOKEN: "not-a-real-token",
            CONF_API_ENDPOINT: BASE_URL,
            CONF_DEVELOPER_OPTIONS: {CONF_USE_MOCK_DATA: True},
        },
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_USE_MOCK_DATA] is True
    assert [device.name for device in result["data"]["devices"]] == [
        "Mock Heatpump",
        "Mock Tech controller",
    ]


async def test_options_flow_keeps_the_endpoint_and_the_mock_switch(hass):
    """Saving the options used to drop everything but the token and devices."""
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

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_API_TOKEN: "another-token",
            CONF_API_ENDPOINT: BASE_URL,
            CONF_DEVELOPER_OPTIONS: {CONF_USE_MOCK_DATA: True},
        },
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_API_TOKEN] == "another-token"
    assert entry.data[CONF_API_ENDPOINT] == BASE_URL
    assert entry.data[CONF_USE_MOCK_DATA] is True
    assert [device.name for device in entry.data["devices"]] == [
        "Mock Heatpump",
        "Mock Tech controller",
    ]


async def test_setup_migrates_an_entry_still_pointing_at_the_mock_host(hass):
    """The mock host never resolved; such an entry becomes a mock switch."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_API_TOKEN: "token",
            CONF_API_ENDPOINT: "https://mock.test",
            "devices": [],
        },
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.data[CONF_API_ENDPOINT] == BASE_URL
    assert entry.data[CONF_USE_MOCK_DATA] is True
