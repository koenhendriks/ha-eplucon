"""Tests for how the client reports portal error responses.

The portal answers a failed module request with ``auth: true``, a
``message`` and a non-200 ``error_code`` but no ``data``, for example::

    {"auth": true, "message": "Invalid account", "error_code": 400}

These must surface as an ApiError carrying that message, never as a bare
KeyError from indexing the missing ``data`` member.
"""

import json

import pytest

from custom_components.eplucon.eplucon_api.eplucon_client import (
    MOCK_DIR,
    ApiAuthError,
    ApiError,
    EpluconApi,
)

from .test_zones import FakeResponse, FakeSession

MODULE_ID = 1003151

INVALID_ACCOUNT = {"auth": True, "message": "Invalid account", "error_code": 400}

# The bundled mock fixture is a complete, known-good portal response.
REALTIME_OK = json.loads((MOCK_DIR / "get_realtime_info.json").read_text("utf-8"))

HEATLOADING_OK = {
    "auth": True,
    "data": {
        "heatloading_active": False,
        "configurations": {"domestic_hot_water": False},
    },
    "error_code": 200,
}

DEVICES_OK = {
    "auth": True,
    "data": [
        {
            "id": MODULE_ID,
            "account_module_index": "3ed585a0a0d045e0aa2759296fc13e07",
            "name": "Warmtepomp",
            "type": "heat_pump",
        }
    ],
    "error_code": 200,
}


def client(*responses):
    return EpluconApi("token", "http://api.test", FakeSession(*responses))


# ----------------------------
# The reported failure
# ----------------------------

async def test_realtime_info_invalid_account_is_an_api_error():
    api = client(FakeResponse(status=400, payload=INVALID_ACCOUNT))

    with pytest.raises(ApiError) as excinfo:
        await api.get_realtime_info(MODULE_ID)

    assert "Invalid account" in str(excinfo.value)
    assert str(MODULE_ID) in str(excinfo.value)


async def test_realtime_info_error_in_body_only():
    """The error_code is checked even when the HTTP status says 200."""
    with pytest.raises(ApiError) as excinfo:
        await client(FakeResponse(payload=INVALID_ACCOUNT)).get_realtime_info(MODULE_ID)

    assert "Invalid account" in str(excinfo.value)


async def test_heatloading_status_invalid_account_is_an_api_error():
    with pytest.raises(ApiError) as excinfo:
        await client(FakeResponse(status=400, payload=INVALID_ACCOUNT)).get_heatpump_heatloading_status(MODULE_ID)

    assert "Invalid account" in str(excinfo.value)


async def test_devices_error_response_does_not_pass_as_an_empty_list():
    with pytest.raises(ApiError) as excinfo:
        await client(FakeResponse(status=400, payload=INVALID_ACCOUNT)).get_devices()

    assert "Invalid account" in str(excinfo.value)


# ----------------------------
# Other malformed envelopes
# ----------------------------

@pytest.mark.parametrize(
    "payload",
    [
        {"auth": True, "error_code": 200},
        {"auth": True, "data": None, "error_code": 200},
        {"auth": True, "data": {}, "error_code": 200},
        {"auth": True, "data": {"common": None}, "error_code": 200},
    ],
)
async def test_realtime_info_without_common_is_an_api_error(payload):
    with pytest.raises(ApiError):
        await client(FakeResponse(payload=payload)).get_realtime_info(MODULE_ID)


@pytest.mark.parametrize("payload", [{"auth": True}, {"auth": True, "data": None}])
async def test_heatloading_status_without_data_is_an_api_error(payload):
    with pytest.raises(ApiError):
        await client(FakeResponse(payload=payload)).get_heatpump_heatloading_status(MODULE_ID)


@pytest.mark.parametrize("payload", [{"auth": True}, {"auth": True, "data": {}}])
async def test_devices_without_a_list_is_an_api_error(payload):
    with pytest.raises(ApiError):
        await client(FakeResponse(payload=payload)).get_devices()


@pytest.mark.parametrize("status", [500, 502, 404])
async def test_realtime_info_raises_on_server_error(status):
    with pytest.raises(ApiError):
        await client(FakeResponse(status=status, payload={"message": "boom"})).get_realtime_info(MODULE_ID)


@pytest.mark.parametrize("status", [401, 403])
async def test_realtime_info_raises_auth_error_on_unauthorized(status):
    with pytest.raises(ApiAuthError):
        await client(FakeResponse(status=status, payload=None)).get_realtime_info(MODULE_ID)


async def test_realtime_info_raises_auth_error_on_auth_false():
    with pytest.raises(ApiAuthError):
        await client(FakeResponse(payload={"auth": False})).get_realtime_info(MODULE_ID)


async def test_realtime_info_raises_on_non_json_body():
    with pytest.raises(ApiError):
        await client(FakeResponse(payload=None)).get_realtime_info(MODULE_ID)


# ----------------------------
# Successful responses still parse
# ----------------------------

async def test_realtime_info_parses_a_good_response():
    info = await client(FakeResponse(payload=REALTIME_OK)).get_realtime_info(MODULE_ID)

    assert info.common.indoor_temperature == REALTIME_OK["data"]["common"]["indoor_temperature"]
    assert info.heatpump == REALTIME_OK["data"]["heatpump"]


async def test_realtime_info_tolerates_a_missing_error_code():
    payload = {k: v for k, v in REALTIME_OK.items() if k != "error_code"}

    info = await client(FakeResponse(payload=payload)).get_realtime_info(MODULE_ID)

    assert info.common.indoor_temperature == REALTIME_OK["data"]["common"]["indoor_temperature"]


async def test_heatloading_status_parses_a_good_response():
    status = await client(FakeResponse(payload=HEATLOADING_OK)).get_heatpump_heatloading_status(MODULE_ID)

    assert status.heatloading_active is False


async def test_devices_parse_a_good_response():
    devices = await client(FakeResponse(payload=DEVICES_OK)).get_devices()

    assert [d.id for d in devices] == [MODULE_ID]
