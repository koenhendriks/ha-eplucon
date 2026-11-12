"""Polling and writing heat pump settings through the portal website."""

from __future__ import annotations

import logging
import time
from dataclasses import replace
from collections.abc import Callable
from datetime import timedelta

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, WEB_CONTROL_SCAN_INTERVAL
from .eplucon_api.DTO.DeviceDTO import DeviceDTO
from .eplucon_api.web_control import (
    TYPE_FLOAT,
    ControlState,
    EpluconWebControl,
    WebControlAuthError,
    WebControlError,
    WebControlTwoFactorRequired,
)

_LOGGER = logging.getLogger(__name__)

SESSION_STORE_KEY = f"{DOMAIN}.web_session"
SESSION_STORE_VERSION = 1

ISSUE_WEB_AUTH = "web_control_auth"
ISSUE_WEB_TWO_FACTOR = "web_control_two_factor"

# The portal showed a written value within 5-20 s in testing.
REFRESH_AFTER_WRITE = 20
# Until the portal reports a written value, show the value that was sent, so
# an entity doesn't jump back while the change is still on its way.
PENDING_TIMEOUT = 300

WebData = dict[str, dict[str, ControlState]]


def session_store(hass: HomeAssistant) -> Store:
    return Store(hass, SESSION_STORE_VERSION, SESSION_STORE_KEY, private=True)


class EpluconWebCoordinator(DataUpdateCoordinator[WebData]):
    """Settings of every heat pump, keyed by account_module_index."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: EpluconWebControl,
        heat_pumps: list[DeviceDTO],
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name="Eplucon web control",
            update_interval=timedelta(seconds=WEB_CONTROL_SCAN_INTERVAL),
        )
        self.client = client
        self.heat_pumps = heat_pumps
        # (module_index, key) -> (value sent, monotonic deadline)
        self._pending: dict[tuple[str, str], tuple[float | int, float]] = {}
        self._refresh_unsub: Callable[[], None] | None = None
        self._failing: set[str] = set()
        entry.async_on_unload(self._cancel_refresh)

    async def _async_update_data(self) -> WebData:
        data: WebData = {}
        failures: list[Exception] = []
        try:
            for device in self.heat_pumps:
                index = device.account_module_index
                try:
                    data[index] = await self.client.async_get_states(index)
                except (WebControlError, aiohttp.ClientError, TimeoutError) as err:
                    # Login problems concern every heat pump: handled below.
                    if isinstance(err, WebControlAuthError):
                        raise
                    self._warn_once(device, err)
                    failures.append(err)
                else:
                    self._failing.discard(index)
            if not data and failures:
                raise failures[0]
        except WebControlTwoFactorRequired as err:
            self._raise_issue(ISSUE_WEB_TWO_FACTOR)
            raise UpdateFailed(f"Eplucon web control: {err}") from err
        except WebControlAuthError as err:
            self._raise_issue(ISSUE_WEB_AUTH)
            raise UpdateFailed(f"Eplucon web control: {err}") from err
        except (WebControlError, aiohttp.ClientError, TimeoutError) as err:
            raise UpdateFailed(f"Eplucon web control: {err}") from err

        for issue in (ISSUE_WEB_AUTH, ISSUE_WEB_TWO_FACTOR):
            ir.async_delete_issue(self.hass, DOMAIN, issue)
        return self._apply_pending(data)

    def _warn_once(self, device: DeviceDTO, err: Exception) -> None:
        if device.account_module_index in self._failing:
            return
        self._failing.add(device.account_module_index)
        _LOGGER.warning(
            "Eplucon web control can't read heat pump %s (%s), its controls stay "
            "unavailable until it can: %s",
            device.name,
            device.id,
            err,
        )

    def _apply_pending(self, data: WebData) -> WebData:
        now = time.monotonic()
        for (index, key), (value, deadline) in list(self._pending.items()):
            state = data.get(index, {}).get(key)
            if state is None or state.value == value or now > deadline:
                del self._pending[(index, key)]
                continue
            data[index][key] = replace(state, value=value)
        return data

    def _raise_issue(self, issue_id: str) -> None:
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.ERROR,
            translation_key=issue_id,
        )

    def value(self, module_index: str, key: str) -> float | int | None:
        state = self.state(module_index, key)
        return None if state is None else state.value

    def state(self, module_index: str, key: str) -> ControlState | None:
        if not self.data:
            return None
        return self.data.get(module_index, {}).get(key)

    async def async_set_value(self, module_index: str, key: str, value: float | int) -> None:
        """Write one setting and show it right away; the portal confirms later."""
        try:
            state = await self.client.async_set_value(module_index, key, value)
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err
        except WebControlTwoFactorRequired as err:
            self._raise_issue(ISSUE_WEB_TWO_FACTOR)
            raise HomeAssistantError(f"Eplucon web control: {err}") from err
        except WebControlAuthError as err:
            self._raise_issue(ISSUE_WEB_AUTH)
            raise HomeAssistantError(f"Eplucon web control: {err}") from err
        except (WebControlError, aiohttp.ClientError, TimeoutError) as err:
            raise HomeAssistantError(f"Eplucon web control: {err}") from err

        # As the portal will report it: 21.25 is sent and stored as 21.2.
        sent = state.validate(value)
        value = float(sent) if state.type == TYPE_FLOAT else int(sent)

        self._pending[(module_index, key)] = (value, time.monotonic() + PENDING_TIMEOUT)
        if self.data and key in self.data.get(module_index, {}):
            self.data[module_index][key] = replace(self.data[module_index][key], value=value)
            self.async_update_listeners()

        self._cancel_refresh()
        self._refresh_unsub = async_call_later(self.hass, REFRESH_AFTER_WRITE, self._refresh)

    @callback
    def _refresh(self, _now) -> None:
        self._refresh_unsub = None
        self.hass.async_create_task(self.async_request_refresh())

    @callback
    def _cancel_refresh(self) -> None:
        if self._refresh_unsub is not None:
            self._refresh_unsub()
            self._refresh_unsub = None
