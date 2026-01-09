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

---

## MQTT Protocol

### Connection

MQTT is delivered over WebSocket using AWS IoT Core. Connection requires:
1. AWS Cognito authentication
2. SigV4-signed WebSocket URL
3. MQTT protocol version 3.1.1

### Topics

Each device has three topics:
- `/v1/dev/{device_id}/in` - Commands TO device
- `/v1/dev/{device_id}/out` - State FROM device  
- `/v1/dev/{device_id}/batch` - Batch updates

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

### Message Types

| MsgType | Direction | Description                    |
|:--------|:----------|:-------------------------------|
| 6       | → Device  | Settings changed notification  |
| 40      | ← Device  | State update                   |
| 44      | → Device  | Command (wrapped)              |
| 44      | ← Device  | Command response               |

---

## Command Reference

### All Devices

#### Set Temperature
```json
{"cmd": [{"sp": 21.0, "stpt": 21.0, "a_sp": 21.0, "tm": -1}], "type": TYPE, "ver": 1}
```
- `sp` / `stpt` / `a_sp`: Target temperature in Celsius (supports 0.5° increments)
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

#### Set Button Lock
```json
{"cmd": [{"lk": 1, "tm": -1}], "type": TYPE, "ver": 1}
```
- `lk`: 0 = Unlocked, 1 = Locked

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

### Authentication

Uses AWS Cognito with JWT tokens. Include auth header on all requests.

### Endpoints

#### GET /users
Returns current user information.

#### GET /devices
Returns list of all devices with settings.

#### GET /devices/state
Returns live state (temperature, humidity, sensors) for all devices.

#### GET /devices/{device_id}
Returns settings for a specific device.

#### POST /devices/{device_id}
Update device settings. Body is JSON with settings to change.

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
| SetPoint/sp | Target temperature    | float         |
| Mode/md     | HVAC mode             | int           |
| Lock/lk     | Button lock state     | int (0/1)     |
| Rssi        | WiFi signal strength  | int (dBm)     |

### Heating Thermostat Fields
| Field         | Description              | Type        |
|:--------------|:-------------------------|:------------|
| Duty/dc       | Heater duty cycle        | int (0-100) |
| Voltage       | Line voltage             | float       |
| Current       | Line current             | float       |
| HeatSink      | Heat sink temperature    | float       |
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
