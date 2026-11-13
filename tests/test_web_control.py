"""Tests for the portal web control client, against a fake portal.

The fake answers like the real portal did when it was probed (see
docs/web-control.md): a login form, a 2FA form for accounts that have it,
401 for dialogs without a session, a JSON error while 2FA is pending, and the
real settings dialogs shipped as mock data.
"""

import json
import re
import secrets
from urllib.parse import parse_qsl

import aiohttp
import pytest
from aiohttp import web

from custom_components.eplucon.eplucon_api import web_control as wc
from custom_components.eplucon.eplucon_api.web_control import (
    CONTROLS,
    EpluconWebControl,
    WebControlAuthError,
    WebControlModuleUnknown,
    WebControlTwoFactorInvalid,
    WebControlError,
    WebControlTwoFactorRequired,
    is_totp_secret,
    parse_modal,
    parse_zone_forms,
    portal_url_from_api,
    totp,
    zone_key,
)

INDEX = "1aa111a1a1a111a1aa1111111aa11a11"
ZONES_INDEX = "2aa222a2a2a222a2aa2222222aa22a22"
# RFC 6238 test secret "12345678901234567890".
TOTP_KEY = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"

LOGIN_PAGE = """<form method="POST" action="/login">
<input type="hidden" name="_token" value="{token}" autocomplete="off">
<input type="text" name="username"><input type="password" name="password">
<input id="remember" type="checkbox" name="remember" value="1"></form>"""
TWO_FA_PAGE = """<form method="POST" action="/2fa">
<input type="hidden" name="_token" value="{token}" autocomplete="off">
<input id="one_time_password" type="text" name="one_time_password" required></form>"""
DASHBOARD = "<html><body>e-control</body></html>"


def mock_dialog(code: str) -> str:
    return json.loads((wc.MOCK_DIR / f"modal_{code}.json").read_text())["html"]


def mock_zones_page() -> str:
    return (wc.MOCK_DIR / "zones.html").read_text()


