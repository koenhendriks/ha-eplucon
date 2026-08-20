# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
* A **Use mock data** switch under **Developer tools** in the setup and options dialog. With it on, all data comes from the JSON fixtures in `custom_components/eplucon/eplucon_api/mock/` — a mock heat pump and a mock zone controller with five zones — so the integration can be run and developed without a real installation or an API token. No request is sent and the API endpoint is left untouched. Fixtures are re-read on every refresh, can be overridden per module (`get_zones.1007331.json`), and can mock an error response with an `http_status` key. See the "Mock data" section in the README.

### Changed
* All API requests now go through one request helper. A response whose content type isn't JSON is reported as an API error, the same as an unparseable body, instead of raising an aiohttp `ContentTypeError` past the config flow's error handling.

### Removed
* `eplucon_api/eplucon_client_mock.py`, a copy of the client that had drifted behind the real one and could only be used by editing an import. The **Use mock data** switch replaces it.

### Fixed
* A custom API endpoint was reset to the default the next time the integration options were saved. Saving the options wrote back only the API token and the device list, so every other field in the config entry was dropped; the options step now keeps them. Reported by a user running a custom endpoint.   

Thanks for reporting, Markus!

* Config entries pointing at `https://mock.test`, the short-lived way of selecting mock data, are migrated at startup to the default endpoint with the **Use mock data** switch turned on, instead of failing to resolve that host.

## [1.6.0](https://github.com/koenhendriks/ha-eplucon/releases/1.6.0) - 2026-08-12

