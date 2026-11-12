import logging
import aiohttp
import voluptuous as vol
from typing import Any, Dict, Optional
from homeassistant import config_entries
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.data_entry_flow import FlowResult, section
from .const import (
    DOMAIN,
    SUPPORTED_TYPES,
    EPLUCON_API_TOKENS_URL,
    CONF_API_TOKEN,
    CONF_API_ENDPOINT,
    CONF_DEVELOPER_OPTIONS,
    CONF_USE_MOCK_DATA,
    CONF_WEB_CONTROL,
    CONF_WEB_USERNAME,
    CONF_WEB_PASSWORD,
    CONF_WEB_TWO_FACTOR,
    DEFAULT_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    MAX_SCAN_INTERVAL,
)
from .eplucon_api.eplucon_client import EpluconApi, ApiAuthError, ApiError, BASE_URL
from .eplucon_api.web_control import (
    EpluconWebControl,
    WebControlAuthError,
    WebControlError,
    WebControlTwoFactorInvalid,
    WebControlTwoFactorRequired,
    is_totp_secret,
    portal_url_from_api,
)
from .web_coordinator import session_store

_LOGGER = logging.getLogger(__name__)


def build_schema(
    api_token: Optional[str] = None,
    api_endpoint: str = BASE_URL,
    use_mock_data: bool = False,
    scan_interval: int = DEFAULT_SCAN_INTERVAL,
    web_control: Optional[Dict[str, str]] = None,
) -> vol.Schema:
    """Build the form schema shared by the setup step and the options step.

    The mock switch sits in its own collapsed "Developer tools" section rather
    than being a magic API endpoint: a fake host still has to resolve in DNS,
    so it could never be reached. The section is shown expanded once mock data
    is on, so it can't be left enabled unnoticed.

    Web control is optional but shown open, so it gets noticed; developer
    tools stay last. The web control fields use suggested values rather than
    defaults so they can be emptied to turn web control off again.
    """
    web_control = web_control or {}

    def suggested(key: str) -> dict:
        value = web_control.get(key)
        return {"suggested_value": value} if value else {}

    api_token_key = (
        vol.Required(CONF_API_TOKEN)
        if api_token is None
        else vol.Required(CONF_API_TOKEN, default=api_token)
    )

    return vol.Schema({
        api_token_key: str,
        vol.Required(CONF_API_ENDPOINT, default=api_endpoint): str,
        vol.Required(CONF_SCAN_INTERVAL, default=scan_interval): vol.All(
            vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)
        ),
        vol.Optional(CONF_WEB_CONTROL): section(
            vol.Schema({
                vol.Optional(CONF_WEB_USERNAME, description=suggested(CONF_WEB_USERNAME)): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="username")
                ),
                vol.Optional(CONF_WEB_PASSWORD, description=suggested(CONF_WEB_PASSWORD)): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="current-password")
                ),
                vol.Optional(CONF_WEB_TWO_FACTOR, description=suggested(CONF_WEB_TWO_FACTOR)): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="one-time-code")
                ),
            }),
            {"collapsed": False},
        ),
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


def read_web_control(user_input: Dict[str, Any]) -> Dict[str, str]:
    """Read the web control section; empty fields come back as ''."""
    web = user_input.get(CONF_WEB_CONTROL) or {}
    return {
        key: (web.get(key) or "").strip()
        for key in (CONF_WEB_USERNAME, CONF_WEB_PASSWORD, CONF_WEB_TWO_FACTOR)
    }


def stored_web_control(entry_data: Dict[str, Any]) -> Dict[str, str]:
    return {
        key: entry_data.get(key) or ""
        for key in (CONF_WEB_USERNAME, CONF_WEB_PASSWORD, CONF_WEB_TWO_FACTOR)
    }


