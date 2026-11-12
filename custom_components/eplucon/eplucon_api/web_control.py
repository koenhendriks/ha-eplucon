"""Control a heat pump through the Eplucon portal website ("e-control").

The official API is read-only. The portal's own pages can change settings, so
this client logs in like a browser and replays what the settings dialogs send.
Everything it relies on was taken from the live portal; see
docs/web-control.md. It is opt-in and can break whenever the website changes.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import re
import struct
import time
from dataclasses import dataclass, field
from html import unescape
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode

import aiohttp
from yarl import URL

_LOGGER = logging.getLogger(__package__)

MOCK_DIR = Path(__file__).parent / "mock" / "webcontrol"

# Modal form `type` values: how the dialog asks for its value.
TYPE_INTEGER = "1"
TYPE_FLOAT = "2"
TYPE_SWITCH = "10"
TYPE_SELECT = "11"

# Cookies worth keeping across restarts. The remember cookie skips the
# password but not the 2FA code, so the session cookie matters as much.
SESSION_COOKIE_PREFIXES = ("remember_web_", "portaal_eplucon_session", "XSRF-TOKEN")

XHR_HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}


class WebControlError(Exception):
    """The portal could not be reached or answered something unexpected."""


class WebControlModuleUnknown(WebControlError):
    """The portal login has no heat pump with this module index."""


class WebControlAuthError(WebControlError):
    """The portal rejected the username or password."""


class WebControlTwoFactorRequired(WebControlAuthError):
    """The portal asks for a 2FA code and there is no key to make one."""


class WebControlTwoFactorInvalid(WebControlAuthError):
    """The portal rejected the 2FA code."""


@dataclass(frozen=True)
class ControlSpec:
    key: str
    code: str
    block_type: str


# Codes and block types as the portal's own tiles use them. Five sit on the
# heat pump dashboard ("module"), the rest in its service menu ("menu").
CONTROLS: dict[str, ControlSpec] = {
    spec.key: spec
    for spec in (
        ControlSpec("indoor_temperature", "5704", "module"),
        ControlSpec("boiler_temperature", "5700", "module"),
        ControlSpec("warm_water_active", "5711", "module"),
        ControlSpec("heatpump_active", "5715", "module"),
        ControlSpec("heatpump_operation_mode", "5712", "module"),
        ControlSpec("boiler_temperature_delta", "5804", "menu"),
        ControlSpec("heating_active", "5813", "menu"),
        ControlSpec("stop_heating_above", "5814", "menu"),
        ControlSpec("heating_curve_correction", "5886", "menu"),
        ControlSpec("cooling_active", "5817", "menu"),
        ControlSpec("stop_passive_cooling_below", "5901", "menu"),
        ControlSpec("stop_active_cooling_below", "5818", "menu"),
    )
}


@dataclass
class ControlState:
    """One settings dialog as the portal rendered it."""

    key: str
    type: str
    value: float | int | None
    action: str
    # Form fields in document order, `tile_value` included: the portal gets
    # them back exactly like the browser sends them.
    fields: list[tuple[str, str]]
    label: str | None = None
    min: float | None = None
    max: float | None = None
    step: float | None = None
    # Option value -> the portal's label, for switches and selects.
    options: dict[int, str] = field(default_factory=dict)

    @property
    def is_number(self) -> bool:
        return self.type in (TYPE_INTEGER, TYPE_FLOAT)

    def validate(self, value: float | int) -> str:
        """Return `value` formatted as the portal expects, or raise ValueError."""
        if self.is_number:
            number = float(value)
            if self.min is not None and number < self.min:
                raise ValueError(f"{self.key}: {value} is below the minimum {self.min}")
            if self.max is not None and number > self.max:
                raise ValueError(f"{self.key}: {value} is above the maximum {self.max}")
            if self.type == TYPE_INTEGER:
                if number != int(number):
                    raise ValueError(f"{self.key}: {value} is not a whole number")
                return str(int(number))
            return f"{number:.1f}"

        try:
            option = int(value)
        except (TypeError, ValueError):
            raise ValueError(f"{self.key}: {value!r} is not an option") from None
        if option != value or option not in self.options:
            raise ValueError(
                f"{self.key}: {value!r} is not one of {sorted(self.options)}"
            )
        return str(option)


def totp(secret: str, at: float | None = None) -> str:
    """RFC 6238 code (SHA-1, 6 digits, 30 s), as authenticator apps make them."""
    key = re.sub(r"\s", "", secret).upper()
    raw = base64.b32decode(key + "=" * (-len(key) % 8))
    counter = int((time.time() if at is None else at) // 30)
    digest = hmac.new(raw, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return f"{code % 1_000_000:06d}"


def is_totp_secret(value: str) -> bool:
    """Tell a base32 authenticator key from a one-time 6-digit code."""
    key = re.sub(r"\s", "", value or "").upper()
    if len(key) < 16 or not re.fullmatch(r"[A-Z2-7]+=*", key):
        return False
    try:
        base64.b32decode(key + "=" * (-len(key) % 8))
    except ValueError:
        return False
    return True


def portal_url_from_api(api_endpoint: str) -> str:
    """https://portaal.eplucon.nl/api/v2 -> https://portaal.eplucon.nl"""
    url = URL(api_endpoint)
    return str(url.origin())


