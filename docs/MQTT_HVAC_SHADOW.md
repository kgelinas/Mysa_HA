# Mysa MQTT Central HVAC (ST-V1) Shadow Protocol

This document details the MQTT shadow protocol used by Mysa Central HVAC (ST-V1) devices. These devices use AWS IoT Device Shadows for state management and control.

> [!TIP]
> See also: [Backend API Reference](BACKEND_API.md) for HTTP endpoints including `/iot-token` for MQTT credentials and `/state/batch` for device telemetry.

## Topic Structure

*   **Update Topic:** `$aws/things/{safe_device_id}/shadow/name/{shadow_name}/update`
*   **Get Topic:** `$aws/things/{safe_device_id}/shadow/name/{shadow_name}/get`

**`{safe_device_id}`**: MAC address with colons removed, lowercase (e.g., `abc123def456`).
**`{shadow_name}`**: The specific shadow (e.g., `modes`, `targetHeat`, `physicalInterface`).

## Payload Structure

### Request (Update)
```json
{
  "state": {
    "desired": {
      "key": value,
      "source": 3
    }
  }
}
```

**`source` Values:**
| Value | Meaning |
|:---:|:---|
| `3` | Mobile App command |
| `4` | Device/Cloud Integrations |
| `16` | System (unit conversion) |

---

## 1. Modes Shadow (`modes`)

Controls operation mode, fan, and HVAC state.

| Key | Type | Description | Values |
|:---|:---|:---|:---|
| `mode` | int | HVAC Operation Mode | `0`=Off, `1`=Auto, `3`=Cool, `4`=Heat, `7`=Fan |
| `fan_mode` | int | Fan Mode | `0`=Auto |
| `hvacState` | int | Running State | `0`=Idle, `4`=Active |
| `lockoutModes` | int | Mode Permissions | observed: `255` |
| `autoDeadband` | int | Auto Mode Deadband | decidegrees (e.g., `150`=1.5°C) |

---

## 2. Target Heat Shadow (`targetHeat`)

Heating setpoint and limits. **All values in Celsius decidegrees.**

| Key | Type | Description | Writable |
|:---|:---|:---|:---:|
| `setpoint` | int | Current heating target | ✅ |
| `lockoutMax` | int | User-configurable max limit | ✅ |
| `lockoutMin` | int | User-configurable min limit | ✅ |
| `max` | int | System absolute max (3000) | ❌ |
| `min` | int | System absolute min (500) | ❌ |

---

## 3. Target Cool Shadow (`targetCool`)

Cooling setpoint and limits. **All values in Celsius decidegrees.**

| Key | Type | Description | Writable |
|:---|:---|:---|:---:|
| `setpoint` | int | Current cooling target | ✅ |
| `lockoutMax` | int | User-configurable max limit | ✅ |
| `lockoutMin` | int | User-configurable min limit | ✅ |
| `max` | int | System absolute max (3700) | ❌ |
| `min` | int | System absolute min (1600) | ❌ |

---

## 4. Target Auto Shadow (`targetAuto`)

Auto mode (Heat/Cool) configuration.

| Key | Type | Description | Writable |
|:---|:---|:---|:---:|
| `heatSetpoint` | int | Heating target (decidegrees) | ✅ |
| `coolSetpoint` | int | Cooling target (decidegrees) | ✅ |
| `deadband` | int | Gap between setpoints | ✅ |
| `enabled` | int | Auto mode enabled (`0`/`1`) | ✅ |
| `activeMode` | int | Current active action | ❌ (read-only) |

**`activeMode` Values:** `0`=Idle, `3`=Cooling, `4`=Heating, `7`=Fan

---

## 5. Physical Interface Shadow (`physicalInterface`)

Display and button settings.

