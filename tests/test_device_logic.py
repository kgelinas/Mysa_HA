"""Tests for Mysa Device Logic."""
import pytest
from custom_components.mysa.device import MysaDeviceLogic
from custom_components.mysa.const import AC_PAYLOAD_TYPE

@pytest.mark.unit
class TestMysaDeviceLogic:
    """Test device logic helper."""

    def test_is_ac_device(self):
        assert MysaDeviceLogic.is_ac_device({"Model": "AC-V1"}) is True
        assert MysaDeviceLogic.is_ac_device({"Model": "BB-V2"}) is False
        assert MysaDeviceLogic.is_ac_device({}) is False
        assert MysaDeviceLogic.is_ac_device(None) is False

    def test_get_payload_type(self):
        # Empty
        assert MysaDeviceLogic.get_payload_type({}) == 1
        assert MysaDeviceLogic.get_payload_type(None) == 1

        # BB-V1 (Baseboard or BB-V1)
        assert MysaDeviceLogic.get_payload_type({"Model": "BB-V1"}) == 1
        assert MysaDeviceLogic.get_payload_type({"Model": "Baseboard"}) == 1

        # BB-V2 (V2 or BB-V2)
        assert MysaDeviceLogic.get_payload_type({"Model": "BB-V2"}) == 4
        assert MysaDeviceLogic.get_payload_type({"Model": "V2"}) == 4
        assert MysaDeviceLogic.get_payload_type({"FirmwareVersion": "V2.0"}) == 4

        # Lite (BB-V2-L)
        assert MysaDeviceLogic.get_payload_type({"Model": "BB-V2-L"}) == 5
        assert MysaDeviceLogic.get_payload_type({"Model": "Lite"}) == 1 # Unknown model returns 1

        # In-Floor (INF-V1 or Floor)
        assert MysaDeviceLogic.get_payload_type({"Model": "INF-V1"}) == 3
        assert MysaDeviceLogic.get_payload_type({"Model": "Floor"}) == 3

        # AC
        assert MysaDeviceLogic.get_payload_type({"Model": "AC-V1"}) == AC_PAYLOAD_TYPE

        # Upgraded Lite
        assert MysaDeviceLogic.get_payload_type({"Id": "dev1"}, upgraded_lite_devices=["dev1"]) == 5
        assert MysaDeviceLogic.get_payload_type({"Id": "dev1:00"}, upgraded_lite_devices=["dev100"]) == 5

        # Fallback
        assert MysaDeviceLogic.get_payload_type({"Model": "Unknown"}) == 1

    def test_normalize_state_basic(self):
        state = {
            "sp": 21.0,
            "md": 1,
            "dc": 100,
            "rssi": -50,
            "volts": 120,
            "amps": 5,
            "hs": 30,
            "if": 22,
            "br": 50,
            "lk": 1,
            "Connected": "true",
            "zn": "zone1",
            "px": 1,
            "ab": 1,
            "eco": 0
        }
        MysaDeviceLogic.normalize_state(state)

        assert state["SetPoint"] == 21.0
        assert state["Mode"] == 1
        assert state["Duty"] == 100
        assert state["Rssi"] == -50
        assert state["Voltage"] == 120
        assert state["Current"] == 5
        assert state["HeatSink"] == 30
        assert state["Infloor"] == 22
        assert state["Brightness"] == 50
        assert state["Lock"] == 1
        assert state["Connected"] is True
        assert state["ProximityMode"] is True
        assert state["AutoBrightness"] is True
        assert state["EcoMode"] is True

    def test_normalize_state_variants(self):
        # Testing alternate keys
        state = {
            "SetPoint": 22.0,
            "TstatMode": 2,
            "DutyCycle": 50,
            "Rssi": -60,
            "Voltage": 240,
            "Current": 10,
            "HeatSink": 40,
            "Infloor": 25,
            "MaxBrightness": 80,
            "ButtonState": "Locked",
            "zone_id": "z2",
            "ProximityMode": "On",
            "AutoBrightness": "On",
            "ecoMode": 1
        }
        MysaDeviceLogic.normalize_state(state)

        assert state["SetPoint"] == 22.0
        assert state["Mode"] == 2
        assert state["Duty"] == 50
        assert state["Lock"] == 1
        assert state["ProximityMode"] is True
        assert state["EcoMode"] is False # 1 is Off


    def test_sensor_mode_priority(self):
        """Test that TrackedSensor takes priority over ControlMode."""
        # TrackedSensor says 3 (Floor), ControlMode says 0 (Ambient)
        # Should result in 1 (Floor) because TrackedSensor is the source of truth
        data = {"TrackedSensor": 3, "ControlMode": 0}
        MysaDeviceLogic.normalize_state(data)
        assert data["SensorMode"] == 1

    def test_normalize_state_ecomode_variants(self):
        """Test all variants that normalize to EcoMode."""
        # ecoMode=0 (ON)
        state = {"ecoMode": 0}
        MysaDeviceLogic.normalize_state(state)
        assert state["EcoMode"] is True

        # ecoMode=1 (OFF)
        state = {"ecoMode": 1}
        MysaDeviceLogic.normalize_state(state)
        assert state["EcoMode"] is False

        # eco (short key)
        state = {"eco": 0}
        MysaDeviceLogic.normalize_state(state)
        assert state["EcoMode"] is True

        # it (IsThermostatic short key)
        state = {"it": 1}
        MysaDeviceLogic.normalize_state(state)
        assert state["EcoMode"] is True

        # IsThermostatic
        state = {"IsThermostatic": True}
        MysaDeviceLogic.normalize_state(state)
        assert state["EcoMode"] is True

    def test_normalize_state_infloor_duty_loop(self):
        """Test In-Floor specialized keys (heatStat, lineVtg)."""
        # heatStat -> DutyCycle
        # lineVtg -> Voltage
        state = {
            "heatStat": 50,
            "lineVtg": 240,
            "sl": 3
        }
        MysaDeviceLogic.normalize_state(state)

        assert state["DutyCycle"] == 50
        assert state["Voltage"] == 240

    def test_normalize_state_infloor_sensor_mode(self):
        """Test normalization of SensorMode and Infloor variants."""
        # Test SensorMode and if
        state = {"SensorMode": 1, "if": 22.5}
        MysaDeviceLogic.normalize_state(state)
        assert state["Infloor"] == 22.5

        # Test SensorMode and Infloor
        state = {"SensorMode": 0, "Infloor": 21.0}
        MysaDeviceLogic.normalize_state(state)
        assert state["SensorMode"] == 0
        assert state["Infloor"] == 21.0

    def test_normalize_state_nested_v(self):
        # Key: {"v": value}
        state = {
            "sp": {"v": 23.0},
            "Brightness": {"a_br": 90}, # V2 brightness special handling
            "lk": {"v": "off"}
        }
        MysaDeviceLogic.normalize_state(state)

        assert state["SetPoint"] == 23.0
        assert state["Brightness"] == 90
        assert state["Lock"] == 0

    def test_normalize_state_ac_diag(self):
        # AC + Diagnostics
        state = {
            "mnbr": 10,
            "mxbr": 90,
            "mxc": 16,
            "mxs": 30,
            "tz": "UTC",
            "fn": 1,
            "ss": 3,
            "ssh": 2,
            "TstatMode": 1,
            "ACState": {
                "v": {
                    "1": 1, # Power
                    "2": 2, # Mode
                    "3": 24.5, # Temp
                    "4": 2, # Fan
                    "5": 1 # Swing
                }
            }
        }
        MysaDeviceLogic.normalize_state(state)

        assert state["MinBrightness"] == 10
        assert state["MaxBrightness"] == 90
        assert state["MaxCurrent"] == 16
        assert state["MaxSetpoint"] == 30
        assert state["TimeZone"] == "UTC"
        assert state["FanSpeed"] == 1 # From fn
        assert state["SwingState"] == 3 # From ss
        assert state["SwingStateHorizontal"] == 2

        # But wait, ACState usually overrides or complements?
        # Logic says: if "fn" exists set FanSpeed.
        # Then later ACState parsing sets FanSpeed if not in state.
        # Since "fn" set it, ACState won't overwrite it.
        # Let's test ACState alone.

    def test_normalize_state_ac_state_only(self):
        state = {
            "ACState": {
                "v": {
                    "1": 1, # Power
                    "2": 2, # Mode
                    "3": 24.5, # Temp
                    "4": 2, # Fan
                    "5": 1 # Swing
                }
            }
        }
        MysaDeviceLogic.normalize_state(state)

        assert state["ACPower"] == 1
        assert state["ACMode"] == 2
        assert state["ACTemp"] == 24.5
        assert state["FanSpeed"] == 2
        assert state["SwingState"] == 1

    def test_normalize_state_skip_dict_no_v(self):
        """Test skipping dict without 'v' key."""
        # We need to target a key where get_v is called with multiple options,
        # and the FIRST one exists but is a dict-without-v.
        # min_br = get_v(['MinBrightness', 'mnbr'])
        # So we set MinBrightness to the bad dict, and mnbr to the backup value.
        state = {
            "MinBrightness": {"bad": 1}, # returns dict, no 'v'
            "mnbr": 10  # fallback key
        }
        MysaDeviceLogic.normalize_state(state)
        # Should skip MinBrightness and pick up mnbr
        assert state["MinBrightness"] == 10


    def test_normalize_state_exceptions(self):
        """Test exception handling in normalize_state."""
        # TstatMode invalid value (lines 192-193 of device.py)
        state = {
            "TstatMode": "invalid"
        }
        MysaDeviceLogic.normalize_state(state)
        # Should keep "invalid" string (except caught)
        assert state["TstatMode"] == "invalid"

    def test_normalize_state_coverage_gaps(self):
        """Test exception handling for coverage."""
        # Invalid TrackedSensor
        state = {"TrackedSensor": "invalid"}
        MysaDeviceLogic.normalize_state(state)
        assert "SensorMode" not in state

        # Invalid Brightness
        state = {"br": "invalid"}
        MysaDeviceLogic.normalize_state(state)
        assert "Brightness" not in state

        # Unknown TrackedSensor value (e.g. 2)
        state = {"TrackedSensor": 2}
        MysaDeviceLogic.normalize_state(state)
        assert "SensorMode" not in state

        # Dict without v, no fallback -> should return None (not set)
        state = {"SensorMode": {"nov": 1}}
        MysaDeviceLogic.normalize_state(state)
        # Should remain unchanged (dict) because normalization failed
        assert state["SensorMode"] == {"nov": 1}

    def test_get_device_info_mac_formatting(self):
        """Test MAC address formatting in get_device_info."""
        from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
        from custom_components.mysa.const import DOMAIN

        # 12-char hex string should be formatted with colons
        info = MysaDeviceLogic.get_device_info("aabbccddeeff", {})
        # Note: indentifiers uses DOMAIN, connections uses CONNECTION_NETWORK_MAC ("mac")
        assert info["connections"] == {(CONNECTION_NETWORK_MAC, "aa:bb:cc:dd:ee:ff")}

        # Already formatted should be kept
        info2 = MysaDeviceLogic.get_device_info("aa:bb:cc:dd:ee:ff", {})
        assert info2["connections"] == {(CONNECTION_NETWORK_MAC, "aa:bb:cc:dd:ee:ff")}

        # Non-12-char should be ignored (just passed through)
        info3 = MysaDeviceLogic.get_device_info("short", {})
        assert info3["connections"] == {(CONNECTION_NETWORK_MAC, "short")}

    def test_normalize_state_coverage_final_push(self):
        """Cover remaining lines in device.py."""
        # 1. Brightness as dict (Settings echo)
        state = {"br": {"val": 100}}
        MysaDeviceLogic.normalize_state(state)
        assert state["BrightnessSettings"] == {"val": 100}
        assert "Brightness" not in state # Should be popped

        # 2. loadCurr -> Current
        state = {"loadCurr": 2.5}
        MysaDeviceLogic.normalize_state(state)
        assert state["Current"] == 2.5

        # 3. grp -> Zone
        state = {"grp": "Living Room"}
        MysaDeviceLogic.normalize_state(state)
        assert state["Zone"] == "Living Room"

        # 4. reg -> Region
        state = {"reg": "CA"}
        MysaDeviceLogic.normalize_state(state)
        assert state["Region"] == "CA"

        # 5. ip -> IP
        state = {"ip": "192.168.1.5"}
        MysaDeviceLogic.normalize_state(state)
        assert state["ip"] == "192.168.1.5"

        # 6. TrackedSensor -> Ambient (0 or 5)
        # We need a case where SensorMode is missing so it falls back
        state = {"TrackedSensor": 5}
        MysaDeviceLogic.normalize_state(state)
        assert state["SensorMode"] == 0

    def test_get_device_info_fallbacks(self):
        """Test get_device_info falling back to current_state."""
        # Case 1: Serial missing in device_data, present in state
        d_data = {"Model": "V2"}
        c_state = {"serial_number": "SN123", "FirmwareVersion": "2.1.0"}
        info = MysaDeviceLogic.get_device_info("id1", d_data, c_state)
        assert info["serial_number"] == "SN123"
        assert info["sw_version"] == "2.1.0"

        # Case 2: Firmware "None" string
        d_data = {"FirmwareVersion": "None"}
        info = MysaDeviceLogic.get_device_info("id1", d_data, c_state)
        assert info["sw_version"] == "2.1.0"
        state = {"fv": "1.2.3"}
        MysaDeviceLogic.normalize_state(state)
        assert state["FirmwareVersion"] == "1.2.3"

        # Test 'ver'
        state = {"ver": "2.0.0"}
        MysaDeviceLogic.normalize_state(state)
        assert state["FirmwareVersion"] == "2.0.0"

        # Test 'fwVersion'
        state = {"fwVersion": "3.4.5"}
        MysaDeviceLogic.normalize_state(state)
        assert state["FirmwareVersion"] == "3.4.5"

    def test_normalize_state_ac_conflict_flat(self):
        """Test that internal AC key '2' overrides generic 'mode'."""
        # Generic mode says Auto (2), Internal engine says Cool (4)
        state = {
            "mode": 2,
            "2": 4,
            "ambTemp": 21.0
        }
        MysaDeviceLogic.normalize_state(state)
        # Should favor Cool (4)
        assert state["Mode"] == 4
        assert state["ACMode"] == 4

    def test_normalize_state_ac_conflict_nested(self):
        """Test that nested ACState key '2' overrides generic 'mode'."""
        state = {
            "mode": 2,
            "ACState": {
                "2": 4,
                "3": 22.0
            }
        }
        MysaDeviceLogic.normalize_state(state)
        assert state["Mode"] == 4
        assert state["ACMode"] == 4
        assert state["ACTemp"] == 22.0
        assert state["stpt"] == 22.0

    def test_normalize_state_flat_ac_keys(self):
        """Test logic handles flattened keys (1-5) from MsgType 30."""
        state = {
            "mode": 2, # Generic Auto
            "1": 1,  # Power On
            "2": 4,  # Mode Cool
            "3": 21.5, # Temp
            "4": 2, # Fan Med (assuming 2=Med)
            "5": 0 # Swing Off
        }
        MysaDeviceLogic.normalize_state(state)

        assert state["ACPower"] == 1
        assert state["ACMode"] == 4
        assert state["Mode"] == 4
        assert state["ACTemp"] == 21.5
        assert state["stpt"] == 21.5
        assert state["FanSpeed"] == 2
        assert state["SwingState"] == 0

    def test_normalize_state_local_ip_variant(self):
        """Test Local IP normalization (from test_coverage_gap.py)."""
        state = {"Local IP": "10.0.0.1"}
        MysaDeviceLogic.normalize_state(state)
        assert state["ip"] == "10.0.0.1"

        # Also test MaxCurrent which is near it
        state = {"MaxCurrent": 15}
        MysaDeviceLogic.normalize_state(state)
        assert state["MaxCurrent"] == 15
