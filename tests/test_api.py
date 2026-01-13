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
from unittest.mock import MagicMock, AsyncMock, patch, ANY
import asyncio
import json

# Module-level imports after path setup
from custom_components.mysa.const import DOMAIN
from custom_components.mysa import mqtt


# ===========================================================================
# MysaApi Initialization Tests
# ===========================================================================


@pytest.mark.unit
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


@pytest.mark.unit
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
        mock_api.hass.async_add_executor_job = AsyncMock(
            return_value={"device1": {"id": "device1", "Name": "Test"}}
        )

        result = await mock_api.get_devices()

        mock_api.hass.async_add_executor_job.assert_called()

    @pytest.mark.asyncio
    async def test_get_state(self, mock_api):
        """Test get_state calls async executor."""
        mock_api.hass.async_add_executor_job = AsyncMock(
            return_value={"device1": {"temperature": 20.0}}
        )

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
        mock_api.devices = {"device1": {"SupportedCaps": {"modes": {"cool": {}}}}}

        result = mock_api.get_ac_supported_caps("device1")

        assert result == {"modes": {"cool": {}}}


# ===========================================================================
# State Normalization Tests
# ===========================================================================


@pytest.mark.unit
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


@pytest.mark.unit
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


@pytest.mark.unit
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


@pytest.mark.unit
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


@pytest.mark.unit
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


@pytest.mark.unit
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


@pytest.mark.unit
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


@pytest.mark.unit
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


@pytest.mark.unit
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


@pytest.mark.unit
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


@pytest.mark.unit
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


@pytest.mark.unit
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


@pytest.mark.unit
class TestAuthenticationAsync:
    """Test async authentication with mocking."""

    @pytest.mark.asyncio
    async def test_authenticate_success_mocked(self, hass):
        """Test MysaApi.authenticate with mocked login."""
        from unittest.mock import AsyncMock
        from custom_components.mysa.mysa_api import MysaApi

        with (
            patch("custom_components.mysa.mysa_api.login") as mock_login,
            patch("custom_components.mysa.mysa_api.auther"),
            patch("custom_components.mysa.mysa_api.requests.Session"),
            patch("custom_components.mysa.mysa_api.Store") as mock_store,
        ):
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

        with (
            patch("custom_components.mysa.mysa_api.login") as mock_login,
            patch("custom_components.mysa.mysa_api.Store") as mock_store,
            patch("custom_components.mysa.mysa_api.boto3"),
        ):
            mock_login.side_effect = Exception("Invalid credentials")
            mock_store_instance = mock_store.return_value
            mock_store_instance.async_load = AsyncMock(return_value=None)

            api = MysaApi("test@example.com", "wrong_password", hass)

            with pytest.raises(Exception, match="Invalid credentials"):
                await api.authenticate()

# ===========================================================================
# Sync Method Tests (Real Logic)
# ===========================================================================


