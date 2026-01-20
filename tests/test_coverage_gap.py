"""Tests to reach 100% coverage by exercising defensive None checks and special branches."""
import pytest
import time
from unittest.mock import MagicMock
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.components.sensor import SensorStateClass, SensorDeviceClass
from homeassistant.const import UnitOfTemperature

from custom_components.mysa.climate import MysaClimate
from custom_components.mysa.sensor import (
    MysaDiagnosticSensor, MysaPowerSensor, MysaCurrentSensor,
    MysaIpSensor, MysaTemperatureSensor, MysaHumiditySensor
)
from custom_components.mysa.number import MysaNumber
from custom_components.mysa.switch import MysaSwitch
from custom_components.mysa.select import MysaHorizontalSwingSelect
from custom_components.mysa.const import AC_SWING_AUTO, AC_SWING_POSITION_3
from pytest_homeassistant_custom_component.common import MockConfigEntry

@pytest.fixture
def mock_coordinator(hass):
    mock_entry = MockConfigEntry(domain="mysa", data={})
    mock_entry.add_to_hass(hass)
    coordinator = DataUpdateCoordinator(
        hass,
        MagicMock(),
        name="test",
        update_method=MagicMock(),
        config_entry=mock_entry
    )
    coordinator.data = {}
    return coordinator

@pytest.fixture
def mock_entry():
    return MockConfigEntry(domain="mysa", data={})

@pytest.fixture
def mock_api():
    api = MagicMock()
    api.simulated_energy = False
    return api

def test_climate_coverage(mock_coordinator, mock_entry):
    """Exercise climate.py missing lines."""
    entity = MysaClimate(mock_coordinator, "dev1", {}, MagicMock(), mock_entry)
    # 212-213 (None state)
    assert entity._extract_value(None, ["key"]) is None
    # 206-207 (None data)
    mock_coordinator.data = None
    assert entity._get_state_data() is None
    # 230 sticky expiration
    entity._pending_updates["test"] = {"value": 1, "ts": time.time() - 31}
    assert entity._get_sticky_value("test", 0) == 0

def test_sensor_diagnostic_coverage(mock_coordinator, mock_entry):
    """Exercise sensor.py diagnostic missing lines."""
    entity = MysaDiagnosticSensor(mock_coordinator, "dev1", {}, "key", "key", None, SensorStateClass.MEASUREMENT, None, mock_entry)
    # 299-300
    assert entity._extract_value(None, ["key"]) is None
    # Try to hit value conversion failure if possible
    mock_coordinator.data = {"dev1": {"key": "not_a_number"}}
    # Instead of mocking extract_value, let's just test that it returns the string if float fails
    assert entity.native_value == "not_a_number"

def test_sensor_power_coverage(mock_coordinator, mock_entry, mock_api):
    """Exercise sensor.py power missing lines."""
    entity = MysaPowerSensor(mock_coordinator, "dev1", {}, mock_api, mock_entry)
    # 351, 367, 370, 425
    assert entity._extract_value(None, ["key"]) is None
    mock_coordinator.data = None
    assert entity.native_value is None
    assert entity.extra_state_attributes == {}
    mock_coordinator.data = {"other": {}}
    assert entity.native_value is None

def test_sensor_current_coverage(mock_coordinator, mock_entry, mock_api):
    """Exercise sensor.py current missing lines."""
    entity = MysaCurrentSensor(mock_coordinator, "dev1", {}, mock_api, mock_entry)
    # 479, 497
    assert entity._extract_value(None, ["key"]) is None
    mock_coordinator.data = None
    assert entity.native_value is None
    mock_coordinator.data = {"other": {}}
    assert entity.native_value is None

