# Mysa MQTT ST-V1-0 (HVAC) Shadow Protocol

This document details the MQTT shadow protocol used by Mysa ST-V1-0 (HVAC) devices. These devices use AWS IoT Device Shadows for state management and control, unlike the standard message envelope used by other Mysa devices.

## Topic Structure

Communication occurs over standard AWS IoT Shadow topics.

*   **Update Topic:** `$aws/things/{safe_device_id}/shadow/name/{shadow_name}/update`
*   **Get Topic:** `$aws/things/{safe_device_id}/shadow/name/{shadow_name}/get`

**`{safe_device_id}`**: The MAC address of the device with colons removed and converted to lowercase (e.g., `abc123def456`).
**`{shadow_name}`**: The specific shadow being accessed (e.g., `modes`, `targetHeat`).

## Payload Structure

### Request (Update)
To update a shadow, the payload follows the standard AWS Shadow format:

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

*   **`source`**: Set to `3` for commands valid from the app/integration.

### Response (Update/Get)
The device responds on the standard AWS Shadow response topics (e.g., `/update/accepted`, `/get/accepted`).

## Shadows & Keys

The following named shadows are used to control different aspects of the HVAC device.

### 1. Modes Shadow (`modes`)
Controls the operation mode, fan speed, and auto deadband.

**Topic:** `$aws/things/{id}/shadow/name/modes/update`

| Key | Type | Description | Values |
| :--- | :--- | :--- | :--- |
| `mode` | Integer | HVAC Operation Mode | `0` = Off<br>`1` = Auto (Heat/Cool)<br>`3` = Cool<br>`4` = Heat<br>`7` = Fan Only |
| `fan_mode` | Integer | Fan Speed | `0` = Auto<br>`1` = Low<br>`2` = Medium<br>`3` = High |
| `autoDeadband`| Integer | Deadband for Auto Mode | Value in Celsius * 100 (e.g., `200` = 2.0°C) |

### 2. Target Heat Shadow (`targetHeat`)
Controls the setpoint for Heating mode.

**Topic:** `$aws/things/{id}/shadow/name/targetHeat/update`

| Key | Type | Description | Values |
| :--- | :--- | :--- | :--- |
| `setpoint` | Integer | Target Temperature | Value in Celsius * 100 (e.g., `2150` = 21.5°C) |

### 3. Target Cool Shadow (`targetCool`)
Controls the setpoint for Cooling mode.

**Topic:** `$aws/things/{id}/shadow/name/targetCool/update`

| Key | Type | Description | Values |
| :--- | :--- | :--- | :--- |
| `setpoint` | Integer | Target Temperature | Value in Celsius * 100 (e.g., `2400` = 24.0°C) |

### 4. Target Auto Shadow (`targetAuto`)
Controls both setpoints simultaneously for Auto (Heat/Cool) mode.

**Topic:** `$aws/things/{id}/shadow/name/targetAuto/update`

| Key | Type | Description | Values |
| :--- | :--- | :--- | :--- |
| `heatSetpoint`| Integer | Heating Target | Value in Celsius * 100 |
| `coolSetpoint`| Integer | Cooling Target | Value in Celsius * 100 |

## Diagnostic Fields

The device also reports diagnostic information in the shadow updates (often in the `modes` shadow or combined updates).

| Key | Description |
| :--- | :--- |
| `hvacState` | Current operational state (`0`=Idle, `4`=Active/Running) |
| `rssi` | WiFi Signal Strength |
| `humidity` | Relative Humidity (%) |
| `ip_address` | Local IP Address |
| `lockoutModes`| Keypad Lock Status |
| `filter` | Filter Life Remaining (%) |
| `lockoutMin` | Minimum Setpoint Limit (C * 100) |
| `lockoutMax` | Maximum Setpoint Limit (C * 100) |
