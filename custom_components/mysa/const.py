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
AC_FAN_AUTO = 1
AC_FAN_LOW = 3
AC_FAN_MEDIUM_LOW = 5
AC_FAN_MEDIUM = 7
AC_FAN_HIGH = 8
AC_FAN_SLEEP = 12

# Home Assistant fan mode names
AC_FAN_MODES = {
    AC_FAN_AUTO: "auto",
    AC_FAN_LOW: "low",
    AC_FAN_MEDIUM_LOW: "medium_low",
    AC_FAN_MEDIUM: "medium",
    AC_FAN_HIGH: "high",
    AC_FAN_SLEEP: "sleep",
}

# Reverse mapping for setting fan mode
AC_FAN_MODES_REVERSE = {v: k for k, v in AC_FAN_MODES.items()}

# Swing Positions (vertical and horizontal share the same values)
AC_SWING_AUTO = 3
AC_SWING_POSITION_1 = 4  # Top / Left
AC_SWING_POSITION_2 = 5
AC_SWING_POSITION_3 = 6  # Middle / Center
AC_SWING_POSITION_4 = 7
AC_SWING_POSITION_5 = 8
AC_SWING_POSITION_6 = 9  # Bottom / Right

# Home Assistant swing mode names (vertical)
AC_SWING_MODES = {
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