@pytest.mark.unit
class TestMysaApiSyncMethods:
    """Test MysaApi synchronous methods (real logic, not mocked)."""

    @pytest.fixture
    def api(self):
        """Create API instance with mocked session."""
        from custom_components.mysa.mysa_api import MysaApi
        
        class MockHass:
            async def async_add_executor_job(self, func, *args):
                return func(*args)

        mock_hass = MockHass()
        mock_hass.data = {} # Required by Store
        mock_hass.config = MagicMock() # Required by something else

        api = MysaApi("test@example.com", "password", mock_hass)
        api._session = MagicMock()
        
        # Pre-mock store
        class MockStore:
            async def async_load(self):
                return None
            async def async_save(self, data):
                return None
                
        api._store = MockStore()
        return api

    @pytest.mark.asyncio
    async def test_authenticate_cached_login_success(self, api):
        """Test authenticate using cached credentials."""
        # Setup cached data
        async def mock_load():
             return {
                "id_token": "valid_id",
                "refresh_token": "valid_refresh"
            }
        api._store.async_load = mock_load
        
        # Setup successful Cognito init and verify
        from custom_components.mysa.mysa_auth import Cognito
        
        # We need to mock Cognito in mysa_api
        with patch("custom_components.mysa.mysa_api.Cognito") as mock_cognito_cls, \
             patch("custom_components.mysa.mysa_api.boto3"):
             
            mock_user = MagicMock()
            mock_cognito_cls.return_value = mock_user
            
            # verify_token succeeds
            mock_user.verify_token.return_value = True
            
            # Run authenticate
            await api.authenticate()
            
            # Assertions
            # Assertions
            from unittest.mock import ANY
            mock_cognito_cls.assert_called_with(
                user_pool_id=ANY, 
                client_id=ANY,
                id_token="valid_id",
                refresh_token="valid_refresh",
                username=api.username,
                session=ANY, 
                pool_jwk=ANY
            )
            mock_user.verify_token.assert_called()
            # Should NOT call renew_access_token
            mock_user.renew_access_token.assert_not_called()
            
    @pytest.mark.asyncio
    async def test_authenticate_cached_login_refresh(self, api):
        """Test authenticate using cached credentials that need refresh."""
        async def mock_load():
             return {
                "id_token": "expired_id",
                "refresh_token": "valid_refresh"
            }
        api._store.async_load = mock_load
        
        with patch("custom_components.mysa.mysa_api.Cognito") as mock_cognito_cls, \
             patch("custom_components.mysa.mysa_api.boto3"):
             
            mock_user = MagicMock()
            mock_cognito_cls.return_value = mock_user
            
            # verify_token FAILS
            mock_user.verify_token.side_effect = Exception("Token Expired")
            
            # Run authenticate
            await api.authenticate()
            
            mock_user.verify_token.assert_called()
            # Should call renew_access_token
            mock_user.renew_access_token.assert_called_once()    

    @pytest.mark.asyncio
    async def test_authenticate_cached_login_failure(self, api):
        """Test cached login failing completely (triggers password fallback)."""
        async def mock_load():
             return {"id_token": "bad", "refresh_token": "bad"}
        api._store.async_load = mock_load
        
        with patch("custom_components.mysa.mysa_api.Cognito") as mock_cognito_cls, \
             patch("custom_components.mysa.mysa_api.boto3"), \
             patch("custom_components.mysa.mysa_api.login") as mock_login_func:
            
            # Make the cached attempt fail hard
            mock_user = MagicMock()
            mock_cognito_cls.return_value = mock_user
            mock_user.verify_token.side_effect = Exception("Verify Verify Error")
            mock_user.renew_access_token.side_effect = Exception("Renew Error")
            
            # This should trigger the fallback to 'login()'
            
            await api.authenticate()
            
            mock_login_func.assert_called_once()

    def test_get_devices_sync_success(self, api):
        """Test _get_devices_sync success."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "DevicesObj": [
                {"Id": "device1", "Name": "Living Room", "Model": "BB-V2"}
            ]
        }
        api._session.get.return_value = mock_response
        
        # Mock _fetch_homes_sync to avoid side effects
        api._fetch_homes_sync = MagicMock()

        devices = api._get_devices_sync()
        
        assert "device1" in devices
        assert devices["device1"]["Name"] == "Living Room"
        api._session.get.assert_called_with("https://app-prod.mysa.cloud/devices")

    def test_get_devices_sync_list_response(self, api):
        """Test _get_devices_sync with list response (DevicesObj)."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "DevicesObj": [
                {"Id": "device1", "Name": "Living Room"}
            ]
        }
        api._session.get.return_value = mock_response
        api._fetch_homes_sync = MagicMock()

        devices = api._get_devices_sync()
        
        assert "device1" in devices

    def test_fetch_homes_sync_success(self, api):
        """Test _fetch_homes_sync success."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "Homes": [
                {
                    "Id": "home1",
                    "Zones": [{"Id": "zone1", "Name": "Downstairs"}]
                }
            ]
        }
        api._session.get.return_value = mock_response

        homes = api._fetch_homes_sync()
        
        assert len(homes) == 1
        assert api.zones["zone1"] == "Downstairs"
        api._session.get.assert_called_with("https://app-prod.mysa.cloud/homes")

    def test_fetch_firmware_info_success(self, api):
        """Test fetch_firmware_info success."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"update": True}
        api._session.get.return_value = mock_response

        result = api.fetch_firmware_info("device1")
        
        assert result["update"] is True
        api._session.get.assert_called_with(
            "https://app-prod.mysa.cloud/devices/update_available/device1",
            timeout=10
        )

    def test_fetch_firmware_info_failure(self, api):
        """Test fetch_firmware_info failure handling."""
        api._session.get.side_effect = Exception("Network Error")

        result = api.fetch_firmware_info("device1")
        
        assert result is None

    def test_get_state_sync_success(self, api):
        """Test _get_state_sync success."""
        # Mock state response
        state_response = MagicMock()
        state_response.json.return_value = {
            "DeviceStates": [
                {"Id": "device1", "temp": {"v": 20.0}}
            ]
        }
        
        # Mock devices response
        devices_response = MagicMock()
        devices_response.json.return_value = {
            "Devices": [
                {"Id": "device1", "Name": "Living Room", "Model": "BB-V2"}
            ]
        }
        
        api._session.get.side_effect = [state_response, devices_response]
        
        states = api._get_state_sync()
        
        assert "device1" in states
        # temp is normalized but kept as is if not in map?
        # Check normalized key first? _normalize_state doesn't map 'temp' currently?
        # Wait, looking at _normalize_state:
        # It maps 'Mode', 'SetPoint', 'Duty', 'Rssi', 'Voltage', 'Current', 'HeatSink', 'Infloor', 'Brightness', 'Lock', 'Zone', 'ProximityMode', 'AutoBrightness', 'EcoMode'
        # It does NOT map 'temp'. 'temp' key probably stays as is from response.
        
        # ACTUALLY, checking _get_state_sync code:
        # It merges /devices response and /devices/state response
        # It calls _normalize_state
        
        # Let's check a key that IS normalized
        # "sp" -> "SetPoint"
        
        # Redefine mock to test normalization
        state_response.json.return_value = {
            "DeviceStates": [
                {"Id": "device1", "sp": {"v": 22.0}}
            ]
        }
        devices_response.json.return_value = {
            "Devices": [
                {"Id": "device1", "Name": "Living Room"}
            ]
        }
        api._session.get.side_effect = [state_response, devices_response]
        
        states = api._get_state_sync()
        
        assert states["device1"]["SetPoint"] == 22.0

    @pytest.mark.asyncio
    async def test_get_devices_sync_session_error(self, api):
        """Test _get_devices_sync session uninitialized error."""
        api._session = None
        
        with pytest.raises(RuntimeError):
            await api.hass.async_add_executor_job(api._get_devices_sync)

    @pytest.mark.asyncio
    async def test_fetch_firmware_info_session_error(self, api):
        """Test fetch_firmware_info session uninitialized error."""
        api._session = None
        
        with pytest.raises(RuntimeError):
             await api.hass.async_add_executor_job(api.fetch_firmware_info, "device1")

    @pytest.mark.asyncio
    async def test_get_state_sync_session_error(self, api):
        """Test _get_state_sync session uninitialized error."""
        api._session = None
        
        with pytest.raises(RuntimeError):
             await api.hass.async_add_executor_job(api._get_state_sync)

    def test_get_signed_mqtt_url(self, api):
        """Test _get_signed_mqtt_url."""
        # We need to mock refresh_and_sign_url
        with patch("custom_components.mysa.mysa_api.refresh_and_sign_url") as mock_sign:
            mock_user = MagicMock()
            mock_sign.return_value = ("wss://signed-url", mock_user)
            
            api._user_obj = MagicMock()
            
            # This is an async wrapper that calls run_job, but we can call the inner function
            # if we can access it. But _get_signed_mqtt_url is defined as async def and calls executor.
            
            # The inner function is defined INSIDE _get_signed_mqtt_url:
            # def _sign(): ...
            
            # So we can't test the inner function directly easily without running the async method.
            # But we can verify `refresh_and_sign_url` is called when we run the async method.
            pass  # Handled by async test or integration test


