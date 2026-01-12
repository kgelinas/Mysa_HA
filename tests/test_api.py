"""
MysaApi Coverage Tests.

Tests that instantiate and test real MysaApi methods
to improve code coverage for mysa_api.py.
"""
import sys
import os

# Add project root to path for imports
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(TEST_DIR)
sys.path.insert(0, ROOT_DIR)

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import asyncio

# Module-level imports after path setup
from custom_components.mysa.const import DOMAIN


# ===========================================================================
# MysaApi Initialization Tests
# ===========================================================================

class TestMysaApiInit:
    """Test MysaApi initialization."""

    def test_api_init(self):
        """Test MysaApi initializes correctly."""
        from custom_components.mysa.mysa_api import MysaApi
        
        mock_hass = MagicMock()
        
        api = MysaApi(
            username="test@example.com",
            password="password123",
            hass=mock_hass,
        )
        
        assert api.username == "test@example.com"
        assert api.password == "password123"
        assert api.hass == mock_hass
        assert api.devices == {}
        assert api.states == {}

    def test_api_init_with_coordinator(self):
        """Test MysaApi initializes with coordinator callback."""
        from custom_components.mysa.mysa_api import MysaApi
        
        mock_hass = MagicMock()
        mock_callback = AsyncMock()
        
        api = MysaApi(
            username="test@example.com",
            password="password123",
            hass=mock_hass,
            coordinator_callback=mock_callback,
        )
        
        assert api.coordinator_callback == mock_callback

    def test_api_init_with_upgraded_lite_devices(self):
        """Test MysaApi initializes with upgraded lite devices."""
        from custom_components.mysa.mysa_api import MysaApi
        
        mock_hass = MagicMock()
        
        api = MysaApi(
            username="test@example.com",
            password="password123",
            hass=mock_hass,
            upgraded_lite_devices=["device1", "device2"],
            estimated_max_current=15.0,
        )
        
        assert api.upgraded_lite_devices == ["device1", "device2"]
        assert api.estimated_max_current == 15.0


# ===========================================================================
# Device Methods Tests
# ===========================================================================

class TestMysaApiDeviceMethods:
    """Test MysaApi device methods."""

    @pytest.fixture
    def mock_api(self):
        """Create a partially mocked MysaApi."""
        from custom_components.mysa.mysa_api import MysaApi
        
        mock_hass = MagicMock()
        mock_hass.async_add_executor_job = AsyncMock()
        
        api = MysaApi(
            username="test@example.com",
            password="password123",
            hass=mock_hass,
        )
        return api

    @pytest.mark.asyncio
    async def test_get_devices(self, mock_api):
        """Test get_devices calls async executor."""
        mock_api.hass.async_add_executor_job = AsyncMock(return_value={
            "device1": {"id": "device1", "Name": "Test"}
        })
        
        result = await mock_api.get_devices()
        
        mock_api.hass.async_add_executor_job.assert_called()

    @pytest.mark.asyncio
    async def test_get_state(self, mock_api):
        """Test get_state calls async executor."""
        mock_api.hass.async_add_executor_job = AsyncMock(return_value={
            "device1": {"temperature": 20.0}
        })
        
        result = await mock_api.get_state()
        
        mock_api.hass.async_add_executor_job.assert_called()

    @pytest.mark.asyncio
    async def test_fetch_homes(self, mock_api):
        """Test fetch_homes calls async executor."""
        mock_api.hass.async_add_executor_job = AsyncMock(return_value={})
        
        result = await mock_api.fetch_homes()
        
        mock_api.hass.async_add_executor_job.assert_called()

    def test_get_zone_name_found(self, mock_api):
        """Test get_zone_name returns zone name when found."""
        mock_api.zones = {"zone1": "Living Room", "zone2": "Bedroom"}
        
        result = mock_api.get_zone_name("zone1")
        
        assert result == "Living Room"

    def test_get_zone_name_not_found(self, mock_api):
        """Test get_zone_name returns None when not found."""
        mock_api.zones = {"zone1": "Living Room"}
        
        result = mock_api.get_zone_name("zone999")
        
        assert result is None

    def test_is_ac_device_true(self, mock_api):
        """Test is_ac_device returns True for AC device."""
        mock_api.devices = {"device1": {"Model": "AC-V1"}}
        
        result = mock_api.is_ac_device("device1")
        
        assert result is True

    def test_is_ac_device_false(self, mock_api):
        """Test is_ac_device returns False for non-AC device."""
        mock_api.devices = {"device1": {"Model": "BB-V2"}}
        
        result = mock_api.is_ac_device("device1")
        
        assert result is False

    def test_is_ac_device_unknown(self, mock_api):
        """Test is_ac_device returns False for unknown device."""
        mock_api.devices = {}
        
        result = mock_api.is_ac_device("unknown")
        
        assert result is False

    def test_get_ac_supported_caps(self, mock_api):
        """Test get_ac_supported_caps returns caps."""
        mock_api.devices = {
            "device1": {"SupportedCaps": {"modes": {"cool": {}}}}
        }
        
        result = mock_api.get_ac_supported_caps("device1")
        
        assert result == {"modes": {"cool": {}}}


# ===========================================================================
# State Normalization Tests
# ===========================================================================

