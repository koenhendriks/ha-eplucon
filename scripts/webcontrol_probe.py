"""Read-only probe of the Eplucon portal's web control pages.

Logs in with EPLUCON_EMAIL / EPLUCON_PASSWORD from prod.env (or the
environment), then saves what the portal answers to .live/<timestamp>/ so the
web control client can be built and tested against real responses. Nothing is
written to the heat pump: only GET requests follow the login.

    .venv/bin/python scripts/webcontrol_probe.py [stage] [otp]

Stages: login, pages, modals, remember. Default runs all of them in order.
`keepalive [interval_s] [hours]` reuses the saved session without logging in.
Accounts with 2-step authentication need the current 6-digit code as `otp`,
or EPLUCON_TOTP_KEY (the authenticator app's base32 key) in prod.env.
The cookie jar is saved to .live/cookies.pickle and reused by the next run,
so a code is only needed once per portal session.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import struct
import time
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

import aiohttp

ROOT = Path(__file__).resolve().parent.parent
PORTAL = os.environ.get("EPLUCON_PORTAL", "https://portaal.eplucon.nl")

# code, blockType (as EpluControl and the portal's own tiles use them)
CONTROL_CODES = {
    "indoor_temperature": ("5704", "module"),
    "boiler_temperature": ("5700", "module"),
    "boiler_temperature_delta": ("5804", "menu"),
    "warm_water_active": ("5711", "module"),
    "heatpump_active": ("5715", "module"),
    "heatpump_operation_mode": ("5712", "module"),
    "heating_active": ("5813", "menu"),
    "stop_heating_above": ("5814", "menu"),
    "heating_curve_correction": ("5886", "menu"),
    "cooling_active": ("5817", "menu"),
    "stop_passive_cooling_below": ("5901", "menu"),
    "stop_active_cooling_below": ("5818", "menu"),
}


def load_env() -> tuple[str, str]:
    env_file = ROOT / "prod.env"
    if env_file.is_file():
        for line in env_file.read_text().splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() and key.strip() not in os.environ:
                os.environ[key.strip()] = value.strip().strip('"').strip("'")
    return os.environ["EPLUCON_EMAIL"], os.environ["EPLUCON_PASSWORD"]


def totp(key: str, at: float | None = None) -> str:
    """RFC 6238 code (SHA-1, 6 digits, 30 s), as authenticator apps make them."""
    secret = base64.b32decode(key.replace(" ", "").upper() + "=" * (-len(key.replace(" ", "")) % 8))
    counter = int((time.time() if at is None else at) // 30)
    digest = hmac.new(secret, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return f"{code % 1_000_000:06d}"


def form_inputs(html: str) -> dict[str, str]:
    fields = {}
    for tag in re.findall(r"<input\b[^>]*>", html, re.S):
        name = re.search(r'name="([^"]*)"', tag)
        value = re.search(r'value="([^"]*)"', tag)
        if name:
            fields[name.group(1)] = value.group(1) if value else ""
    return fields


class Probe:
    def __init__(self, session: aiohttp.ClientSession, out: Path, secrets: list[str]):
        self.session = session
        self.out = out
        self.secrets = secrets
        self.n = 0

    def redact(self, text: str) -> str:
        for secret in self.secrets:
            if secret:
                text = text.replace(secret, "<redacted>")
        return text

    def save(self, name: str, response: aiohttp.ClientResponse, body: str) -> None:
        self.n += 1
        stem = f"{self.n:02d}_{name}"
        (self.out / f"{stem}.body").write_text(self.redact(body))
        meta = {
            "method": response.method,
            "url": str(response.url),
            "status": response.status,
            "history": [(r.status, str(r.url)) for r in response.history],
            "content_type": response.headers.get("Content-Type"),
            "location": response.headers.get("Location"),
            "set_cookie_names": [
                c.split("=", 1)[0] for c in response.headers.getall("Set-Cookie", [])
            ],
            "length": len(body),
        }
        (self.out / f"{stem}.meta.json").write_text(json.dumps(meta, indent=2))
        print(f"{stem}: {meta['method']} {meta['url']} -> {meta['status']} "
              f"{meta['content_type']} {meta['length']}B history={meta['history']}")

    async def get(self, name: str, url: str, **kwargs) -> tuple[aiohttp.ClientResponse, str]:
        async with self.session.get(url, **kwargs) as response:
            body = await response.text()
        self.save(name, response, body)
        return response, body


def on_2fa_page(html: str) -> bool:
    return 'name="one_time_password"' in html


def logged_in(html: str) -> bool:
    return 'name="password"' not in html and not on_2fa_page(html)


async def login(probe: Probe, username: str, password: str, otp: str | None) -> bool:
    _, html = await probe.get("session_check", f"{PORTAL}/e-control")
    if logged_in(html):
        print("saved session still logged in")
        return True
    if on_2fa_page(html):
        return await second_factor(probe, html, otp)

    _, html = await probe.get("login_form", f"{PORTAL}/login")
    data = form_inputs(html)
    data.update(username=username, password=password, remember="1")
    async with probe.session.post(f"{PORTAL}/login", data=data) as response:
        body = await response.text()
    probe.save("login_post", response, body)
    print("cookies after login:", {c.key: c["expires"] for c in probe.session.cookie_jar})
    if on_2fa_page(body):
        return await second_factor(probe, body, otp)
    ok = logged_in(body)
    print("login", "OK" if ok else "FAILED (login form shown again)")
    return ok


async def second_factor(probe: Probe, html: str, otp: str | None) -> bool:
    if not otp and os.environ.get("EPLUCON_TOTP_KEY"):
        otp = totp(os.environ["EPLUCON_TOTP_KEY"])
        print("2FA code generated from EPLUCON_TOTP_KEY")
    if not otp:
        print("2FA page shown and no code given; pass the current code as the second argument")
        return False
    data = form_inputs(html)
    data["one_time_password"] = otp
    async with probe.session.post(f"{PORTAL}/2fa", data=data) as response:
        body = await response.text()
    probe.save("2fa_post", response, body)
    print("cookies after 2fa:", {c.key: c["expires"] for c in probe.session.cookie_jar})
    ok = logged_in(body)
    print("2fa", "OK" if ok else "FAILED")
    return ok


async def pages(probe: Probe) -> list[str]:
    indexes: set[str] = set()
    for name, path in (("e_control", "/e-control"), ("heatpump", "/e-control/heatpump"), ("zones", "/e-control/zones"), ("heatpump_service", "/e-control/heatpump/service")):
        _, body = await probe.get(name, f"{PORTAL}{path}")
        indexes.update(re.findall(r"account_module_index[=\"':\s]+([0-9a-f]{32})", body))
        indexes.update(re.findall(r'"([0-9a-f]{32})"', body))
    found = sorted(indexes)
    print("candidate module indexes:", len(found))
    return found


async def modals(probe: Probe, indexes: list[str]) -> None:
    xsrf = next((unquote(c.value) for c in probe.session.cookie_jar if c.key == "XSRF-TOKEN"), None)
    headers = {"X-Requested-With": "XMLHttpRequest"}
    if xsrf:
        headers["X-XSRF-TOKEN"] = xsrf
    for index in indexes:
        await probe.get(
            f"dashboard_{index[:6]}",
            f"{PORTAL}/e-control/ajax/dashboard",
            params={"account_module_index": index},
            headers=headers,
        )
        for key, (code, block_type) in CONTROL_CODES.items():
            await probe.get(
                f"modal_{key}_{index[:6]}",
                f"{PORTAL}/e-control/ajax/modal/{code}",
                params={"blockType": block_type, "account_module_index": index},
                headers=headers,
            )


async def remember(out: Path, secrets: list[str], jar: aiohttp.CookieJar, indexes: list[str]) -> None:
    """Fresh session carrying only the remember cookie: is it still logged in?"""
    remember_cookies = [c for c in jar if c.key.startswith("remember_")]
    if not remember_cookies:
        print("no remember cookie was set")
        return
    fresh = aiohttp.CookieJar()
    for c in remember_cookies:
        fresh.update_cookies({c.key: c.value}, aiohttp.client.URL(PORTAL))
    async with aiohttp.ClientSession(cookie_jar=fresh) as session:
        probe = Probe(session, out, secrets)
        probe.n = 90
        _, body = await probe.get("remember_only_e_control", f"{PORTAL}/e-control")
        state = "logged in" if logged_in(body) else "2FA page" if on_2fa_page(body) else "login page"
        print("fresh session with only the remember cookie:", state)


async def main(stage: str | None, otp: str | None) -> None:
    username, password = load_env()
    out = ROOT / ".live" / datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True)
    print("saving to", out)
    secrets = [username, password]

    jar = aiohttp.CookieJar()
    jar_file = ROOT / ".live" / "cookies.pickle"
    if jar_file.is_file():
        jar.load(jar_file)
    async with aiohttp.ClientSession(cookie_jar=jar) as session:
        probe = Probe(session, out, secrets)
        ok = await login(probe, username, password, otp)
        jar.save(jar_file)
        if not ok:
            return
        if stage == "login":
            return
        indexes = await pages(probe)
        (out / "module_indexes.json").write_text(json.dumps(indexes))
        if stage == "pages":
            return
        if stage in (None, "modals"):
            await modals(probe, indexes)
        jar.save(jar_file)
    if stage in (None, "remember"):
        await remember(out, secrets, jar, indexes)




async def keepalive(interval: int, hours: float) -> None:
    """Reuse the saved session every `interval` s without ever logging in.

    Shows how long a 2FA-verified session survives on polling alone, which is
    what an integration without the TOTP key would depend on. Stops at the
    first request that lands on the login or 2FA page.
    """
    username, password = load_env()
    # A session of its own, logged in once here, so other probe runs can't
    # keep it alive on its behalf.
    jar = aiohttp.CookieJar()
    jar_file = ROOT / ".live" / "keepalive.pickle"
    log = ROOT / ".live" / "keepalive.log"
    out = ROOT / ".live" / f"keepalive-{datetime.now():%Y%m%d-%H%M%S}"
    out.mkdir(parents=True)
    start = time.time()
    async with aiohttp.ClientSession(cookie_jar=jar) as session:
        if not await login(Probe(session, out, [username, password]), username, password, None):
            return
        with log.open("a") as fh:
            fh.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} new session, polling every {interval}s\n")
        while time.time() - start < hours * 3600:
            async with session.get(f"{PORTAL}/e-control/heatpump") as response:
                body = await response.text()
            state = "logged in" if logged_in(body) else "2FA page" if on_2fa_page(body) else "login page"
            line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {response.status} {state}"
            with log.open("a") as fh:
                fh.write(line + "\n")
            print(line, flush=True)
            jar.save(jar_file)
            if state != "logged in":
                return
            await asyncio.sleep(interval)


if __name__ == "__main__":
    args = sys.argv[1:] + [None, None, None]
    if args[0] == "keepalive":
        asyncio.run(keepalive(int(args[1] or 300), float(args[2] or 12)))
    else:
        stage = None if args[0] in (None, "all") else args[0]
        asyncio.run(main(stage, args[1]))
