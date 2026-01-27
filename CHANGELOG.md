# Changelog

All notable changes to this project will be documented in this file.


## [0.9.1-beta1] - 2026-01-26
### Fixed
- **In-Floor Temperature**: Resolved issue where In-Floor units displayed Ambient (Air) temperature instead of Floor temperature.
- **Tracked Sensor Support**: Added automatic detection of `TrackedSensor` and `trackedSnsr` keys to correctly infer the active sensor mode (Ambient vs Floor).
- **MQTT Stability**: Fixed parsing of JSON payloads containing unescaped newlines (error 1005) by using `strict=False` in JSON decoder.

### Added
- **Sensor Mode Selector**: New `Sensor Mode` select entity for In-Floor devices (INF-V1). Allows manual switching between "Ambient" and "Floor" modes, which forces the thermostat to display the correct temperature source.
- **Beta Channel**: Documented beta release process for HACS testing.

## [0.9.1] - 2026-01-25
### Changed
- **Documentation**: Added detailed Energy Dashboard configuration guide, including best practices for "Individual Devices" vs "Grid Consumption".

### Fixed
- **Electricity Rate**: Handled cases where the electricity rate contains a comma instead of a dot.
- **Electricity Rate**: Now refreshes from the cloud periodically (every 120s) instead of only on startup. ensure rates are kept in sync with the Mysa App.

## [0.9.0] - 2026-01-25
### Added
- **Documentation**: Added comprehensive explanations for API and Protocol documentation to improve maintainability.

### Changed
- **Major Refactor**: Major refactoring of the integration to align with Home Assistant best practices and a lot of change to the codebase. Some breaking change may occur.

## [0.8.10] - 2026-01-19
### Fixed
- **Energy Calculation (Critical)**: Resolved 10x overestimation bug in power and energy sensors. The `Current` sensor reports the last-measured value when the heater was ON, not instantaneous current. Power is now correctly calculated as `Voltage × Current × DutyCycle%`.

### Added
- **API Reference**: New comprehensive HTTP API documentation (`docs/API_REFERENCE.md`) with full endpoint descriptions, response structures, and field explanations.
- **Mysa Extended Integration**: New optional integration (`mysa_extended`) to house advanced or experimental features, starting with the "Magic Upgrade" services.
- **Custom Electricity Rate**: Added `custom_erate` option to Mysa Extended to override the cloud-provided electricity rate for energy cost calculations.
- **UI Config Flow**: Mysa Extended can now be added via the Home Assistant "Add Integration" UI.
- **Killer Ping Service**: New `mysa_extended.killer_ping` service to restart a device into pairing mode (use with extreme caution).

### Changed
- **Service Migration**: Moved `upgrade_lite_device` and `downgrade_lite_device` services from the core `mysa` integration to `mysa_extended`. This keeps the core integration lean and focused on standard features.
- **Documentation**: Simplified `docs/TESTING.md`.
- **Test Retirement**: Removed VCR cassette-based end-to-end tests to reduce maintenance overhead. Core logic remains at 100% unit test coverage.
- **Tooling**: Removed unused dependencies and cleaned up imports in `tools/mysa_debug.py`.

### ⚠️ Migration Guide (v0.8.10)
This release includes a major refactoring that splits the integration into two parts. Standard users do **not** need to do anything, but if you use advanced features, please read below:

1. **Magic Upgrade Services**: If you previously used `mysa.upgrade_lite_device` or `mysa.downgrade_lite_device`, you must now install the `mysa_extended` component. These services have moved to the `mysa_extended` domain.
2. **Installation**: Copy the `custom_components/mysa_extended` folder to your Home Assistant `config/custom_components/` directory and restart.
3. **Automations**: Update any automations or scripts that called the old services to use `mysa_extended.upgrade_lite_device` or `mysa_extended.downgrade_lite_device`.
4. **Energy Stats**: Due to the power calculation fix, your Energy dashboard may show a "spike" or change in behavior as it now reflects real usage instead of peak wattage. No action is required, but you can reset your energy sensors if you want a clean start.