class FakePortal:
    def __init__(self, *, two_factor: bool = False) -> None:
        self.username = "user@example.com"
        self.password = "secret"
        self.two_factor = two_factor
        self.sessions: dict[str, str] = {}  # session id -> "2fa" | "ok"
        self.logins = 0
        self.codes: list[str] = []
        self.saves: list[dict] = []
        self.values: dict[str, str] = {}
        self.zone_saves: list[dict] = []
        self.zone_values: dict[str, str] = {}  # internal zone id -> constant_temp

    def app(self) -> web.Application:
        app = web.Application()
        app.router.add_get("/e-control", self.page)
        app.router.add_get("/login", self.login_form)
        app.router.add_post("/login", self.login)
        app.router.add_post("/2fa", self.second_factor)
        app.router.add_get("/e-control/ajax/modal/{code}", self.modal)
        app.router.add_post("/e-control/ajax/send_control_data", self.save)
        app.router.add_get("/e-control/zones", self.zones)
        app.router.add_post("/e-control/set_constant_temp", self.save_zone)
        return app

    def state(self, request) -> str | None:
        return self.sessions.get(request.cookies.get("portaal_eplucon_session", ""))

    def expire_sessions(self) -> None:
        self.sessions.clear()

    async def page(self, request):
        state = self.state(request)
        if state == "ok":
            return web.Response(text=DASHBOARD, content_type="text/html")
        if state == "2fa":
            return web.Response(text=TWO_FA_PAGE.format(token="t"), content_type="text/html")
        return web.Response(text=LOGIN_PAGE.format(token="t"), content_type="text/html")

    async def login_form(self, request):
        return web.Response(text=LOGIN_PAGE.format(token="t"), content_type="text/html")

    async def login(self, request):
        form = await request.post()
        if (form.get("username"), form.get("password")) != (self.username, self.password):
            return web.Response(text=LOGIN_PAGE.format(token="t"), content_type="text/html")
        self.logins += 1
        session = secrets.token_hex(8)
        self.sessions[session] = "2fa" if self.two_factor else "ok"
        response = web.Response(
            text=TWO_FA_PAGE.format(token="t") if self.two_factor else DASHBOARD,
            content_type="text/html",
        )
        response.set_cookie("portaal_eplucon_session", session)
        response.set_cookie("remember_web_abc", "remember")
        return response

    async def second_factor(self, request):
        form = await request.post()
        code = form.get("one_time_password")
        self.codes.append(code)
        session = request.cookies.get("portaal_eplucon_session", "")
        if self.sessions.get(session) != "2fa" or code not in (totp(TOTP_KEY), "654321"):
            return web.Response(text=TWO_FA_PAGE.format(token="t"), content_type="text/html")
        self.sessions[session] = "ok"
        return web.Response(text=DASHBOARD, content_type="text/html")

    async def modal(self, request):
        state = self.state(request)
        if state is None:
            return web.json_response({"message": "Unauthenticated."}, status=401)
        if state == "2fa":
            return web.json_response({"message": ["Er is een onbekende foutmelding opgetreden"]})
        if request.query.get("account_module_index") != INDEX:
            return web.Response(text="", content_type="text/html")
        code = request.match_info["code"]
        html = mock_dialog(code).replace(
            "https://portaal.eplucon.nl", str(request.url.origin())
        )
        if code in self.values:
            html = html.replace('value="60"', f'value="{self.values[code]}"')
        return web.json_response({"id": code, "html": html})

    async def save(self, request):
        if self.state(request) != "ok":
            return web.json_response({"message": "Unauthenticated."}, status=401)
        form = await request.post()
        self.saves.append({key: form.getall(key) for key in form})
        self.values[form["ido"]] = form["tile_value"]
        return web.Response(text="1")


    async def zones(self, request):
        # A full page: without a session the portal redirects to the login.
        state = self.state(request)
        if state is None:
            raise web.HTTPFound("/login")
        if state == "2fa":
            return web.Response(text=TWO_FA_PAGE.format(token="t"), content_type="text/html")
        index = request.query.get("account_module_index")
        if index == INDEX:
            # The heat pump: a zones page without any zone on it.
            return web.Response(text=DASHBOARD, content_type="text/html")
        if index != ZONES_INDEX:
            return web.Response(text="Server Error", status=500, content_type="text/html")
        html = mock_zones_page().replace("https://portaal.eplucon.nl", str(request.url.origin()))
        html = re.sub(r"<form\b.*?</form>", self._with_zone_value, html, flags=re.S)
        return web.Response(text=html, content_type="text/html")

    def _with_zone_value(self, form: re.Match) -> str:
        html = form.group(0)
        zone = re.search(r'name="zone_id" value="(\d+)"', html)
        if zone is None or zone.group(1) not in self.zone_values:
            return html
        value = self.zone_values[zone.group(1)]
        html = re.sub(r'(name="constant_temp" value=")\d+', rf"\g<1>{value}", html)
        return re.sub(r'value="\d+"( step="1")', rf'value="{value}"\1', html)

    async def save_zone(self, request):
        if self.state(request) != "ok":
            return web.json_response({"message": "Unauthenticated."}, status=401)
        form = await request.post()
        self.zone_saves.append({key: form.getall(key) for key in form})
        self.zone_values[form["zone_id"]] = form["constant_temp"]
        return web.Response(text="1")


@pytest.fixture
async def portal(aiohttp_server, socket_enabled):
    async def start(**kwargs):
        fake = FakePortal(**kwargs)
        server = await aiohttp_server(fake.app())
        fake.url = str(server.make_url("")).rstrip("/")
        return fake

    return start


@pytest.fixture
async def session():
    # unsafe: the fake portal runs on an IP address, whose cookies aiohttp
    # would otherwise drop.
    async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as s:
        yield s