def _attrs(tag: str) -> dict[str, str]:
    attrs = {
        name.lower(): unescape(value)
        for name, value in re.findall(r'([\w-]+)="([^"]*)"', tag)
    }
    if re.search(r"\schecked[\s/>]", tag):
        attrs["checked"] = "checked"
    return attrs


def form_inputs(html: str) -> dict[str, str]:
    """Name/value of every <input> on a page, for replaying a form."""
    fields = {}
    for tag in re.findall(r"<input\b[^>]*>", html, re.S):
        attrs = _attrs(tag)
        if "name" in attrs:
            fields[attrs["name"]] = attrs.get("value", "")
    return fields


def page_state(html: str) -> str:
    """'2fa', 'login' or 'ok' for a full portal page."""
    if 'name="one_time_password"' in html:
        return "2fa"
    if 'name="password"' in html:
        return "login"
    return "ok"


def _number(raw: str | None) -> float | None:
    try:
        return float(raw) if raw not in (None, "") else None
    except ValueError:
        return None


def parse_modal(key: str, html: str) -> ControlState:
    """Read a settings dialog: where it posts, its fields and current value."""
    form = re.search(r"<form\b[^>]*>", html)
    if form is None:
        raise WebControlError(f"Settings dialog for {key} has no form")
    form_attrs = _attrs(form.group(0))
    action = form_attrs.get("data-action")
    if not action:
        raise WebControlError(f"Settings dialog for {key} has no save URL")

    fields: list[tuple[str, str]] = []
    options: dict[int, str] = {}
    value: float | int | None = None
    bounds: dict[str, str] = {}

    for match in re.finditer(r"<input\b[^>]*>", html, re.S):
        attrs = _attrs(match.group(0))
        name = attrs.get("name")
        if not name:
            continue
        kind = attrs.get("type", "text").lower()
        if kind == "radio":
            raw = attrs.get("value", "")
            # The label text follows the input inside its <label>.
            label = re.match(r"\s*([^<]*)", html[match.end():]).group(1).strip()
            try:
                options[int(raw)] = unescape(label)
            except ValueError:
                continue
            if "checked" in attrs:
                value = int(raw)
                fields.append((name, raw))
            continue
        if kind == "range":
            bounds = attrs
            value = _number(attrs.get("value"))
        fields.append((name, attrs.get("value", "")))

    form_type = dict(fields).get("type", form_attrs.get("data-type", ""))
    if form_type == TYPE_INTEGER and value is not None:
        value = int(value)

    if options and not any(name == "tile_value" for name, _ in fields):
        # Nothing checked: keep the field's place so a write can fill it in.
        ido = next((i for i, (name, _) in enumerate(fields) if name == "ido"), len(fields))
        fields.insert(ido, ("tile_value", ""))

    if not any(name == "tile_value" for name, _ in fields):
        raise WebControlError(f"Settings dialog for {key} has no value field")

    return ControlState(
        key=key,
        type=form_type,
        value=value,
        action=unescape(action),
        fields=fields,
        label=dict(fields).get("label"),
        min=_number(bounds.get("min")),
        max=_number(bounds.get("max")),
        step=_number(bounds.get("step")),
        options=options,
    )


