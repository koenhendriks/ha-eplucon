"""Tests for the zones endpoint parsing and error handling."""

import json

import aiohttp
import pytest

from custom_components.eplucon.eplucon_api.eplucon_client import (
    ApiAuthError,
    ApiError,
    EpluconApi,
)

# Trimmed from the sample in docs/zones-api.md; keeps every field the client
# actually reads.
RAW_DATA = {
    "zone": {
        "id": 9010,
        "currentTemperature": 215,
        "setTemperature": 205,
        "flags": {"relayState": "on", "algorithm": "cooling"},
        "zoneState": "noAlarm",
        "signalStrength": 73,
        "batteryLevel": 92,
        "actuatorsOpen": 0,
        "humidity": 69,
    },
    "description": {"name": "Woonkamer"},
}

ZONE_ITEM = {
    "id": 3073,
    "name": "Woonkamer",
    "set_temperature": 20.6,
    "mode": "constantTemp",
    "current_temperature": 21.5,
    "raw_data": json.dumps(RAW_DATA),
}


def zone_item(**overrides):
    """A copy of the documented zone entry with fields replaced."""
    return {**ZONE_ITEM, **overrides}


# ----------------------------
# _parse_zone
# ----------------------------

def test_parse_zone_documented_payload():
    zone = EpluconApi._parse_zone(ZONE_ITEM)

    assert zone.id == 3073
    assert zone.name == "Woonkamer"
    assert zone.mode == "constantTemp"
    assert zone.set_temperature == 20.6
    assert zone.current_temperature == 21.5
    assert zone.humidity == 69
    assert zone.battery_level == 92
    assert zone.signal_strength == 73
    assert zone.actuators_open == 0
    assert zone.zone_state == "noAlarm"
    assert zone.relay_state == "on"
    assert zone.algorithm == "cooling"


@pytest.mark.parametrize(
    "raw_data",
    [
        json.dumps({"zone": None}),
        json.dumps({"zone": {"flags": None}}),
        json.dumps({"zone": [1, 2]}),
        json.dumps({"zone": {"flags": "on"}}),
        json.dumps({"other": 1}),
        json.dumps("a bare string"),
        "not json at all",
        None,
        "",
    ],
    ids=[
        "zone-null",
        "flags-null",
        "zone-not-an-object",
        "flags-not-an-object",
        "no-zone-key",
        "not-an-object",
        "unparseable",
        "absent",
        "empty",
    ],
)
def test_parse_zone_keeps_top_level_fields_when_raw_data_is_unusable(raw_data):
    """Unusable raw_data must not cost us the fields that did parse."""
    zone = EpluconApi._parse_zone(zone_item(raw_data=raw_data))

    assert zone.id == 3073
    assert zone.name == "Woonkamer"
    assert zone.current_temperature == 21.5
    assert zone.set_temperature == 20.6
    # Enrichment simply stays empty.
    assert zone.humidity is None
    assert zone.relay_state is None
    assert zone.algorithm is None


def test_parse_zone_partial_raw_data():
    """A zone record missing flags still yields the fields it does have."""
    zone = EpluconApi._parse_zone(
        zone_item(raw_data=json.dumps({"zone": {"humidity": 55}}))
    )

    assert zone.humidity == 55
    assert zone.relay_state is None


@pytest.mark.parametrize(
    "item",
    [{"name": "Woonkamer"}, {"id": None}, {"id": "not-a-number"}, "a string"],
    ids=["no-id", "null-id", "non-numeric-id", "not-an-object"],
)
def test_parse_zone_rejects_unidentifiable_entry(item):
    with pytest.raises(ValueError):
        EpluconApi._parse_zone(item)


def test_parse_zone_accepts_string_id():
    assert EpluconApi._parse_zone({"id": "3073", "name": "X"}).id == 3073


# ----------------------------
# get_zones
# ----------------------------

