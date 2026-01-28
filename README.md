# Mysa for Home Assistant

[![Version](https://img.shields.io/badge/version-0.9.1--beta3-blue.svg)](https://github.com/kgelinas/Mysa_HA)

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

- **Mysa for Baseboards V1** (BB-V1)
- **Mysa for Baseboards V2** (BB-V2)
- **Mysa for Baseboards V2 Lite** (BB-V2-L) - *With "Magic Upgrade" support*
- **Mysa for AC/Mini-Split** (AC-V1)
- **Mysa for In-Floor** (INF-V1)
- **Mysa for Central AC/Heat** (ST-V1)

## Known Limitations
- **Cloud Dependent**: Requires an active internet connection to authenticate and connect to Mysa's backend. This is **not a local-only integration** (local API was removed by Mysa).
- **Polling Fallback**: Uses a slower polling interval (120s) as a fail-safe, relying primarily on push updates.

## Troubleshooting

### Authentication Failed
- Double-check your email and password.

### Delay in updates
- This integrations uses a persistent MQTT connection. If updates are slow, check your internet connection or logs for "Reconnecting..." messages.

---


## Installation via HACS

1. Go to HACS -> Integrations
2. Click the 3 dots in the top right corner and select "Custom repositories"
3. Add `kgelinas/Mysa_HA` as a custom repository
4. Click "Install"
5. Restart Home Assistant

5. Go to **Settings → Devices & Services → Add Integration → Mysa**

### Manual
1. Copy `custom_components/mysa` to your Home Assistant `config/custom_components/` folder
2. Restart Home Assistant
3. Add the integration via **Settings → Devices & Services**

## Removal

1. Go to **Settings → Devices & Services**.
2. Select the **Mysa** integration.
3. Click the three dots on the integration entry and select **Delete**.
4. If you used HACS, go to HACS → Integrations → Mysa → three dots → Remove.
5. Restart Home Assistant.

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
| Temperature | Enabled | Standard |
| Humidity | Enabled | Standard |
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

## Troubleshooting

### Authentication Failed
If you see "Authentication failed" errors, ensure your email and password are correct. If you recently changed your password, re-configure the integration via **Settings → Devices & Services → Mysa → Configure** (or delete and re-add).

### Devices Unavailable
If devices show as "Unavailable":
1. Check if the device is online in the official Mysa app.
2. Verify your Home Assistant internet connection.
3. Check the logs for specific error messages (Settings → System → Logs).

### Ghost Devices
Integration requires devices to be assigned to a specific "Home" within the Mysa app. Devices not assigned to a home (ghost devices) may be ignored or fail to update. ensuring all devices are assigned to a home in the Mysa app is recommended.

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

## Advanced Configuration (Automation)

Mysa entities can be automated using standard Home Assistant triggers and actions.

### Example: Turn off AC when window opens

```yaml
alias: "Turn off AC if window open"
description: "Turn off Mysa AC when living room window is opened"
trigger:
  - platform: state
    entity_id: binary_sensor.living_room_window
    to: "on"
    for:
      seconds: 30
condition:
  - condition: state
    entity_id: climate.living_room_ac
    state: "cool"
action:
  - service: climate.turn_off
    target:
      entity_id: climate.living_room_ac
```

## Credits

- [mysotherm](https://github.com/dlenski/mysotherm) by @dlenski - Authentication and API logic
- [mqttpacket](https://github.com/jlitzingerdev/mqttpacket) by @jlitzingerdev - MQTT packet implementation (adapted)

---
*Made with ❤️ for the Mysa community*