## [0.8.9] - 2026-01-16
### Fixed
- **Update Sensor**: Fixed critical crash where firmware info was not properly awaited.
- **E-Rate**: Correctly fetching Electricity Rate from home data (resolves "unknown" state).

### Changed
- **Dependencies**: Reworked library to use async version. Start time  should be better now.
- **Testing**: Added comprehensive VCR (cassette) tests for recording/replaying API interactions.
- **Documentation**: Created detailed testing guide in `docs/TESTING.md`.
- **Version Requirements**: Updated minimum Home Assistant version to 2024.1.0 (required for `ConfigFlowResult`).

## [0.8.6] - 2026-01-15
### Fixed
- **Config Flow Crash**: Fixed `AttributeError` when configuring options, caused by incorrect handling of zone data structure.
- **Pytest Warning**: Resolved deprecation warning for async tests in `tests/test_api.py`.

## [0.8.5] - 2026-01-15
### Added
- **Standalone Debug Tool**: Added cross-platform build support for the `mysa_debug` tool. Users can now download single-file executables for Windows (`.exe`), Linux, and macOS from GitHub Actions/Releases without needing Python installed.
- **Robust Authentication**: Refactored `mysa_auth` and `client` modules to use `boto3` sessions more consistently, improving stability for both the integration and the debug tool.
- **Client Coverage**: Achieved 100% test coverage for `client.py` by covering edge cases for uninitialized sessions.

## [0.8.3] - 2026-01-15
### Added
- **Energy Cost Sensor**: New sensor entity `_electricity_rate` that exposes the electricity rate configured in the Mysa App (per home) to Home Assistant. This allows users to track energy costs natively in the Energy Dashboard.
- **Interactive Options Flow**: Massive overhaul of the configuration options. Users can now rename zones directly in Home Assistant and configure energy simulation settings per device.
- **Dynamic Config UI**: Input fields now show dynamic current values (e.g. "Rename Zone: Living Room") and localized field descriptions.
- **Forced Simulated Energy**: Added a global "Force Simulated Energy" toggle. This bypasses real-time Voltage/Current readings from the device and forces the integration to calculate power based on Wattage * Duty Cycle. Useful for devices with faulty sensors or for testing.

### Fixed
- **API Zone Overrides**: `MysaApi.get_zone_name` now correctly checks for user-defined overrides before falling back to the cloud name.

## [0.8.2] - 2026-01-14
### Added
- **Native Energy Entity**: Added a virtual Energy (kWh) sensor that tracks usage over time (Riemann sum integration) for all devices.
- **Floor Temperature Sensor Support**: Added support for `flrSnsrTemp` key used by some Mysa In-Floor models.
- **Infloor Sensor Enabled Default**: The "Infloor Temperature" sensor is now enabled by default for supported devices.
- **100% Test Coverage**: Achieved full coverage for `climate.py` (AC logic), `mysa_api.py` (core logic), `sensor.py`, `config_flow.py`, `binary_sensor.py`, and `__init__.py`.
- **Robustness Tests**: Added rigorous exception handling verification for MQTT loop timeouts and generic errors in `mysa_api.py`.
- **Optimistic UI**: Instant feedback for all controls (Switches, Climate, Number, Select) with sticky state logic.
- **New Service**: `mysa.upgrade_lite_device` ("Magic Upgrade") to check and upgrade BB-V2-0-L Lite devices to Full feature set.
- **Revert Service**: Added `mysa.downgrade_lite_device` to revert "Magic Upgrade" changes (Full -> Lite).
- **Call for Testers**: Mysa for Central AC/Heat (ST-V1) is now available for testing. Support is **NOT** verified; we need users to provide logs and feedback to implement full support.

### Fixed
- **Simulated Sensor Tests**: Resolution of failing tests in simulated current/power sensor logic.
- **Fixture Conflicts**: Fixed `api` fixture conflicts in `tests/test_api.py`.

### Changed
- **Test Consolidation**: Merged all modular coverage tests into `tests/test_api.py` and `tests/test_sensor.py`.
- **Cleanup**: Removed temporary test files and consolidated re-authentication tests into `tests/test_config_flow.py`.
- **Documentation**: Updated protocol docs with `flrSnsrTemp` field.