def client_for(fake, session, **kwargs) -> EpluconWebControl:
    return EpluconWebControl(fake.url, fake.username, fake.password, session, **kwargs)


# --- parsing -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("key", "type_", "value", "bounds", "options"),
    [
        ("indoor_temperature", "2", 22.4, (10.0, 30.0, 0.1), {}),
        ("boiler_temperature", "1", 60, (0.0, 65.0, 1.0), {}),
        ("warm_water_active", "10", 1, (None, None, None), {1: "Inschakelen", 0: "Uitschakelen"}),
        (
            "heatpump_operation_mode",
            "11",
            2,
            (None, None, None),
            {1: "Koeling", 2: "Verwarming", 3: "Auto th-TOUCH", 4: "Auto Wp", 5: "Haard"},
        ),
        (
            "heating_curve_correction",
            "11",
            2,
            (None, None, None),
            {0: "-4°C", 1: "-2°C", 2: "0°C", 3: "+2°C", 4: "+4°C"},
        ),
    ],
)
def test_parse_real_dialogs(key, type_, value, bounds, options):
    state = parse_modal(key, mock_dialog(CONTROLS[key].code))

    assert state.type == type_
    assert state.value == value
    assert type(state.value) is type(value)
    assert (state.min, state.max, state.step) == bounds
    assert state.options == options
    assert state.action.endswith(f"send_control_data?account_module_index={INDEX}")
    assert [name for name, _ in state.fields] == [
        "_token", "format", "type", "label", "menutype", "blockType", "tile_value", "ido",
    ]


def test_every_shipped_dialog_parses():
    for key, spec in CONTROLS.items():
        assert parse_modal(key, mock_dialog(spec.code)).value is not None, key


@pytest.mark.parametrize(
    ("key", "value", "sent"),
    [
        ("indoor_temperature", 21, "21.0"),
        ("indoor_temperature", 21.25, "21.2"),
        ("boiler_temperature", 55.0, "55"),
        ("warm_water_active", 0, "0"),
        ("heatpump_operation_mode", 3, "3"),
    ],
)
def test_validate_formats_like_the_portal(key, value, sent):
    assert parse_modal(key, mock_dialog(CONTROLS[key].code)).validate(value) == sent


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("indoor_temperature", 9.9),
        ("indoor_temperature", 30.1),
        ("boiler_temperature", 55.5),
        ("warm_water_active", 2),
        ("heatpump_operation_mode", 0),
        ("heating_curve_correction", 1.5),
    ],
)
def test_validate_rejects_what_the_dialog_does_not_offer(key, value):
    with pytest.raises(ValueError):
        parse_modal(key, mock_dialog(CONTROLS[key].code)).validate(value)


def test_totp_matches_rfc_6238():
    assert totp(TOTP_KEY, at=59) == "287082"
    assert totp(TOTP_KEY.lower(), at=1111111109) == "081804"


def test_two_factor_field_tells_a_key_from_a_code():
    assert is_totp_secret(TOTP_KEY)
    assert is_totp_secret("gezd gnbv gy3t qojq")
    assert not is_totp_secret("123456")
    assert not is_totp_secret("")


def test_portal_url_follows_the_api_endpoint():
    assert portal_url_from_api("https://portaal.eplucon.nl/api/v2") == "https://portaal.eplucon.nl"
    assert portal_url_from_api("https://portaal.eplucon.be/api/v2/") == "https://portaal.eplucon.be"


# --- session handling ----------------------------------------------------------


async def test_reads_after_logging_in_with_the_password(portal, session):
    fake = await portal()
    saved = []
    client = client_for(fake, session, on_cookies=saved.append)

    state = await client.async_get_state(INDEX, "indoor_temperature")

    assert state.value == 22.4
    assert fake.logins == 1
    assert "remember_web_abc" in saved[-1]
    assert "portaal_eplucon_session" in saved[-1]