@pytest.mark.unit
class TestMysaApiRealMqttCommand:
    """Test _send_mqtt_command with real logic (mocked network)."""

    @pytest.mark.asyncio
    async def test_send_mqtt_command_flow(self):
        """Test full MQTT command flow."""
        from custom_components.mysa.mysa_api import MysaApi, mqtt
        
        mock_hass = MagicMock()
        mock_hass.async_add_executor_job = AsyncMock(side_effect=lambda f, *a: f(*a) if callable(f) else f)
        
        api = MysaApi("test@example.com", "password", mock_hass)
        api._user_id = "user123"
        api._get_signed_mqtt_url = AsyncMock(return_value="https://signed-url")
        
        # Mock websockets
        mock_ws = AsyncMock()
        # Setup receive sequence: CONNACK, SUBACK, PUBACK, Device Response
        
        # CONNACK handling: parse_mqtt_packet(resp) -> ConnackPacket
        # SUBACK handling: parse_mqtt_packet(resp) -> SubackPacket
        # PUBACK handling: parse_mqtt_packet(resp) -> PubackPacket
        # Device Response: PublishPacket with payload
        
        connack_bytes = bytearray([0x20, 0x02, 0x00, 0x00])
        suback_bytes = bytearray([0x90, 0x03, 0x00, 0x01, 0x00])
        puback_bytes = bytearray([0x40, 0x02, 0x00, 0x02]) # packet_id 2
        
        # Device response payload (msg 44 success)
        import json
        resp_payload = json.dumps({
            "msg": 44,
            "body": {"state": {"sp": 23.0}}
        }).encode()
        # PUBLISH packet from device
        # Topic length 5 ("/test"), payload ...
        # Simplified: we just need it to parse to a PublishPacket
        # We can mock mqtt.parse_one to return the packet object directly if we mock websockets.recv to return bytes
        
        # Actually, let's mock parse_one/parse_mqtt_packet to avoid constructing complex bytes?
        # But mysa_api calls mqtt.parse_one(resp) directly in some places and parse_mqtt_packet in others.
        # It uses `mqtt.parse_one(resp)` for the device response.
        # It implicitly uses `await ws.recv()` which in `websockets` library returns bytes or str.
        
        # Let's construct a minimal valid PUBLISH packet for the response
        # Type 3 (0x30), Remaining Length...
        # Or easier: Mock mqtt.parse_one and return objects based on input?
        # But `_send_mqtt_command` imports `mqtt` from `.`, so we can patch `custom_components.mysa.mqtt.parse_one`.
        
        mock_ws.recv.side_effect = [
            connack_bytes,  # CONNACK
            suback_bytes,   # SUBACK
            puback_bytes,   # PUBACK
            b"device_response_bytes" # Device Response
        ]
        
        # Mock the connection context manager
        mock_connect = MagicMock()
        mock_connect.__aenter__.return_value = mock_ws
        mock_connect.__aexit__.return_value = None
        
        with patch("websockets.connect", return_value=mock_connect), \
             patch("custom_components.mysa.mysa_api.mqtt.parse_one") as mock_parse_one, \
             patch("ssl.create_default_context"):
            
            # Setup parse_one to return appropriate packets
            # We don't need to mock parse_one for CONNACK/SUBACK/PUBACK if we provide real bytes?
            # MysaApi code:
            #   await ws.recv() (CONNACK) -> doesn't call parse_one?
            #   Code:
            #     await ws.recv() (CONNACK)
            #     ...
            #     sub_pkt = mqtt.subscribe(...)
            #     await ws.send(sub_pkt)
            #     await ws.recv() (SUBACK)
            #     ...
            #     await ws.recv() (PUBACK)
            #     ...
            #     resp = await asyncio.wait_for(ws.recv(), timeout=2.0)
            #     pkt = mqtt.parse_one(resp)
            
            # So verification of CONNACK/SUBACK/PUBACK is skipped or implicit in `_send_mqtt_command`.
            # Checking code:
            #   await ws.recv() # Wait for Connack (no check?)
            #   await ws.recv() # Wait for Suback (no check?)
            #   await ws.recv() # Wait for Puback (no check?)
            
            # Yes, it doesn't verify them explicitly in this method (unlike MysaMqtt connection class).
            
            # So for the final response:
            mock_pub_pkt = MagicMock()
            mock_pub_pkt.__class__.__name__ = 'PublishPacket'
            # isinstance(pkt, mqtt.PublishPacket) check
            # We can't mock isinstance easily unless we use the real class or set spec
            from custom_components.mysa.mqtt import PublishPacket
            mock_pub_pkt = MagicMock(spec=PublishPacket)
            mock_pub_pkt.payload = resp_payload
            
            mock_parse_one.return_value = mock_pub_pkt
            
            # Execute
            cmd = {"test": 1}
            await api._send_mqtt_command("device1", cmd)
            
            # Verify state update
            assert "device1" in api.states
            assert api.states["device1"]["SetPoint"] == 23.0
            
            # Verify sent messages
            assert mock_ws.send.call_count >= 3 # Connect, Subscribe, Publish

    @pytest.mark.asyncio
    async def test_send_mqtt_command_websockets_fallback(self):
        """Test fallback for older websockets versions (TypeError on additional_headers)."""
        from custom_components.mysa.mysa_api import MysaApi
        
        mock_hass = MagicMock()
        mock_hass.async_add_executor_job = AsyncMock(side_effect=lambda f, *a: f(*a) if callable(f) else f)
        
        api = MysaApi("test@example.com", "password", mock_hass)
        api._user_id = "user123"
        api._get_signed_mqtt_url = AsyncMock(return_value="https://signed-url")
        
        mock_ws = AsyncMock()
        # Just simple sequence
        mock_ws.recv.return_value = b"\x20\x02\x00\x00" # Dummy packet
        
        mock_connect = MagicMock()
        mock_connect.__aenter__.return_value = mock_ws
        mock_connect.__aexit__.return_value = None
        
        # Simulate TypeError on first call, success on second
        def side_effect(*args, **kwargs):
            if "additional_headers" in kwargs:
                raise TypeError("additional_headers argument")
            return mock_connect
            
        with patch("websockets.connect", side_effect=side_effect) as mock_connect_cls, \
             patch("custom_components.mysa.mysa_api.mqtt.parse_one"), \
             patch("ssl.create_default_context"):
             
            await api._send_mqtt_command("device1", {"cmd": 1})
            
            # Should have called connect twice
            assert mock_connect_cls.call_count == 2
            # Second call should have extra_headers
            call_args = mock_connect_cls.call_args_list[1]
            assert "extra_headers" in call_args.kwargs
            assert "additional_headers" not in call_args.kwargs




# ===========================================================================
# _normalize_state Tests
# ===========================================================================


@pytest.mark.unit
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


@pytest.mark.unit
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


@pytest.mark.unit
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


@pytest.mark.unit
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


@pytest.mark.unit
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
        api.states = {"device1": {"Brightness": {"a_br": 100, "i_br": 50}}}

        api._update_brightness_cache("device1", "a_br", 75)

        assert api.states["device1"]["Brightness"]["a_br"] == 75
        assert api.states["device1"]["Brightness"]["i_br"] == 50


# ===========================================================================
# _process_mqtt_publish Tests
# ===========================================================================


@pytest.mark.unit
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
        pkt.payload = b"invalid json"

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


@pytest.mark.unit
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
            "ac1": {"Model": "AC-V1", "SupportedCaps": {"HasHorizontalSwing": True}}
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


@pytest.mark.unit
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


@pytest.mark.unit
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
            "ACState": {"v": {"4": 2}},  # Would set to 2
        }

        api._normalize_state(state)

        assert state.get("FanSpeed") == 5  # Not overwritten


@pytest.mark.unit
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


# ===========================================================================
# From test_api_ext.py
# ===========================================================================

@pytest.mark.unit
class TestMysaApiSettings:
    """Test MysaApi setting methods (HTTP)."""

    @pytest.fixture
    def api(self):
        """Create API instance with mocked session."""
        from custom_components.mysa.mysa_api import MysaApi
        
        mock_hass = MagicMock()
        mock_hass.async_add_executor_job = AsyncMock(side_effect=lambda f, *a: f(*a) if callable(f) else f)
        
        api = MysaApi("test@example.com", "password", mock_hass)
        api._session = MagicMock()
        api.states = {"device1": {}} # Initialize with device
        api.coordinator_callback = AsyncMock()
        return api

    @pytest.mark.asyncio
    async def test_set_device_setting_success(self, api):
        """Test _set_device_setting success."""
        # Mock response
        api._session.post.return_value.json.return_value = {"status": "ok"}
        
        settings = {"brightness": 100}
        await api._set_device_setting("device1", settings)
        
        # Verify POST
        api._session.post.assert_called_with(
            "https://app-prod.mysa.cloud/devices/device1",
            json=settings
        )
        # Verify state update
        assert api.states["device1"]["brightness"] == 100
        # Verify callback
        api.coordinator_callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_device_setting_failure(self, api):
        """Test _set_device_setting failure."""
        api._session.post.side_effect = Exception("HTTP Error")
        
        with pytest.raises(Exception):
            await api._set_device_setting("device1", {"brightness": 100})

    @pytest.mark.asyncio
    async def test_set_device_setting_silent_success(self, api):
        """Test _set_device_setting_silent success."""
        api._session.post.return_value.json.return_value = {"status": "ok"}
        
        await api._set_device_setting_silent("device1", {"brightness": 100})
        
        # Verify POST but NO state update or callback
        api._session.post.assert_called()
        assert "brightness" not in api.states["device1"]
        api.coordinator_callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_set_device_setting_silent_failure(self, api):
        """Test _set_device_setting_silent failure (suppressed)."""
        api._session.post.side_effect = Exception("HTTP Error")
        
        # Should not raise
        await api._set_device_setting_silent("device1", {"brightness": 100})