## [0.8.1] - 2026-01-13
### Added
- **Reauthentication**: Added support for updating integration credentials (e.g. password change) without removing and re-adding the device.
- **Diagnostics**: Added `diagnostics.py` to allow users to download a sanitized JSON dump of their device data for troubleshooting. Includes full redaction of sensitive credentials.
- **System Health**: Added `system_health.py` to display API connectivity, device count, and MQTT listener status in HA's System Health panel.
- **100% Test Coverage**: Achieved full coverage for core modules `mysa_api.py`, `mysa_auth.py`, and `mysa_mqtt.py`.
- **Test Markers**: Standardized `pytest` markers (`@pytest.mark.unit`, `@pytest.mark.asyncio`) for better test organization.

### Changed
- **Config Entry Handling**: Changed authentication errors during setup to use `ConfigEntryNotReady`, enabling automatic retries when the API is temporarily unavailable.
- **Test Consolidation**: Merged multiple API test files into a single, comprehensive `tests/test_api.py` module.
- **Robustness**: Improved error handling in `mysa_api.py` for synchronous methods and MQTT connection loops.
- **Test Refactoring**: Updated `test_api.py` to use `AsyncMock` correctly for all awaitable mocks.

### Fixed
- **AC Mode Logic**: Fixed a bug in `set_hvac_mode` where "cool" mode incorrectly matched "heat_cool".
- **Test Suite**: Fixed `UnboundLocalError` and various mock definitions in the test suite.
- **Edge Case Handling**: Resolved multiple potential `RuntimeError` and `TypeError` exceptions in `mysa_api.py` during handshake failures or empty API responses.

## [0.8.0] - 2026-01-11
### Added
- **Simulated Current/Power Sensors**: For all Lite devices (BB-V2-0-L), configure an estimated max current to enable simulated energy tracking based on duty cycle. Works for both upgraded and non-upgraded Lite devices.
- **Test Coverage**: Massive expansion of test suite to ~85% total coverage (up from ~77%). 10 modules now at 100% coverage.
- **Developer Docs**: Updated README with testing commands and coverage stats.
- **Token Refresh Test Script**: New `tools/test_token_refresh.py` for validating token expiration and re-authentication without waiting 10 hours.
- **Async Context Manager**: Added `MqttConnection` class for cleaner MQTT connection handling with automatic connect/subscribe/cleanup.

### Fixed
- **MQTT Connection Stability**: Fixed connection drops after ~10 hours by adding automatic re-authentication when tokens expire.
- **MQTT Subscription Error**: Removed problematic `/batch` topic subscription that caused immediate disconnection with 1005 error.
- **Token Refresh**: Changed from passive `check_token()` to active `renew_access_token()` with full re-login fallback.
- **MQTT State Parsing**: Fixed parsing of command echo messages by extracting state values from nested `cmd` array structure.
- **Device ID Anonymization Bug**: Fixed potentially incorrect assertions in tests where generic device IDs were used instead of real MAC addresses.
- **Test Fixtures**: Corrected `hass.data` keys in test fixtures to ensure reliable testing of config entries.
- **Zone Name Display**: Zone sensors now show friendly names (e.g., "Basement") from the `/homes` API instead of UUIDs. Updates dynamically when changed in Mysa app.
- **Missing Imports**: Restored `ssl`, `urlparse`, `uuid1`, and `websockets` imports that were accidentally removed during cleanup.
- **Code Cleanup**: Removed thousands of lines of redundant, orphaned, and dead code from the test suite. Conslidated 41 test files into 15 maintained modules.

### Changed
- **Documentation**: Clarified that the "magic upgrade" is only needed for Mysa app users, not Home Assistant-only users.
- **Code Refactoring**: Created shared `mysa_mqtt.py` module to prevent code drift between integration and debug tool. Both now use identical MQTT connection, authentication, and subscription logic.
- **Type Hints**: Added comprehensive type annotations to `mysa_mqtt.py` and `mysa_auth.py` for better IDE support and code clarity.
- **Constants Consolidation**: Moved MQTT constants (`MQTT_KEEPALIVE`, `MQTT_PING_INTERVAL`, `MQTT_USER_AGENT`) to central `const.py`.
- **Debug Tool**: Refactored to use `MqttConnection` async context manager, reducing MQTT loop code from 38 to 22 lines.

