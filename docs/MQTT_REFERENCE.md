# Mysa MQTT Protocol Reference

This document provides a deep dive into the MQTT-based communication used by Mysa devices. For an overview of the entire protocol, see [MYSA_PROTOCOL.md](MYSA_PROTOCOL.md).

## Connection

Mysa uses **AWS IoT Core** for MQTT communication, delivered over WebSockets.

### Requirements
- **Protocol**: MQTT v3.1.1
- **Broker**: AWS IoT Core (WSS endpoint)
- **Signature**: AWS SigV4 (with specific nuances)

### SigV4 Nuances
Mysa uses a non-standard AWS SigV4 signing implementation. The `X-Amz-Security-Token` (session token) must be added to the query parameters **after** the signature has been calculated, rather than being part of the signed request string.

---

## Topics

Each device communicates via three primary topics. The `{device_id}` is the MAC address (lowercase, no colons).

| Topic | Direction | Description |
|:------|:----------|:------------|
| `/v1/dev/{device_id}/out` | ← Device | Real-time state updates (Automatic broadcast) |
| `/v1/dev/{device_id}/in` | → Device | Direct commands and control |
| `/v1/dev/{device_id}/batch` | ← Device | High-precision binary telemetry (MsgType 3) |

---

## Message Envelope (MsgType 44)

Most interaction with the device is wrapped in a JSON envelope:

```json
{
  "Timestamp": 1704825600,
  "body": { /* payload */ },
  "dest": {"ref": "DEVICE_ID", "type": 1},
  "id": 1704825600000,
  "msg": 44,
  "resp": 2,
  "src": {"ref": "USER_ID", "type": 100},
  "time": 1704825600,
  "ver": "1.0"
}
```

---

## Message Types (MsgType)

The `MsgType` field indicates the payload's intent.

| MsgType | Direction | Description |
|:--------|:----------|:------------|
| 1 | ← Device | Status Update (Standard Telemetry) |
| 3 | ← Device | Batch Data (High-frequency energy readings) |
| 4 | ← Device | Device Log (Info/Error/Debug JSON) |
| 5 | → Device | Killer Ping (Reset to pairing mode) |
| 6 | → Device | Settings Nudge (Force cloud-to-device sync) |
| 7 | → Device | Metadata Request (Info/FW/IP/Serial) |
| 10 | ← Device | Boot Status (IP, Firmware, Serial) |
| 11 | → Device | State Poll / Broadcast Request |
| 20 | ← Device | Heartbeat / Status Request Response |
| 30 | ← Device | Telemetry (AC Only: 1s updates) |
| 30 | ← Device | Device Shadow (Legacy) | Pinned state object |
| 31 | ← Device | ACState Object Dump (AC Only) |
| 40 | ← Device | Standard Telemetry (Alt) | Temperature, Humidity, Duty Cycle |
| 44 | → Device | Set Setting (Cloud) | Ack for `POST /devices/{id}` updates |
| 44 | ← Device | Command Response |
| 61 | ← Device | Firmware Report (Response to MsgType 20) |

---

## Batch Data Structure (MsgType 3)

Batch data provides high-precision historical telemetry. The payload `body.readings` is a base64-encoded binary blob containing a 3-byte header followed by 25-33 byte reading records.

### Binary Record Format

| Offset | Field | Type | Unit | Description |
|:-------|:------|:-----|:-----|:------------|
| 0 | Magic | 2B | - | `0xCA 0xA0` |
| 2 | Version | 1B | - | `0x00`, `0x01`, or `0x03` |
| 3 | Timestamp | uint32 | sec | Unix Timestamp (LE) |
| 7 | SensorTemp| int16 | °C/10| Internal sensor temperature |
| 9 | AmbTemp | int16 | °C/10| Ambient room temperature |
| 11 | Setpoint | int16 | °C/10| Target temperature |
| 13 | Humidity | int8 | % | Relative humidity |
| 14 | Duty | int8 | % | Heater duty cycle |
| 15 | OnMs | int16 | ms | Consecutive milliseconds ON |
| 17 | OffMs | int16 | ms | Consecutive milliseconds OFF |
| 19 | HeatSink | int16 | °C/10| Triac/Heatsink temperature |
| 21 | FreeHeap | uint16 | B | Available device memory |
| 23 | RSSI | int8 | dBm | WiFi signal strength |
| 24 | State | int8 | 0/1 | Binary output state |

### Version Trailers

Depending on the version byte at offset 2, the following fields are appended:

#### Version 0 (V1 Hardware)
| Offset | Field | Type | Description |
|:-------|:------|:-----|:------------|
| 25 | Checksum | uint8 | XOR Checksum |

#### Version 1 (V2 Hardware - Preliminary)
| Offset | Field | Type | Description |
|:-------|:------|:-----|:------------|
| 25 | Voltage | int16 | Line voltage (LE) |
| 27 | Checksum | uint8 | XOR Checksum |

#### Version 3 (V2+ Hardware)
| Offset | Field | Type | Description |
|:-------|:------|:-----|:------------|
| 25 | Voltage | int16 | Line voltage (LE) |
| 27 | Current | int16 | Current in mA (LE) |
| 29 | Reserved| 3B | Internal flags/reserved |
| 32 | Checksum | uint8 | XOR Checksum |

### Checksum Calculation
The XOR checksum is calculated across all bytes from the **Timestamp** (offset 3) up to the byte immediately preceding the **Checksum** field.

---

## Command Reference

### Standard Commands (MsgType 44)

**Set Temperature**
```json
{"cmd": [{"sp": 21.0, "stpt": 21.0, "a_sp": 21.0, "tm": -1}], "type": TYPE, "ver": 1}
```

**Set HVAC Mode**
```json
{"cmd": [{"md": MODE, "tm": -1}], "type": TYPE, "ver": 1}
```
- Modes: 1=Off, 3=Heat (Thermostats); 1=Off, 4=Cool, etc. (AC)

### Special Commands (No Envelope)

> [!WARNING]
> For all Special Commands (MsgType 5, 6, 11), the `Device` parameter MUST be the lowercase MAC address without colons. If uppercase characters are used, the device will silently ignore the command.

**Killer Ping (MsgType 5)**
Resets device to pairing mode.
```json
{"Device": "ID", "Timestamp": 170, "MsgType": 5, "EchoID": 1}
```

**Settings Nudge (MsgType 6)**
Forces cloud-to-device sync.
```json
{"Device": "ID", "EventType": 0, "MsgType": 6, "Timestamp": 170}
```

**Metadata Request (MsgType 7)**
Request firmware version, IP, and hardware details. Response is via MsgType 10.
```json
{"Device": "ID", "Timestamp": 170, "MsgType": 7}
```

**State Poll (MsgType 11)**
Forces the device to aggressively broadcast state updates for a set timeout.
```json
{"Device": "ID", "Timestamp": 170, "MsgType": 11, "Timeout": 300}
```