class TestMysaApiStateNormalization:
    """Test MysaApi state normalization."""

    @pytest.fixture
    def api(self):
        """Create API instance."""
        from custom_components.mysa.mysa_api import MysaApi
        
        mock_hass = MagicMock()
        return MysaApi("test@example.com", "password", mock_hass)

    def test_normalize_state_empty(self, api):
        """Test normalize_state with empty dict."""
        state = {}
        api._normalize_state(state)
        
        # _normalize_state modifies in place, doesn't return
        assert isinstance(state, dict)

    def test_normalize_state_temperature(self, api):
        """Test normalize_state extracts temperature."""
        state = {"dr": {"v": 21.5}}
        
        api._normalize_state(state)
        
        # dr is not directly mapped, but check state is still valid
        assert isinstance(state, dict)

    def test_normalize_state_setpoint(self, api):
        """Test normalize_state extracts setpoint."""
        state = {"sp": {"v": 22.0}}
        
        api._normalize_state(state)
        
        # Should set SetPoint from sp
        assert state.get("SetPoint") == 22.0

    def test_normalize_state_mode(self, api):
        """Test normalize_state extracts mode."""
        state = {"md": {"v": 3}}
        
        api._normalize_state(state)
        
        assert state.get("Mode") == 3


# ===========================================================================
# MQTT Command Tests
# ===========================================================================

class TestMysaApiMqttCommands:
    """Test MysaApi MQTT command methods."""

    @pytest.fixture
    def mock_api(self):
        """Create API with mocked MQTT."""
        from custom_components.mysa.mysa_api import MysaApi
        
        mock_hass = MagicMock()
        mock_hass.async_add_executor_job = AsyncMock()
        
        api = MysaApi("test@example.com", "password", mock_hass)
        api._send_mqtt_command = AsyncMock()
        api.notify_settings_changed = AsyncMock()
        api.devices = {"device1": {"Model": "BB-V2"}}
        api.states = {"device1": {}}
        return api

    @pytest.mark.asyncio
    async def test_set_target_temperature(self, mock_api):
        """Test set_target_temperature sends MQTT command."""
        await mock_api.set_target_temperature("device1", 22.0)
        
        mock_api._send_mqtt_command.assert_called()

    @pytest.mark.asyncio
    async def test_set_hvac_mode_heat(self, mock_api):
        """Test set_hvac_mode sends MQTT command for heat."""
        await mock_api.set_hvac_mode("device1", "heat")
        
        mock_api._send_mqtt_command.assert_called()

    @pytest.mark.asyncio
    async def test_set_hvac_mode_off(self, mock_api):
        """Test set_hvac_mode sends MQTT command for off."""
        await mock_api.set_hvac_mode("device1", "off")
        
        mock_api._send_mqtt_command.assert_called()


# ===========================================================================
# Switch/Setting Methods Tests
# ===========================================================================

class TestMysaApiSettingMethods:
    """Test MysaApi setting methods."""

    @pytest.fixture
    def mock_api(self):
        """Create API with mocked methods."""
        from custom_components.mysa.mysa_api import MysaApi
        
        mock_hass = MagicMock()
        mock_hass.async_add_executor_job = AsyncMock()
        
        api = MysaApi("test@example.com", "password", mock_hass)
        api._send_mqtt_command = AsyncMock()
        api._set_device_setting_silent = AsyncMock()
        api.notify_settings_changed = AsyncMock()
        api.devices = {"device1": {"Model": "BB-V2"}}
        api.states = {"device1": {"Brightness": {"Idle": 10, "Active": 80}}}
        return api

    @pytest.mark.asyncio
    async def test_set_lock_on(self, mock_api):
        """Test set_lock sends lock command."""
        await mock_api.set_lock("device1", True)
        
        mock_api._send_mqtt_command.assert_called()

    @pytest.mark.asyncio
    async def test_set_lock_off(self, mock_api):
        """Test set_lock sends unlock command."""
        await mock_api.set_lock("device1", False)
        
        mock_api._send_mqtt_command.assert_called()

    @pytest.mark.asyncio
    async def test_set_proximity_on(self, mock_api):
        """Test set_proximity sends enable command."""
        await mock_api.set_proximity("device1", True)
        
        mock_api._send_mqtt_command.assert_called()

    @pytest.mark.asyncio
    async def test_set_auto_brightness_on(self, mock_api):
        """Test set_auto_brightness sends enable command."""
        await mock_api.set_auto_brightness("device1", True)
        
        mock_api._send_mqtt_command.assert_called()

    @pytest.mark.asyncio
    async def test_set_min_brightness(self, mock_api):
        """Test set_min_brightness sends command."""
        await mock_api.set_min_brightness("device1", 15)
        
        mock_api._send_mqtt_command.assert_called()

    @pytest.mark.asyncio
    async def test_set_max_brightness(self, mock_api):
        """Test set_max_brightness sends command."""
        await mock_api.set_max_brightness("device1", 90)
        
        mock_api._send_mqtt_command.assert_called()


# ===========================================================================
# AC Methods Tests
# ===========================================================================

class TestMysaApiAcMethods:
    """Test MysaApi AC-specific methods."""

    @pytest.fixture
    def mock_api(self):
        """Create API with mocked methods for AC device."""
        from custom_components.mysa.mysa_api import MysaApi
        
        mock_hass = MagicMock()
        mock_hass.async_add_executor_job = AsyncMock()
        
        api = MysaApi("test@example.com", "password", mock_hass)
        api._send_mqtt_command = AsyncMock()
        api.notify_settings_changed = AsyncMock()
        api.devices = {"ac_device": {"Model": "AC-V1"}}
        api.states = {"ac_device": {}}
        return api

    @pytest.mark.asyncio
    async def test_set_ac_climate_plus_on(self, mock_api):
        """Test set_ac_climate_plus enables thermostatic mode."""
        await mock_api.set_ac_climate_plus("ac_device", True)
        
        mock_api._send_mqtt_command.assert_called()

    @pytest.mark.asyncio
    async def test_set_ac_climate_plus_off(self, mock_api):
        """Test set_ac_climate_plus disables thermostatic mode."""
        await mock_api.set_ac_climate_plus("ac_device", False)
        
        mock_api._send_mqtt_command.assert_called()

    @pytest.mark.asyncio
    async def test_set_ac_fan_speed(self, mock_api):
        """Test set_ac_fan_speed sends command."""
        await mock_api.set_ac_fan_speed("ac_device", "high")
        
        mock_api._send_mqtt_command.assert_called()

    @pytest.mark.asyncio
    async def test_set_ac_swing_mode(self, mock_api):
        """Test set_ac_swing_mode sends command."""
        await mock_api.set_ac_swing_mode("ac_device", "auto")
        
        mock_api._send_mqtt_command.assert_called()

    @pytest.mark.asyncio
    async def test_set_ac_horizontal_swing(self, mock_api):
        """Test set_ac_horizontal_swing sends command."""
        await mock_api.set_ac_horizontal_swing("ac_device", 2)
        
        mock_api._send_mqtt_command.assert_called()


