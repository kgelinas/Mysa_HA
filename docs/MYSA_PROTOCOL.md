# Mysa Protocol Reference

This document describes the HTTP and MQTT protocols used to communicate with Mysa devices.

## Overview

Mysa uses a hybrid communication architecture:
- **HTTP API**: For device settings, firmware info, and user data
- **MQTT over WebSocket**: For real-time control and state updates

## Device Types

Each Mysa device model uses a specific payload type for MQTT commands:

| Model       | Payload Type | Description              |
|:------------|:-------------|:-------------------------|
| BB-V1       | `1`          | Baseboard V1             |
| AC-V1       | `2`          | AC Controller            |
| INF-V1      | `3`          | In-Floor Heating         |
| BB-V2       | `4`          | Baseboard V2             |
| BB-V2-L     | `5`          | Baseboard V2 Lite        |
| ST-V1-0     | `Shadow`     | Central AC/Heat (Modern) |

---

## Communication Protocols

For detailed specifications, refer to the following documentation:

- 🚀 **[MQTT Reference](MQTT_REFERENCE.md)**: Real-time control, SigV4 nuances, and Batch binary formats.
- 🌐 **[HTTP API Reference](API_REFERENCE.md)**: Cloud registration, device settings, and polling logic.

---

## State & Telemetry Fields

The structure of state updates (via both MQTT and HTTP) is standardized across models.

### Common Fields
| Field | Description | Type |
|:------|:------------|:-----|
| Temperature | Current temperature | float |
| Humidity | Current humidity | int (0-100) |
| SetPoint | Target temperature | float |
| Mode | HVAC mode ID | int |
| Rssi | WiFi signal strength | int (dBm) |
| Connected | Online status | bool |

### Heating Thermostats (BB/INF)
| Field | Description | Type |
|:------|:------------|:-----|
| Duty | Heater duty cycle | int (0-100) |
| Voltage | Line voltage | float |
| Current | Line current | float |
| HeatSink | Heat sink temperature| float |
| flrSnsrTemp | Floor temperature (V2/INF) | float |

### AC Controller (AC-V1)
| Field | Description | Type |
|:------|:------------|:-----|
| FanSpeed | Current fan speed | int |
| SwingState | Vertical swing pos | int |
| IsThermostatic| Climate+ status | int |
| CorrectedTemp | Calibrated temp | float |
| SensorTemp | Raw sensor temp | float |

---

## Technical Details

### Device Polling
The Home Assistant integration polls the HTTP API every **120 seconds** to sync settings. Real-time changes are pushed via MQTT topics defined in the [MQTT Reference](MQTT_REFERENCE.md).

### Staleness Guard
To prevent "rubber-banding" (UI state reverting after a command), the integration ignores HTTP updates if a command was sent within the last **90 seconds**, unless the update contains a newer timestamp.

> [!IMPORTANT]
> The integration must accept updates where the incoming HTTP timestamp **equals** the current cached timestamp. Because MQTT real-time updates may sometimes push the same timestamp before HTTP polling finishes (or vice-versa), rejecting equal timestamps can discard fresh and valid application state transitions.
