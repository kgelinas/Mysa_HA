"""Tests for DeviceCapabilities."""
from typing import Any
from custom_components.mysa.capabilities import DeviceCapabilities
from homeassistant.components.climate.const import HVACMode

class MockApi:
    def __init__(self):
        self.upgraded_lite_devices = []

def test_capabilities_basics():
    """Test basic capability detection."""
    api = MockApi()
    device_data = {"Model": "BB-V2-0"}
    state = {
        "mxs": 2500,  # 25.0
        "mns": 1000,  # 10.0
        "hvac_config_index": 0
    }

    caps = DeviceCapabilities.from_device("dev1", device_data, state, api)

    assert caps.device_id == "dev1"
    assert not caps.is_ac
    assert not caps.is_stv10
    assert not caps.is_lite
    assert caps.supports_floor_sensor_hardware
    assert caps.max_temp == 25.0
    assert caps.min_temp == 10.0
    assert HVACMode.HEAT in caps.hvac_modes

def test_capabilities_lite_upgrade():
    """Test Lite device upgrade logic."""
    api = MockApi()
    device_data = {"Model": "BB-V2-0-L"}
    state = {}

    caps = DeviceCapabilities.from_device("lite1", device_data, state, api)
    assert caps.is_lite

    # Upgrade it
    api.upgraded_lite_devices = ["lite1"]
    assert not caps.is_lite

def test_capabilities_stv10_modes():
    """Test ST-V1-0 mode determination."""
    api = MockApi()
    device_data = {"Model": "ST-V1-0"}

    # Heat pump config
    state = {"hvac_config_index": 3}
    caps = DeviceCapabilities.from_device("st1", device_data, state, api)
    assert caps.is_stv10
    assert HVACMode.COOL in caps.hvac_modes
    assert HVACMode.AUTO in caps.hvac_modes

    # Heat only config
    state = {"hvac_config_index": 1}
    caps.refresh_dynamic(state)
    assert HVACMode.COOL not in caps.hvac_modes

def test_capabilities_ac_modes():
    """Test AC mode determination."""
    api = MockApi()
    device_data = {"Model": "AC-V1"}
    state = {}
    caps = DeviceCapabilities.from_device("ac1", device_data, state, api)
    assert caps.is_ac
    assert HVACMode.COOL in caps.hvac_modes
    assert HVACMode.DRY in caps.hvac_modes

def test_capabilities_refresh_check():
    """Test needs_refresh logic."""
    api = MockApi()
    device_data = {"Model": "BB-V2"}
    state = {"hvac_config_index": 0}
    caps = DeviceCapabilities.from_device("dev1", device_data, state, api)

    assert not caps.needs_refresh({"hvac_config_index": 0})
    assert caps.needs_refresh({"hvac_config_index": 1})

def test_capabilities_temp_fallbacks():
    """Test temperature format fallbacks."""
    api = MockApi()

    # Dict format {v: value}
    state = {"MaxSetpoint": {"v": 2800}, "MinSetpoint": {"v": 1200}}
    assert DeviceCapabilities._get_max_temp(state) == 28.0
    assert DeviceCapabilities._get_min_temp(state) == 12.0

    # mxs format
    state = {"mxs": 2200}
    assert DeviceCapabilities._get_max_temp(state) == 22.0

    # Default
    assert DeviceCapabilities._get_max_temp({}) == 30.0
    assert DeviceCapabilities._get_min_temp({}) == 5.0

def test_capabilities_refresh_full():
    """Test full refresh of dynamic capabilities."""
    api = MockApi()
    device_data = {"Model": "ST-V1-0"}
    state = {
        "hvac_config_index": 1,
        "heating_stage_two_exists": 0,
        "cooling_stage_two_exists": 0
    }
    caps = DeviceCapabilities.from_device("st1", device_data, state, api)

    new_state = {
        "hvac_config_index": 3,
        "heating_stage_two_exists": 1,
        "cooling_stage_two_exists": 1,
        "mxs": 3500,
        "mns": 1500
    }
    caps.refresh_dynamic(new_state)

    assert caps.hvac_config_index == 3
    assert caps.has_aux_heat
    assert caps.has_stage_2_cool
    assert caps.max_temp == 35.0
    assert caps.min_temp == 15.0
    assert HVACMode.COOL in caps.hvac_modes

def test_capabilities_stv10_from_json():
    """Test ST-V1-0 capabilities from JSON endpoint."""
    api = MockApi()
    caps_json = {
        "features": {
            "climateControl": {
                "mode": {"validValues": ["off", "heat", "cool", "auto", "fanOnly"]},
                "heat": {"setpoint": {"validValues": [10, 15, 20]}, "stages": 2},
                "cool": {"setpoint": {"validValues": [20, 25, 30]}, "stages": 2},
            }
        },
        "system": {"model": "ST-V1-0", "configCode": "A"}
    }
    caps = DeviceCapabilities.from_stv10_capabilities("st1", caps_json, api)

    assert caps.is_stv10
    assert caps.min_temp == 10
    assert caps.max_temp == 30
    assert caps.target_temperature_step == 5
    assert caps.has_stage_2_heat
    assert caps.has_stage_2_cool
    assert HVACMode.AUTO in caps.hvac_modes
    assert caps.hardware_model == "ST-V1-0"