async def test_wrong_password_is_an_auth_error(portal, session):
    fake = await portal()
    client = EpluconWebControl(fake.url, fake.username, "wrong", session)

    with pytest.raises(WebControlAuthError):
        await client.async_login()


async def test_two_factor_with_a_key_logs_in_again_on_its_own(portal, session):
    fake = await portal(two_factor=True)
    client = client_for(fake, session, two_factor=TOTP_KEY)

    assert client.can_relogin
    await client.async_get_state(INDEX, "boiler_temperature")
    fake.expire_sessions()
    state = await client.async_get_state(INDEX, "boiler_temperature")

    assert state.value == 60
    assert fake.logins == 2


async def test_a_one_time_code_is_used_once(portal, session):
    fake = await portal(two_factor=True)
    client = client_for(fake, session, two_factor="654321")

    assert not client.can_relogin
    await client.async_login()
    assert fake.codes == ["654321"]

    fake.expire_sessions()
    with pytest.raises(WebControlTwoFactorRequired):
        await client.async_get_state(INDEX, "boiler_temperature")
    assert fake.codes == ["654321"]


async def test_a_rejected_code_is_reported(portal, session):
    fake = await portal(two_factor=True)
    client = client_for(fake, session, two_factor="000000")

    with pytest.raises(WebControlTwoFactorInvalid):
        await client.async_login()


async def test_two_factor_without_code_or_key(portal, session):
    fake = await portal(two_factor=True)

    with pytest.raises(WebControlTwoFactorRequired):
        await client_for(fake, session).async_login()


async def test_saved_cookies_skip_the_login(portal, session):
    fake = await portal(two_factor=True)
    first = client_for(fake, session, two_factor="654321")
    await first.async_login()
    cookies = first.session_cookies()

    async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as other:
        # The jar only takes cookies for the portal's own host.
        second = client_for(fake, other, cookies=cookies)
        state = await second.async_get_state(INDEX, "indoor_temperature")

    assert state.value == 22.4
    assert fake.logins == 1


async def test_a_module_the_login_cannot_see_is_reported_without_relogin(portal, session):
    fake = await portal(two_factor=True)
    client = client_for(fake, session, two_factor="654321")
    await client.async_login()

    with pytest.raises(WebControlModuleUnknown):
        await client.async_get_state("0" * 32, "indoor_temperature")
    assert fake.logins == 1
    assert (await client.async_get_state(INDEX, "indoor_temperature")).value == 22.4


# --- writing -------------------------------------------------------------------


async def test_set_value_posts_the_dialog_like_the_browser(portal, session):
    fake = await portal()
    client = client_for(fake, session)

    await client.async_set_value(INDEX, "boiler_temperature", 55)

    (save,) = fake.saves
    assert save["tile_value"] == ["55"]
    assert save["ido"] == ["5700"]
    assert save["format"] == ["1"] and save["type"] == ["1"]
    assert save["menutype"] == ["MU"] and save["blockType"] == ["module"]
    assert save["_token"] == ["mock-csrf-token"]
    assert {"name": "tile_value", "value": "55"} in json.loads(save["data"][0])
    assert ("tile_value", "55") in parse_qsl(save["dataSerialize"][0])
    assert (await client.async_get_state(INDEX, "boiler_temperature")).value == 55


async def test_out_of_range_value_is_never_sent(portal, session):
    fake = await portal()
    client = client_for(fake, session)

    with pytest.raises(ValueError):
        await client.async_set_value(INDEX, "boiler_temperature", 70)

    assert fake.saves == []


async def test_mock_mode_needs_no_portal():
    client = EpluconWebControl("https://portal.invalid", "u", "p", None, use_mock_data=True)

    await client.async_set_value(INDEX, "indoor_temperature", 19.5)

    assert (await client.async_get_state(INDEX, "indoor_temperature")).value == 19.5
    assert (await client.async_get_state("other", "indoor_temperature")).value == 22.4


