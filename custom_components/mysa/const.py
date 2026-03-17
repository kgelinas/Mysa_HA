"""Constants for the Mysa integration."""

DOMAIN = "mysa"

PLATFORMS = [
    "climate",
    "sensor",
    "update",
    "switch",
    "number",
    "select",
    "binary_sensor",
]

# =============================================================================
# MQTT Connection Constants
# =============================================================================

MQTT_KEEPALIVE: int = 60
"""MQTT keepalive interval in seconds"""

MQTT_PING_INTERVAL: int = 25
"""Interval between MQTT PINGREQ packets (less than keepalive)"""

MQTT_USER_AGENT: str = "okhttp/4.11.0"
"""User-Agent header matching Mysa Android app"""

# =============================================================================
# AC Controller Constants (Model: AC-V1-*)
# =============================================================================

# HVAC Modes - Mysa value to Home Assistant mode mapping
AC_MODE_OFF = 1
AC_MODE_AUTO = 2
AC_MODE_HEAT = 3
AC_MODE_COOL = 4
AC_MODE_FAN_ONLY = 5
AC_MODE_DRY = 6

# Fan Speeds - Mysa value to name mapping
# Following KeyID - 7 mapping pattern (8=Auto, 9=Low, 10=Medium, 11=High)
AC_FAN_AUTO = 1
AC_FAN_LOW = 2
AC_FAN_MEDIUM = 3
AC_FAN_HIGH = 4
AC_FAN_TURBO = 5
AC_FAN_STRONG = 6
AC_FAN_QUIET = 7
AC_FAN_EASY = 10
AC_FAN_SLEEP = 12

# KeyIDs from APK for discovery
AC_KEY_FAN_AUTO = 8
AC_KEY_FAN_LOW = 9
AC_KEY_FAN_MEDIUM = 10
AC_KEY_FAN_HIGH = 11

# Home Assistant fan mode names
AC_FAN_MODES = {
    AC_FAN_AUTO: "auto",
    AC_FAN_LOW: "low",
    AC_FAN_MEDIUM: "medium",
    AC_FAN_HIGH: "high",
    AC_FAN_TURBO: "turbo",
    AC_FAN_STRONG: "strong",
    AC_FAN_QUIET: "quiet",
    AC_FAN_EASY: "easy",
    AC_FAN_SLEEP: "sleep",
}

# Reverse mapping for setting fan mode
AC_FAN_MODES_REVERSE = {v: k for k, v in AC_FAN_MODES.items()}

# KeyIDs for swing discovery
AC_KEY_SWING_V_ON = 39
AC_KEY_SWING_V_OFF = 40

# Swing Positions (vertical and horizontal share the same values)
AC_SWING_OFF = 0
AC_SWING_VERTICAL = 1
AC_SWING_AUTO = 2
AC_SWING_POSITION_1 = 3  # Top
AC_SWING_POSITION_2 = 4
AC_SWING_POSITION_3 = 5  # Middle
AC_SWING_POSITION_4 = 6
AC_SWING_POSITION_5 = 7
AC_SWING_POSITION_6 = 8  # Bottom
AC_SWING_HORIZONTAL = 10  # Moved out of vertical sequence


# Home Assistant swing mode names (vertical)
AC_SWING_MODES = {
    AC_SWING_OFF: "off",
    AC_SWING_VERTICAL: "vertical",
    AC_SWING_AUTO: "auto",
    AC_SWING_POSITION_1: "top",
    AC_SWING_POSITION_2: "upper",
    AC_SWING_POSITION_3: "middle",
    AC_SWING_POSITION_4: "lower",
    AC_SWING_POSITION_5: "low",
    AC_SWING_POSITION_6: "bottom",
}

# Reverse mapping for setting swing mode
AC_SWING_MODES_REVERSE = {v: k for k, v in AC_SWING_MODES.items()}

# Horizontal swing positions (for select entity if needed)
AC_HORIZONTAL_SWING_MODES: dict[int, str] = {
    AC_SWING_AUTO: "auto",
    AC_SWING_POSITION_1: "left",
    AC_SWING_POSITION_2: "left_center",
    AC_SWING_POSITION_3: "center",
    AC_SWING_POSITION_4: "right_center",
    AC_SWING_POSITION_5: "right_wide",
    AC_SWING_POSITION_6: "right",
}

AC_HORIZONTAL_SWING_MODES_REVERSE = {v: k for k, v in AC_HORIZONTAL_SWING_MODES.items()}

# AC Payload type for MQTT commands
AC_PAYLOAD_TYPE = 2


# =============================================================================
# In-Floor Constants
# =============================================================================

SENSOR_MODE_AMBIENT = 0
SENSOR_MODE_FLOOR = 1

SENSOR_MODES = {
    SENSOR_MODE_AMBIENT: "ambient",
    SENSOR_MODE_FLOOR: "floor",
}

SENSOR_MODES_REVERSE = {v: k for k, v in SENSOR_MODES.items()}