| Key | Type | Description | Values |
|:---|:---|:---|:---|
| `format` | str | Temperature unit | `"C"` or `"F"` |
| `activeIntensity` | int | Display brightness (active) | 0-100 |
| `idleIntensity` | int | Display brightness (idle) | 0-100 |
| `wakeOnApproach` | int | Proximity wake | `0`/`1` |
| `woaSensitivity` | int | Wake sensitivity | 0-100 |
| `lockout` | int | Button lock state | `1`=Unlocked, `3`=Locked |
| `allowedMax` | int | Max temp limit (read-only) | |
| `allowedMin` | int | Min temp limit (read-only) | |

---

## 6. HVAC Config Shadow (`hvacConfig`)

Full HVAC system configuration (30+ keys). Key subset:

### Fan Configuration
| Key | Description |
|:---|:---|
| `advFanRuntimeSeconds` | Fan runtime per cycle |
| `advFanRuntimePeriodSeconds` | Cycle period (1800=30min, 3600=1hr) |
| `advFanAlwaysOn` | Fan always on (0/1) |
| `advFanRampMinutes` | Fan ramp-up time |
| `advCoolFanDelayMinutes` | Delay before cooling fan starts |
| `advHeatFanDelayMinutes` | Delay before heating fan starts |
| `advCoolFanRunOnMinutes` | Cooling fan run-on time |
| `advHeatFanRunOnMinutes` | Heating fan run-on time |
| `advMaxCoolFanSpeed` | Max cooling fan speed |
| `advMaxHeatFanSpeed` | Max heating fan speed |
| `multiple_fan_speeds` | Supports multi-speed fan (`0`/`1`) |
| `fan_sequence` | Fan relay sequence logic |

### Staging Configuration
| Key | Description |
|:---|:---|
| `advHeatStageOneCph` | Heat stage 1 cycles/hour |
| `advCoolStageOneCph` | Cool stage 1 cycles/hour |
| `advHeatStageTwoDelta` | Stage 2 heat delta (decidegrees) |
| `advCoolStageTwoDelta` | Stage 2 cool delta (decidegrees) |
| `advHeatStageTwoDelayMinutes` | Stage 2 heat delay |
| `advCoolStageTwoDelayMinutes` | Stage 2 cool delay |

### System Features
| Key | Description |
|:---|:---|
| `heating_stage_one_exists` | Has stage 1 heating |
| `cooling_stage_one_exists` | Has stage 1 cooling |
| `fan_circuit_exists` | Has fan circuit |
| `advCompressorMinOffTimeMinutes` | Compressor min off time |
| `advFreezeProtectionTemp` | Freeze protection (decidegrees) |

---

## HVAC Configuration Codes (Decoding)

The `hvac_config_index` corresponds to a 3-digit alphanumeric code (e.g., **61B**, **16B**) that defines the system capabilities.

### Digit 1: Heating Type
| Digit | Heating System | Stages | Cycle Rate (CPH) | Relays |
|:---:|:---|:---|:---|:---|
| 0 | No Heating | N/A | N/A | N/A |
| 1 | Forced-Air (Gas/Oil) | 1 | 6 (10m) | W1 |
| 2 | Forced-Air (Electric) | 1 | 12 (5m) | W1 |
| 3 | Forced-Air (Heatpump) | 1 | 3 (20m) | Y1 |
| 4 | Hydronic (Radiant/FCU) | 1 | 3 (20m) | W1 |
| 6 | **Forced-Air (Gas/Oil)** | **2** | 6 (10m) | **W1, W2** |
| 7 | **Forced-Air (Electric)** | **2** | 12 (5m) | **W1, W2** |
| 8 | **Forced-Air (Heatpump)** | **2** | 3 (20m) | **Y1, Y2** |
| 9 | **Hydronic** | **2** | 3 (20m) | **W1, W2** |

> **Key Feature:** Digits 6-9 enable `heating_stage_two_exists`.

