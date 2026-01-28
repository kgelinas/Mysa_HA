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
| ST-V1       | `?`          | Central AC/Heat (Unknown)|

---

## MQTT Protocol

### Connection

MQTT is delivered over WebSocket using AWS IoT Core. Connection requires:
1. AWS Cognito authentication
2. SigV4-signed WebSocket URL
3. MQTT protocol version 3.1.1

#### SigV4 Nuances
Mysa uses a non-standard AWS SigV4 signing implementation. The `X-Amz-Security-Token` (session token) must be added to the query parameters **after** the signature has been calculated, rather than being part of the signed request string.

### Topics

Each device has three topics:
- `/v1/dev/{device_id}/out` - State FROM device
- `/v1/dev/{device_id}/in` - Commands TO device
- `/v1/dev/{device_id}/batch` - High-frequency energy data (MsgType 3)

The `{device_id}` is the MAC address without colons, lowercase.

### Message Envelope (MsgType 44)

Commands are wrapped in an envelope structure:

```json
{
  "Timestamp": 1704825600,
  "body": { /* command payload */ },
  "dest": {"ref": "DEVICE_ID", "type": 1},
  "id": 1704825600000,
  "msg": 44,
  "resp": 2,
  "src": {"ref": "USER_ID", "type": 100},
  "time": 1704825600,
  "ver": "1.0"
}
```

### Message Types (MsgType)

Messages are JSON objects containing a `MsgType` (or `msg` in some responses) field.

| MsgType | Direction | Description                                |
|:--------|:----------|:-------------------------------------------|
| 3       | ← Device  | Batch Data (High-frequency energy readings)|
| 4       | ← Device  | Device Log (Info/Error/Debug JSON)         |
| 5       | → Device  | Killer Ping (Reset to pairing mode)        |
| 6       | → Device  | Settings Nudge (Force cloud-to-device sync)|
| 7       | → Device  | Metadata Dump (Request Info/FW/IP/Serial)   |
| 10      | ← Device  | Boot Status (IP, Firmware, Serial)         |
| 20      | ← Device  | Heartbeat / Status Request Response        |
| 30      | ← Device  | Telemetry (AC Only: 1s updates)            |
| 31      | ← Device  | ACState Object Dump (AC Only)              |
| 34      | → Device  | Event Hash / Sync (ver 3.0.0)              |
| 40      | ← Device  | State update (Automatic Broadcast)         |
| 44      | ← Device  | Command response                           |
| 61      | ← Device  | Firmware Report (Response to MsgType 20)   |


---

## Command Reference

### All Devices

#### Set Temperature
```json
{"cmd": [{"sp": 21.0, "stpt": 21.0, "a_sp": 21.0, "tm": -1}], "type": TYPE, "ver": 1}
```
- `sp` / `stpt` / `a_sp`: Target temperature in Celsius.
  - Heating (BB/INF): Supports `0.5°` increments.
  - Cooling (AC-V1): Supports `1.0°` increments only.
- `tm`: Timer (-1 = permanent)

#### Set HVAC Mode
```json
{"cmd": [{"md": MODE, "tm": -1}], "type": TYPE, "ver": 1}
```

**Thermostat modes (BB/INF):**
| Value | Mode |
|:------|:-----|
| 1     | Off  |
| 3     | Heat |

**AC modes (AC-V1):**
| Value | Mode     |
|:------|:---------|
| 1     | Off      |
| 2     | Auto     |
| 3     | Heat     |
| 4     | Cool     |
| 5     | Fan Only |
| 6     | Dry      |

- `lk`: 0 = Unlocked, 1 = Locked

#### Killer Ping (Reboot to Pairing)
```json
{
  "Device": "DEVICE_ID",
  "Timestamp": 1704825600,
  "MsgType": 5,
  "EchoID": 1
}
```
*Note: This message is sent WITHOUT the standard MsgType 44 envelope.*

#### Settings Nudge
```json
{
  "Device": "DEVICE_ID",
  "EventType": 0,
  "MsgType": 6,
  "Timestamp": 1704825600
}
```
*Note: This message is sent WITHOUT the standard MsgType 44 envelope. It is used to notify the cloud that settings were changed via HTTP, triggering a state push to the device.*

