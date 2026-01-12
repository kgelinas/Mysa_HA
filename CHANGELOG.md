# Changelog

All notable changes to this project will be documented in this file.

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
