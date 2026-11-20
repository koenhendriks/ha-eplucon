"""A null in the realtime snapshot stored with the config entry must not
break setup after a restart."""

import json

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.eplucon.const import (
    CONF_API_ENDPOINT,
    CONF_API_TOKEN,
    CONF_USE_MOCK_DATA,
    DOMAIN,
)
from custom_components.eplucon.eplucon_api import eplucon_client
from custom_components.eplucon.eplucon_api.eplucon_client import BASE_URL


async def test_setup_survives_null_operation_mode_in_stored_device(hass):
    mock = eplucon_client.MOCK_DIR / "get_realtime_info.json"
    realtime = json.loads(mock.read_text())
    realtime["data"]["common"]["operation_mode"] = None
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_API_TOKEN: "token",
            CONF_API_ENDPOINT: BASE_URL,
            CONF_USE_MOCK_DATA: True,
            "devices": [
                {
                    "id": 1001337,
                    "account_module_index": "1aa111a1a1a111a1aa1111111aa11a11",
                    "name": "Mock Heatpump",
                    "type": "heat_pump",
                    "realtime_info": realtime["data"],
                }
            ],
        },
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
