# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Homeassistant device description to map entities per device in the integration.
- Debugging logs for API calls to be able to trace received data.

### Removed
- Device name from default entity name

## [1.0.0](https://github.com/koenhendriks/ha-ecuplon/releases/1.0.0) - 2024-08-28
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