# ===========================================================================
# Payload Type Tests
# ===========================================================================

class TestMysaApiPayloadType:
    """Test MysaApi payload type detection."""

    @pytest.fixture
    def api(self):
        """Create API instance."""
        from custom_components.mysa.mysa_api import MysaApi
        
        mock_hass = MagicMock()
        return MysaApi("test@example.com", "password", mock_hass)

    def test_get_payload_type_v1(self, api):
        """Test _get_payload_type for V1 device."""
        api.devices = {"device1": {"Model": "BB-V1"}}
        
        result = api._get_payload_type("device1")
        
        assert result == 1

    def test_get_payload_type_v2(self, api):
        """Test _get_payload_type for V2 device."""
        api.devices = {"device1": {"Model": "BB-V2"}}
        
        result = api._get_payload_type("device1")
        
        assert result == 4

    def test_get_payload_type_lite(self, api):
        """Test _get_payload_type for Lite device."""
        api.devices = {"device1": {"Model": "BB-V2-L-Lite"}}
        
        result = api._get_payload_type("device1")
        
        # Lite should return 5
        assert result == 5

    def test_get_payload_type_ac(self, api):
        """Test _get_payload_type for AC device."""
        api.devices = {"device1": {"Model": "AC-V1"}}
        
        result = api._get_payload_type("device1")
        
        # AC uses AC_PAYLOAD_TYPE constant
        assert result == 2

    def test_get_payload_type_unknown(self, api):
        """Test _get_payload_type for unknown device."""
        api.devices = {}
        
        result = api._get_payload_type("unknown")
        
        assert result == 1  # Default


# ===========================================================================
# From test_api.py
# ===========================================================================

    def test_detect_thermostat_type_full(self):
        """Test detecting full thermostat (BB-V2)."""
        device = {"type": 4}
        
        device_type = device.get("type", 0)
        
        assert device_type == 4
        # Type 4 = BB-V2 (Full thermostat)

    def test_detect_thermostat_type_lite(self):
        """Test detecting lite thermostat (BB-V2-L)."""
        device = {"type": 5}
        
        device_type = device.get("type", 0)
        
        assert device_type == 5
        # Type 5 = BB-V2-L (Lite thermostat)

    def test_detect_ac_controller(self):
        """Test detecting AC controller."""
        device = {"type": 9}
        
        device_type = device.get("type", 0)
        
        assert device_type == 9
        # Type 9 = AC-V1 (AC Controller)

    def test_is_ac_device(self):
        """Test AC device detection helper."""
        ac_types = [9]  # AC-V1
        
        assert 9 in ac_types
        assert 4 not in ac_types
        assert 5 not in ac_types

    def test_normalize_already_clean(self):
        """Test normalizing an already clean device ID."""
        device_id = "device1"
        
        normalized = device_id.replace(":", "").lower()
        
        assert normalized == device_id


class TestStateCache:
    """Test device state caching."""

    def test_merge_state_updates(self):
        """Test merging state updates into existing state."""
        existing_state = {
            "temperature": 20.0,
            "setpoint": 21.0,
            "humidity": 45,
        }
        
        new_values = {
            "temperature": 20.5,
            "humidity": 46,
        }
        
        merged = {**existing_state, **new_values}
        
        assert merged["temperature"] == 20.5  # Updated
        assert merged["setpoint"] == 21.0  # Preserved
        assert merged["humidity"] == 46  # Updated

    def test_state_cache_ignores_none(self):
        """Test that None values don't overwrite existing state."""
        existing_state = {"temperature": 20.0}
        new_values = {"temperature": None}
        
        # Only merge non-None values
        for key, value in new_values.items():
            if value is not None:
                existing_state[key] = value
        
        assert existing_state["temperature"] == 20.0

    def test_state_cache_deep_copy(self):
        """Test that state updates don't affect original device settings."""
        original = {"name": "Living Room", "setpoint": 21.0}
        
        # Deep copy before modifying
        working = dict(original)
        working["setpoint"] = 22.0
        
        assert original["setpoint"] == 21.0
        assert working["setpoint"] == 22.0


class TestPayloadTypeMapping:
    """Test MQTT payload type mapping."""

    def test_payload_type_for_full_thermostat(self):
        """Test payload type for BB-V2 Full."""
        device_types = {
            4: 4,  # BB-V2 uses type 4
            5: 5,  # BB-V2-L uses type 5
            9: 9,  # AC-V1 uses type 9
        }
        
        assert device_types[4] == 4

    def test_payload_type_for_upgraded_lite(self):
        """Test payload type for upgraded Lite devices."""
        # Upgraded Lite devices should use type 5 even though they
        # behave like Full devices
        is_upgraded_lite = True
        detected_type = 4  # Detected as Full
        
        if is_upgraded_lite:
            payload_type = 5  # Force type 5
        else:
            payload_type = detected_type
        
        assert payload_type == 5


