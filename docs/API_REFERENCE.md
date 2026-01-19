# Mysa HTTP API Reference

This document describes the HTTP REST API used by the Mysa cloud service.

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

### GET /users

Returns the current user's profile and device associations.

**Response:**
```json
{
  "User": {
    "Id": "user-uuid-string",
    "AllowedDevices": ["device-id-1", "device-id-2"],
    "AllowedHomes": ["home-uuid"],
    "PrimaryHome": "home-uuid",
    "ERate": "0.07",
    "LanguagePreference": "en-CA",
    "LastAppVersion": "4.11.0",
    "MysaIntegration": true,
    "DevicesPaired": {
      "State": {
        "BB": {
          "409151e40de0": {
            "deviceType": "BB-V2-0",
            "firstPairingTimestamp": 1701542924,
            "latestPairingTimestamp": 1736266276
          }
        },
        "AC": { },
        "INF": { }
      }
    },
    "CognitoAttrs": {
      "sub": "cognito-user-uuid",
      "email": "user@example.com",
      "email_verified": "true",
      "name": "User Name"
    }
  }
}
```

| Field | Type | Description |
|:------|:-----|:------------|
| `Id` | string | User UUID |
| `AllowedDevices` | string[] | Device IDs this user can control |
| `AllowedHomes` | string[] | Home UUIDs this user belongs to |
| `PrimaryHome` | string | Default home UUID |
| `ERate` | string | Electricity rate ($/kWh) |
| `MysaIntegration` | bool | Smart home integration flag (exact purpose unknown) |
| `DevicesPaired.State` | object | Pairing history by device type (BB/AC/INF) |

---

### GET /devices

Returns all devices accessible to the user.

**Response:**
```json
{
  "DevicesObj": {
    "409151e40de0": {
      "Id": "device-uuid",
      "Model": "BB-V2-0",
      "Name": "Office",
      "Home": "home-uuid",
      "Zone": "zone-uuid",
      "Owner": "user-uuid",
      "AllowedUsers": ["user-uuid"],
      "SetPoint": 21,
      "MinSetpoint": 5,
      "MaxSetpoint": 30,
      "Format": "celsius",
      "TimeZone": "America/Toronto",
      "Voltage": 240,
      "MaxCurrent": 5.03,
      "HeaterType": "pi",
      "Mode": {
        "Id": 1,
        "LastUpdated": 1768740918199
      },
      "ButtonState": "Unlocked",
      "Lock": 0,
      "ecoMode": 1,
      "ProximityMode": true,
      "AutoBrightness": true,
      "MinBrightness": 34,
      "MaxBrightness": 100,
      "Brightness": {
        "a_b": 0,
        "a_br": 100,
        "i_br": 10,
        "a_dr": 100,
        "i_dr": 10
      },
      "Animation": "off",
      "LastPaired": 1736266277
    }
  }
}
```

#### Device Fields