Big thanks to [@knz](https://github.com/knz) for this release.

### Added
* ([#36](https://github.com/koenhendriks/ha-eplucon/pull/36)) Support for `zones_system_controller` modules (th-TOUCH). Each regulation zone / control panel is exposed as its own Home Assistant device with read-only sensors: current temperature, target temperature, humidity, battery, signal strength, mode and regulation direction, plus a "Call for Heat" binary sensor. Zone entities are named after their zone (`sensor.woonkamer_temperature`), and become unavailable when the zone drops out of the API rather than reporting a stale value. Related to ([#28](https://github.com/koenhendriks/ha-eplucon/issues/28)), though note the target temperature still cannot be changed from Home Assistant, because the public API does not expose a way to set it. By [@knz](https://github.com/knz)
* ([#36](https://github.com/koenhendriks/ha-eplucon/pull/36)) Documentation of the zones API in `docs/zones-api.md` by [@knz](https://github.com/knz)
* ([#36](https://github.com/koenhendriks/ha-eplucon/pull/36)) Tests for the zones endpoint: `raw_data` parsing, the documented HTTP 406 path, and zone entity naming and availability by [@knz](https://github.com/knz)
* pytest now runs in CI, so the test suite gates pushes and pull requests alongside the existing HACS and hassfest validation.

### Fixed
* Hassfest validation failed because the config flow description had the API token URL written inline in `strings.json`. The URL is now supplied as a `description_placeholders` value, which is what hassfest asks for. The text shown when setting up the integration is unchanged.

## [1.5.1](https://github.com/koenhendriks/ha-eplucon/releases/1.5.1) - 2026-01-27

### Fixed
* ([#31](https://github.com/koenhendriks/ha-eplucon/pull/31)) Changed import_energy and export_energy types to Union to handle both int and float values by [@joopmartens](https://github.com/joopmartens)

## [1.5.0](https://github.com/koenhendriks/ha-eplucon/releases/1.5.0) - 2026-01-23

### Fixed
* ([#14](https://github.com/koenhendriks/ha-eplucon/issues/14)) Config flow has been updated as of home assistant >2025.12 by [@reddevil82](https://github.com/reddevil82)
* ([#17](https://github.com/koenhendriks/ha-eplucon/issues/17)) Updated the Eplucon API client to handle device fetching and response validation more robustly by [@reddevil82](https://github.com/reddevil82)


### Updated
* Refactored sensor entity descriptions for clearer implementation and reduced duplication by [@reddevil82](https://github.com/reddevil82)
* Streamlined the coordinator's device update mechanism to ensure more accurate state representation in Home Assistant by [@reddevil82](https://github.com/reddevil82)

### Added
* Enhanced error handling and debugging outputs in API data fetching methods by [@reddevil82](https://github.com/reddevil82)


## [1.4.1](https://github.com/koenhendriks/ha-eplucon/releases/1.4.1) - 2025-03-23

### Fixed

- Fixed error when mapping json from API to CommonInfoDTO ([#23](https://github.com/koenhendriks/ha-eplucon/issues/23))

## [1.4.0](https://github.com/koenhendriks/ha-eplucon/releases/1.4.0) - 2025-02-03

### Added
* ([!18](https://github.com/koenhendriks/ha-eplucon/pull/18)) Adding HeatLoading Status and sensors by [@ArneDT](https://github.com/ArneDT)
* ([#19](https://github.com/koenhendriks/ha-eplucon/issues/19)) Added friendly text sensor (thanks to [@joopmartens](https://github.com/joopmartens)) for Heating Mode displaying the state as following:
    * Turned off
    * Turned on
    * Emergency operation
    * APX
  
### Fixed
* ([#15](https://github.com/koenhendriks/ha-eplucon/issues/15)) Total active power (and inverter temperature) is now parsed as float.
* ([#13](https://github.com/koenhendriks/ha-eplucon/issues/13)) Total active power is now in KiloWatt, Import and export energy are now divided by 100 where possible.

## [1.3.0](https://github.com/koenhendriks/ha-eplucon/releases/1.3.0) - 2024-11-05

### Added 
* ([#10](https://github.com/koenhendriks/ha-eplucon/issues/10)) Add option to enter custom endpoint for API
* ([#9](https://github.com/koenhendriks/ha-eplucon/issues/9)) Added friendly text sensor for Operation Mode displaying the state as following:
    *  Koeling
    * Verwarming
    * Auto th-TOUCH
    * Auto Wp
    * Haard

### Fixed
* ([#8](https://github.com/koenhendriks/ha-eplucon/issues/8)) Sensors with missing measurements
    * SPF
    * Position Expansion Ventil
    * Number of Starts
    * Operation Mode


## [1.2.2](https://github.com/koenhendriks/ha-eplucon/releases/1.2.2) - 2024-09-23

### Fixed
- Fixed [#4](https://github.com/koenhendriks/ha-eplucon/issues/4), Brine and Production Circulation Pump now have percentage as unit.

### Updated
- Updated `requirements.txt` to version `dacite` up until next major release ([#2](https://github.com/koenhendriks/ha-eplucon/issues/2)). 

## [1.2.1](https://github.com/koenhendriks/ha-eplucon/releases/1.2.1) - 2024-09-08

### Added
- Setup to only allow supported devices with a certain product type (`heat_pump` for now).
- Mock client to be used with testing specific API responses.

### Fixed
- Fixed [#1](https://github.com/koenhendriks/ha-eplucon/issues/1) by checking for supported devices.

## [1.2.0](https://github.com/koenhendriks/ha-eplucon/releases/1.2.0) - 2024-09-08


### Added
- All missing sensors from the API output:
  - Operation Mode
  - Seasonal Performance Factor (SPF)
  - Position Expansion Ventil
  - Number of Starts
  - Heating Mode
  - Warm Water
  - Alarm Active
  - Current Heating Pump State
  - Current Heating State

## [1.1.0](https://github.com/koenhendriks/ha-eplucon/releases/1.1.0) - 2024-09-02
### Added
- Homeassistant device info to map entities per device in the integration.
- Debugging logs for API calls to be able to trace received data.
- CI using GitHub Actions including HACS validation.
- Missing Binary sensors (as reported by [killer8](https://tweakers.net/gallery/304893/)):
  - Active WW request
  - Direct Outlet (DG1)
  - Mixture Outlet (SG2)
  - Mixture Outlet (SG3)
  - Mixture Outlet (SG4)  
  

### Changed
- Checking for existing value of entity is now stricter on entity value instead of global device `realtime_info`

### Removed
- Device name from default entity name

## [1.0.0](https://github.com/koenhendriks/ha-eplucon/releases/1.0.0) - 2024-08-28
### Added
- Initial release of the Eplucon Home Assistant Integration.
- Support for retrieving real-time device information from the Eplucon API.
- Added `DeviceDTO`, `RealtimeInfoDTO`, and `CommonInfoDTO` for structured data management.
- Integration with Home Assistant's sensor platform.
- Automatic sensor entity creation based on Eplucon devices and their real-time data.
- Configuration via Home Assistant's UI, including token-based authentication.
- Data fetching and update mechanism using Home Assistant's `DataUpdateCoordinator`.
- Error handling and logging for API errors and data fetching issues.

### Fixed
- Issues with sensor entity registration on restart.
- Corrected handling of DTO conversion from API responses.
- Addressed bug with entity setup causing entities to be marked as "no longer provided" after restart.

### Known Issues
- Some device data may be returned as empty lists (e.g., `heatpump` data) due to API response inconsistencies.
- Minor delays in data updates may occur depending on API response time.

[Unreleased]: https://github.com/your-repo/eplucon-home-assistant-integration/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/your-repo/eplucon-home-assistant-integration/releases/tag/v1.0.0