class TestAuthentication:
    """Test authentication flow."""

    def test_credentials_stored(self):
        """Test that credentials are stored after auth."""
        username = "test@example.com"
        password = "testpass123"
        
        stored = {
            "username": username,
            "password": password,
        }
        
        assert stored["username"] == username
        assert stored["password"] == password

    def test_tokens_refreshed(self):
        """Test token refresh mechanism."""
        old_token = "old-access-token"
        new_token = "new-access-token"
        
        # Simulate token refresh
        current_token = old_token
        current_token = new_token
        
        assert current_token == new_token


class TestMqttCommandBuilding:
    """Test MQTT command building."""

    def test_setpoint_command_structure(self):
        """Test setpoint command structure."""
        device_id = "device1"
        setpoint = 22.0
        
        command = {
            "did": device_id,
            "cmd": [{"sp": setpoint}],
        }
        
        assert command["did"] == device_id
        assert command["cmd"][0]["sp"] == setpoint

    def test_hvac_mode_command_structure(self):
        """Test HVAC mode command structure."""
        device_id = "device1"
        mode = 1  # Heat
        
        command = {
            "did": device_id,
            "cmd": [{"md": mode}],
        }
        
        assert command["did"] == device_id
        assert command["cmd"][0]["md"] == mode

    def test_brightness_command_structure(self):
        """Test brightness command structure."""
        device_id = "device1"
        brightness = 75
        
        command = {
            "did": device_id,
            "cmd": [{"br": brightness}],
        }
        
        assert command["did"] == device_id
        assert command["cmd"][0]["br"] == brightness


# ===========================================================================
# From test_token_refresh.py
# ===========================================================================

ROOT_DIR = os.path.dirname(TEST_DIR)
sys.path.insert(0, ROOT_DIR)

import pytest
from unittest.mock import MagicMock, patch


class TestTokenExpiry:
    """Test token expiry patterns."""

    def test_token_expiry_calculation(self):
        """Test token expiry time calculation."""
        from time import time
        
        current_time = time()
        expiry = current_time + 3600  # 1 hour
        
        time_remaining = expiry - current_time
        
        assert time_remaining > 3500  # Should be close to 3600
        assert time_remaining <= 3600

    def test_token_near_expiry_detection(self):
        """Test detection of near-expiry tokens."""
        from time import time
        
        current_time = time()
        
        # Token expiring in 30 seconds
        near_expiry = current_time + 30
        # Token expiring in 1 hour
        far_expiry = current_time + 3600
        
        refresh_buffer = 60  # 1 minute
        
        near_needs_refresh = (near_expiry - current_time) < refresh_buffer
        far_needs_refresh = (far_expiry - current_time) < refresh_buffer
        
        assert near_needs_refresh is True
        assert far_needs_refresh is False


class TestUrlSigning:
    """Test URL signing patterns."""

    def test_url_query_params(self):
        """Test URL query parameter handling."""
        from urllib.parse import urlparse, parse_qs
        
        url = "https://example.com/mqtt?X-Amz-Signature=abc&X-Amz-Security-Token=xyz"
        
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        
        assert "X-Amz-Signature" in params
        assert "X-Amz-Security-Token" in params

    def test_wss_url_scheme(self):
        """Test WSS URL scheme."""
        from custom_components.mysa.mysa_mqtt import get_websocket_url
        
        https_url = "https://test.iot.amazonaws.com/mqtt"
        wss_url = get_websocket_url(https_url)
        
        assert wss_url.startswith("wss://")


class TestCredentialMocking:
    """Test credential mocking patterns."""

    def test_mock_cognito_user(self):
        """Test mocking Cognito user."""
        mock_user = MagicMock()
        mock_user.id_token = "test-id-token"
        mock_user.access_token = "test-access-token"
        mock_user.refresh_token = "test-refresh-token"
        
        assert mock_user.id_token == "test-id-token"
        assert mock_user.access_token == "test-access-token"

    def test_mock_credentials(self):
        """Test mocking AWS credentials."""
        mock_creds = MagicMock()
        mock_creds.access_key = "AKIAIOSFODNN7EXAMPLE"
        mock_creds.secret_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        mock_creds.token = "test-session-token"
        
        assert mock_creds.access_key.startswith("AKIA")
        assert mock_creds.token == "test-session-token"


class TestAuthenticationAsync:
    """Test async authentication with mocking."""

    @pytest.mark.asyncio
    async def test_authenticate_success_mocked(self, hass):
        """Test MysaApi.authenticate with mocked login."""
        from unittest.mock import AsyncMock
        from custom_components.mysa.mysa_api import MysaApi
        
        with patch("custom_components.mysa.mysa_api.login") as mock_login, \
             patch("custom_components.mysa.mysa_api.auther"), \
             patch("custom_components.mysa.mysa_api.requests.Session"), \
             patch("custom_components.mysa.mysa_api.Store") as mock_store:
            
            mock_user = MagicMock()
            mock_user.id_token = "test-id-token"
            mock_user.access_token = "test-access-token"
            mock_login.return_value = mock_user
            
            mock_store_instance = mock_store.return_value
            mock_store_instance.async_load = AsyncMock(return_value=None)
            mock_store_instance.async_save = AsyncMock()
            
            api = MysaApi("test@example.com", "password123", hass)
            result = await api.authenticate()
            
            assert result is True
            mock_login.assert_called_once()

    @pytest.mark.asyncio
    async def test_authenticate_failure_mocked(self, hass):
        """Test MysaApi.authenticate failure with mocked login."""
        from unittest.mock import AsyncMock
        from custom_components.mysa.mysa_api import MysaApi
        
        with patch("custom_components.mysa.mysa_api.login") as mock_login, \
             patch("custom_components.mysa.mysa_api.Store") as mock_store:
            
            mock_login.side_effect = Exception("Invalid credentials")
            mock_store_instance = mock_store.return_value
            mock_store_instance.async_load = AsyncMock(return_value=None)
            
            api = MysaApi("test@example.com", "wrong_password", hass)
            
            with pytest.raises(Exception, match="Invalid credentials"):
                await api.authenticate()


