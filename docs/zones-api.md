# Eplucon zones / control-panel API

Notes on how the Eplucon portal (`https://portaal.eplucon.nl`) exposes
"regulation zones" and their per-zone control panels (th-TOUCH /
`zones_system_controller`), and how their target temperature is changed.

Everything below was verified against a live production deployment on
2026-07-13, and the write path again on 2026-11-13 (section 4). Where a
statement is inferred rather than directly observed, it is marked as such.

## Summary

There are two distinct surfaces with different auth models:

| Purpose | Surface | Auth | State |
|---|---|---|---|
| **Read** zones (temperature, humidity, battery, …) | public API `/api/v2` | Bearer API token | documented in OpenAPI, stable |
| **Write** zone target temperature | portal web route `/e-control/*` | web session cookie + CSRF | **undocumented**, used by the portal UI itself |

The public documented API is **read-only** for zones. There is no `/api/v2`
endpoint to set a zone's temperature — the portal front-end performs that write
against a session-authenticated web route, not the token API. An HA integration
that wants to actuate setpoints therefore needs the portal **username/password**
in addition to the API token. (Posting the write with a Bearer token
and no session returns `419 CSRF token mismatch`.)

---

## 1. Module discovery (public API)

`GET /api/v2/econtrol/modules` — Bearer token.

```json
{
  "auth": true,
  "data": [
    { "id": 1003355, "account_module_index": "1605d52f…", "name": "warmtepomp", "type": "heat_pump" },
    { "id": 1003495, "account_module_index": "27b2a803…", "name": "Thtouch",    "type": "zones_system_controller" }
  ],
  "error_code": 200
}
```

A zone controller has `type == "zones_system_controller"`. (The portal CSS also
references a `zones_controller` type; only `zones_system_controller` was seen on
this deployment.) Note the two identifiers per module:

- `id` — integer module id, used in `/api/v2/econtrol/modules/{id}/…` read paths.
- `account_module_index` — opaque hex string, used as a query parameter on the
  `/e-control/*` **write** routes.

Both are needed for full zone support.

## 2. Reading zones (public API)

`GET /api/v2/econtrol/modules/{moduleId}/zones` — Bearer token.

Documented in the portal OpenAPI (`/docs/api.json`, operation `zones`).
For a non-zone module it returns `406` with
`message: "Account is not a zone-controller"`.

```json
{
  "auth": true,
  "data": [
    {
      "id": 3073,
      "name": "Woonkamer",
      "set_temperature": 20.6,
      "mode": "constantTemp",
      "current_temperature": 21.5,
      "raw_data": "{…escaped JSON…}"
    }
  ],
  "error_code": 200
}
```

Per-zone top-level fields:

| Field | Type | Notes |
|---|---|---|
| `id` | int | **Portal** zone id (e.g. `3073`). Stable per zone. Used in `/e-control/zones/store/{id}`. |
| `name` | string | Zone display name. |
| `set_temperature` | number | Target temperature in °C (already divided by 10). |
| `current_temperature` | number | Measured temperature in °C. |
| `mode` | string | e.g. `constantTemp` (constant setpoint) or a schedule mode. |
| `raw_data` | string | JSON-encoded string with the full th-TOUCH zone record (below). |

The OpenAPI schema types these as `string`; in practice numeric fields arrive as
JSON numbers. Treat them defensively (the existing client already coerces).

### `raw_data` structure

`raw_data` is a JSON **string** that must be parsed a second time. It carries the
richer sensor data that is not in the top-level fields. Example (one zone):