def test_sensor_ip_coverage(mock_coordinator, mock_entry):
    """Exercise sensor.py IP missing lines."""
    entity = MysaIpSensor(mock_coordinator, "dev1", {}, mock_entry)
    # 739 (native_value state None)
    mock_coordinator.data = {} # state is None
    assert entity.native_value is None
    mock_coordinator.data = {"dev1": {"ip": "1.2.3.4"}}
    assert entity.native_value == "1.2.3.4"
    mock_coordinator.data = {"dev1": {"Local IP": "5.6.7.8"}}
    assert entity.native_value == "5.6.7.8"

    # Nested dict cases for 739-742
    mock_coordinator.data = {"dev1": {"ip": {"v": "1.1.1.1"}}}
    assert entity.native_value == "1.1.1.1" # Covers 739
    mock_coordinator.data = {"dev1": {"ip": {"v": None, "Id": "2.2.2.2"}}}
    assert entity.native_value == "2.2.2.2" # Covers 741
    mock_coordinator.data = {"dev1": {"ip": {"v": None, "Id": None}}}
    assert entity.native_value is None # Covers the end of loop

def test_device_ip_normalization():
    """Exercise device.py line 236."""
    from custom_components.mysa.device import MysaDeviceLogic
    state = {"Local IP": "10.0.0.1"}
    MysaDeviceLogic.normalize_state(state)
    assert state["ip"] == "10.0.0.1"

    # Also test MaxCurrent which is near it
    state = {"MaxCurrent": 15}
    MysaDeviceLogic.normalize_state(state)
    assert state["MaxCurrent"] == 15

def test_sensor_temp_coverage(mock_coordinator, mock_entry):
    """Exercise sensor.py Temperature missing lines."""
    entity = MysaTemperatureSensor(mock_coordinator, "dev1", {}, MagicMock(), mock_entry)
    # 774-775, 781, 784
    mock_coordinator.data = None
    assert entity.device_info is not None
    assert entity.native_value is None
    mock_coordinator.data = {"other": {}}
    assert entity.native_value is None

def test_sensor_hum_coverage(mock_coordinator, mock_entry):
    """Exercise sensor.py Humidity missing lines."""
    entity = MysaHumiditySensor(mock_coordinator, "dev1", {}, MagicMock(), mock_entry)
    # 837-838, 844, 847
    mock_coordinator.data = None
    assert entity.device_info is not None
    assert entity.native_value is None
    mock_coordinator.data = {"other": {}}
    assert entity.native_value is None

def test_number_coverage(mock_coordinator, mock_entry):
    """Exercise number.py missing lines."""
    entity = MysaNumber(mock_coordinator, "dev1", {}, MagicMock(), mock_entry, "key", "key")
    # 89, 95, 110
    mock_coordinator.data = None
    assert entity.device_info is not None
    assert entity._extract_value(None, ["key"]) is None
    assert entity._get_value_with_pending(["key"]) is None

def test_switch_coverage(mock_coordinator, mock_entry):
    """Exercise switch.py missing lines."""
    entity = MysaSwitch(mock_coordinator, "dev1", {}, MagicMock(), mock_entry, "key", "key")
    # 100, 115, 118, 126, 131
    assert entity._extract_value(None, ["key"]) is None
    mock_coordinator.data = None
    assert entity._get_state_with_pending(["key"]) is False
    mock_coordinator.data = {"other": {}}
    assert entity._get_state_with_pending(["key"]) is False
    # Expiration
    entity._pending_state = True
    entity._pending_timestamp = time.time() - 31
    mock_coordinator.data = {"dev1": {"key": False}}
    assert entity._get_state_with_pending(["key"]) is False
    # Convergence
    entity._pending_state = True
    entity._pending_timestamp = time.time()
    mock_coordinator.data = {"dev1": {"key": True}}
    assert entity._get_state_with_pending(["key"]) is True
    assert entity._pending_state is None

def test_select_coverage(mock_coordinator, mock_entry):
    """Exercise select.py missing lines."""
    entity = MysaHorizontalSwingSelect(mock_coordinator, "dev1", {}, MagicMock(), mock_entry)
    # 146, 152 sticky expiration and convergence
    # Expiration
    entity._pending_option = "swing1"
    entity._pending_timestamp = time.time() - 31
    mock_coordinator.data = {"dev1": {"ssh": AC_SWING_AUTO}} # 3 -> 'auto'
    assert entity.current_option == "auto"
    assert entity._pending_option is None
    # Convergence
    entity._pending_option = "center"
    entity._pending_timestamp = time.time()
    mock_coordinator.data = {"dev1": {"ssh": AC_SWING_POSITION_3}} # 6 -> 'center'
    assert entity.current_option == "center"
    assert entity._pending_option is None
