# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
