"""Device logic and constants for Mysa devices."""
# pylint: disable=too-many-return-statements, too-many-branches
# pylint: disable=too-many-statements, too-many-locals
# Justification: Device logic requires handling diverse payloads and state normalizations
# in a single pass.
import logging
from typing import Any, Dict, List, Optional
from homeassistant.helpers.device_registry import DeviceInfo, CONNECTION_NETWORK_MAC


from .const import (
    DOMAIN,
    AC_FAN_MODES,
    AC_SWING_MODES,
    AC_PAYLOAD_TYPE,
)

_LOGGER = logging.getLogger(__name__)


class MysaDeviceLogic:
    """Helper class for device-specific logic."""

    @staticmethod
    def get_device_info(
        device_id: str,
        device_data: Dict[str, Any],
        current_state: Optional[Dict[str, Any]] = None
    ) -> DeviceInfo:
        """Construct standard DeviceInfo for a Mysa device."""
        # Format MAC address with colons if needed (assuming device_id is raw hex)
        mac = device_id
        if ":" not in mac and len(mac) == 12:
            mac = ":".join(mac[i:i + 2] for i in range(0, 12, 2))

        # Try to find Serial Number in state or device_data
        serial = device_data.get("serial_number")
        if not serial and current_state:
            serial = current_state.get("serial_number")

        # Try to find Firmware Version in state or device_data
        sw_version = device_data.get("FirmwareVersion")
        if (not sw_version or str(sw_version) == "None") and current_state:
            sw_version = current_state.get("FirmwareVersion")

        return DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=str(device_data.get("Name", device_id)),
            manufacturer="Mysa",
            model=str(device_data.get("Model", "Unknown")),
            sw_version=str(sw_version),
            serial_number=str(serial) if serial else None,
            connections={(CONNECTION_NETWORK_MAC, mac)}
        )

    @staticmethod
    def is_ac_device(device_info: Optional[Dict[str, Any]]) -> bool:
        """Check if device is an AC controller."""
        if not device_info:
            return False
        model = str(device_info.get("Model", ""))
        return model.startswith("AC-")

    @staticmethod
    def get_payload_type(
        device_info: Optional[Dict[str, Any]],
        upgraded_lite_devices: Optional[List[str]] = None
    ) -> int:
        """Determine MQTT payload type based on device model."""
        if not device_info:
            return 1

        device_id = str(device_info.get("Id", ""))

        # Check upgraded lite devices
        if upgraded_lite_devices:
            normalized_id = device_id.replace(":", "").lower()
            for upgraded_id in upgraded_lite_devices:
                if upgraded_id.replace(":", "").lower() == normalized_id:
                    return 5

        model = str(
            device_info.get("Model")
            or device_info.get("ProductModel")
            or device_info.get("productModel")
            or ""
        )
        fw = str(device_info.get("FirmwareVersion", ""))

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
    def normalize_state(state: Dict[str, Any]) -> None:
        # Helper to get first available value that isn't None
        def get_v(keys: List[str], prefer_v: bool = True) -> Any:
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
        mode_val = get_v(['md', 'mode', 'TstatMode', 'Mode'])
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
        if 'if' in state or 'flrSnsrTemp' in state:
            val = get_v(['if', 'Infloor', 'flrSnsrTemp'])
            state['Infloor'] = val

        # Brightness variants
        # prefer 'br' then 'MaxBrightness' then complex 'Brightness' dict
        # Check for 'br' dictionary contamination (echo from settings change)
        br_raw = state.get('br')
        if isinstance(br_raw, dict):
            # This is a settings object, not a brightness level
            # Move it to BrightnessSettings to avoid contamination
            state['BrightnessSettings'] = br_raw
            # Remove from 'br' so it doesn't get picked up as an int below
            state.pop('br', None)

        br_val = get_v(['br', 'MaxBrightness', 'Brightness'])
        if br_val is not None:
            # Ensure we don't accidentally cast a dict to int if get_v failed to filter
            if not isinstance(br_val, dict):
                try:
                    state['Brightness'] = int(br_val)
                except (ValueError, TypeError):
                    pass

        duty_val = get_v(['dc', 'Duty', 'DutyCycle', 'heatStat'])
        if duty_val is not None:
            state['DutyCycle'] = duty_val

        # Voltage (lineVtg for In-Floor)
        volt_val = get_v(['loadVtg', 'voltage', 'lineVtg'])
        if volt_val is not None:
            state['Voltage'] = volt_val

        load_val = get_v(['loadCurr', 'current'])
        if load_val is not None:
            state['Current'] = load_val

        # --- Device Settings ---

        # 1. Zone
        grp_val = get_v(['grp', 'Zone'])
        if grp_val is not None:
            state['Zone'] = grp_val

        # 2. Timezone/Region
        reg_val = get_v(['reg', 'Region'])
        if reg_val is not None:
            state['Region'] = reg_val

        # 3. Mode/Schedule
        # For simplicity, we just look for 'mode' or 'sched' for now if needed

        # 4. Lock
        lk_val = get_v(['lk', 'lock', 'Lock', 'ButtonState', 'alk', 'lc'])
        if lk_val is not None:
             # Handle int/string/bool. 'Locked' is a string value from ButtonState.
            state['Lock'] = 1 if (str(lk_val).lower() in ['1', 'true', 'on', 'locked']) else 0

        # 5. Proximity
        px_val = get_v(['px', 'ProximityMode'])
        if px_val is not None:
            state['ProximityMode'] = str(px_val).lower() in ['1', 'true', 'on']

        # Connectivity variant
        conn_val = get_v(['Connected'])
        if conn_val is not None:
            state['Connected'] = (str(conn_val).lower() in ['1', 'true', 'on'])

        # SensorMode variants (0=Ambient/Air, 1=Floor)
        sm_val = get_v(['SensorMode'])
        if sm_val is not None:
            state['SensorMode'] = int(sm_val)
        else:
            # Fallback: Infer from TrackedSensor (In-Floor devices)
            # Observed: 3 = Floor, 5 = Ambient
            ts_val = get_v(['TrackedSensor', 'trackedSnsr'])
            if ts_val is not None:
                try:
                    ts_int = int(ts_val)
                    if ts_int == 3: # 3=Floor (Active)
                        state['SensorMode'] = 1  # Floor
                    elif ts_int == 5: # 5=Ambient (Active)
                        state['SensorMode'] = 0  # Ambient
                except (ValueError, TypeError):
                    pass

        # AutoBrightness variants
        ab_val = get_v(['ab', 'AutoBrightness'])
        if ab_val is not None:
            state['AutoBrightness'] = str(ab_val).lower() in ['1', 'true', 'on']


        # EcoMode / Climate+ variants
        # ecoMode/eco: 0=On, 1=Off
        # IsThermostatic/it: 1=On/True, 0=Off/False
        eco_val = get_v(['ecoMode', 'eco'])
        if eco_val is not None:
            state['EcoMode'] = str(eco_val) == '0'
        else:
            it_val = get_v(['it', 'IsThermostatic'])
            if it_val is not None:
                state['EcoMode'] = str(it_val).lower() in ['1', 'true', 'on']

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
        ip_val = get_v(['ip', 'Local IP', 'IPAddress', 'LocalIP'])
        if ip_val is not None:
            state['ip'] = str(ip_val)

        # Firmware Version variants
        fw_val = get_v(['fv', 'ver', 'fwVersion', 'FirmwareVersion', 'fw'])
        if fw_val is not None:
            state['FirmwareVersion'] = str(fw_val)

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
            try:
                state['TstatMode'] = int(tstat_val)
            except (ValueError, TypeError):
                state['TstatMode'] = tstat_val

        # ACState object (contains mode, temp, fan, swing as numbered keys)
        # Also handle "flat" ACState keys (1-5) at root level (MsgType 30)

        # 1: Power
        pwr_val = state.get('1')
        if pwr_val is not None:
            state['ACPower'] = int(pwr_val)

        # 2: Mode (This is the "Engine" mode, e.g. 4=Cool)
        eng_mode_val = state.get('2')
        if eng_mode_val is not None:
            state['ACMode'] = int(eng_mode_val)
            # FORCE override of generic Mode if present
            # This is required for MsgType 31 (Update) which only sends key '2'
            state['Mode'] = int(eng_mode_val)

        # 3: Temperature (Setpoint)
        eng_temp_val = state.get('3')
        if eng_temp_val is not None:
            state['ACTemp'] = float(eng_temp_val)
            state['stpt'] = float(eng_temp_val)
            state['SetPoint'] = float(eng_temp_val)

        # 4: Fan Speed
        eng_fan_val = state.get('4')
        if eng_fan_val is not None:
            state['FanSpeed'] = int(eng_fan_val)
            state['FanMode'] = AC_FAN_MODES.get(int(eng_fan_val), 'unknown')

        # 5: Swing
        eng_swing_val = state.get('5')
        if eng_swing_val is not None:
            state['SwingState'] = int(eng_swing_val)
            state['SwingMode'] = AC_SWING_MODES.get(int(eng_swing_val), 'unknown')

        acstate = state.get('ACState')
        if isinstance(acstate, dict):
            acstate_v = acstate.get('v', acstate)
            if isinstance(acstate_v, dict):
                # Extract values from ACState numbered keys
                if '1' in acstate_v:  # Power state
                    state['ACPower'] = int(acstate_v['1'])
                if '2' in acstate_v:  # Mode
                    state['ACMode'] = int(acstate_v['2'])
                    state['Mode'] = int(acstate_v['2']) # Also override here
                if '3' in acstate_v:  # Temperature
                    state['ACTemp'] = float(acstate_v['3'])
                    state['stpt'] = float(acstate_v['3'])
                if '4' in acstate_v:  # Fan speed
                    if 'FanSpeed' not in state:
                        state['FanSpeed'] = int(acstate_v['4'])
                        state['FanMode'] = AC_FAN_MODES.get(int(acstate_v['4']), 'unknown')
                if '5' in acstate_v:  # Vertical swing
                    if 'SwingState' not in state:
                        state['SwingState'] = int(acstate_v['5'])
                        state['SwingMode'] = AC_SWING_MODES.get(int(acstate_v['5']), 'unknown')
