# Mysa (Native Cloud) for Home Assistant

A high-performance, native cloud integration for Mysa Thermostats in Home Assistant. This component uses the official Mysa Cloud architecture (MQTT + HTTP) to provide a "native" feel with real-time updates and instant command execution.

## Key Features
*   🚀 **Instant Commands**: Uses MQTT Type 4 payloads for near-instant temperature and mode changes (optimized for BB-V2 hardware).
*   🔄 **Real-Time Sync**: captured real-time state updates from the thermostat via MQTT `/out` topics.
*   🛡️ **No "Snap-Back"**: Implements 15-second state protection to prevent the Home Assistant UI from reverting while waiting for cloud confirmation.
*   📟 **V2 Ready**: Specifically addressed issues with Baseboard V2.0 devices being ignored by older implementations.
*   📦 **Self-Contained**: Includes vendored dependencies (`mysotherm` and `mqttpacket`) to ensure stability and compatibility.

## Installation
1. Copy the `custom_components/mysa` folder to your Home Assistant `custom_components` directory.
2. Restart Home Assistant.
3. Go to **Settings > Devices & Services > Add Integration** and search for **Mysa**.

## Requirements
*   A Mysa account (Username/Password).
*   For BB-V2 devices, ensure they are connected to your Mysa account.

## Credits
*   Original logic based on [mysotherm](https://github.com/dlenski/mysotherm).
*   Enhanced and fixed for modern V2 hardware and real-time synchronisation.

---
*Created with ❤️ for the Mysa community.*