```jsonc
{
  "zone": {
    "id": 9010,                 // th-TOUCH internal zone id (NOT the portal id 3073)
    "parentId": 9002,
    "time": "2026-07-13T19:38:55",
    "duringChange": false,
    "index": 0,
    "currentTemperature": 215,  // ×10  → 21.5 °C
    "setTemperature": 205,      // ×10  → 20.5 °C
    "flags": {
      "relayState": "on",       // "on" | "off" — call-for-heat / actuator relay
      "minOneWindowOpen": false,
      "algorithm": "cooling",   // "heating" | "cooling" — current regulation direction
      "floorSensor": 0,
      "humidityAlgorytm": 0,
      "zoneExcluded": 0
    },
    "zoneState": "noAlarm",
    "signalStrength": 73,       // wireless link, 0–100 (%). Inferred unit.
    "batteryLevel": 92,         // %
    "actuatorsOpen": 0,
    "humidity": 69,             // % relative humidity
    "visibility": true
  },
  "description": { "id": 9011, "parentId": 9010, "name": "Woonkamer", "styleId": 0, "styleIcon": "living_room", "duringChange": false },
  "mode":        { "id": 9012, "parentId": 9010, "mode": "constantTemp", "constTempTime": 60, "setTemperature": 205, "scheduleIndex": 0 },
  "schedule":    { "id": 9014, "parentId": 9010, "index": -1, "p0Days": ["1","1","1","1","1","0","0"], "p0Intervals": [{"start":1020,"stop":1380,"temp":205}], "p0SetbackTemp": 195, "p1Days": […], "p1Intervals": […], "p1SetbackTemp": 195 },
  "actuators": [], "underfloor": {}, "windowsSensors": [], "additionalContacts": [], "color": "#a04515"
}
```

Fields worth surfacing as HA entities:

| Path in `raw_data` | Meaning | Unit |
|---|---|---|
| `zone.currentTemperature` / 10 | measured temperature | °C |
| `zone.setTemperature` / 10 | target temperature | °C |
| `zone.humidity` | relative humidity | % |
| `zone.batteryLevel` | control-panel battery | % |
| `zone.signalStrength` | wireless signal (unit inferred: %) | % |
| `zone.flags.relayState` | call-for-heat / relay | `on`/`off` |
| `zone.flags.algorithm` | regulation direction | `heating`/`cooling` |
| `zone.flags.minOneWindowOpen` | any window open | bool |
| `zone.actuatorsOpen` | open actuators count | int |
| `zone.zoneState` | alarm state | `noAlarm`/… |

**Temperature scaling:** the top-level `set_temperature`/`current_temperature`
are in °C; the `raw_data` `*Temperature` values and the write `constant_temp`
field are all **×10** (deci-degrees).

**ID mapping** (needed to write — confirmed identical across all 4 zones):

| Write field | Source |
|---|---|
| `zone_id`  | `raw_data.zone.id` |
| `parent_id`| `raw_data.mode.parentId` (equals `zone.id` on this deployment) |
| `mode_id`  | `raw_data.mode.id` |

The portal zone id (`data[].id`, e.g. `3073`) is **not** used by the constant-temp
write; it is only used by `/e-control/zones/store/{id}` (rename/icon config).

## 3. Setting a zone's target temperature (portal web route)

This is the endpoint the portal UI uses. It is **not** in the public OpenAPI.

```
POST /e-control/set_constant_temp?account_module_index={account_module_index}
```

**Auth / headers** (all required):

- `Cookie: portaal_eplucon_session=…; XSRF-TOKEN=…` — from a logged-in web session.
- `X-CSRF-TOKEN: {token}` — the CSRF token (from the `<meta name="csrf-token">`
  tag of any authenticated portal page, or the decrypted `XSRF-TOKEN` cookie).
- `X-Requested-With: XMLHttpRequest`

**Body** — `multipart/form-data` (also accepts standard form encoding):

| Field | Example | Meaning |
|---|---|---|
| `_token` | `QMIANr5B…` | CSRF token (same value as header). |
| `active_schedule` | `0` | `0` = constant temp mode (override schedule). |
| `mode` | `constantTemp` | Fixed for a setpoint override. |
| `mode_id` | `9012` | `raw_data.mode.id`. |
| `zone_id` | `9010` | `raw_data.zone.id`. |
| `parent_id` | `9010` | `raw_data.mode.parentId`. |
| `constant_temp` | `206` | **target °C × 10** (206 = 20.6 °C). |

The portal front-end additionally sends `dataSerialize` (url-encoded copy) and
`data` (JSON copy) of the same fields; these are redundant jQuery-serialize
artifacts and are not required — a POST with only the seven fields above
succeeds.

**Range:** the UI slider is `min=50 max=350 step=1`, i.e. **5.0 – 35.0 °C** in
0.1 °C steps.

**Response:** HTTP `200`, body `1` on success. `419` + `CSRF token mismatch`
if the session/CSRF is wrong.

### Web login (to obtain the session)