#### Metadata Dump (MsgType 7)
```json
{
  "Device": "DEVICE_ID",
  "Timestamp": 1704825600,
  "MsgType": 7
}
```
*Note: Request the device at its local IP to publish device-specific information including Firmware version, Local IP, Serial Number, and MAC address.*

---

### Diagnostic Messages (From Device)

#### Device Logs (MsgType 4)
Contains internal device logs, including local IP and serial number upon boot.
```json
{
  "Device": "DEVICE_ID",
  "Timestamp": 1704825600,
  "MsgType": 4,
  "Level": "INFO",
  "Message": "Local IP: 192.168.1.100"
}
```

#### Boot Status (MsgType 10)
Sent when the device reboots. Contains firmware version, boot count, and reason.
```json
{
  "device": "DEVICE_ID",
  "timestamp": 1704825600,
  "MsgType": 10,
  "bootTime": 1704825000,
  "bootCount": 1024,
  "version": "3.17.4.1",
  "ip": "192.168.1.100"
}
```

#### Heartbeat / State (MsgType 20)
Periodic status update from the device.
```json
{
  "Device": "DEVICE_ID",
  "Timestamp": 25,
  "MsgType": 20
}
```


---

### Batch Data (MsgType 3)
High-frequency voltage/current/power readings, sent to the `/batch` topic. The payload body contains a base64-encoded binary blob of `MysaReading` structs.

```json
{
  "msg": 3,
  "body": {
    "readings": "BASE64_ENCODED_DATA..."
  },
  "ts": 1704825600
}
```

The binary format generally follows 22 bytes of common data + version-specific trailer.

**Common Header (22 bytes):**
1. `Timestamp` (uint32, LE)
2. `SensorTemp` (int16, LE, /10.0)
3. `AmbTemp` (int16, LE, /10.0)
4. `Setpoint` (int16, LE, /10.0)
5. `Humidity` (int8)
6. `Duty` (int8)
7. `OnMs` (int16, LE)
8. `OffMs` (int16, LE)
9. `HeatSink` (int16, LE, /10.0)
10. `FreeHeap` (uint16, LE)
11. `RSSI` (int8, negated)
12. `State` (int8, 1=On, 0=Off)

**Version 3 Trailer (8 bytes):**
13. `Voltage` (int16, LE)
14. `Current` (int16, LE, /1000.0)
15. `Reserved` (3 bytes, 0x00)
16. `Checksum` (uint8, XOR of bytes 0-31)

---

### Heating Thermostats Only (BB/INF)

#### Set Proximity Mode (Wake on Approach)
```json
{"cmd": [{"pr": 1, "tm": -1}], "type": TYPE, "ver": 1}
```
- `pr`: 0 = Off, 1 = On

#### Set Brightness Settings
```json
{"cmd": [{"tm": -1, "br": {
  "a_b": 1,
  "a_br": 100,
  "i_br": 50,
  "a_dr": 60,
  "i_dr": 30
}}], "type": TYPE, "ver": 1}
```
- `a_b`: Auto brightness (0 = Off, 1 = On)
- `a_br`: Active brightness percentage (0-100)
- `i_br`: Idle brightness percentage (0-100)
- `a_dr`: Active duration in seconds
- `i_dr`: Idle duration in seconds

---

### AC Controller Only (AC-V1)

#### Set Fan Speed
```json
{"cmd": [{"fn": SPEED, "tm": -1}], "type": 2, "ver": 1}
```

| Value | Fan Speed   |
|:------|:------------|
| 1     | Auto        |
| 3     | Low         |
| 5     | Medium-Low  |
| 7     | Medium      |
| 8     | High        |
| 12    | Sleep       |

#### Set Vertical Swing
```json
{"cmd": [{"ss": POSITION, "tm": -1}], "type": 2, "ver": 1}
```

| Value | Position |
|:------|:---------|
| 3     | Auto     |
| 4     | Top      |
| 5     | Upper    |
| 6     | Middle   |
| 7     | Lower    |
| 8     | Low      |
| 9     | Bottom   |

#### Set Horizontal Swing
```json
{"cmd": [{"ssh": POSITION, "tm": -1}], "type": 2, "ver": 1}
```