# --- zones ---------------------------------------------------------------------


def test_parse_zone_forms_reads_the_constant_temperature_form():
    states = parse_zone_forms(mock_zones_page())

    assert sorted(states) == [zone_key(i) for i in (3221, 3222, 3223, 3224, 3225)]
    state = states[zone_key(3224)]
    assert state.value == 245
    assert (state.min, state.max, state.step) == (50, 350, 1)
    assert state.value_field == "constant_temp"
    # The ids the portal needs back, as the API's raw_data has them.
    assert dict(state.fields) == {
        "_token": "mock-csrf-token",
        "active_schedule": "0",
        "mode": "constantTemp",
        "mode_id": "531",
        "zone_id": "114",
        "parent_id": "114",
        "constant_temp": "245",
    }
    assert state.action.endswith(f"/e-control/set_constant_temp?account_module_index={ZONES_INDEX}")


def test_a_zone_setpoint_must_be_in_the_form_range():
    state = parse_zone_forms(mock_zones_page())[zone_key(3221)]

    assert state.validate(206) == "206"
    for value in (49, 351, 205.5):
        with pytest.raises(ValueError):
            state.validate(value)


async def test_zone_setpoint_posts_the_form_like_the_browser(portal, session):
    fake = await portal()
    client = client_for(fake, session)

    await client.async_set_value(ZONES_INDEX, zone_key(3222), 215)

    (save,) = fake.zone_saves
    assert save["constant_temp"] == ["215"]
    assert save["mode"] == ["constantTemp"] and save["active_schedule"] == ["0"]
    assert (save["zone_id"], save["parent_id"], save["mode_id"]) == (["111"], ["111"], ["501"])
    assert save["_token"] == ["mock-csrf-token"]
    assert {"name": "constant_temp", "value": "215"} in json.loads(save["data"][0])
    assert ("constant_temp", "215") in parse_qsl(save["dataSerialize"][0])
    # Only the zone that was written changes.
    states = await client.async_get_zone_states(ZONES_INDEX)
    assert states[zone_key(3222)].value == 215
    assert states[zone_key(3221)].value == 240
    assert fake.saves == []


async def test_zones_page_logs_in_again_when_the_session_is_gone(portal, session):
    fake = await portal(two_factor=True)
    client = client_for(fake, session, two_factor=TOTP_KEY)
    await client.async_login()
    fake.expire_sessions()

    states = await client.async_get_zone_states(ZONES_INDEX)

    assert states[zone_key(3221)].value == 240
    assert fake.logins == 2


async def test_zones_of_a_module_without_zones_are_reported(portal, session):
    fake = await portal()
    client = client_for(fake, session)

    with pytest.raises(WebControlModuleUnknown):
        await client.async_get_zone_states(INDEX)
    with pytest.raises(WebControlError, match="HTTP 500"):
        await client.async_get_zone_states("0" * 32)
    with pytest.raises(WebControlError, match="no setpoint"):
        await client.async_set_value(ZONES_INDEX, zone_key(9999), 200)
    assert fake.logins == 1 and fake.zone_saves == []


async def test_zone_setpoint_out_of_range_is_never_sent(portal, session):
    fake = await portal()
    client = client_for(fake, session)

    with pytest.raises(ValueError):
        await client.async_set_value(ZONES_INDEX, zone_key(3221), 400)

    assert fake.zone_saves == []


async def test_mock_mode_keeps_zone_setpoints():
    client = EpluconWebControl("https://portal.invalid", "u", "p", None, use_mock_data=True)

    await client.async_set_value(ZONES_INDEX, zone_key(3223), 190)

    states = await client.async_get_zone_states(ZONES_INDEX)
    assert states[zone_key(3223)].value == 190
    assert dict(states[zone_key(3223)].fields)["constant_temp"] == "190"
