# Mysa HTTP API Reference (Legacy)

**Base URL:** `https://app-prod.mysa.cloud`

> [!NOTE]
> This is the **legacy API**. The newer `mysa-backend.mysa.cloud` API is documented in [BACKEND_API.md](BACKEND_API.md). Both APIs are currently in use.

This document describes the original HTTP REST API used by the Mysa cloud service.

## Base URL

```
https://app-prod.mysa.cloud
```

## Authentication

All requests require AWS Cognito authentication. Include the ID token in the `Authorization` header:

```
Authorization: <id_token>
```

### Headers

```
authorization: <id_token>
content-type: application/json
x-requested-with: XMLHttpRequest
```

---

## Endpoints



### GET /devices/state

Returns real-time state for all devices.

**Response:**
```json
{
  "DeviceStatesObj": {
    "000000000000": {
      "Device": "device-uuid",
      "Timestamp": 1768748867,
      "Connected": { "t": 1768722229972, "v": true },
      "CorrectedTemp": { "t": 1768748867, "v": 20.1 },
      "SensorTemp": { "t": 1768748867, "v": 23.8 },
      "Humidity": { "t": 1768748867, "v": 43 },
      "SetPoint": { "t": 1768748867, "v": 20 },
      "Mode": { "t": 1768748867, "v": 1 },
      "Duty": { "t": 1768748867, "v": 0 },
      "Current": { "t": 1768748867, "v": 4.52 },
      "Voltage": { "t": 1768748867, "v": 240 },
      "HeatSink": { "t": 1768748867, "v": 27.8 },
      "Rssi": { "t": 1768748867, "v": -28 },
      "Lock": { "t": 1768740918, "v": 0 },
      "Brightness": { "t": 1768740918, "v": 72 },
      "ScheduleMode": { "t": 1768740918, "v": 1 },
      "HoldTime": { "t": 1768740918, "v": -1 },
      "TstatMode": { "t": 1768748867, "v": 3 },
      "FreeHeap": { "t": 1768748867, "v": 68050 }
    }
  }
}
```

#### State Value Format

All state values use a timestamp/value object:
```json
{ "t": 1768748867, "v": 20.1 }
```
- `t`: Unix timestamp when value was recorded
- `v`: The actual value

#### Common State Fields

| Field | Type | Description |
|:------|:-----|:------------|
| `Connected` | bool | Device online status |
| `CorrectedTemp` | number | Calibrated room temperature (°C) - **Priority for UI** |
| `SensorTemp` | number | Raw sensor temperature (°C) - Elevated by device heat. **Warning logged if used as fallback.** |
| `Humidity` | number | Relative humidity (0-100%) |
| `SetPoint` | number | Target temperature (°C) |
| `Mode` | number | HVAC mode ID |
| `TstatMode` | number | Operating mode |
| `Rssi` | number | WiFi signal strength (dBm) |
| `Lock` | number | Button lock state |

#### Electric Heat State

| Field | Type | Description |
|:------|:-----|:------------|
| `Duty` | number | Heater duty cycle (0-100%) |
| `Current` | number | Measured current (amps) |
| `Voltage` | number | Line voltage |
| `HeatSink` | number | Heat sink temperature (°C) |
| `OnTime` | number | Seconds heater was on |
| `OffTime` | number | Seconds heater was off |

#### Mini-Split Heat Pump State

| Field | Type | Description |
|:------|:-----|:------------|
| `FanSpeed` | number | Current fan speed setting |
| `SwingState` | number | Vertical swing position |
| `SwingStateHorizontal` | number | Horizontal swing position |
| `IsThermostatic` | number | Climate+ mode (0/1) |
| `Delta` | number | Temperature delta |
| `ACState` | object | Raw codes: `1`:Power, `2`:Mode, `3`:Temp, `4`:Fan, `5`:Swing |
| `FanSpeed` | number | Current fan speed setting (also in `fn`) |

---

### GET /devices/firmware

Batch endpoint to get firmware versions for all accessible devices.

**Response:**
```json
{
  "Firmware": {
    "000000000000": {
      "InstalledVersion": "1.2.3"
    },
    ...
  }
}
```

---

### POST /devices/{device_id}

Update device settings.

**Request Body Examples:**

```json
{"Name": "Living Room"}
{"SetPoint": 21.5}
{"ButtonState": "Locked"}
{"ecoMode": 0}
{"ProximityMode": true}
{"Format": "fahrenheit"}
{"Model": "BB-V2-0"}  // Upgrade Lite to Full
```

**Response:** Updated device object

---

### DELETE /devices/{device_id}

Remove a device from the user account.

**Example:**
```http
DELETE https://app-prod.mysa.cloud/devices/aabbccddeeff
```

**Response:** Status 200 OK

---

## Device Models

| Model | Description | Payload Type |
|:------|:------------|:------------:|
| `BB-V1-0` | Baseboard V1 | 1 |
| `BB-V2-0` | Baseboard V2 | 4 |
| `BB-V2-0-L` | Baseboard V2 Lite | 5 |
| `AC-V1-0` | Mini-Split Heat Pump | 2 |
| `INF-V1-0` | In-Floor Heating | 3 |

---

## HVAC Modes

### Electric Heat (Baseboard/Floor)

| Mode ID | Description |
|:--------|:------------|
| 1 | Off |
| 3 | Heat |

### Mini-Split Heat Pumps

| Mode ID | Description |
|:--------|:------------|
| 1 | Off |
| 2 | Auto |
| 3 | Heat |
| 4 | Cool |
| 5 | Fan Only |
| 6 | Dry |

---

## Error Responses

```json
{
  "error": "Unauthorized",
  "message": "Token expired"
}
```

| Status | Description |
|:-------|:------------|
| 401 | Authentication required or token expired |
| 403 | Access denied to resource |
| 404 | Device or resource not found |
| 500 | Server error |

---

## Notes

- All temperatures are in Celsius
- Device keys in `DevicesObj` and `DeviceStatesObj` are MAC addresses (lowercase, no colons)
- The `Id` field inside device objects is a UUID, different from the MAC-based key
- State timestamps are Unix timestamps in seconds
- Connected timestamp may be in milliseconds (13 digits)