| Value | Position     |
|:------|:-------------|
| 3     | Auto         |
| 4     | Left         |
| 5     | Left-Center  |
| 6     | Center       |
| 7     | Right-Center |
| 8     | Right-Wide   |
| 9     | Right        |

#### Set Climate+ Mode (Thermostatic Control)
```json
{"cmd": [{"it": 1, "tm": -1}], "type": 2, "ver": 1}
```
- `it`: 0 = Off (IR remote mode), 1 = On (uses Mysa temp sensor)

---

## HTTP API

Base URL: `https://app.mysa.cloud/api/v2`

### Polling & Synchronization
- **Poll Interval**: The integration polls `/devices` and `/devices/state` every **120 seconds** (2 minutes).
- **Staleness Logic**:
  1. **Timestamp Check (Primary)**: If an update contains a timestamp older than the latest known timestamp for the device, it is ignored.
  2. **90-Second Guard (Fallback)**: If no timestamp is present, HTTP updates are ignored if a command was sent to the device within the last **90 seconds**. This prevents "rubber-banding" from slow cloud APIs. Real-time MQTT updates are always accepted.

### Authentication

Uses AWS Cognito with JWT tokens. Include auth header on all requests.

### Endpoints

#### GET /homes
Returns list of homes and associated zones.
- `Id`: Home UUID
- `Zones`: Array of zone objects (`Id`, `Name`)
- `ERate`: Electricity rate in $/kWh (float)

#### GET /users
Returns current user information and paired devices.
- `Id`: User UUID
- `CognitoAttrs`: email, name, etc.
- `DevicesPaired`: State of all paired devices

#### GET /devices
Returns list of all devices with settings.

#### GET /devices/state
Returns live state (temperature, humidity, sensors) for all devices.

#### GET /devices/{device_id}
Returns settings for a specific device.

#### POST /devices/{device_id}
Update device settings or metadata.
**Advanced Example: Model Conversion (Lite to Full)**
```json
{"Model": "BB-V2-0"}  // Change model from BB-V2-0-L to BB-V2-0
```

**Common settings:**
```json
{"ButtonState": 1}          // Lock: 0=Unlock, 1=Lock
{"ecoMode": "0"}            // Eco: "0"=On, "1"=Off (inverted!)
{"ProximityMode": true}     // Wake on approach
{"AutoBrightness": true}    // Auto brightness
{"MinBrightness": 20}       // Idle brightness 0-100
{"MaxBrightness": 100}      // Active brightness 0-100
{"Format": "celsius"}       // Temperature unit
{"Name": "Living Room"}     // Device name
```

#### GET /devices/update_available/{device_id}
Returns firmware update information.

---

## State Fields

### Common Fields
| Field       | Description           | Type          |
|:------------|:----------------------|:--------------|
| Temperature | Current temperature   | float         |
| Humidity    | Current humidity      | int (0-100)   |
| SetPoint/sp/stpt | Target temperature | float         |
| Mode/md/mode | HVAC mode             | int           |
| Lock/lk     | Button lock state     | int (0/1)     |
| Rssi        | WiFi signal strength  | int (dBm)     |

### Heating Thermostat Fields
| Field         | Description              | Type        |
|:--------------|:-------------------------|:------------|
| Duty/dc       | Heater duty cycle        | int (0-100) |
| Voltage       | Line voltage             | float       |
| Current       | Line current             | float       |
| HeatSink      | Heat sink temperature    | float       |
| flrSnsrTemp   | Floor temperature (V2)   | float       |
| Brightness/br | Display brightness       | int/dict    |
| ProximityMode | Wake on approach         | bool        |

### AC Controller Fields
| Field                | Description           | Type |
|:---------------------|:----------------------|:-----|
| FanSpeed/fn          | Current fan speed     | int  |
| SwingState/ss        | Vertical swing pos    | int  |
| SwingStateHorizontal | Horizontal swing pos  | int  |
| IsThermostatic/it    | Climate+ enabled      | int  |
| TstatMode            | AC HVAC mode          | int  |
| CorrectedTemp        | Adjusted Temp (Priority) | float |
| SensorTemp           | Raw Sensor Temp (Elevated/Warning) | float |