class EpluconWebControl:
    """Logged-in portal session for reading and changing heat pump settings."""

    def __init__(
        self,
        portal_url: str,
        username: str,
        password: str,
        session: aiohttp.ClientSession | None,
        *,
        two_factor: str | None = None,
        cookies: dict[str, str] | None = None,
        on_cookies: Callable[[dict[str, str]], Any] | None = None,
        use_mock_data: bool = False,
    ) -> None:
        self._portal = portal_url.rstrip("/")
        self._username = username
        self._password = password
        self._session = session
        self._mock = use_mock_data
        self._on_cookies = on_cookies
        self._lock = asyncio.Lock()
        self._mock_values: dict[str, dict[str, float | int]] = {}

        # A key keeps working; a one-time code only for the first login.
        two_factor = (two_factor or "").strip()
        self._totp_secret = two_factor if is_totp_secret(two_factor) else None
        self._one_time_code = None if self._totp_secret else (two_factor or None)

        if session is None and not self._mock:
            raise RuntimeError("aiohttp ClientSession is required")

        if cookies and session is not None:
            session.cookie_jar.update_cookies(cookies, URL(self._portal))

    @property
    def can_relogin(self) -> bool:
        """Whether a lost session can be restored without the user."""
        return self._totp_secret is not None

    def session_cookies(self) -> dict[str, str]:
        if self._session is None:
            return {}
        return {
            cookie.key: cookie.value
            for cookie in self._session.cookie_jar
            if cookie.key.startswith(SESSION_COOKIE_PREFIXES)
        }

    async def async_login(self) -> None:
        """Log in with the password and, when asked, a 2FA code."""
        if self._mock:
            return
        async with self._lock:
            await self._login()

    async def async_get_states(self, module_index: str) -> dict[str, ControlState]:
        """Every known setting of one heat pump, read from its dialogs."""
        states = {}
        for key in CONTROLS:
            states[key] = await self.async_get_state(module_index, key)
        return states

    async def async_get_state(self, module_index: str, key: str) -> ControlState:
        spec = CONTROLS[key]
        if self._mock:
            return await self._mock_state(module_index, spec)
        html = await self._modal_html(module_index, spec)
        return parse_modal(key, html)

    async def async_set_value(
        self, module_index: str, key: str, value: float | int
    ) -> ControlState:
        """Change one setting. Returns the dialog state the write was based on.

        The dialog is fetched fresh first: it carries the CSRF token and the
        exact fields the portal expects back, and its bounds are checked
        before anything is sent.
        """
        state = await self.async_get_state(module_index, key)
        formatted = state.validate(value)

        if self._mock:
            self._mock_values.setdefault(module_index, {})[key] = (
                float(formatted) if state.type == TYPE_FLOAT else int(formatted)
            )
            _LOGGER.info("Mock web control: %s set to %s", key, formatted)
            return state

        fields = [
            (name, formatted if name == "tile_value" else val)
            for name, val in state.fields
        ]
        form = aiohttp.FormData()
        for name, val in fields:
            form.add_field(name, val)
        # The browser adds these two copies of the form as well.
        form.add_field("dataSerialize", urlencode(fields))
        form.add_field(
            "data",
            json.dumps(
                [{"name": name, "value": val} for name, val in fields],
                separators=(",", ":"),
            ),
        )

        async with self._lock:
            _LOGGER.debug("Web control: setting %s of %s to %s", key, module_index, formatted)
            async with self._session.post(
                state.action, data=form, headers=XHR_HEADERS
            ) as response:
                status = response.status
                body = await response.text()

        _LOGGER.debug("Web control: save %s answered HTTP %s: %s", key, status, body[:500])
        if status != 200:
            raise WebControlError(
                f"Saving {key} failed with HTTP {status}: {body[:200]}"
            )
        try:
            answer = json.loads(body)
        except ValueError:
            answer = None
        if isinstance(answer, dict) and answer.get("message") and not answer.get("status"):
            message = answer["message"]
            if isinstance(message, list):
                message = " ".join(str(m) for m in message)
            raise WebControlError(f"Saving {key} was refused: {message}")
        return state

    async def _modal_html(self, module_index: str, spec: ControlSpec) -> str:
        url = f"{self._portal}/e-control/ajax/modal/{spec.code}"
        params = {"blockType": spec.block_type, "account_module_index": module_index}

        for attempt in (1, 2):
            async with self._lock:
                async with self._session.get(url, params=params, headers=XHR_HEADERS) as response:
                    status = response.status
                    body = await response.text()
            try:
                data = json.loads(body) if body.strip() else None
            except ValueError:
                data = None

            if status == 200 and isinstance(data, dict) and isinstance(data.get("html"), str):
                return data["html"]

            # Seen for a module of another account and for a made-up index;
            # the session itself is fine, so logging in again won't help.
            if status == 200 and not body.strip():
                raise WebControlModuleUnknown(
                    f"The portal login has no heat pump with module index {module_index}"
                )

            if attempt == 2 or status not in (200, 401, 419):
                raise WebControlError(
                    f"Reading {spec.key} failed with HTTP {status}: {str(data)[:200]}"
                )

            # 401 means no session, a JSON error without a dialog means the
            # session still waits for its 2FA code. Either way: log in again.
            _LOGGER.debug(
                "Web control session not usable (HTTP %s: %s), logging in again",
                status,
                data,
            )
            async with self._lock:
                await self._login()

        raise AssertionError("unreachable")

    async def _login(self) -> None:
        """Bring the session to logged in. Caller holds the lock."""
        html = await self._get_page("/e-control")
        state = page_state(html)

        if state == "login":
            html = await self._get_page("/login")
            data = form_inputs(html)
            data.update(username=self._username, password=self._password, remember="1")
            html = await self._post_page("/login", data)
            state = page_state(html)
            if state == "login":
                raise WebControlAuthError("The portal rejected the username or password")

        if state == "2fa":
            code = self._next_code()
            data = form_inputs(html)
            data["one_time_password"] = code
            html = await self._post_page("/2fa", data)
            state = page_state(html)
            if state == "2fa":
                raise WebControlTwoFactorInvalid("The portal rejected the 2FA code")
            if state == "login":
                raise WebControlAuthError("The portal asked for the password again after 2FA")

        _LOGGER.debug("Web control: logged in to %s", self._portal)
        if self._on_cookies is not None:
            self._on_cookies(self.session_cookies())

    def _next_code(self) -> str:
        if self._totp_secret:
            return totp(self._totp_secret)
        if self._one_time_code:
            code, self._one_time_code = self._one_time_code, None
            return code
        raise WebControlTwoFactorRequired(
            "The portal asks for a 2FA code; enter a new one in the integration options"
        )

    async def _get_page(self, path: str) -> str:
        async with self._session.get(f"{self._portal}{path}") as response:
            if response.status != 200:
                raise WebControlError(f"GET {path} failed with HTTP {response.status}")
            return await response.text()

    async def _post_page(self, path: str, data: dict[str, str]) -> str:
        async with self._session.post(f"{self._portal}{path}", data=data) as response:
            if response.status != 200:
                raise WebControlError(f"POST {path} failed with HTTP {response.status}")
            return await response.text()

    async def _mock_state(self, module_index: str, spec: ControlSpec) -> ControlState:
        path = MOCK_DIR / f"modal_{spec.code}.json"
        loop = asyncio.get_running_loop()
        try:
            raw = await loop.run_in_executor(None, path.read_text, "utf-8")
            html = json.loads(raw)["html"]
        except (OSError, ValueError, KeyError) as err:
            raise WebControlError(f"No usable mock dialog at {path}: {err}") from err

        state = parse_modal(spec.key, html)
        stored = self._mock_values.get(module_index, {}).get(spec.key)
        if stored is not None:
            state.value = stored
            state.fields = [
                (name, str(stored) if name == "tile_value" else val)
                for name, val in state.fields
            ]
        return state
