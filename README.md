# Mysa for Home Assistant

[![Version](https://img.shields.io/badge/version-0.7.1-blue.svg)](https://github.com/kgelinas/Mysa_HA)
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
| 🔄 Firmware Updates | ✓ | ✓ |
| ⚡ Real-time MQTT Sync | ✓ | ✓ |

## Supported Devices

- **Mysa Baseboard V1** (BB-V1)
- **Mysa Baseboard V2** (BB-V2)
- **Mysa Baseboard V2 Lite** (BB-V2-L)
- **Mysa In-Floor** (INF-V1)
- **Mysa AC Controller** (AC-V1) ✨ *New*

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

## Debug Tool

A command-line debug tool is included for development and troubleshooting:

```bash
cd tools
python mysa_debug.py
```

Features include MQTT sniffing, HTTP/MQTT command testing, and advanced operations like Lite-to-Full conversion and device pairing mode reset.

See [docs/MYSA_DEBUG.md](docs/MYSA_DEBUG.md) for usage details.

## Protocol Documentation

For developers interested in the Mysa API, see [docs/MYSA_PROTOCOL.md](docs/MYSA_PROTOCOL.md).

## Requirements

- Mysa account (email/password)
- Home Assistant 2024.1.0 or later

## Credits

- [mysotherm](https://github.com/dlenski/mysotherm) by @dlenski - Authentication and API logic
- [mqttpacket](https://github.com/jlitzingerdev/mqttpacket) by @jlitzingerdev - MQTT packet implementation (adapted)

---
*Made with ❤️ for the Mysa community*
