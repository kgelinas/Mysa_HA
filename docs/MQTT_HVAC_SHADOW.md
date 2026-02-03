# Mysa MQTT ST-V1-0 (HVAC) Shadow Protocol

This document details the MQTT shadow protocol used by Mysa ST-V1-0 (HVAC) devices. These devices use AWS IoT Device Shadows for state management and control.

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
| `advMaxCoolFanSpeed` | Max cooling fan speed |
| `advMaxHeatFanSpeed` | Max heating fan speed |

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

## HVAC Configuration Codes

The `hvac_config_index` corresponds to Mysa's 3-digit configuration codes:

| Code | `hvac_config_index` | System Type | O/B | Stage 2 |
|:---:|:---:|:---|:---:|:---:|
| 11B | 19 | Standard Furnace + AC | — | ❌ |
| 21B | 35 | Electric Furnace | — | ❌ |
| 31L | 57 | Heat Pump (B-valve) | 0 | ❌ |
| 31P | 61 | Heat Pump (O-valve) | 1 | ❌ |
| 41B | 87 | Boiler + AC | — | ❌ |
| 61B | 103 | 2nd Stage Heat | — | ✅ |

**O/B Column:** `advCoolWhenReversed` (1=O-valve, 0=B-valve)

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

## State Reporting Flow

1. **Commands:** Sent to `.../shadow/name/{shadow}/update` with `desired` state.
2. **Confirmations:** Received on `.../shadow/name/{shadow}/update/accepted`.
3. **Spontaneous Updates:** Device reports on `.../shadow/name/{shadow}/update`.
4. **Delta Messages:** Ignored by integration; wait for full state documents.