```
GET  /login          → parse <meta name="csrf-token"> and hidden form fields
POST /login          → form: _token, username, password, remember=1,
                       plus honeypot fields echoed from the GET form
                       (an empty name-honeypot input and a `valid_from` token)
```

On success the portal sets `portaal_eplucon_session` and `XSRF-TOKEN` cookies and
redirects to `/e-control`. The login page also carries anti-spam honeypot fields
(`my_name_*` left empty, and an encrypted `valid_from` value echoed back); a login
succeeded in testing even without echoing `valid_from`, but echoing both is
safest.

> Note: `POST /api/v2/auth/login` (documented) returns an `access_token` that, on
> this account, is **identical to the API token** and is a *token*, not a web
> session — it does not carry the CSRF/session cookies the `/e-control/*` write
> route requires.

### Where the form comes from (re-checked 2026-11-13)

`GET /e-control/zones?account_module_index={zone controller}` returns the full
zones page. Each zone has a dialog (`#zoneModalConstantTemperature{portalZoneId}`)
with two forms posting to `set_constant_temp`, both with `data-id` set to the
**portal** zone id (the API's `data[].id`):

| `mode` | Fields after `_token` | Meaning |
|---|---|---|
| `constantTemp` | `active_schedule=0`, `mode`, `mode_id`, `zone_id`, `parent_id`, `constant_temp` (range input, `min=50 max=350 step=1`, value = current setpoint ×10) | "Constante temperatuur": hold this setpoint |
| `timeLimit` | `active_schedule=0`, `mode`, `constant_temp` (hidden), `mode_id`, `zone_id`, `parent_id`, `hours`, `minutes` (ranges) | "Tijdelijke verhoging": temporary raise |

The ids in the forms are the same as those in the API's `raw_data` (table in
section 2), so the form is the single source for a write: it carries the CSRF
token, the ids and the bounds. The portal JavaScript submits both forms with
the same `saveTileData` function as the heat pump's settings dialogs (the form
fields as `multipart/form-data` plus the `dataSerialize` and `data` copies),
and the integration replays it the same way. A write of the current setpoint
answered HTTP 200 / `1` and left the setpoint and mode unchanged. A write of
20.6 °C (and back to 20.5 °C) through the integration's client showed in the
zones page form and in the API's `set_temperature` at the same time, within
7 s, and the zone stayed on `constantTemp`: the API does not lag the portal.

Other answers of the zones page:

| Request | Answer |
|---|---|
| No session | 302 to `/login` |
| Index of the heat pump (not a zone controller) | 200, a zones page without any zone form |
| Made-up index | HTTP 500 |
| No `account_module_index` | 200, the zones page of the account's first zone controller |

Schedules ("Programma's") are loaded separately from
`GET /e-control/zones/{portalZoneId}/ajax/programs` and were not investigated.

## 4. Other zone web routes seen (not needed for temperature control)

- `GET  /e-control/zones` — the HTML zones page (source of the forms above).
- `GET  /e-control/zones/ajax/refresh?account_module_index=…` — returns
  `{ html: … }` used to refresh the tile grid.
- `POST /e-control/zones/store/{portalZoneId}` — rename / icon / master config;
  fields include `name`, `icon`, `is_master`, `description_id`, `internal_zone_id`.

## 5. How the HA integration uses this

- **Reads** (all zone sensors, and the zone thermostat's readings and target)
  use the Bearer-token client: `get_zones(module_id)` and `raw_data`.
- **Writes** go through the optional web control login (see
  [`web-control.md`](web-control.md)): portal username + password (and 2FA),
  its own cookie jar and session handling. Each zone's setpoint is a web
  control keyed `zone_{portalZoneId}`, with its value in tenths of a degree as
  the form has it. The web control coordinator reads the zones page with the
  heat pump dialogs every 5 minutes, and a write fetches it fresh first, so the
  CSRF token and the bounds are current. Without the web login, zones stay
  read-only.
- The write is a cloud round-trip through the portal UI's own route; it may
  be more fragile than the documented API (CSRF token rotation, session
  expiry, login honeypot changes). If the zones page can't be read, the zone
  thermostats keep their API readings and refuse a new target.
- After a write, the integration refreshes the zones page and then the API
  about 20 s later. Until the portal reports the value sent, the thermostat
  shows that; after that, whichever source updated last.