class FakeResponse:
    """Minimal stand-in for an aiohttp response used as an async context manager."""

    def __init__(self, status=200, payload=None, json_error=None):
        self.status = status
        self._payload = payload
        self._json_error = json_error

    async def json(self, content_type=None):
        if self._json_error is not None:
            raise self._json_error
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


class FakeSession:
    def __init__(self, *responses):
        self._responses = list(responses)
        self.calls = 0

    def get(self, url, headers=None):
        self.calls += 1
        # Repeat the last response once the scripted ones run out.
        index = min(self.calls - 1, len(self._responses) - 1)
        return self._responses[index]


def client(*responses):
    return EpluconApi("token", "http://api.test", FakeSession(*responses))


def ok(data, error_code=200):
    return FakeResponse(payload={"auth": True, "data": data, "error_code": error_code})


async def test_get_zones_parses_documented_response():
    zones = await client(ok([ZONE_ITEM])).get_zones(1)

    assert [z.name for z in zones] == ["Woonkamer"]


async def test_get_zones_skips_bad_entry_but_keeps_the_rest():
    """One unusable entry must not take the whole zone list with it."""
    zones = await client(ok([{"name": "no id here"}, ZONE_ITEM])).get_zones(1)

    assert [z.id for z in zones] == [3073]


async def test_get_zones_returns_empty_on_406():
    """406 means the module has no zones; not an error worth failing over."""
    api = client(FakeResponse(status=406, payload={"message": "Account is not a zone-controller"}))

    assert await api.get_zones(1) == []


async def test_get_zones_406_warns_only_once(caplog):
    api = client(FakeResponse(status=406, payload={"message": "Account is not a zone-controller"}))

    for _ in range(3):
        assert await api.get_zones(1) == []

    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1
    assert "does not expose zones" in warnings[0].message


async def test_get_zones_406_in_body_only():
    """Some portal errors carry the code in error_code rather than the status."""
    api = client(FakeResponse(payload={"auth": True, "error_code": 406, "message": "nope"}))

    assert await api.get_zones(1) == []


async def test_get_zones_warns_once_per_module():
    api = client(FakeResponse(status=406, payload={"message": "nope"}))

    await api.get_zones(1)
    await api.get_zones(2)

    assert api._not_a_zone_controller == {1, 2}


@pytest.mark.parametrize("status", [500, 502, 404])
async def test_get_zones_raises_on_server_error(status):
    with pytest.raises(ApiError):
        await client(FakeResponse(status=status, payload={"message": "boom"})).get_zones(1)


@pytest.mark.parametrize("status", [401, 403])
async def test_get_zones_raises_auth_error_on_unauthorized(status):
    with pytest.raises(ApiAuthError):
        await client(FakeResponse(status=status, payload=None)).get_zones(1)


async def test_get_zones_raises_on_auth_false():
    with pytest.raises(ApiAuthError):
        await client(FakeResponse(payload={"auth": False, "data": []})).get_zones(1)


async def test_get_zones_raises_on_error_code_mismatch():
    with pytest.raises(ApiError):
        await client(ok([], error_code=500)).get_zones(1)


@pytest.mark.parametrize("payload", [{"auth": True}, {"auth": True, "data": None}, {"auth": True, "data": {}}])
async def test_get_zones_raises_when_data_is_not_a_list(payload):
    with pytest.raises(ApiError):
        await client(FakeResponse(payload=payload)).get_zones(1)


async def test_get_zones_raises_on_non_json_body():
    """An HTML error page served with HTTP 200 must not pass silently."""
    api = client(
        FakeResponse(
            json_error=aiohttp.ContentTypeError(None, None, message="not json")
        )
    )

    with pytest.raises(ApiError):
        await api.get_zones(1)


async def test_get_zones_tolerates_string_error_code():
    zones = await client(ok([ZONE_ITEM], error_code="200")).get_zones(1)

    assert len(zones) == 1
