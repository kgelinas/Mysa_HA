"""Device logic and constants for Mysa devices."""
import logging
from .const import (
    AC_FAN_MODES,
    AC_SWING_MODES,
    AC_PAYLOAD_TYPE,
)

_LOGGER = logging.getLogger(__name__)

class MysaDeviceLogic:
    """Helper class for device-specific logic."""

    @staticmethod
    def is_ac_device(device_info: dict | None) -> bool:
        """Check if device is an AC controller."""
        if not device_info:
            return False
        model = device_info.get("Model", "")
        return model.startswith("AC-")

    @staticmethod
    def get_payload_type(device_info: dict | None, upgraded_lite_devices: list | None = None) -> int:
        """Determine MQTT payload type based on device model."""
        if not device_info:
            return 1

        device_id = device_info.get("Id", "")

        # Check upgraded lite devices
        if upgraded_lite_devices:
            normalized_id = device_id.replace(":", "").lower()
            for upgraded_id in upgraded_lite_devices:
                if upgraded_id.replace(":", "").lower() == normalized_id:
                    return 5

        model = (device_info.get("Model") or device_info.get("ProductModel") or
                 device_info.get("productModel") or "")
        fw = device_info.get("FirmwareVersion", "")

        # AC controllers use payload type 2
        if model.startswith("AC-"):
            return AC_PAYLOAD_TYPE

        if "BB-V2" in model or "V2" in model:
            if "Lite" in model or "-L" in model:
                return 5
            return 4
        if "INF-V1" in model or "Floor" in model:
            return 3
        if "BB-V1" in model or "Baseboard" in model:
            return 1

        if "V2" in fw:
            return 4

        return 1

    @staticmethod
    def normalize_state(state: dict) -> None:
        """Standardize keys across HTTP and MQTT responses. Modifies state in-place."""

        # Helper to get first available value that isn't None
        def get_v(keys, prefer_v=True):
            for k in keys:
                val = state.get(k)
                if val is not None:
                    if isinstance(val, dict):
                        extracted = val.get('v')
                        if extracted is not None:
                            return extracted
                        # V2 Brightness logic: prefer active_brightness (a_br)
                        if k == 'Brightness':
                            v2_br = val.get('a_br')
                            if v2_br is not None:
                                return v2_br
                        # If no 'v' and it's a dict, we might want to continue to next key
                        if prefer_v:
                            continue
                    return val
            return None

        # Basic mappings - only set if value exists
        # For V2, sp and md are often more reliable than the long names
        mode_val = get_v(['md', 'TstatMode', 'Mode'])
        if mode_val is not None:
            state['Mode'] = mode_val
        sp_val = get_v(['sp', 'stpt', 'SetPoint'])
        if sp_val is not None:
            state['SetPoint'] = sp_val
        duty_val = get_v(['dc', 'Duty', 'DutyCycle'])
        if duty_val is not None:
            state['Duty'] = duty_val
        rssi_val = get_v(['rssi', 'Rssi', 'RSSI'])
        if rssi_val is not None:
            state['Rssi'] = rssi_val
        voltage_val = get_v(['volts', 'Voltage', 'LineVoltage'])
        if voltage_val is not None:
            state['Voltage'] = voltage_val
        current_val = get_v(['amps', 'Current'])
        if current_val is not None:
            state['Current'] = current_val
        hs_val = get_v(['hs', 'HeatSink'])
        if hs_val is not None:
            state['HeatSink'] = hs_val
        if 'if' in state:
            state['Infloor'] = get_v(['if', 'Infloor'])

        # Brightness variants
        # prefer 'br' then 'MaxBrightness' then complex 'Brightness' dict
        br_val = get_v(['br', 'MaxBrightness', 'Brightness'])
        if br_val is not None:
            state['Brightness'] = int(br_val)

        # Lock variants
        lock_val = get_v(['ButtonState', 'alk', 'lc', 'lk', 'Lock'])
        if lock_val is not None:
            # Handle int/string/bool
            state['Lock'] = 1 if (str(lock_val).lower() in ['1', 'true', 'on', 'locked']) else 0

        # Connectivity variant
        conn_val = get_v(['Connected'])
        if conn_val is not None:
            state['Connected'] = (str(conn_val).lower() in ['1', 'true', 'on'])

        # Zone identification
        zone_val = get_v(['Zone', 'zone_id', 'zn'])
        if zone_val is not None:
            state['Zone'] = zone_val

        # Proximity variants
        px_val = get_v(['px', 'ProximityMode'])
        if px_val is not None:
            state['ProximityMode'] = str(px_val).lower() in ['1', 'true', 'on']

        # AutoBrightness variants
        ab_val = get_v(['ab', 'AutoBrightness'])
        if ab_val is not None:
            state['AutoBrightness'] = str(ab_val).lower() in ['1', 'true', 'on']

        # EcoMode variants (0=On, 1=Off)
        eco_val = get_v(['ecoMode', 'eco'])
        if eco_val is not None:
            state['EcoMode'] = str(eco_val) == '0'

        # New Diagnostic mappings - only set if value exists
        min_br = get_v(['MinBrightness', 'mnbr'])
        if min_br is not None:
            state['MinBrightness'] = min_br
        max_br = get_v(['MaxBrightness', 'mxbr'])
        if max_br is not None:
            state['MaxBrightness'] = max_br
        max_current = get_v(['MaxCurrent', 'mxc'])
        if max_current is not None:
            state['MaxCurrent'] = max_current
        max_setpoint = get_v(['MaxSetpoint', 'mxs'])
        if max_setpoint is not None:
            state['MaxSetpoint'] = max_setpoint
        timezone = get_v(['TimeZone', 'tz'])
        if timezone is not None:
            state['TimeZone'] = timezone

        # =================================================================
        # AC Controller specific mappings
        # =================================================================

        # Fan Speed (AC)
        fan_val = get_v(['fn', 'FanSpeed'])
        if fan_val is not None:
            state['FanSpeed'] = int(fan_val)
            # Also store the HA-friendly name
            state['FanMode'] = AC_FAN_MODES.get(int(fan_val), 'unknown')

        # Vertical Swing (AC)
        swing_val = get_v(['ss', 'SwingState'])
        if swing_val is not None:
            state['SwingState'] = int(swing_val)
            state['SwingMode'] = AC_SWING_MODES.get(int(swing_val), 'unknown')

        # Horizontal Swing (AC)
        hswing_val = get_v(['ssh', 'SwingStateHorizontal'])
        if hswing_val is not None:
            state['SwingStateHorizontal'] = int(hswing_val)

        # TstatMode for AC (maps to HVAC mode)
        tstat_val = get_v(['TstatMode'])
        if tstat_val is not None:
            state['TstatMode'] = int(tstat_val) if isinstance(
                tstat_val, (int, float)
            ) else tstat_val

        # ACState object (contains mode, temp, fan, swing as numbered keys)
        acstate = state.get('ACState')
        if isinstance(acstate, dict):
            acstate_v = acstate.get('v', acstate)
            if isinstance(acstate_v, dict):
                # Extract values from ACState numbered keys
                if '1' in acstate_v:  # Power state
                    state['ACPower'] = int(acstate_v['1'])
                if '2' in acstate_v:  # Mode
                    state['ACMode'] = int(acstate_v['2'])
                if '3' in acstate_v:  # Temperature
                    state['ACTemp'] = float(acstate_v['3'])
                if '4' in acstate_v:  # Fan speed
                    if 'FanSpeed' not in state:
                        state['FanSpeed'] = int(acstate_v['4'])
                        state['FanMode'] = AC_FAN_MODES.get(int(acstate_v['4']), 'unknown')
                if '5' in acstate_v:  # Vertical swing
                    if 'SwingState' not in state:
                        state['SwingState'] = int(acstate_v['5'])
                        state['SwingMode'] = AC_SWING_MODES.get(int(acstate_v['5']), 'unknown')