### Digit 2: Cooling Type
| Digit | Cooling System | Stages | Cycle Rate (CPH) | Relays |
|:---:|:---|:---|:---|:---|
| 0 | No Cooling | N/A | N/A | N/A |
| 1 | Forced-Air (AC & HP) | 1 | 3 (20m) | Y1 |
| 4 | Fan Coil, 2 Fan Spd | 1 | TBD | Y1 |
| 5 | Fan Coil, 3 Fan Spd | 1 | TBD | Y1 |
| 6 | **Forced-Air (AC & HP)** | **2** | 3 (20m) | **Y1, Y2** |

> **Key Feature:** Digit 6 enables `cooling_stage_two_exists`.

### Digit 3: Features & Valve Logic
| Digit | Fan | Aux | HP | Rev/Valve | Notes |
|:---:|:---:|:---:|:---:|:---:|:---|
| A | N | N | N | N/A | No Fan Control |
| B | **Y** | N | N | N/A | Standard (Gas/Electric/Boiler) |
| L | **Y** | **Y** | **Y** | **B-Valve** | HP (Heat Active) |
| P | **Y** | **Y** | **Y** | **O-Valve** | HP (Cool Active) |

> **Key Feature:**
> *   `L` sets `advCoolWhenReversed=0`
> *   `P` sets `advCoolWhenReversed=1`
> *   `L` & `P` enable `is_reversible_heat_pump=1`

### Common Configuration Codes
| Code | Index | System Description | Key Features |
|:---:|:---:|:---|:---|
| **11B** | 19 | 1H/1C Gas/Oil | Standard |
| **61B** | 103 | 2H/1C Gas/Oil | `heating_stage_two_exists` |
| **16B** | 27 | 1H/2C Gas/Oil | `cooling_stage_two_exists` |
| **26B** | 43 | 1H/2C Electric | `cooling_stage_two_exists` |
| **66B** | 107 | 2H/2C Gas/Oil | `heating_stage_two_exists`, `cooling_stage_two_exists` |
| **71B** | 115 | 2H/1C Electric | `heating_stage_two_exists` |
| **76B** | 119 | 2H/2C Electric | `heating_stage_two_exists`, `cooling_stage_two_exists` |
| **21B** | 35 | 1H/1C Electric | |
| **31L** | 57 | 1H/1C HP (B) | `is_reversible_heat_pump`, `B-Valve` |
| **31P** | 61 | 1H/1C HP (O) | `is_reversible_heat_pump`, `O-Valve` |

---

## Stage 2 Configuration

Enable and configure Stage 2 heating/cooling in `hvacConfig` (requires 61B config):

| Key | Type | Range | Confirmed |
|:---|:---|:---|:---:|
| `heating_stage_two_exists` | int | 0/1 | ✅ |
| `advHeatStageTwoDelta` | int | decidegrees (50 increments) | ✅ |
| `advHeatStageTwoDelayMinutes` | int | 1-120 (10 min increments) | ✅ |
| `advHeatStageTwoCph` | int | cycles/hour | default |
| `cooling_stage_two_exists` | int | 0/1 | — |
| `advCoolStageTwoDelta` | int | decidegrees | — |

---

## Heat Pump Keys (Future)

Present in shadow but UI-locked unless on 31P/31L config:

| Key | Description |
|:---|:---|
| `is_reversible_heat_pump` | Has reversing valve |
| `advCoolWhenReversed` | O/B valve logic |
| `advCompressorMinOffTimeMinutes` | Compressor protection |
| `heat_stage_one_uses_heat_pump` | HP for heating |
| `cool_stage_one_uses_heat_pump` | HP for cooling |
| `advHeatStageTwoDelta` | Stage 2 Heat Delta |
| `advHeatStageTwoDelayMinutes` | Stage 2 Heat Delay (Minutes) |
| `advCoolStageTwoDelta` | Stage 2 Cool Delta |
| `advCoolStageTwoDelayMinutes` | Stage 2 Cool Delay (Minutes) |

---

## Temperature Conversion

**All setpoints stored in Celsius decidegrees regardless of display unit.**

```
Fahrenheit → Celsius decidegrees:
decidegrees = (°F - 32) × 5/9 × 100

Examples:
- 62°F → 1667
- 68°F → 2000
- 80°F → 2667
- 97°F → 3611
```

