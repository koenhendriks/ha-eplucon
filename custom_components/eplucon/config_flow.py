import logging
import voluptuous as vol
from typing import Any, Dict, Optional
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import aiohttp_client
from homeassistant.data_entry_flow import FlowResult, section
from .const import (
    DOMAIN,
    SUPPORTED_TYPES,
    EPLUCON_API_TOKENS_URL,
    CONF_API_TOKEN,
    CONF_API_ENDPOINT,
    CONF_DEVELOPER_OPTIONS,
    CONF_USE_MOCK_DATA,
)
from .eplucon_api.eplucon_client import EpluconApi, ApiAuthError, ApiError, BASE_URL

_LOGGER = logging.getLogger(__name__)


def build_schema(
    api_token: Optional[str] = None,
    api_endpoint: str = BASE_URL,
    use_mock_data: bool = False,
) -> vol.Schema:
    """Build the form schema shared by the setup step and the options step.

    The mock switch sits in its own collapsed "Developer tools" section rather
    than being a magic API endpoint: a fake host still has to resolve in DNS,
    so it could never be reached. The section is shown expanded once mock data
    is on, so it can't be left enabled unnoticed.
    """
    api_token_key = (
        vol.Required(CONF_API_TOKEN)
        if api_token is None
        else vol.Required(CONF_API_TOKEN, default=api_token)
    )

    return vol.Schema({
        api_token_key: str,
        vol.Required(CONF_API_ENDPOINT, default=api_endpoint): str,
        vol.Required(CONF_DEVELOPER_OPTIONS): section(
            vol.Schema({
                vol.Required(CONF_USE_MOCK_DATA, default=use_mock_data): bool,
            }),
            {"collapsed": not use_mock_data},
        ),
    })


def read_use_mock_data(user_input: Dict[str, Any]) -> bool:
    """Read the mock switch out of the developer options section."""
    developer_options = user_input.get(CONF_DEVELOPER_OPTIONS) or {}
    return bool(developer_options.get(CONF_USE_MOCK_DATA, False))


class EpluconConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Eplucon."""

    VERSION = 1

    async def async_step_user(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """Handle the initial step."""
        errors: Dict[str, str] = {}
        api_token: Optional[str] = None
        api_endpoint: str = BASE_URL
        use_mock_data = False

        _LOGGER.debug("Starting Eplucon config flow")

        if user_input is not None:
            # Attempt to connect to the API using the provided API token & endpoint
            api_token = user_input[CONF_API_TOKEN]
            api_endpoint = user_input[CONF_API_ENDPOINT]
            use_mock_data = read_use_mock_data(user_input)
            client = EpluconApi(
                api_token,
                api_endpoint,
                aiohttp_client.async_get_clientsession(self.hass),
                use_mock_data=use_mock_data,
            )

            try:
                devices = await client.get_devices()

                _LOGGER.debug(f"Received the following devices from API: {devices}")

                for device in devices:
                    if device.type not in SUPPORTED_TYPES:
                        _LOGGER.warning(
                            f"Device {device.name} with type {device.type} is not supported yet. Skipping...")
                        devices.remove(device)

                if len(devices) > 0:
                    return self.async_create_entry(title="Eplucon", data={
                        "devices": devices,
                        CONF_API_TOKEN: api_token,
                        CONF_API_ENDPOINT: api_endpoint,
                        CONF_USE_MOCK_DATA: use_mock_data,
                    })

                errors["base"] = "no-devices"

            except ApiAuthError:
                # Handle authentication error
                _LOGGER.info("Authentication failed with the provided API token")
                errors["base"] = "auth"

            except ApiError:
                # Handle general API error
                _LOGGER.info("Failed to fetch devices from Eplucon API")
                errors["base"] = "api"

            except Exception as e:
                # Handle any other unexpected exceptions
                _LOGGER.exception("Unexpected exception: %s", e)
                errors["base"] = "unknown"

        # If the user input is not valid or an error occurred, show the form again with the error message
        return self.async_show_form(
            step_id="user",
            data_schema=build_schema(api_token, api_endpoint, use_mock_data),
            errors=errors,
            description_placeholders={"api_tokens_url": EPLUCON_API_TOKENS_URL},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return EpluconOptionsFlowHandler(config_entry)


class EpluconOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle Eplucon options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize Eplucon options flow."""
        super().__init__()
        self._config_entry = config_entry

    async def async_step_init(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """Manage the options for the integration."""
        errors: Dict[str, str] = {}
        entry_data = self._config_entry.data
        api_token = entry_data.get(CONF_API_TOKEN)
        api_endpoint = entry_data.get(CONF_API_ENDPOINT, BASE_URL)
        use_mock_data = entry_data.get(CONF_USE_MOCK_DATA, False)

        if user_input is not None:
            # If the user has provided new data, update the config entry
            api_token = user_input.get(CONF_API_TOKEN)
            api_endpoint = user_input.get(CONF_API_ENDPOINT, BASE_URL)
            use_mock_data = read_use_mock_data(user_input)

            # Revalidate the API token to ensure it's correct
            client = EpluconApi(
                api_token,
                api_endpoint,
                aiohttp_client.async_get_clientsession(self.hass),
                use_mock_data=use_mock_data,
            )

            try:
                devices = await client.get_devices()

                _LOGGER.info(f"Devices found: {devices}")

                # Skip unsupported devices
                for device in devices:
                    if device.type not in SUPPORTED_TYPES:
                        _LOGGER.debug(
                            f"Device {device.name} with type {device.type} is not supported yet. Skipping...")
                        devices.remove(device)

                if len(devices) > 0:
                    # Update the configuration entry with the new API token and devices.
                    # Keep the rest of the entry data: dropping the endpoint or the
                    # mock switch here would silently reset them on every save.
                    self.hass.config_entries.async_update_entry(
                        self._config_entry,
                        data={
                            **entry_data,
                            CONF_API_TOKEN: api_token,
                            CONF_API_ENDPOINT: api_endpoint,
                            CONF_USE_MOCK_DATA: use_mock_data,
                            "devices": devices,
                        }
                    )
                    return self.async_create_entry(title="", data={})

                errors["base"] = "no-devices"

            except ApiAuthError:
                # Handle authentication error
                _LOGGER.info("Authentication failed with the provided API token")
                errors["base"] = "auth"

            except ApiError:
                # Handle general API error
                _LOGGER.info("Failed to fetch devices from Eplucon API")
                errors["base"] = "api"

            except Exception as e:
                # Handle any other unexpected exceptions
                _LOGGER.exception("Unexpected exception: %s", e)
                errors["base"] = "unknown"

        # Show the options form with the current API token as the default value
        return self.async_show_form(
            step_id="init",
            data_schema=build_schema(api_token, api_endpoint, use_mock_data),
            errors=errors
        )
