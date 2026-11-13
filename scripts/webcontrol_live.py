"""Drive the integration's web control client against the real portal.

    .venv/bin/python scripts/webcontrol_live.py read
    .venv/bin/python scripts/webcontrol_live.py set <control> <value>
    EPLUCON_MODULE_INDEX=<zone controller> .venv/bin/python scripts/webcontrol_live.py zones
    EPLUCON_MODULE_INDEX=<zone controller> .venv/bin/python scripts/webcontrol_live.py set zone_<id> <tenths>

Credentials come from prod.env (EPLUCON_EMAIL, EPLUCON_PASSWORD and, for 2FA
accounts, EPLUCON_TOTP_KEY). The heat pump is the first module index the
probe found (.live/*/module_indexes.json) unless EPLUCON_MODULE_INDEX is set.
`set` changes the real heat pump: it prints the value before and after.
`zones` reads the zone setpoints, in tenths of a degree; a zone is set the same
way, as `zone_<id>` (the API's zone id) and tenths (205 is 20.5 °C).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import aiohttp

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "custom_components"))

from eplucon.eplucon_api.web_control import CONTROLS, EpluconWebControl, is_zone_key  # noqa: E402

COOKIES = ROOT / ".live" / "client_cookies.json"


def load_env() -> None:
    env_file = ROOT / "prod.env"
    if env_file.is_file():
        for line in env_file.read_text().splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() and key.strip() not in os.environ:
                os.environ[key.strip()] = value.strip().strip('"').strip("'")


def module_index() -> str:
    if os.environ.get("EPLUCON_MODULE_INDEX"):
        return os.environ["EPLUCON_MODULE_INDEX"]
    found = sorted((ROOT / ".live").glob("2026*/module_indexes.json"))
    return json.loads(found[-1].read_text())[0]


def show(states) -> None:
    for key, state in states.items():
        extra = state.options or f"{state.min}..{state.max} step {state.step}"
        print(f"  {key:28} {state.value!r:8} {state.label!r:32} {extra}")


async def main(args: list[str]) -> None:
    load_env()
    cookies = json.loads(COOKIES.read_text()) if COOKIES.is_file() else None

    def save(new: dict[str, str]) -> None:
        COOKIES.write_text(json.dumps(new))
        print("session cookies saved:", sorted(new))

    async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar()) as session:
        client = EpluconWebControl(
            "https://portaal.eplucon.nl",
            os.environ["EPLUCON_EMAIL"],
            os.environ["EPLUCON_PASSWORD"],
            session,
            two_factor=os.environ.get("EPLUCON_TOTP_KEY"),
            cookies=cookies,
            on_cookies=save,
        )
        index = module_index()

        if args[0] == "read":
            show(await client.async_get_states(index))
        elif args[0] == "zones":
            show(await client.async_get_zone_states(index))
        elif args[0] == "set":
            key, raw = args[1], args[2]
            if key not in CONTROLS and not is_zone_key(key):
                raise SystemExit(f"unknown control {key}; known: {', '.join(CONTROLS)}")
            value = float(raw) if "." in raw else int(raw)
            before = await client.async_get_state(index, key)
            print(f"before: {key} = {before.value!r}")
            await client.async_set_value(index, key, value)
            print(f"sent:   {key} = {value!r}")
            elapsed = 0
            for wait in (5, 15, 30, 60):
                await asyncio.sleep(wait)
                elapsed += wait
                after = await client.async_get_state(index, key)
                print(f"after {elapsed:3d}s: {key} = {after.value!r}")
        save(client.session_cookies())


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.DEBUG if os.environ.get("DEBUG") else logging.INFO)
    asyncio.run(main(sys.argv[1:] or ["read"]))
