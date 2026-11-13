# Eplucon heat pump web control

How the Eplucon portal website (`https://portaal.eplucon.nl`) changes heat pump
settings, and how `eplucon_api/web_control.py` replays it. The official API
(`/api/v2`) is read-only, so this is the only way to control the heat pump.

Everything below was observed on the live portal on 2026-11-12 with
`scripts/webcontrol_probe.py` (read-only) and `scripts/webcontrol_live.py`,
on an account with one ecoGEO heat pump and 2-step authentication enabled. The
starting point was [pdevick/EpluControl](https://github.com/pdevick/EpluControl).

## Login

1. `GET /login`: a form with a hidden `_token` (CSRF), `username`, `password`
   and a `remember` checkbox (value `1`). Sets `XSRF-TOKEN` and
   `portaal_eplucon_session`, both with a 2 hour lifetime.
2. `POST /login` with those fields: 302 to `/e-control`. With `remember=1` it
   also sets `remember_web_<hash>`, valid for a year. A wrong password shows
   the login form again.
3. Accounts with 2-step authentication now get the 2FA page on every page:
   a form posting `_token` and `one_time_password` to `/2fa`. A correct code
   redirects to `/e-control`; a wrong one shows the 2FA form again.

The remember cookie only skips the password, not the 2FA code: a new session
that carries only `remember_web_*` lands on the 2FA page. So once logged in,
the client keeps the session cookie alive by polling and saves the session
cookies to `.storage/eplucon.web_session`, so a restart within the 2 hour
lifetime can reuse them. If the session is lost, the client logs in again on
its own when it has the authenticator key. With only a one-time code it can't:
the integration raises a repair issue asking for a new code.

## Telling a lost session apart

| Situation | `GET /e-control/ajax/modal/..` with `X-Requested-With: XMLHttpRequest` |
|---|---|
| Logged in | 200 `{"id": "<code>", "html": "<div class=\"modal ...\"> ..."}` |
| No session | 401 `{"message": "Unauthenticated."}` |
| Session waiting for its 2FA code | 200 `{"message": ["Er is een onbekende foutmelding opgetreden"]}` |
| Module index not on this login (another account's, or made up) | 200 `text/html` with an empty body |

The client treats a 401, 419, or a JSON body without `html` as "log in again"
and retries once. An empty body means the session is fine but the login can't
see that heat pump: it is reported as such, and the other heat pumps keep
their controls. `GET /e-control` then shows which step is missing: the
login form, the 2FA form, or the dashboard.

## Reading a setting

`GET /e-control/ajax/modal/{code}?blockType={blockType}&account_module_index={index}`

`account_module_index` is the same value the API returns for the module. The
response's `html` is the settings dialog the website shows when a tile is
clicked:

```html
<form data-type="2" data-id="5704" action="#" method="post"
      data-action="https://portaal.eplucon.nl/e-control/ajax/send_control_data?account_module_index=...">
  <input type="hidden" name="_token" value="...">
  <input type="hidden" name="format" value="2"/>
  <input type="hidden" name="type" value="2"/>
  <input type="hidden" name="label" value="Kamer ingestelde temp."/>
  <input type="hidden" name="menutype" value="MU"/>
  <input type="hidden" name="blockType" value="module"/>
  ...
  <input id="range-5704-item" value="22.4" step="0.1" min="10" max="30" type="range" name="tile_value">
  ...
  <input type="hidden" name="ido" value="5704"/>
</form>
```

`type` says how the value is asked for: `1` whole number and `2` one decimal
(both a range input with `min`, `max` and `step`); `10` on/off and `11` a
choice (radio inputs named `tile_value`, the current one `checked`, the label
text after each input). The current value, the bounds and the options all
come from the dialog, so nothing in the client hard-codes them.

The hidden `blockType` just echoes the request; values are the same either
way. The client asks with the block type the website's own tiles use.

## Changing a setting

The website's `saveTileData` posts the dialog's form as `multipart/form-data`
to its `data-action`:

- every field of the form, in document order, with `tile_value` set to the new
  value (`21.5` for type 2, `55` for type 1, `0`/`1`, or the option value);
- `dataSerialize`: the same fields URL-encoded;
- `data`: the same fields as a JSON list of `{"name": ..., "value": ...}`.

The portal answers HTTP 200 with the body `1`. The dialog shows the new value
within 5-20 s (observed on two real writes). The client fetches the dialog
fresh before every write: it carries the CSRF token, and the value is checked
against its bounds and options before anything is sent.

## Settings

| Key | Code | Block type | Type | Portal label | Values (as observed) |
|---|---|---|---|---|---|
| `indoor_temperature` | 5704 | module | 2 | Kamer ingestelde temp. | 10-30 °C, step 0.1 |
| `boiler_temperature` | 5700 | module | 1 | Ingestelde temp. WW | 0-65 °C, step 1 |
| `warm_water_active` | 5711 | module | 10 | WW | 1 on, 0 off |
| `heatpump_active` | 5715 | module | 11 | Warmtepomp | 0 Uit, 1 Ingeschakeld, 2 Noodbedrijf, 3 APX |
| `heatpump_operation_mode` | 5712 | module | 11 | Operatie modus | 1 Koeling, 2 Verwarming, 3 Auto th-TOUCH, 4 Auto Wp, 5 Haard |
| `boiler_temperature_delta` | 5804 | menu | 2 | DT setpoint | -99.9-99.9, step 0.1 |
| `heating_active` | 5813 | menu | 10 | Verwarming | 1 on, 0 off |
| `stop_heating_above` | 5814 | menu | 2 | Stop verwarmen | -99.9-99.9 °C, step 0.1 |
| `heating_curve_correction` | 5886 | menu | 11 | Correction heatcurve DG1 | 0 -4 °C, 1 -2 °C, 2 0 °C, 3 +2 °C, 4 +4 °C |
| `cooling_active` | 5817 | menu | 10 | Koeling | 1 on, 0 off |
| `stop_passive_cooling_below` | 5901 | menu | 2 | Stop passief koeling onder | 0-35 °C, step 0.1 |
| `stop_active_cooling_below` | 5818 | menu | 2 | Stop actief koeling onder | 0-35 °C, step 0.1 |

The five `module` settings are tiles on the heat pump dashboard
(`/e-control/heatpump`, loaded from `GET /e-control/ajax/dashboard`); the
`menu` ones sit in its service menu (`/e-control/heatpump/service`).
EpluControl used `menu` for 5700 and 5715; the dashboard tiles say `module`.

## Zones

A zone controller's zones each have a target temperature, set on the zones
page rather than in a settings dialog:
`GET /e-control/zones?account_module_index={zone controller}` (a full page, not
an XHR) holds a `constantTemp` form per zone, posting to
`/e-control/set_constant_temp`. The form's `data-id` is the zone id the API
reports, and its `constant_temp` range input has the setpoint in tenths of a
degree (`min=50 max=350 step=1`). The website saves it with the same
`saveTileData` as the dialogs above, so the client posts it the same way, with
`constant_temp` in place of `tile_value`. A lost session redirects the page to
`/login` (or shows the 2FA form) and is handled like a lost session on the
dialogs. Details, including the ids and the other answers of the page, are in
[zones-api.md](zones-api.md).

The dialogs under `custom_components/eplucon/eplucon_api/mock/webcontrol/` are
the real ones, with the module index replaced by the mock heat pump's and the
CSRF token by `mock-csrf-token`. `zones.html` holds the real zone forms with
the mock zones' ids. Mock mode serves them and keeps written values in memory.
