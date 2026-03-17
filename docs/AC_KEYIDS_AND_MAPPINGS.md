# Mysa AC Internal Identifiers (KeyIDs)

This document provides a comprehensive list of internal IDs and mappings discovered from the decompiled Mysa Android APK (`index.android.bundle`). These IDs are used for feature discovery, command sending, and state interpretation for AC (Mini-Split) devices.

## 1. Device AC Key Codes (Internal Command IDs)
These IDs (1-47) are used by the app to identify supported features and send specific IR commands.

| KeyID | Internal Name | Description |
|-------|---------------|-------------|
| 1     | POWER_ON      | Turn device on |
| 2     | POWER_OFF     | Turn device off |
| 3     | MODE_AUTO     | Set mode to Auto |
| 4     | MODE_COOL     | Set mode to Cool |
| 5     | MODE_DRY      | Set mode to Dry |
| 6     | MODE_FAN      | Set mode to Fan |
| 7     | MODE_HEAT     | Set mode to Heat |
| 8     | FAN_AUTO      | Set fan speed to Auto (maps to `fn: 1`) |
| 9     | FAN_LOW       | Set fan speed to Low (maps to `fn: 2`) |
| 10    | FAN_MED       | Set fan speed to Medium (maps to `fn: 3`) |
| 11    | FAN_HIGH      | Set fan speed to High (maps to `fn: 4`) |
| 12    | SWING         | Toggle Vertical Swing |
| 13    | TEMP_UP       | Increase Temperature |
| 14    | TEMP_DOWN     | Decrease Temperature |
| 21    | POWER_TOGGLE  | Toggle Power |
| 22    | MODE_CHANGE   | Cycle through Modes |
| 24    | SLEEP         | Toggle Sleep Mode |
| 27    | FAN_SPD_CHANGE| Cycle through Fan Speeds |
| 28    | FAN_SPD_UP    | Increase Fan Speed |
| 29    | FAN_SPD_DOWN  | Decrease Fan Speed |
| 39    | SWING_ON      | Turn Vertical Swing On |
| 40    | SWING_OFF     | Turn Vertical Swing Off |
| 47    | SWING_K       | Unknown Swing variant |

---

## 2. HVAC Mode Mapping (`md` / `TStatMode`)
Internal values used in MQTT payloads and state objects for AC devices.

| Value | Name |
|-------|------|
| 1     | OFF  |
| 2     | AUTO |
| 3     | HEAT |
| 4     | COOL |
| 5     | FAN  |
| 6     | DRY  |

---

## 3. Swing State Mapping (`ss` / `SwingState`)
The APK uses 1-based internal constants, while the device reports 0-based integers in MQTT.

| MQTT Value | APK Value | Internal Name | Description |
|------------|-----------|---------------|-------------|
| 0          | 1         | OFF           | Swing Off |
| 1          | 2         | ON            | Vertical Swing On |
| 2          | 3         | AUTO          | Auto Swing |
| 3          | 4         | SWING1        | Top Position |
| 4          | 5         | SWING2        | Position 2 |
| 5          | 6         | SWING3        | Middle Position |
| 6          | 7         | SWING4        | Position 4 |
| 7          | 8         | SWING5        | Low Position |
| 8          | 9         | SWING6        | Bottom Position |

---

## 4. Capability Discovery
The app determines feature support by checking for the presence of these groups in `SupportedCaps.keys`.

- **FAN**: Checks for KeyIDs 8, 9, 10, 11
- **SWING**: Checks for KeyIDs 12, 39, 40
- **POWER**: Checks for KeyIDs 1, 2, 21
- **TEMP**: Checks for KeyIDs 13, 14