async def async_validate_web_control(
    hass: HomeAssistant,
    web: Dict[str, str],
    api_endpoint: str,
    use_mock_data: bool,
    stored: Optional[Dict[str, str]] = None,
) -> tuple[Dict[str, Optional[str]], Optional[str]]:
    """Check the web control login. Returns entry data to store, or an error key.

    A one-time 2FA code is used for this login and then dropped; only an
    authenticator key is kept. Saving the options again without a new code
    keeps the existing portal session instead of logging in again.
    """
    username = web[CONF_WEB_USERNAME]
    password = web[CONF_WEB_PASSWORD]
    two_factor = web[CONF_WEB_TWO_FACTOR]

    if not username and not password:
        return {CONF_WEB_USERNAME: None, CONF_WEB_PASSWORD: None, CONF_WEB_TWO_FACTOR: None}, None
    if not username or not password:
        return {}, "web_credentials_incomplete"

    key = two_factor if is_totp_secret(two_factor) else None
    data = {CONF_WEB_USERNAME: username, CONF_WEB_PASSWORD: password, CONF_WEB_TWO_FACTOR: key}

    stored = stored or {}
    unchanged = (
        username == stored.get(CONF_WEB_USERNAME)
        and password == stored.get(CONF_WEB_PASSWORD)
        and two_factor in ("", stored.get(CONF_WEB_TWO_FACTOR) or "")
    )
    if use_mock_data or unchanged:
        if unchanged:
            data[CONF_WEB_TWO_FACTOR] = stored.get(CONF_WEB_TWO_FACTOR) or None
        return data, None

    # Only for this login test. Home Assistant's own sessions are detached,
    # not closed: they share its connection pool.
    session = aiohttp_client.async_create_clientsession(
        hass, auto_cleanup=False, cookie_jar=aiohttp.CookieJar()
    )
    client = EpluconWebControl(
        portal_url_from_api(api_endpoint),
        username,
        password,
        session,
        two_factor=two_factor,
    )
    try:
        await client.async_login()
    except WebControlTwoFactorRequired:
        return {}, "web_two_factor_required"
    except WebControlTwoFactorInvalid:
        return {}, "web_two_factor_invalid"
    except WebControlAuthError:
        return {}, "web_auth"
    except (WebControlError, aiohttp.ClientError, TimeoutError):
        _LOGGER.info("Could not reach the Eplucon portal for web control", exc_info=True)
        return {}, "web_connect"
    finally:
        cookies = client.session_cookies()
        session.detach()

    await session_store(hass).async_save({"username": username, "cookies": cookies})
    return data, None


class EpluconConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Eplucon."""

    VERSION = 1

    async def async_step_user(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """Handle the initial step."""
        errors: Dict[str, str] = {}
        api_token: Optional[str] = None
        api_endpoint: str = BASE_URL
        use_mock_data = False
        scan_interval = DEFAULT_SCAN_INTERVAL
        web: Dict[str, str] = {}

        _LOGGER.debug("Starting Eplucon config flow")

        if user_input is not None:
            # Attempt to connect to the API using the provided API token & endpoint
            api_token = user_input[CONF_API_TOKEN]
            api_endpoint = user_input[CONF_API_ENDPOINT]
            scan_interval = user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            use_mock_data = read_use_mock_data(user_input)
            web = read_web_control(user_input)
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

                if not devices:
                    errors["base"] = "no-devices"
                else:
                    web_data, web_error = await async_validate_web_control(
                        self.hass, web, api_endpoint, use_mock_data
                    )
                    if web_error:
                        errors["base"] = web_error
                    else:
                        return self.async_create_entry(title="Eplucon", data={
                            "devices": devices,
                            CONF_API_TOKEN: api_token,
                            CONF_API_ENDPOINT: api_endpoint,
                            CONF_SCAN_INTERVAL: scan_interval,
                            CONF_USE_MOCK_DATA: use_mock_data,
                            **web_data,
                        })

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
            data_schema=build_schema(
                api_token, api_endpoint, use_mock_data, scan_interval, web
            ),
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
        scan_interval = entry_data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        stored_web = stored_web_control(entry_data)
        web = stored_web

        if user_input is not None:
            # If the user has provided new data, update the config entry
            api_token = user_input.get(CONF_API_TOKEN)
            api_endpoint = user_input.get(CONF_API_ENDPOINT, BASE_URL)
            scan_interval = user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            use_mock_data = read_use_mock_data(user_input)
            web = read_web_control(user_input)

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

                web_data, web_error = (
                    await async_validate_web_control(
                        self.hass, web, api_endpoint, use_mock_data, stored_web
                    )
                    if devices
                    else ({}, None)
                )

                if not devices:
                    errors["base"] = "no-devices"
                elif web_error:
                    errors["base"] = web_error
                else:
                    # Update the configuration entry with the new API token and devices.
                    # Keep the rest of the entry data: dropping the endpoint or the
                    # mock switch here would silently reset them on every save.
                    self.hass.config_entries.async_update_entry(
                        self._config_entry,
                        data={
                            **entry_data,
                            CONF_API_TOKEN: api_token,
                            CONF_API_ENDPOINT: api_endpoint,
                            CONF_SCAN_INTERVAL: scan_interval,
                            CONF_USE_MOCK_DATA: use_mock_data,
                            "devices": devices,
                            **web_data,
                        }
                    )
                    return self.async_create_entry(title="", data={})

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
            data_schema=build_schema(
                api_token, api_endpoint, use_mock_data, scan_interval, web
            ),
            errors=errors
        )
