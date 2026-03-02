# Mysa Backend API Reference

**Base URL:** `https://mysa-backend.mysa.cloud`

This is the newer backend API used by the Mysa Android app (v4.11.0+). It coexists with the legacy [`app-prod.mysa.cloud` API](API_REFERENCE.md), with some endpoints duplicated and others unique to each backend.

## Authentication

Uses AWS Cognito with SRP (Secure Remote Password) authentication. See [Authentication Details](#authentication-details) below.

### Request Headers

```http
Authorization: <id_token>
Content-Type: application/json
User-Agent: okhttp/4.11.0
Accept: application/json
Accept-Encoding: gzip
```

---

## Endpoints

### Device State & Control

#### `POST /state/batch`

Get real-time state for multiple devices in one request.

**Request:**
```json
{
  "deviceIds": ["aabbccddeeff", "112233445566"]
}
```

**Response:**
```json
{
  "aabbccddeeff": {
    "data": {
      "latestTelemetry": {
        "isConnected": true,
        "lastConnected": 1770898771,
        "reading": {
          "deviceId": "aabbccddeeff",
          "timestamp": 1770898771,
          "rawTemperature": 20.96,
          "roomTemperature": 19.82,
          "humidity": 47,
          "coreTemperature": 22.37,
          "fanOnTime": 30,
          "onTime": 0,
          "hvacState": 0
        }
      }
    }
  }
}
```

**Fields:**
- `latestTelemetry.reading.roomTemperature` - Calibrated room temp (°C)
- `latestTelemetry.reading.rawTemperature` - Raw sensor temp (°C)
- `latestTelemetry.reading.humidity` - Relative humidity (%)
- `latestTelemetry.reading.hvacState` - HVAC operating state
- `latestTelemetry.isConnected` - Device online status
- `latestTelemetry.lastConnected` - Unix timestamp

> [!NOTE]
> This endpoint is used for ST-V1-0 (HVAC) devices. The response structure differs from the legacy `/devices/state` endpoint.

#### `GET /state/{device_id}`

Get state for a single device.

**Response:** Same structure as individual device in `/state/batch`.

#### `POST /state/{device_id}/update`

**ST-V1-0 Control Endpoint** - Send control commands to ST-V1-0 devices via HTTP POST.

**Request:**
```json
{
  "source": 3,
  "modes": {
    "mode": 4
  }
}
```

**Common Payloads:**

Set HVAC mode:
```json
{"source": 3, "modes": {"mode": 4}}
// 0=Off, 1=Auto, 3=Cool, 4=Heat, 7=Fan
```

Set heat setpoint (decimal degrees Celsius):
```json
{"source": 3, "targetHeat": {"setpoint": 21.5}}
```

Set cool setpoint (decimal degrees Celsius):
```json
{"source": 3, "targetCool": {"setpoint": 24.0}}
```

Set auto mode range:
```json
{
  "source": 3,
  "targetAuto": {
    "heatSetpoint": 20.0,
    "coolSetpoint": 25.0
  }
}
```

Set temperature format:
```json
{"source": 3, "physicalInterface": {"format": "F"}}
// "C" or "F"
```

Set lockout (button lock):
```json
{"source": 3, "physicalInterface": {"lockout": 3}}
// 1=Unlocked, 3=Locked
```

**Source Values:**
- `3` = Mobile App (recommended)
- `4` = Device/Cloud Integrations

> [!IMPORTANT]
> **Temperature Precision**: All setpoint values are sent as **decimal degrees** (float), not decidegrees (int). Examples: `21.5`, `14.44`, `16.7` (supports 0.5°C precision).

> [!TIP]
> The official Mysa app uses HTTP POST for all ST-V1-0 control commands. MQTT is used only for reactive feedback (shadow updates).

---

### User Information

#### `GET /users`

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
          "000000000000": {
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

### Device Information

#### `GET /devices`

Returns all devices accessible to the user (same as legacy API).

**Response:**
```json
{
  "DevicesObj": {
    "000000000000": {
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

#### Brightness Settings (Electric Heat)

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

#### `POST /devices/{device_id}`

Update device settings (HTTP endpoint for settings that can't be changed via MQTT).

**Common Settings:**
```json
{"Name": "Living Room"}
{"Format": "celsius"}
{"ButtonState": "Locked"}
```

#### `GET /devices/update_available/{device_id}`

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

### Home Information

#### `GET /homes`

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

### Scheduling

#### `GET /schedule`

Get schedules for all devices.

#### `POST /schedule`

Create or update a schedule.

---

### IoT/MQTT

#### `GET /iot-token`

Get AWS IoT Core credentials for MQTT connection.

**Response:**
```json
{
  "endpoint": "a3q27gia9qg3zy-ats.iot.us-east-1.amazonaws.com",
  "credentials": {
    "accessKeyId": "ASIA...",
    "secretAccessKey": "...",
    "sessionToken": "..."
  },
  "expiration": 1770902238
}
```

> [!IMPORTANT]
> This endpoint returns temporary AWS credentials for establishing MQTT WebSocket connections to AWS IoT Core. Credentials expire after ~1 hour.

---

### Capabilities

#### `GET /capabilities/{device_id}`

Get device capabilities (supported features, modes, temperature ranges, and configuration).

**ST-V1-0 Response:**
```json
{
  "system": {
    "info": {
      "model": "ST-V1-0",
      "configCode": "0x25"
    },
    "hardwareSensors": {
      "temperature": true,
      "humidity": true
    }
  },
  "features": {
    "climateControl": {
      "mode": {
        "supportedModes": ["off", "auto", "cool", "heat", "fan_only"]
      },
      "heat": {
        "stages": 1,
        "setpoint": {
          "userControllable": true,
          "type": "float",
          "validValues": [5, 5.5, 6, 6.5, 7, 7.5, 8, 8.5, 9, 9.5, 10, 10.5, 11, 11.5, 12, 12.5, 13, 13.5, 14, 14.5, 15, 15.5, 16, 16.5, 17, 17.5, 18, 18.5, 19, 19.5, 20, 20.5, 21, 21.5, 22, 22.5, 23, 23.5, 24, 24.5, 25, 25.5, 26, 26.5, 27, 27.5, 28, 28.5, 29, 29.5, 30]
        }
      },
      "cool": {
        "stages": 1,
        "setpoint": {
          "userControllable": true,
          "type": "float",
          "validValues": [16, 16.5, 17, 17.5, 18, 18.5, 19, 19.5, 20, 20.5, 21, 21.5, 22, 22.5, 23, 23.5, 24, 24.5, 25, 25.5, 26, 26.5, 27, 27.5, 28, 28.5, 29, 29.5, 30, 30.5, 31, 31.5, 32, 32.5, 33, 33.5, 34, 34.5, 35, 35.5, 36, 36.5, 37]
        }
      },
      "advancedConfig": {
        "cyclesPerHour": {
          "userControllable": true,
          "validValues": [1, 2, 3, 4, 5, 6, 9, 12]
        },
        "deadband": {
          "userControllable": true,
          "type": "float",
          "validValues": [0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4]
        }
      },
      "fan": {
        "manualControl": false,
        "speeds": null
      }
    },
    "interface": {
      "wakeOnApproach": {
        "supported": true,
        "userControllable": true
      },
      "lockout": {
        "supported": true,
        "userControllable": true,
        "levels": ["unlocked", "partial", "full"]
      },
      "brightness": {
        "supported": true,
        "userControllable": true,
        "range": [0, 100]
      },
      "units": {
        "supported": true,
        "userControllable": true,
        "options": ["C", "F"]
      }
    },
    "smartFeatures": {
      "energyReporting": true,
      "scheduling": true,
      "alerts": true
    }
  }
}
```

**Key Fields:**
- `features.climateControl.heat.setpoint.validValues` - Supported temperature steps (0.5°C increments)
- `features.climateControl.mode.supportedModes` - Available HVAC modes
- `features.climateControl.heat.stages` - Number of heating stages
- `features.climateControl.cool.stages` - Number of cooling stages
- `features.climateControl.advancedConfig.cyclesPerHour.validValues` - CPH options
- `features.interface.lockout.levels` - Lockout modes

> [!TIP]
> Use `validValues` arrays to determine:
> - Temperature step precision (e.g., [5, 5.5, 6, ...] → 0.5°C step)
> - Temperature min/max (first and last values in array)
> - Available configuration options

---

### Telemetry & Usage

#### `GET /telemetry/usage/{device_id}`

Get historical energy usage data for ST-V1-0 devices.

**Query Parameters:**
- `startDate` - ISO 8601 date (e.g., `2026-02-01T00:00:00Z`)
- `endDate` - ISO 8601 date
- `granularity` - `hourly`, `daily`, or `monthly`

**Response:**
```json
{
  "deviceId": "aabbccddeeff",
  "data": [
    {
      "timestamp": "2026-02-01T00:00:00Z",
      "runtime": 3600,
      "energyUsed": 1.5
    }
  ]
}
```

---

### Feature Flags

### Feature Flags

#### `GET /feature-flags/features/check`

Check which feature flags are enabled for the current user.

**Query Parameters:**
- `versionNumber` - App version (e.g., `4.12.1`)

**Response:**
```json
{
  "features": {
    "LV_AUTOMODE_FW": {"value": true},
    "LV_ACCESS": {"value": true},
    "LV_STAGED_AUX_HEAT_FW": {"value": true},
    "LV_ADAPTIVE_BRIGHTNESS_FW": {"value": true},
    "HIDE_MATTER_IN_APP": {"value": true}
  }
}
```

> [!NOTE]
> This endpoint is read-only. Feature flags are controlled server-side.

---

### Demand Response (Utility Integration)

#### `GET /demand-response/applications/utility-details`

Get utility program details by postal code.

**Query Parameters:**
- `postalCode` - Postal/ZIP code (URL encoded)

**Response:**
```json
[]  // or array of available utility programs
```

#### `GET /demand-response/applications`

Get active demand response applications.

**Query Parameters:**
- `homeId` - Home UUID

**Response (404 if not enrolled):**
```json
{
  "message": "Application not found for the specified home"
}
```

---

## Authentication Details

### AWS Cognito Configuration

```python
REGION = "us-east-1"
USER_POOL_ID = "us-east-1_GUFWfhI7g"
CLIENT_ID = "6cktj934gasnc72f7jo2cmf6rt"  # Android app v4.11.0+
IDENTITY_POOL_ID = "us-east-1:e27f246e-ad23-41ce-ac80-eda86f8be424"
```

### Authentication Flow

1. **Cognito SRP Authentication**
   - `InitiateAuth` with `USER_SRP_AUTH` flow
   - `RespondToAuthChallenge` with PASSWORD_VERIFIER
   - Receive: Access Token, ID Token, Refresh Token

2. **Get Identity Pool Credentials**
   - `GetId` from Cognito Identity Pool (using ID Token)
   - `GetCredentialsForIdentity` to get temporary AWS credentials
   - Receive: Access Key, Secret Key, Session Token

3. **Use Tokens**
   - **HTTP API**: Use ID Token in `Authorization` header
   - **MQTT/IoT**: Sign WebSocket URL with AWS SigV4 using temporary credentials

### Token Lifecycle

| Token | Lifetime | Purpose |
|-------|----------|---------|
| Access Token | 1 hour | API authorization |
| ID Token | 1 hour | Contains user profile, used for HTTP API |
| Refresh Token | Long-lived | Obtain new access/ID tokens |
| AWS Credentials | ~1 hour | Sign MQTT WebSocket connections |

---

## Migration from Legacy API

### Endpoint Mapping

| Legacy (`app-prod.mysa.cloud`) | New (`mysa-backend.mysa.cloud`) | Notes |
|--------------------------------|----------------------------------|-------|
| `GET /devices/state` | `POST /state/batch` | Different response structure |
| `GET /devices/{id}/state` | `GET /state/{id}` | - |
| - | `POST /state/{id}/update` | **New** - ST-V1 control via HTTP |
| `POST /devices/{id}` | `POST /devices/{id}` | Both APIs support this |
| `GET /users` | `GET /users` | Both APIs support this |
| `GET /devices` | `GET /devices` | Both APIs support this |
| `GET /homes` | `GET /homes` | Both APIs support this |
| `GET /devices/update_available/{id}` | `GET /devices/update_available/{id}` | Both APIs support this |
| `GET /devices/firmware` | - | **Legacy only** - Batch firmware lookup |
| - | `GET /iot-token` | **New** - MQTT credentials |
| - | `GET /capabilities/{id}` | **New** - Device caps |
| - | `GET /telemetry/usage/{id}` | **New** - Energy usage history |
| - | `GET /schedule/hold/{id}` | **New** - Schedule override status |
| - | `POST /feature-flags/features/check` | **New** - A/B testing |
| `PUT /homes/{id}` | `PUT /homes/{id}` | Both APIs support (ERate, Name) |

> [!NOTE]
> The integration uses a **hybrid approach** for ST-V1-0 devices:
> - **HTTP**: All control commands (`POST /state/{id}/update`) and sensor polling (`POST /state/batch`)
> - **MQTT**: Reactive feedback only (listen for shadow updates)
>
> This matches the official Mysa app behavior and provides better reliability than MQTT-only control.

### Response Structure Changes

**Legacy State (`/devices/state`):**
```json
{
  "CorrectedTemp": {"t": 1768748867, "v": 20.1},
  "Humidity": {"t": 1768748867, "v": 43}
}
```

**New State (`/state/batch`):**
```json
{
  "latestTelemetry": {
    "reading": {
      "roomTemperature": 19.82,
      "humidity": 47,
      "timestamp": 1770898771
    }
  }
}
```

---

## Related Documentation

- [Legacy API Reference](API_REFERENCE.md) - Original `app-prod.mysa.cloud` API
- [MQTT HVAC Shadow Protocol](MQTT_HVAC_SHADOW.md) - ST-V1-0 device shadows
- [MQTT Protocol](MQTT_PROTOCOL.md) - General MQTT message types

---

## Notes

- Both backends are currently active and used by the app
- Device IDs are MAC addresses (lowercase, no colons)
- All temperatures in Celsius (except when explicitly in decidegrees)
- Timestamps are Unix seconds unless otherwise noted
- SRP authentication ensures password never transmitted over network