---

## Write Operations (Commands)

All commands are sent to the `.../shadow/name/{shadow}/update` topic with a `desired` state.

### 1. Change Mode
**Shadow:** `modes`
```json
{
  "state": {
    "desired": {
      "mode": 3,
      "source": 3
    }
  }
}
```
*   `mode`: `0`=Off, `1`=Auto, `3`=Cool, `4`=Heat, `7`=Fan Only.

### 2. Change Setpoint (Heat Mode)
**Shadow:** `targetHeat`
```json
{
  "state": {
    "desired": {
      "setpoint": 2111,
      "source": 3
    }
  }
}
```
*   `setpoint`: Temperature in Celsius decidegrees.

### 3. Change Setpoint (Cool Mode)
**Shadow:** `targetCool`
```json
{
  "state": {
    "desired": {
      "setpoint": 2389,
      "source": 3
    }
  }
}
```

### 4. Change Setpoints (Auto Mode)
**Shadow:** `targetAuto`
```json
{
  "state": {
    "desired": {
      "heatSetpoint": 1556,
      "coolSetpoint": 2222,
      "source": 3
    }
  }
}
```
*   Payload can include `heatSetpoint`, `coolSetpoint`, or both.

---

## State Reporting Flow

1.  **Command Execution:** The client publishes to `.../shadow/name/{shadow}/update` with `desired` values.
2.  **AWS IoT Acceptance:**
    *   `.../update/accepted`: The request was valid and accepted by the shadow service.
    *   `.../update/rejected`: The request was invalid (e.g., bad format, read-only key). Payload contains `code` and `message`.
    *   `.../update/delta`: A difference exists between `desired` and `reported` state. This triggers the device to act.
3.  **Device Sync:** The device receives the `delta`, applies the setting, and reports back.
4.  **State Documentation:** The complete updated state is published to `.../shadow/name/{shadow}/update/documents`.
    *   `current.state.reported` contains the true state of the device.
    *   `current.state.desired` contains the last requested target.

---

## Telemetry & Sensors

These values are typically reported in the root of the shadow or in a standard status update message (MsgType 1), often interleaved with other shadow updates.

| Key | Description | Source |
|:---|:---|:---|
| `ambTemp` | Ambient Temperature (Raw) | Primary Sensor |
| `CorrectedTemp` | Ambient Temperature (Calibrated) | Primary Sensor |
| `ambient_t` | Ambient Temperature (Legacy) | Alternate Key |
| `hum` | Humidity | Sensor |
| `Humidity` | Humidity (Alternate) | Sensor |
| `humidityDisplay` | Display Humidity | Sensor (UI Optimized) |
| `externalTemperature` | External Temperature | Wired Sensor |
| `outdoorTemperature` | Outdoor Temperature | Wired Sensor (Alternate) |
| `filter` | Filter life remaining | Diagnostic |

### ST1 (Modern) Telemetry Structure

For newer models like **ST1 (HVAC Central)**, sensor data is not reported in traditional named shadows. Instead, it is delivered via a complex object structure found in `TELEMETRY_PATHS`:

| Field | Path | Notes |
|:---|:---|:---|
| Room Temperature | `latestTelemetry.reading.roomTemperature` | Value in Celsius decidegrees |
| Humidity | `latestTelemetry.reading.humidity` | |
| HVAC State | `latestTelemetry.reading.hvacState` | |
| Connected State | `latestTelemetry.isConnected` | Boolean |
| Timestamp | `latestTelemetry.reading.timestamp` | |

> **Validation Status:** This structure was identified in the decompiled application bytecode (v4.11.0). While it is named `latestTelemetry`, it has been confirmed **NOT** to be an AWS IOT Named Shadow (fetching it as a shadow returns 404). It is likely delivered via a custom MQTT topic or a GraphQL subscription.

> **Note:** The integration caches these values from any incoming MQTT message that contains them.