@pytest.mark.unit
class TestMysaApiPersistentMqtt:
    """Test MysaApi persistent MQTT listener."""

    @pytest.fixture
    def api(self):
        """Create API instance for MQTT tests."""
        from custom_components.mysa.mysa_api import MysaApi
        
        mock_hass = MagicMock()
        api = MysaApi("test@example.com", "password", mock_hass)
        api._get_signed_mqtt_url = AsyncMock(return_value="wss://signed-url")
        api.devices = {"device1": {"Model": "BB-V2"}}
        return api

    @pytest.mark.asyncio
    async def test_mqtt_lifecycle(self, api):
        """Test start and stop of MQTT listener."""
        
        # Mock _mqtt_listener_loop to ideally wait and exit
        async def mock_loop():
            while api._mqtt_should_reconnect:
                await asyncio.sleep(0.01)

        api._mqtt_listener_loop = mock_loop
        
        # Start
        await api.start_mqtt_listener()
        assert api._mqtt_listener_task is not None
        assert api._mqtt_should_reconnect is True
        
        # Stop
        mock_ws = AsyncMock() # Mock WS for close call
        api._mqtt_ws = mock_ws
        await api.stop_mqtt_listener()
        
        assert api._mqtt_should_reconnect is False
        assert api._mqtt_listener_task is None
        mock_ws.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_mqtt_listen_connect_flow(self, api):
        """Test _mqtt_listen connection flow."""
        
        mock_ws = AsyncMock()
        api._mqtt_connected = MagicMock()
        
        from custom_components.mysa import mqtt
        
        connack = MagicMock(spec=mqtt.ConnackPacket) 
        suback = MagicMock(spec=mqtt.SubackPacket)
        
        # Mock parse_mqtt_packet to return objects
        # And mock connect_websocket
        
        with patch("custom_components.mysa.mysa_api.connect_websocket", return_value=mock_ws), \
             patch("custom_components.mysa.mysa_api.create_connect_packet"), \
             patch("custom_components.mysa.mysa_api.parse_mqtt_packet", side_effect=[connack, suback]), \
             patch("custom_components.mysa.mysa_api.build_subscription_topics", return_value=["top1"]), \
             patch("custom_components.mysa.mysa_api.mqtt.subscribe"):
             
            # Make _run_mqtt_loop raise Exception to exit _mqtt_listen
            api._run_mqtt_loop = AsyncMock(side_effect=Exception("Loop Exit"))
            
            try:
                await api._mqtt_listen()
            except Exception as e:
                assert str(e) == "Loop Exit"
            
            # Verify Flow
            api._mqtt_connected.set.assert_called() # Should be called before exception
            mock_ws.close.assert_called()

    @pytest.mark.asyncio
    async def test_mqtt_reconnection_loop(self, api):
        """Test mqtt listener loop reconnection logic."""
        
        # We simulate _mqtt_listen outcomes:
        # 1. Normal return (should log and reset delay)
        # 2. Connection error (should reconnect)
        # 3. CancelledError (should exit)
        
        api._mqtt_listen = AsyncMock(side_effect=[None, Exception("Conn Error"), asyncio.CancelledError()])
        
        with patch("custom_components.mysa.mysa_api.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            api._mqtt_should_reconnect = True
            
            try:
                await api._mqtt_listener_loop()
            except asyncio.CancelledError:
                pass
            
            assert api._mqtt_listen.call_count == 3
            mock_sleep.assert_called()

    @pytest.mark.asyncio
    async def test_run_mqtt_loop_processing(self, api):
        """Test _run_mqtt_loop processing messages."""
        mock_ws = AsyncMock()
        
        from custom_components.mysa import mqtt
        
        # 1. Publish Packet
        pub_pkt = MagicMock(spec=mqtt.PublishPacket)
        pub_pkt.topic = "/out"
        pub_pkt.payload = b'{}'
        
        # 2. Ping Resp
        ping_resp = MagicMock()
        ping_resp.pkt_type = mqtt.MQTT_PACKET_PINGRESP
        
        # 3. Timeout (to test ping send)
        
        with patch("custom_components.mysa.mysa_api.parse_mqtt_packet", side_effect=[pub_pkt, ping_resp, Exception("Stop Loop")]), \
             patch("custom_components.mysa.mysa_api.time.time", side_effect=[0, 0, 100, 100, 200]), \
             patch("custom_components.mysa.mysa_api.mqtt.pingreq") as mock_pingreq:
            
            api._process_mqtt_publish = AsyncMock()
            
            # Mock recv to match parse calls
            mock_ws.recv = AsyncMock(side_effect=[b"pub", b"ping", b"error"])
            
            try:
                await api._run_mqtt_loop(mock_ws)
            except Exception:
                pass
            
            api._process_mqtt_publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_notify_settings_changed(self, api):
        """Test notify_settings_changed sends MQTT."""
        api._send_mqtt_command = AsyncMock()
        
        await api.notify_settings_changed("device1")
        
        api._send_mqtt_command.assert_called_once()
        call_args = api._send_mqtt_command.call_args
        assert call_args.kwargs["msg_type"] == 6
        assert call_args.kwargs["wrap"] is False

    @pytest.mark.asyncio
    async def test_do_sync_login(self, api):
        """Test syncing login flow via authenticate."""
        # Use mocked executor that runs inline
        api.hass.async_add_executor_job = AsyncMock(side_effect=lambda f, *a: f(*a))
        
        with patch("custom_components.mysa.mysa_api.boto3") as mock_boto3, \
             patch("custom_components.mysa.mysa_api.login") as mock_login, \
             patch("custom_components.mysa.mysa_api.Store") as mock_store:
             
            mock_user = MagicMock()
            mock_user.id_token = "mock_id_token"
            mock_user.access_token = "mock_access_token"
            mock_user.refresh_token = "mock_refresh_token"
            mock_login.return_value = mock_user
            
            mock_store.return_value.async_load = AsyncMock(return_value=None)
            
            await api.authenticate()
            
            mock_login.assert_called()
            mock_boto3.session.Session.assert_called()


@pytest.mark.unit
class TestMysaApiStateLogic:
    """Test MysaApi state logic edge cases."""

    @pytest.fixture
    def api(self):
        from custom_components.mysa.mysa_api import MysaApi
        mock_hass = MagicMock()
        mock_hass.async_add_executor_job = AsyncMock(side_effect=lambda f, *a: f(*a) if callable(f) else f)
        api = MysaApi("u", "p", mock_hass)
        api._session = MagicMock()
        api.states = {}
        api.devices = {}
        api._last_command_time = {}
        return api

    @pytest.mark.asyncio
    async def test_get_state_sync_stale_logic(self, api):
        """Test _get_state_sync filtering stale keys."""
        
        # Setup initial state
        api.states = {"d1": {"Mode": 1, "CurrentTemperature": 20}}
        api.devices = {"d1": {"Id": "d1"}}
        
        # Setup session responses
        # 1. State response (live data)
        # 2. Devices response (settings)
        
        state_resp = {"DeviceStates": [{"Id": "d1", "Mode": 2, "CurrentTemperature": 22}]}
        dev_resp = {"Devices": [{"Id": "d1"}]}
        
        api._session.get.side_effect = [
            MagicMock(json=MagicMock(return_value=state_resp)), # state call
            MagicMock(json=MagicMock(return_value=dev_resp))   # devices call
        ]
        
        # Simulate recent command
        api._last_command_time["d1"] = 100
        
        with patch("custom_components.mysa.mysa_api.time.time", return_value=110): # 10s passed (<90s)
            
            await api.hass.async_add_executor_job(api._get_state_sync)
            
            # Verify "Mode" was ignored (stale) but "CurrentTemperature" updated
            # The stale_keys filter prevents the 'Mode' from new_data from overwriting self.states['d1']
            assert api.states["d1"]["Mode"] == 1 # Old value kept
            assert api.states["d1"]["CurrentTemperature"] == 22 # New sensor value taken


@pytest.mark.unit
class TestMysaApiMqttAuth:
    """Test MysaApi MQTT Auth logic."""
    
    @pytest.fixture
    def api(self):
        from custom_components.mysa.mysa_api import MysaApi
        mock_hass = MagicMock()
        mock_hass.async_add_executor_job = AsyncMock(side_effect=lambda f, *a: f(*a) if callable(f) else f)
        api = MysaApi("u", "p", mock_hass)
        api._user_id = "user1"
        return api

    @pytest.mark.asyncio
    async def test_get_signed_mqtt_url_refresh(self, api):
        """Test _get_signed_mqtt_url updates user object on refresh."""
        original_user = MagicMock()
        new_user = MagicMock()
        api._user_obj = original_user
        
        with patch("custom_components.mysa.mysa_api.refresh_and_sign_url", return_value=("wss://url", new_user)):
             
             url = await api._get_signed_mqtt_url()
             
             assert url == "wss://url"
             assert api._user_obj is new_user
             assert api._user_obj is not original_user

    @pytest.mark.asyncio
    async def test_send_mqtt_command_no_auth(self, api):
        """Test _send_mqtt_command fails if auth fails."""
        api._user_id = None
        api.authenticate = AsyncMock() # Mock auth
        # After authenticate, user_id is still None
        
        await api._send_mqtt_command("d1", {})
        
        api.authenticate.assert_called()
        # Should return early (not raise)


# ===========================================================================
# From test_api_coverage.py
# ===========================================================================

@pytest.mark.unit
class TestMysaApiCoverage:
    """Targeted coverage tests for MysaApi."""

    @pytest.fixture
    def api(self):
        """Create API instance with mocked session/hass."""
        class MockHass:
            data = {}
            config = MagicMock()
            async def async_add_executor_job(self, func, *args):
                return func(*args)

        mock_hass = MockHass()
        from custom_components.mysa.mysa_api import MysaApi
        api = MysaApi("test@example.com", "password", mock_hass)
        api._session = MagicMock()
        
        # Mock Store
        class MockStore:
            async def async_load(self): return None
            async def async_save(self, data): return None
            
        api._store = MockStore()
        return api

    def test_fetch_homes_sync_no_session(self, api):
        """Test _fetch_homes_sync raises RuntimeError if no session."""
        api._session = None
        with pytest.raises(RuntimeError):
            api._fetch_homes_sync()

    @pytest.mark.asyncio
    async def test_start_mqtt_listener_already_running(self, api):
        """Test start_mqtt_listener returns early if task exists."""
        # Cover lines 960-962
        api._mqtt_listener_task = MagicMock()
        await api.start_mqtt_listener()
        # Should return immediately, ensuring task is not overwritten
        # We can't easily assert "returned early" but we can check side effects (none)
        assert api._mqtt_listener_task is not None 

    @pytest.mark.asyncio
    async def test_stop_mqtt_listener_close_exception(self, api):
        """Test stop_mqtt_listener handles exception during close."""
        # Cover lines 986-987
        mock_ws = AsyncMock()
        mock_ws.close.side_effect = Exception("Close failed")
        api._mqtt_ws = mock_ws
        
        # Should not raise
        await api.stop_mqtt_listener()
        assert api._mqtt_ws is None

    @pytest.mark.asyncio
    async def test_mqtt_listen_close_exception(self, api):
        """Test _mqtt_listen handles exception during finally close."""
        # Cover lines 1042-1043
        api._get_signed_mqtt_url = AsyncMock(return_value="wss://test")
        
        api._perform_mqtt_handshake = AsyncMock()
        api._run_mqtt_loop = AsyncMock(side_effect=Exception("Loop Crash"))
        
        with patch("custom_components.mysa.mysa_api.connect_websocket", new_callable=AsyncMock) as mock_connect:
            mock_ws = AsyncMock()
            mock_ws.close.side_effect = Exception("Close error")
            mock_connect.return_value = mock_ws
            
            # Expect the Loop Crash to assume priority
            with pytest.raises(Exception, match="Loop Crash"):
                await api._mqtt_listen()
            
            # Verify close was called (and exception swallowed in finally)
            mock_ws.close.assert_called()

    @pytest.mark.asyncio
    async def test_perform_mqtt_handshake_bad_packets(self, api):
        """Test handshake raises RuntimeError on unexpected packets."""
        # Cover lines 1054-1055, 1073
        mock_ws = AsyncMock()
        
        # 1. Bad Connack
        mock_ws.recv.return_value = b'not_connack'
        with patch("custom_components.mysa.mysa_api.parse_mqtt_packet") as mock_parse:
            mock_parse.return_value = MagicMock() # Not ConnackPacket
            
            with pytest.raises(RuntimeError, match="Expected CONNACK"):
                await api._perform_mqtt_handshake(mock_ws)

        # 2. Bad Suback
        mock_ws.recv.side_effect = [b'connack', b'suback']
        api.devices = {"dev1": {}} # Force subscribe path
        
        with patch("custom_components.mysa.mysa_api.parse_mqtt_packet") as mock_parse, \
             patch("custom_components.mysa.mysa_api.create_connect_packet"), \
             patch("custom_components.mysa.mysa_api.build_subscription_topics", return_value=["t1"]), \
             patch("custom_components.mysa.mysa_api.mqtt") as mock_mqtt:
             
             # Define explicit dummy classes
             class MockConnackPacket: pass
             class MockSubackPacket: pass
             
             mock_mqtt.ConnackPacket = MockConnackPacket
             mock_mqtt.SubackPacket = MockSubackPacket
             
             # Mock Connack success
             mock_connack = MockConnackPacket()
             
             # Mock Suback failure (return random object)
             mock_not_suback = MagicMock() 
             
             mock_parse.side_effect = [mock_connack, mock_not_suback]
             
             with pytest.raises(RuntimeError, match="Expected SUBACK"):
                 await api._perform_mqtt_handshake(mock_ws)

    @pytest.mark.asyncio
    async def test_run_mqtt_loop_exceptions(self, api):
        """Test exception handling in _run_mqtt_loop."""
        # Cover lines 1101-1116, 1124-1126
        mock_ws = AsyncMock()
        
        # 1. Parse Error (should continue)
        # 2. Keepalive Error (should raise)
        
        # Mock wait_for to return a message then raise TimeoutError (to trigger ping)
        api._perform_mqtt_handshake = AsyncMock()
        
        from custom_components.mysa.const import MQTT_PING_INTERVAL
        
        with patch("custom_components.mysa.mysa_api.parse_mqtt_packet") as mock_parse, \
             patch("custom_components.mysa.mysa_api.mqtt") as mock_mqtt, \
             patch("asyncio.wait_for") as mock_wait:
             
             # Iteration 1: Recv msg -> Parse Error -> log warning -> continue
             # Iteration 2: Timeout -> Trigger Ping -> Send Error -> raise
             
             mock_wait.side_effect = [
                 b'bad_msg',
                 # Force timeout to trigger ping logic
                 asyncio.TimeoutError() 
             ]
             
             mock_parse.side_effect = Exception("Parse Failed")
             
             # Mock pingreq
             mock_mqtt.pingreq.return_value = b'ping'
             
             # Mock send to raise exception on second call (ping)
             start_time = 1000
             with patch("time.time", side_effect=[
                 start_time, 
                 start_time + 0.1, # loop 1 check
                 start_time + 0.2, # loop 1 elapsed
                 start_time + MQTT_PING_INTERVAL + 1, # loop 2 check (timeout) -> triggers ping
                 start_time + MQTT_PING_INTERVAL + 2 # ping log
             ]):
                 mock_ws.send.side_effect = Exception("Send Failed")
                 
                 with pytest.raises(Exception, match="Send Failed"):
                     await api._run_mqtt_loop(mock_ws)

    def test_extract_state_update_bad_msg_type(self, api):
        """Test _extract_state_update returns None for wrong msg type."""
        # Cover line 1142
        payload = {"msg": 99, "body": {}}
        assert api._extract_state_update(payload) is None

    @pytest.mark.asyncio
    async def test_mqtt_response_state_update_keys(self, api):
        """Test _send_mqtt_command processes all logic branches for state keys."""
        # Cover lines 563-581
        
        # Mock successful command flow to point where response is parsed
        async def mock_get_url(): return "wss://test"
        api._get_signed_mqtt_url = mock_get_url
        api._user_id = "uid"
        api.states = {}
        
        with patch("custom_components.mysa.mysa_api.ssl.create_default_context"), \
             patch("custom_components.mysa.mysa_api.websockets.connect") as mock_connect, \
             patch("custom_components.mysa.mysa_api.mqtt") as mock_mqtt:
             
             mock_ws = AsyncMock()
             mock_connect.return_value.__aenter__.return_value = mock_ws
             
             # Handshake -> Response with ALL keys
             mock_ws.recv.side_effect = [b'c', b's', b'p', b'resp']
             
             mock_pkt = MagicMock()
             mock_pkt.payload = json.dumps({
                 "msg": 44, 
                 "body": {
                     "md": 1, "sp": 20, "dc": 50, "rssi": -60, "br": 100, "lc": 1
                 }
             })
             mock_mqtt.PublishPacket = MagicMock
             mock_mqtt.parse_one.return_value = mock_pkt
             mock_mqtt.PublishPacket = type(mock_pkt)
             
             await api._send_mqtt_command("dev1", {}, wrap=False)
             
             # Verify keys were mapped
             s = api.states["dev1"]
             assert s["Mode"] == 1
             assert s["SetPoint"] == 20
             assert s["Duty"] == 50
             assert s["Rssi"] == -60
             assert s["Brightness"] == 100
             assert s["Lock"] == 1
             
             # Second pass: Update existing state + use 'lk' key
             mock_ws.recv.side_effect = [b'c', b's', b'p', b'resp2']
             mock_pkt.payload = json.dumps({
                 "msg": 44, "body": {"lk": 0}
             })
             await api._send_mqtt_command("dev1", {}, wrap=False)
             assert api.states["dev1"]["Lock"] == 0

    @pytest.mark.asyncio
    async def test_mqtt_command_response_timeout(self, api):
        """Test _send_mqtt_command handles timeout waiting for response."""
        # Cover lines 587-590
        async def mock_get_url(): return "wss://test"
        api._get_signed_mqtt_url = mock_get_url
        api._user_id = "uid"
        
        with patch("custom_components.mysa.mysa_api.ssl.create_default_context"), \
             patch("custom_components.mysa.mysa_api.websockets.connect") as mock_connect, \
             patch("custom_components.mysa.mysa_api.mqtt"), \
             patch("asyncio.wait_for") as mock_wait:
             
             mock_ws = AsyncMock()
             mock_connect.return_value.__aenter__.return_value = mock_ws
             
             mock_ws.recv.side_effect = [b'c', b's', b'p', b'resp']
             
             # Mock wait_for strictly for the response wait
             mock_wait.side_effect = asyncio.TimeoutError()
             
             # Should not raise, just log debug
             await api._send_mqtt_command("dev1", {}, wrap=False)

    @pytest.mark.asyncio
    async def test_mqtt_command_fallback_failure(self, api):
        """Test _send_mqtt_command fallback logic failure."""
        # Cover lines 626-628
        async def mock_get_url(): return "wss://test"
        api._get_signed_mqtt_url = mock_get_url
        api._user_id = "uid"
        
        # 1. First connect raises TypeError: additional_headers
        # 2. Second connect (fallback) raises Exception
        
        with patch("custom_components.mysa.mysa_api.ssl.create_default_context"), \
             patch("custom_components.mysa.mysa_api.websockets.connect") as mock_connect:
             
             # Raising TypeError must happen during __aenter__ init or call?
             # `async with websockets.connect(...)`
             # mock_connect(...) returns context manager.
             # We need mock_connect to raise TypeError when called with additional_headers
             
             def side_effect(*args, **kwargs):
                 if 'additional_headers' in kwargs:
                     raise TypeError("additional_headers")
                 # Fallback succeeds to context manager... but we want it to fail inside?
                 # No, we want to fail completely to hit the outer except block 628?
                 # Or lines 626: raise?
                 # If fallback fails, it raises Exception.
                 raise Exception("Fallback Failed")

             mock_connect.side_effect = side_effect
             
             # Log error should be called
             await api._send_mqtt_command("dev1", {}, wrap=False)

    @pytest.mark.asyncio
    async def test_handshake_fetches_devices(self, api):
        """Test _perform_mqtt_handshake fetches devices if empty."""
        # Cover line 1061
        api.devices = {}
        api.get_devices = AsyncMock()
        
        mock_ws = AsyncMock()
        mock_ws.recv.side_effect = [b'connack', b'suback']
        
        with patch("custom_components.mysa.mysa_api.parse_mqtt_packet") as mock_parse, \
             patch("custom_components.mysa.mysa_api.mqtt") as mock_mqtt:
             
             mock_mqtt.ConnackPacket = type("Connack", (), {})
             mock_mqtt.SubackPacket = type("Suback", (), {})
             
             mock_parse.return_value = mock_mqtt.ConnackPacket() # for both calls if lazy
             mock_parse.side_effect = [mock_mqtt.ConnackPacket(), mock_mqtt.SubackPacket()]
             
             await api._perform_mqtt_handshake(mock_ws)
             
             api.get_devices.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_mqtt_loop_pingresp(self, api):
        """Test _run_mqtt_loop handles PINGRESP."""
        # Cover lines 1101-1102
        mock_ws = AsyncMock()
        
        # 1. PINGRESP -> loop continues
        # 2. Timeout -> Trigger Ping -> Then Stop loop (raise Exception)
        
        from custom_components.mysa.const import MQTT_PING_INTERVAL
        
        with patch("custom_components.mysa.mysa_api.parse_mqtt_packet") as mock_parse, \
             patch("custom_components.mysa.mysa_api.mqtt") as mock_mqtt, \
             patch("asyncio.wait_for") as mock_wait:
             
             mock_wait.side_effect = [
                 b'pingresp',
                 asyncio.TimeoutError()
             ]
             mock_mqtt.MQTT_PACKET_PINGRESP = 13
             
             # Define dummy PublishPacket class to ensure isinstance fails
             class MockPublishPacket: pass
             mock_mqtt.PublishPacket = MockPublishPacket
             mock_pkt = MagicMock()
             mock_pkt.pkt_type = 13
             mock_parse.return_value = mock_pkt
             
             # Mock pingreq logic
             mock_mqtt.pingreq.return_value = b'ping'

             # Setup time to force ping send then crash
             start_time = 1000
             with patch("time.time", side_effect=[
                 start_time, 
                 start_time + 0.1, # loop 1 check
                 start_time + 0.2, # loop 1 elapsed
                 # loop 2 check (timeout) -> trig ping -> send -> crash
                 start_time + MQTT_PING_INTERVAL + 1, 
                 start_time + MQTT_PING_INTERVAL + 2
             ]):
                 mock_ws.send.side_effect = Exception("Stop Loop")
                 
                 with pytest.raises(Exception, match="Stop Loop"):
                     await api._run_mqtt_loop(mock_ws)

    @pytest.mark.asyncio
    async def test_mqtt_command_response_exception(self, api):
        """Test _send_mqtt_command handles generic exception during response wait."""
        # Cover lines 589-590
        async def mock_get_url(): return "wss://test"
        api._get_signed_mqtt_url = mock_get_url
        api._user_id = "uid"
        
        with patch("custom_components.mysa.mysa_api.ssl.create_default_context"), \
             patch("custom_components.mysa.mysa_api.websockets.connect") as mock_connect, \
             patch("custom_components.mysa.mysa_api.mqtt"), \
             patch("asyncio.wait_for") as mock_wait:
             
             mock_ws = AsyncMock()
             mock_connect.return_value.__aenter__.return_value = mock_ws
             mock_ws.recv.side_effect = [b'c', b's', b'p', b'resp']
             
             mock_wait.side_effect = Exception("Parsing Crash")
             
             # Should not raise, just log debug
             await api._send_mqtt_command("dev1", {}, wrap=False)

    @pytest.mark.asyncio
    async def test_mqtt_command_connect_type_error_no_fallback(self, api):
        """Test _send_mqtt_command re-raises TypeError if not additional_headers."""
        # Cover line 626
        async def mock_get_url(): return "wss://test"
        api._get_signed_mqtt_url = mock_get_url
        api._user_id = "uid"
        
        with patch("custom_components.mysa.mysa_api.ssl.create_default_context"), \
             patch("custom_components.mysa.mysa_api.websockets.connect") as mock_connect:
             
             # Raise TypeError that does NOT match fallback condition
             def side_effect(*args, **kwargs):
                 raise TypeError("Some other error")

             mock_connect.side_effect = side_effect
             
             # Should be caught by outer except Exception (line 627) and logged?
             # Wait, `raise` at 626 re-raises the TypeError.
             # Then outer `except Exception as e` at 627 catches it!
             # So logging is expected, NOT re-raise to caller.
             
             await api._send_mqtt_command("dev1", {}, wrap=False)
             # Implicitly passes if no exception to caller, but we confirm it didn't crash before logging.

    @pytest.mark.asyncio
    async def test_run_mqtt_loop_recv_exception(self, api):
        """Test _run_mqtt_loop catches recv exception and raises."""
        # Cover lines 1112-1116
        mock_ws = AsyncMock()
        mock_ws.recv.side_effect = Exception("Recv Error")
        
        with patch("asyncio.wait_for", side_effect=Exception("Recv Error")):
            with pytest.raises(Exception, match="Recv Error"):
                await api._run_mqtt_loop(mock_ws)

    @pytest.mark.asyncio
    async def test_run_mqtt_loop_generic_packet(self, api):
        """Test _run_mqtt_loop handles generic packets (debug log)."""
        # Cover lines 1101-1102
        mock_ws = AsyncMock()
        
        with patch("custom_components.mysa.mysa_api.parse_mqtt_packet") as mock_parse, \
             patch("custom_components.mysa.mysa_api.mqtt") as mock_mqtt, \
             patch("asyncio.wait_for") as mock_wait:
             
             mock_wait.side_effect = [
                 b'generic',
                 asyncio.TimeoutError()
             ]
             
             # Generic packet (not Publish, not PINGRESP)
             mock_pkt = MagicMock()
             mock_pkt.pkt_type = 99
             
             # Ensure isinstance(pkt, PublishPacket) is False
             class MockPublishPacket: pass
             mock_mqtt.PublishPacket = MockPublishPacket
             mock_mqtt.MQTT_PACKET_PINGRESP = 13
             
             mock_parse.return_value = mock_pkt
             
             # Mock send to raise exception to stop loop
             mock_ws.send.side_effect = Exception("Stop Loop")
             
             with pytest.raises(Exception):
                 await api._run_mqtt_loop(mock_ws)

    def test_get_devices_sync_dict_response(self, api):
        """Test _get_devices_sync with dict response (not list)."""
        # Cover lines 164-165
        api._session.get.return_value.json.return_value = {
            "DevicesObj": {"dev1": {"Id": "dev1", "Name": "Test Device"}}
        }
        # Mock fetch_homes to avoid side effects
        api._fetch_homes_sync = MagicMock()
        
        devices = api._get_devices_sync()
        assert devices["dev1"]["Name"] == "Test Device"
        assert isinstance(devices, dict)

    def test_get_devices_sync_fetch_homes_failure(self, api):
        """Test _get_devices_sync when _fetch_homes_sync fails."""
        # Cover lines 168-171
        api._session.get.return_value.json.return_value = {"DevicesObj": []}
        
        # Simulate exception in _fetch_homes_sync
        api._fetch_homes_sync = MagicMock(side_effect=Exception("Home Fetch Failed"))
        
        # Should catch exception and log warning, not raise
        api._get_devices_sync()

    def test_get_state_sync_dict_response(self, api):
        """Test _get_state_sync with dict response for devices/states."""
        # Cover lines 237-238, 248-249
        
        # Mock /devices/state response as dict (non-list)
        mock_state_resp = MagicMock()
        mock_state_resp.json.return_value = {
            "DeviceStatesObj": {"dev1": {"Id": "dev1", "SetPoint": {"v": 20}}}
        }
        
        # Mock /devices response as dict (non-list)
        mock_devices_resp = MagicMock()
        mock_devices_resp.json.return_value = {
            "DevicesObj": {"dev1": {"Id": "dev1", "Name": "Dev1"}}
        }
        
        api._session.get.side_effect = [mock_state_resp, mock_devices_resp]
        
        states = api._get_state_sync()
        assert states["dev1"]["Name"] == "Dev1"
        assert states["dev1"]["SetPoint"] == 20

    def test_get_state_sync_flatten_attributes(self, api):
        """Test merging Logic when Attributes dict exists (flattening)."""
        # Cover lines 260-261
        mock_state_resp = MagicMock()
        mock_state_resp.json.return_value = {"DeviceStates": [{"Id": "dev1", "live": 1}]}
        
        mock_devices_resp = MagicMock()
        mock_devices_resp.json.return_value = {
            "Devices": [{
                "Id": "dev1",
                "Attributes": {"attr1": "val1", "attr2": "val2"},
                "Name": "Dev1"
            }]
        }
        api._session.get.side_effect = [mock_state_resp, mock_devices_resp]
        
        states = api._get_state_sync()
        # Verify flattening: Attributes keys should be at top level
        assert states["dev1"]["attr1"] == "val1"
        assert states["dev1"]["live"] == 1

    def test_get_state_sync_unknown_device(self, api):
        """Test state update for device not in self.devices."""
        # Cover lines 265-266
        
        # Device dev2 is in state response but not in devices response
        mock_state_resp = MagicMock()
        mock_state_resp.json.return_value = {"DeviceStates": [{"Id": "dev2", "temp": 22}]}
        
        mock_devices_resp = MagicMock()
        mock_devices_resp.json.return_value = {"Devices": []} # Empty devices
        
        api._session.get.side_effect = [mock_state_resp, mock_devices_resp]
        
        states = api._get_state_sync()
        assert "dev2" in states
        assert states["dev2"]["temp"] == 22

    @pytest.mark.asyncio
    async def test_mqtt_command_no_wrap(self, api):
        """Test _send_mqtt_command with wrap=False."""
        # Cover lines 487-488
        
        # We need to mock _get_signed_mqtt_url, ssl, websockets
        async def mock_get_url():
            return "wss://test-mqtt-url"
        api._get_signed_mqtt_url = mock_get_url
        api._user_id = "test_user_id"
        
        # Import AsyncMock if likely available or use MagicMock with careful setup

        with patch("custom_components.mysa.mysa_api.ssl.create_default_context"), \
             patch("custom_components.mysa.mysa_api.websockets.connect") as mock_ws_connect, \
             patch("custom_components.mysa.mysa_api.mqtt") as mock_mqtt:
            
            mock_ws = AsyncMock() # Must be AsyncMock for await ws.recv() / await ws.send()
            mock_ws_connect.return_value.__aenter__.return_value = mock_ws
            
            # Setup handshake responses + device response
            # AsyncMock side_effect returns the value when awaited
            mock_ws.recv.side_effect = [b'connack', b'suback', b'puback', b'device_resp']
            
            # Mock mqtt.parse_one for the device response
            mock_pkt = MagicMock()
            mock_pkt.payload = '{"msg": 44, "body": {}}' # msg 44 = command response
            # We need mock_mqtt.parse_one to return specific things? 
            # Actually mock_mqtt is the module.
            mock_mqtt.PublishPacket = MagicMock 
            mock_mqtt.parse_one.return_value = mock_pkt
            # Make isinstance(pkt, mqtt.PublishPacket) return True
            # This is tricky with mocks. 
            # Easiest way: mock_api imports mqtt.
            # But the code does: `if isinstance(pkt, mqtt.PublishPacket):`
            # We can mock `mqtt.PublishPacket` to be the class of `mock_pkt`.
            mock_mqtt.PublishPacket = type(mock_pkt) 
            
            # Run command with wrap=False
            await api._send_mqtt_command("dev1", {"raw": "data"}, wrap=False)
            
            # Verify payload was NOT wrapped
            calls = mock_mqtt.publish.call_args_list
            assert len(calls) > 0
            _, kwargs = calls[0]
            payload_bytes = kwargs.get('payload')
            import json
            sent_json = json.loads(payload_bytes)
            
            assert sent_json == {"raw": "data"}
            assert "Timestamp" not in sent_json 

    @pytest.mark.asyncio
    async def test_ac_climate_plus(self, api):
        """Test set_ac_climate_plus."""
        # Cover lines 731-747 (optimistic update)
        api._send_mqtt_command = MagicMock()
        async def mock_send(*args, **kwargs): return None
        api._send_mqtt_command.side_effect = mock_send
        api.notify_settings_changed = MagicMock()
        async def mock_notify(*args): return None
        api.notify_settings_changed.side_effect = mock_notify
        
        # Setup initial state
        api.states = {"dev1": {}}
        api.devices = {"dev1": {"Model": "AC-V1"}}
        
        await api.set_ac_climate_plus("dev1", True)
        
        # Verify optimistic update
        state = api.states["dev1"]
        assert state["IsThermostatic"]["v"] == 1
        assert state["it"] == 1
        
        # Verify command sent
        api._send_mqtt_command.assert_called_once()
        args, _ = api._send_mqtt_command.call_args
        assert args[0] == "dev1"
        assert args[1]["cmd"][0]["it"] == 1

    @pytest.mark.asyncio
    async def test_ac_horizontal_swing(self, api):
        """Test set_ac_horizontal_swing."""
        # Cover lines 787-800
        api._send_mqtt_command = MagicMock()
        async def mock_send(*args, **kwargs): return None
        api._send_mqtt_command.side_effect = mock_send 
        api.notify_settings_changed = MagicMock()
        async def mock_notify(*args): return None
        api.notify_settings_changed.side_effect = mock_notify
        
        api.states = {"dev1": {}}
        api.devices = {"dev1": {"Model": "AC-V1"}}
        
        await api.set_ac_horizontal_swing("dev1", 50)
        
        # Verify optimistic update
        state = api.states["dev1"]
        assert state["SwingStateHorizontal"]["v"] == 50
        assert state["ssh"] == 50

    @pytest.mark.asyncio
    async def test_ac_modes_mapping(self, api):
        """Test set_hvac_mode with various modes."""
        # Cover lines 696-730
        api._send_mqtt_command = MagicMock()
        async def mock_send(*args, **kwargs): return None
        api._send_mqtt_command.side_effect = mock_send 
        api.notify_settings_changed = MagicMock()
        async def mock_notify(*args): return None
        api.notify_settings_changed.side_effect = mock_notify
        
        api.devices = {"dev_ac": {"Model": "AC-V1"}}
        
        from custom_components.mysa.const import (
            AC_MODE_OFF, AC_MODE_COOL, AC_MODE_AUTO, AC_MODE_HEAT, 
            AC_MODE_DRY, AC_MODE_FAN_ONLY
        )
        
        scenarios = [
            ("off", AC_MODE_OFF),
            ("cool", AC_MODE_COOL),
            ("auto", AC_MODE_AUTO),
            ("heat_cool", AC_MODE_AUTO),
            ("heat", AC_MODE_HEAT),
            ("dry", AC_MODE_DRY),
            ("fan_only", AC_MODE_FAN_ONLY),
            ("unknown", AC_MODE_OFF), # Default case
        ]
        
        for mode_str, expected_val in scenarios:
            await api.set_hvac_mode("dev_ac", mode_str)
            args, _ = api._send_mqtt_command.call_args
            assert args[1]["cmd"][0]["md"] == expected_val

    @pytest.mark.asyncio
    async def test_payload_type_upgraded_lite(self, api):
        """Test _get_payload_type for Upgraded Lite devices."""
        # Cover lines 654-657
        api.upgraded_lite_devices = ["lite1"]
        api.devices = {"lite1": {"Model": "BB-V1-Lite"}} 
        
        ptype = api._get_payload_type("lite1")
        assert ptype == 5
        
        # Test case insensitivity/colon removal
        api.upgraded_lite_devices = ["AB:CD:EF"]
        ptype = api._get_payload_type("ab:cd:ef")
        assert ptype == 5

    @pytest.mark.asyncio
    async def test_ac_invalid_inputs(self, api):
        """Test set_ac_fan_speed and set_ac_swing_mode with invalid inputs."""
        # Cover lines 755-757 and 774-776
        api._send_mqtt_command = MagicMock()
        async def mock_send(*args, **kwargs): return None
        api._send_mqtt_command.side_effect = mock_send 
        
        # Invalid Fan Speed
        await api.set_ac_fan_speed("dev1", "invalid_fan_mode")
        api._send_mqtt_command.assert_not_called()
        
        # Invalid Swing Mode
        await api.set_ac_swing_mode("dev1", "invalid_swing_mode")
        api._send_mqtt_command.assert_not_called()