## [0.7.2] - 2026-01-09
### Added
- **Upgraded Lite Device Support**: New Options Flow setting to mark devices that have been "magic upgraded" from Lite to Full firmware. These devices require `type: 5` commands despite having full features.
- **Live Options Updates**: Options changes (like Upgraded Lite selection) now take effect immediately without requiring a reload.
- **Translations**: Full translations for German, Spanish, Italian, Dutch, and Portuguese.

### Changed
- Options Flow updated with new title and descriptions for Upgraded Lite feature.

## [0.7.1] - 2026-01-09
### Added
- **Auto-Zone Configuration**: Zones are now automatically fetched from the Mysa API and synced to Home Assistant areas. Manual zone configuration has been removed.
- **Debug Tool Improvements**:
  - Added device filtering to `sniff` command (e.g., `sniff 1` or `sniff <ID>`).
  - Added short aliases for commands (`ls`, `ex`, `?`).
  - Refactored help menu for better readability.

## [0.7.0] - 2026-01-09

### Added
- **Consolidated Authentication**: Merged mysotherm library into single `mysa_auth.py` module (~170 lines vs ~60KB before)
- **Advanced Debug Menu**: New `advanced` command in debug tool with:
  - **Lite-to-Full Conversion**: Upgrade BB-V2-0-L to BB-V2-0
  - **Killer Ping**: Reset device to pairing mode (MsgType 5)
- Comprehensive protocol documentation (`docs/MYSA_PROTOCOL.md`)
- Debug tool documentation (`docs/MYSA_DEBUG.md`)

### Changed
- Removed `lib/mysotherm` directory - all auth code now in `mysa_auth.py`
- Updated imports throughout codebase to use consolidated auth module

---

## [0.6.0] - 2026-01-09

### Added
- **AC Controller Support** (AC-V1):
  - 🌡️ Temperature control
  - ❄️ Full HVAC modes: Cool, Heat, Auto, Fan Only, Dry
  - 💨 Fan speed control (Auto, Low, Medium-Low, Medium, High, Sleep)
  - 🔄 Vertical and Horizontal swing control
  - 🌡️ Climate+ thermostatic mode
- **New Entities for All Devices**:
  - Switch: Button Lock, Auto Brightness, Wake on Approach, Climate+
  - Number: Min/Max Brightness controls
  - Select: Horizontal Swing position (AC)

### Changed
- Refactored climate.py with dedicated `MysaACClimate` class
- Updated sensor entities to hide irrelevant sensors for AC devices

---

## [0.5.0] - 2026-01-09

### Added
- Real-time MQTT state updates via WebSocket connection
- Timestamp-based pending values to prevent "unknown" states
- `prompt_toolkit` support in debug tool for improved UX
- Timestamps in sniffer output

### Fixed
- Stale data handling when cloud returns outdated values after command
- MQTT state updates no longer overwrite valid data with None

---

## [0.4.0] - 2025-12-29

### Added
- Secure credential storage using Home Assistant's `helpers.storage`
- Debug tool with saved credentials (`~/.mysa_debug_auth.json`)
- MQTT command support for real-time device control

### Changed
- Removed failing HTTP control logic
- Focused on core MQTT temperature/mode control

---

## [0.3.0] - 2025-12-26

### Added
- Interactive debug tool (`mysa_debug.py`) for testing commands
- MQTT sniff mode for debugging

### Fixed
- MQTT payload structure for BB-V2 devices
- Device compatibility detection based on model string

---

## [0.2.0] - 2025-12-24

### Added
- Initial MQTT write command support
- Device type detection (BB-V1, BB-V2, INF-V1)

---

## [0.1.0] - 2025-12-22

### Added
- Initial release
- Basic Mysa thermostat support via HTTP API
- Temperature and humidity sensors
- Zone sensor