| Field | Type | Description |
|:------|:-----|:------------|
| `Id` | string | Device UUID (different from MAC-based key) |
| `Model` | string | Device model (see [Models](#device-models)) |
| `Name` | string | User-assigned name |
| `Home` | string | Home UUID |
| `Zone` | string | Zone UUID (optional) |
| `Owner` | string | Owner user UUID |
| `AllowedUsers` | string[] | Users who can control this device |
| `SetPoint` | number | Target temperature (°C) |
| `MinSetpoint` | number | Minimum allowed setpoint |
| `MaxSetpoint` | number | Maximum allowed setpoint |
| `Format` | string | `"celsius"` or `"fahrenheit"` |
| `Mode.Id` | number | Current HVAC mode |
| `Lock` | number | Button lock: 0=unlocked, 1=locked |
| `ecoMode` | number | Eco mode: 0=disabled, 1=enabled |

#### Brightness Settings (Heating Thermostats)

| Field | Type | Description |
|:------|:-----|:------------|
| `AutoBrightness` | bool | Auto brightness enabled |
| `MinBrightness` | number | Idle brightness (0-100) |
| `MaxBrightness` | number | Active brightness (0-100) |
| `Brightness.a_b` | number | Auto brightness flag |
| `Brightness.a_br` | number | Active brightness % |
| `Brightness.i_br` | number | Idle brightness % |
| `Brightness.a_dr` | number | Active duration (seconds) |
| `Brightness.i_dr` | number | Idle duration (seconds) |

#### AC-Specific Fields

| Field | Type | Description |
|:------|:-----|:------------|
| `IsThermostatic` | bool | Climate+ mode enabled |
| `SupportedCaps` | object | Supported modes, fan speeds, swing positions |
| `SupportedCaps.modes` | object | Available HVAC modes with capabilities |
| `SupportedCaps.tempRange` | number[] | [min, max] temperature range |
| `SupportedCaps.temperatureStep` | number | Temperature increment (usually 1) |

---

### GET /devices/state

Returns real-time state for all devices.

**Response:**
```json
{
  "DeviceStatesObj": {
    "409151e40de0": {
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
| `CorrectedTemp` | number | Calibrated room temperature (°C) |
| `SensorTemp` | number | Raw sensor temperature (°C) |
| `Humidity` | number | Relative humidity (0-100%) |
| `SetPoint` | number | Target temperature (°C) |
| `Mode` | number | HVAC mode ID |
| `TstatMode` | number | Thermostat operating mode |
| `Rssi` | number | WiFi signal strength (dBm) |
| `Lock` | number | Button lock state |

#### Heating Thermostat State

| Field | Type | Description |
|:------|:-----|:------------|
| `Duty` | number | Heater duty cycle (0-100%) |
| `Current` | number | Measured current (amps) |
| `Voltage` | number | Line voltage |
| `HeatSink` | number | Heat sink temperature (°C) |
| `OnTime` | number | Seconds heater was on |
| `OffTime` | number | Seconds heater was off |

#### AC Controller State

| Field | Type | Description |
|:------|:-----|:------------|
| `FanSpeed` | number | Current fan speed setting |
| `SwingState` | number | Vertical swing position |
| `SwingStateHorizontal` | number | Horizontal swing position |
| `IsThermostatic` | number | Climate+ mode (0/1) |
| `Delta` | number | Temperature delta |
| `ACState` | object | Raw AC unit state codes |

---

### GET /homes

Returns all homes the user has access to.

**Response:**
```json
{
  "Homes": [
    {
      "Id": "home-uuid",
      "Name": "My Home",
      "Owner": "user-uuid",
      "AllowedUsers": ["user-uuid"],
      "ERate": 0.07,
      "Address": {
        "formattedAddress": "123 Main St, City, State A1A 1A1, Country",
        "streetAddress": "123 Main St",
        "city": "City",
        "postalCode": "A1A 1A1",
        "countryShort": "CA",
        "countryLong": "Canada",
        "adminArea1Short": "ON",
        "adminArea1Long": "Ontario"
      },
      "Zones": [
        {
          "Id": "zone-uuid",
          "Name": "Basement",
          "Owner": "user-uuid"
        }
      ]
    }
  ]
}
```

| Field | Type | Description |
|:------|:-----|:------------|
| `Id` | string | Home UUID |
| `Name` | string | Home name |
| `Owner` | string | Owner user UUID |
| `AllowedUsers` | string[] | Users with access |
| `ERate` | number | Electricity rate ($/kWh) |
| `Address` | object | Location details |
| `Zones` | object[] | Room/zone groupings |

---

### GET /devices/update_available/{device_id}

Check for firmware updates for a specific device.

**Response:**
```json
{
  "UpdateAvailable": true,
  "CurrentVersion": "1.2.3",
  "AvailableVersion": "1.2.4",
  "ReleaseNotes": "Bug fixes and improvements"
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

## Device Models

| Model | Description | Payload Type |
|:------|:------------|:------------:|
| `BB-V1-0` | Baseboard V1 | 1 |
| `BB-V2-0` | Baseboard V2 | 4 |
| `BB-V2-0-L` | Baseboard V2 Lite | 5 |
| `AC-V1-0` | AC Controller | 2 |
| `INF-V1-0` | In-Floor Heating | 3 |

---

## HVAC Modes

### Heating Thermostats (BB/INF)

| Mode ID | Description |
|:--------|:------------|
| 1 | Off |
| 3 | Heat |

### AC Controller

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