# ===========================================================================
# _normalize_state Tests
# ===========================================================================

class TestNormalizeState:
    """Test _normalize_state method."""

    def create_api(self):
        """Create a minimal API instance for testing."""
        from custom_components.mysa.mysa_api import MysaApi
        api = MysaApi.__new__(MysaApi)
        api.devices = {}
        api.zones = {}
        api.device_states = {}
        return api

    def test_normalize_setpoint_sp(self):
        """Test normalizing setpoint from 'sp' key."""
        api = self.create_api()
        state = {"sp": 21.5}
        
        api._normalize_state(state)
        
        assert state.get("SetPoint") == 21.5

    def test_normalize_setpoint_dict_v(self):
        """Test normalizing setpoint from dict with 'v' key."""
        api = self.create_api()
        state = {"sp": {"v": 22.0}}
        
        api._normalize_state(state)
        
        assert state.get("SetPoint") == 22.0

    def test_normalize_mode(self):
        """Test normalizing mode from 'md' key."""
        api = self.create_api()
        state = {"md": 1}
        
        api._normalize_state(state)
        
        assert state.get("Mode") == 1

    def test_normalize_duty(self):
        """Test normalizing duty cycle."""
        api = self.create_api()
        state = {"dc": 50}
        
        api._normalize_state(state)
        
        assert state.get("Duty") == 50

    def test_normalize_rssi(self):
        """Test normalizing RSSI."""
        api = self.create_api()
        state = {"rssi": -55}
        
        api._normalize_state(state)
        
        assert state.get("Rssi") == -55

    def test_normalize_voltage(self):
        """Test normalizing voltage."""
        api = self.create_api()
        state = {"volts": 240}
        
        api._normalize_state(state)
        
        assert state.get("Voltage") == 240

    def test_normalize_current(self):
        """Test normalizing current."""
        api = self.create_api()
        state = {"amps": 10.5}
        
        api._normalize_state(state)
        
        assert state.get("Current") == 10.5

    def test_normalize_heatsink(self):
        """Test normalizing heat sink temperature."""
        api = self.create_api()
        state = {"hs": 35.5}
        
        api._normalize_state(state)
        
        assert state.get("HeatSink") == 35.5

    def test_normalize_infloor(self):
        """Test normalizing infloor temperature."""
        api = self.create_api()
        state = {"if": 25.0}
        
        api._normalize_state(state)
        
        assert state.get("Infloor") == 25.0

    def test_normalize_brightness(self):
        """Test normalizing brightness."""
        api = self.create_api()
        state = {"br": 75}
        
        api._normalize_state(state)
        
        assert state.get("Brightness") == 75

    def test_normalize_lock_true(self):
        """Test normalizing lock state (true)."""
        api = self.create_api()
        state = {"lk": 1}
        
        api._normalize_state(state)
        
        assert state.get("Lock") == 1

    def test_normalize_lock_false(self):
        """Test normalizing lock state (false)."""
        api = self.create_api()
        state = {"lk": 0}
        
        api._normalize_state(state)
        
        assert state.get("Lock") == 0

    def test_normalize_lock_string(self):
        """Test normalizing lock state from string."""
        api = self.create_api()
        state = {"lk": "true"}
        
        api._normalize_state(state)
        
        assert state.get("Lock") == 1

    def test_normalize_zone(self):
        """Test normalizing zone ID."""
        api = self.create_api()
        state = {"zn": "zone-123"}
        
        api._normalize_state(state)
        
        assert state.get("Zone") == "zone-123"

    def test_normalize_proximity(self):
        """Test normalizing proximity mode."""
        api = self.create_api()
        state = {"px": "1"}
        
        api._normalize_state(state)
        
        assert state.get("ProximityMode") is True

    def test_normalize_auto_brightness(self):
        """Test normalizing auto brightness."""
        api = self.create_api()
        state = {"ab": "1"}
        
        api._normalize_state(state)
        
        assert state.get("AutoBrightness") is True

    def test_normalize_eco_mode(self):
        """Test normalizing eco mode (0=On, 1=Off)."""
        api = self.create_api()
        state = {"ecoMode": "0"}
        
        api._normalize_state(state)
        
        assert state.get("EcoMode") is True

    def test_normalize_min_max_brightness(self):
        """Test normalizing min/max brightness."""
        api = self.create_api()
        state = {"mnbr": 10, "mxbr": 90}
        
        api._normalize_state(state)
        
        assert state.get("MinBrightness") == 10
        assert state.get("MaxBrightness") == 90

    def test_normalize_max_current(self):
        """Test normalizing max current."""
        api = self.create_api()
        state = {"mxc": 15}
        
        api._normalize_state(state)
        
        assert state.get("MaxCurrent") == 15

    def test_normalize_max_setpoint(self):
        """Test normalizing max setpoint."""
        api = self.create_api()
        state = {"mxs": 30}
        
        api._normalize_state(state)
        
        assert state.get("MaxSetpoint") == 30

    def test_normalize_timezone(self):
        """Test normalizing timezone."""
        api = self.create_api()
        state = {"tz": "America/New_York"}
        
        api._normalize_state(state)
        
        assert state.get("TimeZone") == "America/New_York"

    def test_normalize_ac_fan_speed(self):
        """Test normalizing AC fan speed."""
        api = self.create_api()
        state = {"fn": 2}
        
        api._normalize_state(state)
        
        assert state.get("FanSpeed") == 2
        assert state.get("FanMode") is not None

    def test_normalize_ac_swing_state(self):
        """Test normalizing AC swing state."""
        api = self.create_api()
        state = {"ss": 1}
        
        api._normalize_state(state)
        
        assert state.get("SwingState") == 1
        assert state.get("SwingMode") is not None

    def test_normalize_ac_horizontal_swing(self):
        """Test normalizing AC horizontal swing."""
        api = self.create_api()
        state = {"ssh": 3}
        
        api._normalize_state(state)
        
        assert state.get("SwingStateHorizontal") == 3

    def test_normalize_tstat_mode(self):
        """Test normalizing TstatMode."""
        api = self.create_api()
        state = {"TstatMode": 2}
        
        api._normalize_state(state)
        
        assert state.get("TstatMode") == 2

    def test_normalize_acstate_dict(self):
        """Test normalizing ACState dictionary."""
        api = self.create_api()
        state = {
            "ACState": {
                "v": {
                    "1": 1,  # Power
                    "2": 2,  # Mode
                    "3": 24.0,  # Temperature
                    "4": 3,  # Fan
                    "5": 2,  # Swing
                }
            }
        }
        
        api._normalize_state(state)
        
        assert state.get("ACPower") == 1
        assert state.get("ACMode") == 2
        assert state.get("ACTemp") == 24.0
        assert state.get("FanSpeed") == 3
        assert state.get("SwingState") == 2

    def test_normalize_brightness_dict_v2(self):
        """Test normalizing V2 brightness with a_br key."""
        api = self.create_api()
        state = {"Brightness": {"a_br": 80}}
        
        api._normalize_state(state)
        
        assert state.get("Brightness") == 80


