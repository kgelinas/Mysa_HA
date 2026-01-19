# Mysa for Home Assistant

[![Version](https://img.shields.io/badge/version-0.8.10-blue.svg)](https://github.com/kgelinas/Mysa_HA)

...

The integration includes a comprehensive test suite with **100% code coverage** for core modules.
[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz/)

A native cloud integration for Mysa devices in Home Assistant. Uses the official Mysa Cloud architecture (MQTT + HTTP) for real-time updates and instant command execution.

## Features

| Feature | Thermostats | AC Controller |
|:--------|:-----------:|:-------------:|
| 🌡️ Temperature Control | ✓ | ✓ |
| 🔥 HVAC Mode (Heat/Off) | ✓ | - |
| ❄️ HVAC Mode (Cool/Heat/Auto/Fan/Dry) | - | ✓ |
| � Fan Speed Control | - | ✓ |
| 🔄 Swing Control (Vertical/Horizontal) | - | ✓ |
| 🌡️ Climate+ (Thermostatic Mode) | - | ✓ |
| 🔒 Button Lock | ✓ | ✓ |
| 💡 Brightness Control | ✓ | - |
| � Wake on Approach | ✓ | - |
| 📊 Diagnostic Sensors | ✓ | ✓ |
| 🔍 Diagnostics Download | ✓ | ✓ |
| 🔄 Firmware Updates | ✓ | ✓ |
| ⚡ Real-time MQTT Sync | ✓ | ✓ |
| 💰 Energy Cost Integration | ✓ | ✓ |

## Supported Devices

- **Mysa Baseboard V1** (BB-V1)
- **Mysa Baseboard V2** (BB-V2)
- **Mysa Baseboard V2 Lite** (BB-V2-L)
- **Mysa In-Floor** (INF-V1)
- **Mysa AC Controller** (AC-V1)

### 🧪 Call for Testers

We are looking for users with the **Mysa for Central AC/Heat (ST-V1)**. Support is currently **unverified**. If you have this device, please install the integration and report your findings (and debug logs) on GitHub to help us fully support it!

## Installation

### HACS (Recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=kgelinas&repository=Mysa_HA&category=integration)

Or manually:
1. Open HACS → Integrations → ⋮ (menu) → Custom repositories
2. Add `https://github.com/kgelinas/Mysa_HA` with category **Integration**
3. Search for "Mysa" and install
4. Restart Home Assistant
5. Go to **Settings → Devices & Services → Add Integration → Mysa**

### Manual
1. Copy `custom_components/mysa` to your Home Assistant `config/custom_components/` folder
2. Restart Home Assistant
3. Add the integration via **Settings → Devices & Services**

## Configuration

1. Enter your Mysa account credentials (email/password)
2. (Optional) Configure zone names for your thermostat groups
3. Devices will appear automatically

## Entities

### Climate
- Temperature control with 0.5°C precision
- HVAC modes appropriate to device type
- AC devices include fan mode and swing controls

### Switches
| Switch | Thermostats | AC |
|:-------|:-----------:|:--:|
| Button Lock | ✓ | ✓ |
| Auto Brightness | ✓ | - |
| Wake on Approach | ✓ | - |
| Climate+ | - | ✓ |

### Number Controls
| Control | Thermostats | AC |
|:--------|:-----------:|:--:|
| Min Brightness | ✓ | - |
| Max Brightness | ✓ | - |

### Select Controls
| Control | Thermostats | AC |
|:--------|:-----------:|:--:|
| Horizontal Swing | - | ✓ |

### Sensors
| Sensor | Default | Category |
|:-------|:--------|:---------|
| Zone | Enabled | Standard |
| Voltage | Hidden | Diagnostic |
| Current | Hidden | Diagnostic |
| Max Current | Hidden | Diagnostic |
| RSSI | Hidden | Diagnostic |
| Duty Cycle | Hidden | Diagnostic |
| Infloor | Enabled | Diagnostic |
| Electricity Rate | Diagnostic | Diagnostic |

## Unlock Features on Lite Devices

> **Note**: If you only use Home Assistant to control your Mysa devices, you do NOT need to perform any upgrade. The Lite thermostat works perfectly with this integration as-is. The "magic upgrade" is only useful if you also use the official Mysa mobile app.

### Why Upgrade?

The Lite-to-Full conversion unlocks features in the **Mysa mobile app** (not Home Assistant):
- Zone control
- Usage graphs
- Humidity display in app
- Per-zone schedules

### How to Upgrade (Magic Upgrade Service)

> [!IMPORTANT]
> This feature requires the **Mysa Extended** integration to be installed.

1.  **Install Mysa Extended**: Copy `custom_components/mysa_extended` to your Home Assistant `config/custom_components/` folder and restart.
2.  Identify your **Mysa Baseboard V2 Lite (BB-V2-0-L)** device.
3.  Go to **Developer Tools** > **Services** (or **Actions**).
4.  Search for `mysa_extended.upgrade_lite_device` (Upgrade Lite Device).
5.  Select your Lite thermostat.
6.  Click **Perform Action**.
7.  **Power Cycle Required**: The device firmware has been updated. You MUST physically flip the breaker off and on (or unplug/wait/plug in) for the change to take effect.

**What happens?**
- The integration sends a command to change the device's Model ID to `BB-V2-0` (Full).
- It **automatically updates** your core Mysa integration configuration to treat this device as an "Upgraded Lite" device (ensuring correct commands are sent).

> ⚠️ **Warning**: This modifies device firmware settings. Use at your own risk.

### How to Revert (Downgrade Service)

1.  Go to **Developer Tools** > **Services** (or **Actions**).
2.  Search for `mysa_extended.downgrade_lite_device`.
3.  Select the device.
4.  Click **Perform Action**.
5.  **Power Cycle Required**: You MUST physically flip the breaker off and on (or unplug/wait/plug in).

**What happens?**
- The integration sends a command to restore the device's Model ID to `BB-V2-0-L` (Lite).
- It **automatically updates** your core integration configuration to remove this device from the "Upgraded Lite" list.

> ⚠️ **Warning**: This modifies device firmware settings. Use at your own risk.

### If You Upgraded Manually

If you performed the upgrade using the debug tool or another method *before* this integration, verify your configuration:
1.  Go to **Settings → Devices & Services → Mysa → Configure**
2.  Ensure your device is checked in "Upgraded Lite Devices"
3.  Click Submit

This manually tells the integration to use Type 5 (Lite) commands for your customized device.

### Custom Electricity Rate (Mysa Extended)

If the electricity rate from your Mysa cloud account is incorrect or missing, you can override it:

1.  Go to **Settings → Devices & Services → Mysa Extended → Configure**
2.  Enter your custom rate in the **Custom Electricity Rate ($/kWh)** field
3.  Click Submit

This override applies to all Mysa devices and will be used instead of the cloud-provided rate.

> **Note**: Leave this field empty to use the rate from your Mysa account.

### Killer Ping (Restart to Pairing Mode)

> [!CAUTION]
> **DANGER**: This is a DESTRUCTIVE action! The device will be **disconnected from your network** and you will need to **physically re-pair** it using the Mysa app.

Use this service only if you need to move a device to a new WiFi network:

1.  Go to **Developer Tools** > **Services** (or **Actions**)
2.  Search for `mysa_extended.killer_ping`
3.  Select your device
4.  Click **Perform Action**

The device will restart into pairing mode. Look for the device's setup network (e.g., "Mysa-XXXX") to complete the pairing process in the Mysa app.

### Simulated Energy Sensors (All Lite Devices)

Since Lite hardware (BB-V2-0-L) lacks a current sensor, you can configure an **estimated max current** to enable simulated power/energy tracking. This works for **any Lite device**, whether upgraded or not.

1. Go to **Settings → Devices & Services → Mysa → Configure**
2. Enter your heater's rated current in "Estimated Max Current (Amps)"
   - Check your heater's nameplate or manual (e.g., 10A for a 2400W baseboard at 240V)
3. This creates two new sensors for each Lite device:
   - **Estimated Current**: `max_current × duty_cycle`
   - **Estimated Power**: `voltage × estimated_current`

> **Note**: These are estimates based on duty cycle, not actual measurements. Use for approximate energy tracking only.

## Debug Tool

A command-line debug tool is included for development and troubleshooting:

```bash
cd tools
python mysa_debug.py
```

Features include MQTT sniffing, HTTP/MQTT command testing, and advanced operations like Lite-to-Full conversion and device pairing mode reset.

### Standalone Executables (Web-based Debugger Replacement)

For users who do not want to install Python, **standalone executables** are available for **Windows, Linux, and macOS**. These single-file applications require no installation.

1.  Go to the **Actions** tab in the GitHub repository.
2.  Select the latest **Build Cross-Platform Debug Tool** workflow run.
3.  Download the artifact for your OS (e.g., `mysa_debug_windows-latest`).
4.  Run the executable directly. Lists devices and commands same as below.

See [docs/MYSA_DEBUG.md](docs/MYSA_DEBUG.md) for usage details.

## Protocol Documentation

For developers interested in the Mysa protocols:

- **HTTP API**: [docs/API_REFERENCE.md](docs/API_REFERENCE.md) - Complete HTTP endpoint documentation with request/response structures
- **MQTT Protocol**: [docs/MYSA_PROTOCOL.md](docs/MYSA_PROTOCOL.md) - Real-time communication protocol details

## Development

### Dev Container

A Dev Container configuration is included for VS Code. Open the project in VS Code and select "Reopen in Container" to get a pre-configured development environment with all dependencies.


## Requirements

- Mysa account (email/password)
- Home Assistant 2024.1.0 or later

## Credits

- [mysotherm](https://github.com/dlenski/mysotherm) by @dlenski - Authentication and API logic
- [mqttpacket](https://github.com/jlitzingerdev/mqttpacket) by @jlitzingerdev - MQTT packet implementation (adapted)

---
*Made with ❤️ for the Mysa community*
