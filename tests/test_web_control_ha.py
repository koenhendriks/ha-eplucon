"""Web control inside Home Assistant: config flow, entities, failures."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries, data_entry_flow
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.eplucon.config_flow import async_validate_web_control
from custom_components.eplucon.const import (
    CONF_API_ENDPOINT,
    CONF_API_TOKEN,
    CONF_DEVELOPER_OPTIONS,
    CONF_USE_MOCK_DATA,
    CONF_WEB_CONTROL,
    CONF_WEB_PASSWORD,
    CONF_WEB_TWO_FACTOR,
    CONF_WEB_USERNAME,
    DOMAIN,
)
from custom_components.eplucon.control_entity import WEB_COORDINATORS
from custom_components.eplucon.eplucon_api.eplucon_client import BASE_URL
from custom_components.eplucon.eplucon_api.web_control import (
    WebControlAuthError,
    WebControlError,
    WebControlTwoFactorInvalid,
    WebControlTwoFactorRequired,
)
from custom_components.eplucon.web_coordinator import ISSUE_WEB_TWO_FACTOR

HEAT_PUMP_ID = 1001337
TOTP_KEY = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
WEB = {CONF_WEB_USERNAME: "user@example.com", CONF_WEB_PASSWORD: "secret"}

MOCK_DEVICES = [
    {"id": 1001337, "account_module_index": "1aa111a1a1a111a1aa1111111aa11a11", "name": "Mock Heatpump", "type": "heat_pump"},
]


async def set_up(hass, **data):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_API_TOKEN: "token",
            CONF_API_ENDPOINT: BASE_URL,
            CONF_USE_MOCK_DATA: True,
            "devices": MOCK_DEVICES,
            **data,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def entity_id(hass, platform: str, key: str) -> str | None:
    return er.async_get(hass).async_get_entity_id(
        platform, DOMAIN, f"{HEAT_PUMP_ID}_control_{key}"
    )


# --- entities ------------------------------------------------------------------


async def test_no_control_entities_without_web_login(hass):
    entry = await set_up(hass)

    assert entity_id(hass, "number", "indoor_temperature") is None
    assert entity_id(hass, "climate", "climate") is None
    assert entry.entry_id not in hass.data[DOMAIN].get(WEB_COORDINATORS, {})
    # The read-only sensors are there as before.
    assert er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{HEAT_PUMP_ID}_indoor_temperature"
    )


async def test_control_entities_show_the_portal_settings(hass):
    await set_up(hass, **WEB)

    number = hass.states.get(entity_id(hass, "number", "indoor_temperature"))
    assert float(number.state) == 22.4
    assert number.attributes["min"] == 10 and number.attributes["max"] == 30
    assert hass.states.get(entity_id(hass, "number", "boiler_temperature")).state == "60.0"
    assert hass.states.get(entity_id(hass, "switch", "warm_water_active")).state == "on"
    select = hass.states.get(entity_id(hass, "select", "heatpump_operation_mode"))
    assert select.state == "heating"
    assert "fireplace" in select.attributes["options"]
    assert hass.states.get(entity_id(hass, "select", "heating_curve_correction")).state == "zero"

    climate = hass.states.get(entity_id(hass, "climate", "climate"))
    assert climate.state == "heat"
    assert climate.attributes["temperature"] == 22.4
    assert climate.attributes["current_temperature"] is not None


async def test_setting_a_number_shows_right_away(hass):
    await set_up(hass, **WEB)
    target = entity_id(hass, "number", "indoor_temperature")

    await hass.services.async_call(
        "number", "set_value", {"entity_id": target, "value": 19.5}, blocking=True
    )

    assert float(hass.states.get(target).state) == 19.5


async def test_a_value_outside_the_dialog_is_refused(hass):
    from homeassistant.exceptions import ServiceValidationError

    await set_up(hass, **WEB)
    target = entity_id(hass, "select", "heatpump_operation_mode")
    coordinator = next(iter(hass.data[DOMAIN][WEB_COORDINATORS].values()))

    with pytest.raises(ServiceValidationError):
        await coordinator.async_set_value(MOCK_DEVICES[0]["account_module_index"], "heatpump_operation_mode", 9)
    assert hass.states.get(target).state == "heating"


async def test_switch_and_select_write_the_portal_values(hass):
    await set_up(hass, **WEB)
    switch = entity_id(hass, "switch", "warm_water_active")
    select = entity_id(hass, "select", "heatpump_active")

    await hass.services.async_call("switch", "turn_off", {"entity_id": switch}, blocking=True)
    await hass.services.async_call(
        "select", "select_option", {"entity_id": select, "option": "apx"}, blocking=True
    )

    assert hass.states.get(switch).state == "off"
    assert hass.states.get(select).state == "apx"


async def test_climate_modes_map_onto_the_heat_pump(hass):
    await set_up(hass, **WEB)
    climate = entity_id(hass, "climate", "climate")
    active = entity_id(hass, "select", "heatpump_active")
    mode = entity_id(hass, "select", "heatpump_operation_mode")

    await hass.services.async_call(
        "climate", "set_hvac_mode", {"entity_id": climate, "hvac_mode": "cool"}, blocking=True
    )
    assert hass.states.get(mode).state == "cooling"
    assert hass.states.get(climate).state == "cool"

    await hass.services.async_call(
        "climate", "set_hvac_mode", {"entity_id": climate, "hvac_mode": "off"}, blocking=True
    )
    assert hass.states.get(active).state == "off"
    assert hass.states.get(climate).state == "off"

    await hass.services.async_call(
        "climate", "set_hvac_mode", {"entity_id": climate, "hvac_mode": "heat_cool"}, blocking=True
    )
    assert hass.states.get(active).state == "on"
    assert hass.states.get(mode).state == "auto_th_touch"

    await hass.services.async_call(
        "climate", "set_temperature", {"entity_id": climate, "temperature": 20.3}, blocking=True
    )
    assert hass.states.get(climate).attributes["temperature"] == 20.3


async def test_web_outage_leaves_the_api_sensors_alone(hass):
    with patch(
        "custom_components.eplucon.eplucon_api.web_control.EpluconWebControl.async_get_states",
        AsyncMock(side_effect=WebControlError("portal down")),
    ):
        entry = await set_up(hass, **WEB)

    assert entry.state is config_entries.ConfigEntryState.LOADED
    assert hass.states.get(entity_id(hass, "number", "indoor_temperature")).state == "unavailable"
    sensor = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{HEAT_PUMP_ID}_indoor_temperature"
    )
    assert hass.states.get(sensor).state not in ("unavailable", "unknown")


async def test_one_unreadable_heat_pump_leaves_the_others_controllable(hass):
    from custom_components.eplucon.eplucon_api.web_control import (
        EpluconWebControl,
        WebControlModuleUnknown,
    )

    other = {"id": 1009999, "account_module_index": "9" * 32, "name": "Other", "type": "heat_pump"}
    original = EpluconWebControl.async_get_states

    async def get_states(self, module_index):
        if module_index == other["account_module_index"]:
            raise WebControlModuleUnknown("not on this login")
        return await original(self, module_index)

    with patch.object(EpluconWebControl, "async_get_states", get_states):
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_API_TOKEN: "token",
                CONF_API_ENDPOINT: BASE_URL,
                CONF_USE_MOCK_DATA: True,
                "devices": MOCK_DEVICES + [other],
                **WEB,
            },
        )
        entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    registry = er.async_get(hass)
    assert float(hass.states.get(entity_id(hass, "number", "indoor_temperature")).state) == 22.4
    other_number = registry.async_get_entity_id("number", DOMAIN, "1009999_control_indoor_temperature")
    assert hass.states.get(other_number).state == "unavailable"


async def test_lost_2fa_session_raises_a_repair_issue(hass):
    with patch(
        "custom_components.eplucon.eplucon_api.web_control.EpluconWebControl.async_get_states",
        AsyncMock(side_effect=WebControlTwoFactorRequired("code needed")),
    ):
        await set_up(hass, **WEB)

    assert ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_WEB_TWO_FACTOR)


# --- config flow -----------------------------------------------------------------


async def start_flow(hass, web):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    return await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_API_TOKEN: "token",
            CONF_API_ENDPOINT: BASE_URL,
            CONF_DEVELOPER_OPTIONS: {CONF_USE_MOCK_DATA: True},
            CONF_WEB_CONTROL: web,
        },
    )


@pytest.mark.parametrize(
    "web",
    [{CONF_WEB_USERNAME: "user@example.com"}, {CONF_WEB_PASSWORD: "secret"}],
)
async def test_flow_needs_both_or_neither(hass, web):
    result = await start_flow(hass, web)

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {"base": "web_credentials_incomplete"}


async def test_flow_without_web_control(hass):
    result = await start_flow(hass, {})

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_WEB_USERNAME] is None


async def test_flow_stores_a_key_but_not_a_code(hass):
    result = await start_flow(hass, {**WEB, CONF_WEB_TWO_FACTOR: TOTP_KEY})
    assert result["data"][CONF_WEB_USERNAME] == "user@example.com"
    assert result["data"][CONF_WEB_TWO_FACTOR] == TOTP_KEY


@pytest.mark.parametrize(
    ("error", "key"),
    [
        (WebControlAuthError("no"), "web_auth"),
        (WebControlTwoFactorRequired("code"), "web_two_factor_required"),
        (WebControlTwoFactorInvalid("bad"), "web_two_factor_invalid"),
        (WebControlError("down"), "web_connect"),
    ],
)
async def test_login_errors_map_to_form_errors(hass, error, key):
    with patch(
        "custom_components.eplucon.config_flow.EpluconWebControl.async_login",
        AsyncMock(side_effect=error),
    ):
        data, result = await async_validate_web_control(
            hass, {**WEB, CONF_WEB_TWO_FACTOR: ""}, BASE_URL, use_mock_data=False
        )

    assert (data, result) == ({}, key)


async def test_login_with_a_one_time_code_keeps_the_session_not_the_code(hass, hass_storage):
    with patch(
        "custom_components.eplucon.config_flow.EpluconWebControl.async_login", AsyncMock()
    ), patch(
        "custom_components.eplucon.config_flow.EpluconWebControl.session_cookies",
        return_value={"portaal_eplucon_session": "abc"},
    ):
        data, error = await async_validate_web_control(
            hass, {**WEB, CONF_WEB_TWO_FACTOR: "123456"}, BASE_URL, use_mock_data=False
        )

    assert error is None
    assert data[CONF_WEB_TWO_FACTOR] is None
    assert hass_storage[f"{DOMAIN}.web_session"]["data"] == {
        "username": "user@example.com",
        "cookies": {"portaal_eplucon_session": "abc"},
    }


async def test_saving_unchanged_options_does_not_log_in_again(hass):
    login = AsyncMock()
    with patch("custom_components.eplucon.config_flow.EpluconWebControl.async_login", login):
        data, error = await async_validate_web_control(
            hass,
            {**WEB, CONF_WEB_TWO_FACTOR: ""},
            BASE_URL,
            use_mock_data=False,
            stored={**WEB, CONF_WEB_TWO_FACTOR: ""},
        )

    assert error is None
    login.assert_not_called()


async def test_options_can_turn_web_control_off(hass):
    entry = await set_up(hass, **WEB)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_API_TOKEN: "token",
            CONF_API_ENDPOINT: BASE_URL,
            CONF_DEVELOPER_OPTIONS: {CONF_USE_MOCK_DATA: True},
            CONF_WEB_CONTROL: {},
        },
    )
    await hass.async_block_till_done()

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_WEB_USERNAME] is None
    assert entry.entry_id not in hass.data[DOMAIN].get(WEB_COORDINATORS, {})
    state = hass.states.get(entity_id(hass, "number", "indoor_temperature"))
    assert state is None or state.state == "unavailable"


def test_web_control_is_open_and_developer_tools_come_last():
    from custom_components.eplucon.config_flow import build_schema

    schema = build_schema().schema
    keys = [str(key) for key in schema]

    assert keys.index(CONF_WEB_CONTROL) < keys.index(CONF_DEVELOPER_OPTIONS) == len(keys) - 1
    web_section = next(value for key, value in schema.items() if str(key) == CONF_WEB_CONTROL)
    assert web_section.options["collapsed"] is False