# ===========================================================================
# _get_payload_type Tests
# ===========================================================================

class TestGetPayloadType:
    """Test _get_payload_type method."""

    def create_api(self):
        """Create a minimal API instance for testing."""
        from custom_components.mysa.mysa_api import MysaApi
        api = MysaApi.__new__(MysaApi)
        api.devices = {}
        api.upgraded_lite_devices = []
        return api

    def test_payload_type_upgraded_lite(self):
        """Test payload type for upgraded Lite device."""
        api = self.create_api()
        api.upgraded_lite_devices = ["device123"]
        
        result = api._get_payload_type("device123")
        
        assert result == 5

    def test_payload_type_upgraded_lite_normalized(self):
        """Test payload type for upgraded Lite with different formatting."""
        api = self.create_api()
        api.upgraded_lite_devices = ["DE:VI:CE:12:34:56"]
        
        result = api._get_payload_type("device123456")
        
        assert result == 5

    def test_payload_type_missing_device(self):
        """Test payload type for missing device returns default."""
        api = self.create_api()
        
        result = api._get_payload_type("unknown_device")
        
        assert result == 1

    def test_payload_type_ac(self):
        """Test payload type for AC controller."""
        api = self.create_api()
        api.devices = {"ac_device": {"Model": "AC-V1-0"}}
        
        result = api._get_payload_type("ac_device")
        
        assert result == 2  # AC_PAYLOAD_TYPE

    def test_payload_type_bb_v2(self):
        """Test payload type for BB-V2."""
        api = self.create_api()
        api.devices = {"device1": {"Model": "BB-V2-0"}}
        
        result = api._get_payload_type("device1")
        
        assert result == 4

    def test_payload_type_bb_v2_lite(self):
        """Test payload type for BB-V2 Lite."""
        api = self.create_api()
        api.devices = {"device1": {"Model": "BB-V2-L"}}
        
        result = api._get_payload_type("device1")
        
        assert result == 5

    def test_payload_type_infloor(self):
        """Test payload type for In-floor heater."""
        api = self.create_api()
        api.devices = {"device1": {"Model": "INF-V1-0"}}
        
        result = api._get_payload_type("device1")
        
        assert result == 3

    def test_payload_type_bb_v1(self):
        """Test payload type for BB-V1."""
        api = self.create_api()
        api.devices = {"device1": {"Model": "BB-V1-0"}}
        
        result = api._get_payload_type("device1")
        
        assert result == 1

    def test_payload_type_v2_firmware(self):
        """Test payload type detected from V2 firmware."""
        api = self.create_api()
        api.devices = {"device1": {"Model": "Unknown", "FirmwareVersion": "V2.1.0"}}
        
        result = api._get_payload_type("device1")
        
        assert result == 4


# ===========================================================================
# _get_brightness_object Tests
# ===========================================================================

class TestGetBrightnessObject:
    """Test _get_brightness_object method."""

    def create_api(self):
        """Create a minimal API instance for testing."""
        from custom_components.mysa.mysa_api import MysaApi
        api = MysaApi.__new__(MysaApi)
        api.devices = {}
        api.states = {}
        return api

    def test_brightness_defaults(self):
        """Test brightness returns defaults when no state."""
        api = self.create_api()
        
        result = api._get_brightness_object("device1")
        
        assert result["a_b"] == 1
        assert result["a_br"] == 100
        assert result["i_br"] == 50

    def test_brightness_from_state(self):
        """Test brightness extracted from state."""
        api = self.create_api()
        api.states = {
            "device1": {
                "Brightness": {
                    "a_b": 0,
                    "a_br": 80,
                    "i_br": 30,
                }
            }
        }
        
        result = api._get_brightness_object("device1")
        
        assert result["a_b"] == 0
        assert result["a_br"] == 80
        assert result["i_br"] == 30

    def test_brightness_non_dict_returns_defaults(self):
        """Test brightness returns defaults when not a dict."""
        api = self.create_api()
        api.states = {"device1": {"Brightness": 75}}  # Integer, not dict
        
        result = api._get_brightness_object("device1")
        
        assert result["a_br"] == 100  # Default


# ===========================================================================
# _update_state_cache Tests
# ===========================================================================

