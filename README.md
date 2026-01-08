# Mysa for Home Assistant

[![Version](https://img.shields.io/badge/version-0.5.0-blue.svg)](https://github.com/kgelinas/Mysa_HA)
[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz/)

A native cloud integration for Mysa Thermostats in Home Assistant. Uses the official Mysa Cloud architecture (MQTT + HTTP) for real-time updates and instant command execution.

## Features

| Feature | Description |
|:--------|:------------|
| 🌡️ **Climate Control** | Temperature and HVAC mode (Heat/Off) |
| 📊 **Sensors** | Brightness, Min/Max Brightness, Zone |
| 🔒 **Binary Sensors** | Lock, Proximity, Auto Brightness, Eco Mode |
| 🔄 **Firmware Updates** | Automatic check every 4 hours |
| 🏠 **Zone Naming** | Group thermostats into Home Assistant areas |
| ⚡ **Real-time Sync** | Persistent MQTT connection for instant updates |

## Supported Devices

- Mysa Baseboard V1 (BB-V1)
- Mysa Baseboard V2 (BB-V2)
- Mysa Baseboard V2 Lite (BB-V2-L)
- Mysa In-Floor (INF-V1)

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

## Entity Visibility

| Type | Default | Category |
|:-----|:--------|:---------|
| Climate, Brightness, Zone, Lock | **Enabled** | Standard |
| Voltage, Current, RSSI, Duty Cycle | Disabled | Diagnostic |

Diagnostic sensors are hidden by default but can be enabled in **Settings → Entities**.

## Requirements

- Mysa account (email/password)
- Home Assistant 2024.1.0 or later

## Credits

- [mysotherm](https://github.com/dlenski/mysotherm) by @dlenski - Authentication and API logic
- [mqttpacket](https://github.com/jlitzingerdev/mqttpacket) by @jlitzingerdev - MQTT packet implementation (adapted)

---
*Made with ❤️ for the Mysa community*