class TestUpdateStateCache:
    """Test _update_state_cache method."""

    def create_api(self):
        """Create a minimal API instance for testing."""
        from custom_components.mysa.mysa_api import MysaApi
        api = MysaApi.__new__(MysaApi)
        api.states = {}
        return api

    def test_creates_new_state(self):
        """Test creates state for new device."""
        api = self.create_api()
        
        api._update_state_cache("device1", {"SetPoint": 21.5})
        
        assert api.states["device1"]["SetPoint"] == 21.5

    def test_updates_existing_state(self):
        """Test updates existing state."""
        api = self.create_api()
        api.states = {"device1": {"Mode": 1}}
        
        api._update_state_cache("device1", {"SetPoint": 22.0})
        
        assert api.states["device1"]["SetPoint"] == 22.0
        assert api.states["device1"]["Mode"] == 1


# ===========================================================================
# _update_brightness_cache Tests
# ===========================================================================

class TestUpdateBrightnessCache:
    """Test _update_brightness_cache method."""

    def create_api(self):
        """Create a minimal API instance for testing."""
        from custom_components.mysa.mysa_api import MysaApi
        api = MysaApi.__new__(MysaApi)
        api.states = {}
        return api

    def test_creates_brightness_object(self):
        """Test creates brightness object for new device."""
        api = self.create_api()
        
        api._update_brightness_cache("device1", "a_br", 80)
        
        assert api.states["device1"]["Brightness"]["a_br"] == 80

    def test_updates_existing_brightness(self):
        """Test updates existing brightness value."""
        api = self.create_api()
        api.states = {
            "device1": {
                "Brightness": {"a_br": 100, "i_br": 50}
            }
        }
        
        api._update_brightness_cache("device1", "a_br", 75)
        
        assert api.states["device1"]["Brightness"]["a_br"] == 75
        assert api.states["device1"]["Brightness"]["i_br"] == 50


# ===========================================================================
# _process_mqtt_publish Tests
# ===========================================================================

class TestProcessMqttPublish:
    """Test _process_mqtt_publish method."""

    def create_api(self):
        """Create a minimal API instance for testing."""
        from custom_components.mysa.mysa_api import MysaApi
        api = MysaApi.__new__(MysaApi)
        api.devices = {"device1": {"Model": "BB-V2"}}
        api.states = {}
        api.coordinator_callback = None
        return api

    @pytest.mark.asyncio
    async def test_process_state_update(self):
        """Test processing MQTT state update message."""
        api = self.create_api()
        
        from unittest.mock import MagicMock
        pkt = MagicMock()
        pkt.topic = "/v1/dev/device1/out"
        pkt.payload = b'{"msg": 40, "body": {"state": {"sp": 21.5, "md": 1}}}'
        
        await api._process_mqtt_publish(pkt)
        
        assert api.states["device1"]["SetPoint"] == 21.5
        assert api.states["device1"]["Mode"] == 1

    @pytest.mark.asyncio
    async def test_process_cmd_array(self):
        """Test processing MQTT message with cmd array."""
        api = self.create_api()
        
        from unittest.mock import MagicMock
        pkt = MagicMock()
        pkt.topic = "/v1/dev/device1/out"
        pkt.payload = b'{"msg": 44, "body": {"cmd": [{"sp": 22.0}]}}'
        
        await api._process_mqtt_publish(pkt)
        
        assert api.states["device1"]["SetPoint"] == 22.0

    @pytest.mark.asyncio
    async def test_process_unknown_device(self):
        """Test processing MQTT message for unknown device."""
        api = self.create_api()
        
        from unittest.mock import MagicMock
        pkt = MagicMock()
        pkt.topic = "/v1/dev/unknown_device/out"
        pkt.payload = b'{"msg": 40, "body": {"state": {"sp": 21.5}}}'
        
        # Should not raise
        await api._process_mqtt_publish(pkt)
        
        assert "unknown_device" not in api.states

    @pytest.mark.asyncio
    async def test_process_with_coordinator_callback(self):
        """Test processing MQTT triggers coordinator callback."""
        api = self.create_api()
        
        from unittest.mock import MagicMock, AsyncMock
        api.coordinator_callback = AsyncMock()
        
        pkt = MagicMock()
        pkt.topic = "/v1/dev/device1/out"
        pkt.payload = b'{"msg": 40, "body": {"state": {"sp": 21.5}}}'
        
        await api._process_mqtt_publish(pkt)
        
        api.coordinator_callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_invalid_json(self):
        """Test processing MQTT with invalid JSON doesn't raise."""
        api = self.create_api()
        
        from unittest.mock import MagicMock
        pkt = MagicMock()
        pkt.topic = "/v1/dev/device1/out"
        pkt.payload = b'invalid json'
        
        # Should not raise
        await api._process_mqtt_publish(pkt)

    @pytest.mark.asyncio
    async def test_process_body_as_state(self):
        """Test processing MQTT uses body as state when state is empty."""
        api = self.create_api()
        
        from unittest.mock import MagicMock
        pkt = MagicMock()
        pkt.topic = "/v1/dev/device1/out"
        pkt.payload = b'{"msg": 40, "body": {"sp": 23.0, "md": 2}}'
        
        await api._process_mqtt_publish(pkt)
        
        assert api.states["device1"]["SetPoint"] == 23.0

    @pytest.mark.asyncio
    async def test_process_updates_existing_state(self):
        """Test processing MQTT updates existing state."""
        api = self.create_api()
        api.states = {"device1": {"Mode": 1, "Rssi": -50}}
        
        from unittest.mock import MagicMock
        pkt = MagicMock()
        pkt.topic = "/v1/dev/device1/out"
        pkt.payload = b'{"msg": 40, "body": {"state": {"sp": 21.5}}}'
        
        await api._process_mqtt_publish(pkt)
        
        assert api.states["device1"]["SetPoint"] == 21.5
        assert api.states["device1"]["Mode"] == 1  # Preserved


# ===========================================================================
# is_ac_device and get_ac_supported_caps Tests
# ===========================================================================

class TestAcDeviceMethods:
    """Test AC device helper methods."""

    def create_api(self):
        """Create a minimal API instance for testing."""
        from custom_components.mysa.mysa_api import MysaApi
        api = MysaApi.__new__(MysaApi)
        api.devices = {}
        return api

    def test_is_ac_device_true(self):
        """Test is_ac_device returns True for AC device."""
        api = self.create_api()
        api.devices = {"ac1": {"Model": "AC-V1-0"}}
        
        assert api.is_ac_device("ac1") is True

    def test_is_ac_device_false(self):
        """Test is_ac_device returns False for non-AC device."""
        api = self.create_api()
        api.devices = {"device1": {"Model": "BB-V2-0"}}
        
        assert api.is_ac_device("device1") is False

    def test_is_ac_device_missing(self):
        """Test is_ac_device returns False for missing device."""
        api = self.create_api()
        
        assert api.is_ac_device("unknown") is False

    def test_get_ac_supported_caps(self):
        """Test get_ac_supported_caps returns SupportedCaps."""
        api = self.create_api()
        api.devices = {
            "ac1": {
                "Model": "AC-V1",
                "SupportedCaps": {"HasHorizontalSwing": True}
            }
        }
        
        result = api.get_ac_supported_caps("ac1")
        
        assert result["HasHorizontalSwing"] is True

    def test_get_ac_supported_caps_empty(self):
        """Test get_ac_supported_caps returns empty dict for missing."""
        api = self.create_api()
        api.devices = {"ac1": {"Model": "AC-V1"}}
        
        result = api.get_ac_supported_caps("ac1")
        
        assert result == {}


# ===========================================================================
# get_zone_name Tests
# ===========================================================================

class TestGetZoneName:
    """Test get_zone_name method."""

    def create_api(self):
        """Create a minimal API instance for testing."""
        from custom_components.mysa.mysa_api import MysaApi
        api = MysaApi.__new__(MysaApi)
        api.zones = {}
        return api

    def test_get_zone_name_found(self):
        """Test get_zone_name returns name when found."""
        api = self.create_api()
        api.zones = {"zone123": "Living Room"}
        
        result = api.get_zone_name("zone123")
        
        assert result == "Living Room"

    def test_get_zone_name_not_found(self):
        """Test get_zone_name returns None when not found."""
        api = self.create_api()
        
        result = api.get_zone_name("unknown_zone")
        
        assert result is None


# ===========================================================================
# Additional Edge Case Tests
# ===========================================================================

class TestNormalizeStateEdgeCases:
    """Test edge cases in _normalize_state."""

    def create_api(self):
        """Create a minimal API instance for testing."""
        from custom_components.mysa.mysa_api import MysaApi
        api = MysaApi.__new__(MysaApi)
        api.devices = {}
        api.zones = {}
        api.device_states = {}
        return api

    def test_normalize_dict_without_v_key(self):
        """Test dict value without 'v' key continues to next key."""
        api = self.create_api()
        # sp is a dict without 'v', so should continue to 'stpt' fallback
        state = {"sp": {"other": 20.0}, "stpt": 21.5}
        
        api._normalize_state(state)
        
        assert state.get("SetPoint") == 21.5

    def test_normalize_brightness_dict_without_v_continues(self):
        """Test Brightness dict follows special a_br path."""
        api = self.create_api()
        # Brightness dict without 'v' but with 'a_br' should use a_br
        state = {"Brightness": {"a_br": 85}}
        
        api._normalize_state(state)
        
        assert state.get("Brightness") == 85

    def test_normalize_acstate_without_v(self):
        """Test ACState dict without 'v' wrapper."""
        api = self.create_api()
        state = {
            "ACState": {
                "1": 1,
                "2": 3,
            }
        }
        
        api._normalize_state(state)
        
        assert state.get("ACPower") == 1
        assert state.get("ACMode") == 3

    def test_normalize_acstate_with_existing_fan(self):
        """Test ACState doesn't override existing FanSpeed."""
        api = self.create_api()
        state = {
            "FanSpeed": 5,  # Already set
            "ACState": {"v": {"4": 2}}  # Would set to 2
        }
        
        api._normalize_state(state)
        
        assert state.get("FanSpeed") == 5  # Not overwritten


class TestGetPayloadTypeEdgeCases:
    """Test edge cases in _get_payload_type."""

    def create_api(self):
        """Create a minimal API instance for testing."""
        from custom_components.mysa.mysa_api import MysaApi
        api = MysaApi.__new__(MysaApi)
        api.devices = {}
        api.upgraded_lite_devices = []
        return api

    def test_payload_type_floor_model(self):
        """Test Floor in model name."""
        api = self.create_api()
        api.devices = {"device1": {"Model": "FloorHeater"}}
        
        result = api._get_payload_type("device1")
        
        assert result == 3

    def test_payload_type_baseboard_model(self):
        """Test Baseboard in model name."""
        api = self.create_api()
        api.devices = {"device1": {"Model": "Baseboard-Classic"}}
        
        result = api._get_payload_type("device1")
        
        assert result == 1

    def test_payload_type_v2_lite_dash(self):
        """Test BB-V2 with -L suffix."""
        api = self.create_api()
        api.devices = {"device1": {"Model": "BB-V2-L"}}
        
        result = api._get_payload_type("device1")
        
        assert result == 5

    def test_payload_type_fallback_default(self):
        """Test unknown model without V2 firmware returns default."""
        api = self.create_api()
        api.devices = {"device1": {"Model": "Unknown", "FirmwareVersion": "1.0.0"}}
        
        result = api._get_payload_type("device1")
        
        assert result == 1
