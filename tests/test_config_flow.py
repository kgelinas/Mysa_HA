"""
Config Flow Coverage Tests.

Tests for config_flow.py: ConfigFlow and MysaOptionsFlowHandler
"""

import sys
import os

# Add project root to path for imports
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(TEST_DIR)
sys.path.insert(0, ROOT_DIR)

import pytest
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD


# Module-level imports after path setup
from custom_components.mysa.const import DOMAIN


# ===========================================================================
# ConfigFlow Tests
# ===========================================================================


class TestConfigFlow:
    """Test ConfigFlow."""

    @pytest.mark.asyncio
    async def test_show_form(self, hass):
        """Test showing the initial form."""
        from custom_components.mysa.config_flow import ConfigFlow

        flow = ConfigFlow()
        flow.hass = hass
        flow._async_current_entries = MagicMock(return_value=[])

        result = await flow.async_step_user()

        assert result["type"] == "form"
        assert result["step_id"] == "user"

    @pytest.mark.asyncio
    async def test_single_instance_abort(self, hass):
        """Test aborting when instance already exists."""
        from custom_components.mysa.config_flow import ConfigFlow

        flow = ConfigFlow()
        flow.hass = hass

        # Simulate existing entry
        mock_entry = MagicMock()
        flow._async_current_entries = MagicMock(return_value=[mock_entry])

        result = await flow.async_step_user()

        assert result["type"] == "abort"
        assert result["reason"] == "single_instance_allowed"

    @pytest.mark.asyncio
    async def test_successful_auth(self, hass):
        """Test successful authentication."""
        from custom_components.mysa.config_flow import ConfigFlow

        flow = ConfigFlow()
        flow.hass = hass
        flow._async_current_entries = MagicMock(return_value=[])

        with patch.object(
            flow, "_validate_credentials", new_callable=AsyncMock
        ) as mock_validate:
            mock_validate.return_value = MagicMock()

            result = await flow.async_step_user(
                {
                    "username": "test@example.com",
                    "password": "password123",
                }
            )

            assert result["type"] == "create_entry"
            assert result["title"] == "test@example.com"
            assert result["data"]["username"] == "test@example.com"

    @pytest.mark.asyncio
    async def test_auth_failure(self, hass):
        """Test authentication failure shows error."""
        from custom_components.mysa.config_flow import ConfigFlow

        flow = ConfigFlow()
        flow.hass = hass
        flow._async_current_entries = MagicMock(return_value=[])

        with patch.object(
            flow, "_validate_credentials", new_callable=AsyncMock
        ) as mock_validate:
            mock_validate.side_effect = Exception("Auth failed")

            result = await flow.async_step_user(
                {
                    "username": "bad@example.com",
                    "password": "wrongpass",
                }
            )

            assert result["type"] == "form"
            assert result["errors"]["base"] == "invalid_auth"

    @pytest.mark.asyncio
    async def test_validate_credentials(self, hass):
        """Test _validate_credentials calls API."""
        from custom_components.mysa.config_flow import ConfigFlow

        flow = ConfigFlow()
        flow.hass = hass

        with patch("custom_components.mysa.config_flow.MysaApi") as MockApi:
            mock_api = AsyncMock()
            mock_api.authenticate = AsyncMock()
            MockApi.return_value = mock_api

            result = await flow._validate_credentials("test@example.com", "pass123")

            MockApi.assert_called_once_with("test@example.com", "pass123", hass)
            mock_api.authenticate.assert_called_once()


# ===========================================================================
# Options Flow Tests
# ===========================================================================


class TestOptionsFlow:
    """Test MysaOptionsFlowHandler."""

    @pytest.fixture
    def mock_config_entry(self):
        """Create mock config entry."""
        entry = MagicMock()
        entry.entry_id = "test_entry_123"
        entry.options = {
            "upgraded_lite_devices": [],
            "estimated_max_current": 0,
        }
        return entry

    @pytest.mark.asyncio
    async def test_options_flow_init(self, hass, mock_config_entry):
        """Test options flow initialization."""
        from custom_components.mysa.config_flow import MysaOptionsFlowHandler

        handler = MysaOptionsFlowHandler(mock_config_entry)

        assert handler._config_entry == mock_config_entry

    @pytest.mark.asyncio
    async def test_options_flow_show_form(self, hass, mock_config_entry):
        """Test options flow shows form with devices."""
        from custom_components.mysa.config_flow import MysaOptionsFlowHandler

        handler = MysaOptionsFlowHandler(mock_config_entry)
        handler.hass = hass

        # Setup mock API with devices
        mock_api = MagicMock()
        mock_api.devices = {
            "device1": {"Name": "Living Room"},
            "device2": {"Name": "Bedroom"},
        }

        hass.data[DOMAIN] = {"test_entry_123": {"api": mock_api}}

        result = await handler.async_step_init()

        assert result["type"] == "form"
        assert result["step_id"] == "init"

    @pytest.mark.asyncio
    async def test_options_flow_show_form_heating_devices(self, hass, mock_config_entry):
        """Test options flow shows form with heating devices (wattage input)."""
        from custom_components.mysa.config_flow import MysaOptionsFlowHandler

        handler = MysaOptionsFlowHandler(mock_config_entry)
        handler.hass = hass

        # Setup mock API with heating devices
        mock_api = MagicMock()
        devices = {
            "device1": {"Name": "Living Room", "Model": "BB-V2"},
        }
        mock_api.devices = devices
        mock_api.get_devices = AsyncMock(return_value=devices)

        # Mock is_ac_device to return False
        mock_api.is_ac_device = MagicMock(return_value=False)

        hass.data[DOMAIN] = {"test_entry_123": {"api": mock_api}}

        result = await handler.async_step_init()

        assert result["type"] == "form"
        # Verify schema contains wattage_device1
        schema = result["data_schema"]

        # Voluptuous schema keys are wrapped, check string representation
        keys = list(schema.schema.keys())
        found = any("wattage_device1" in str(k) for k in keys)
        assert found is True

    @pytest.mark.asyncio
    async def test_options_flow_submit(self, hass, mock_config_entry):
        """Test options flow submission creates entry."""
        from custom_components.mysa.config_flow import MysaOptionsFlowHandler

        handler = MysaOptionsFlowHandler(mock_config_entry)
        handler.hass = hass

        result = await handler.async_step_init(
            {
                "upgraded_lite_devices": ["device1"],
                "estimated_max_current": 15.0,
            }
        )

        assert result["type"] == "create_entry"
        assert result["data"]["upgraded_lite_devices"] == ["device1"]
        assert result["data"]["estimated_max_current"] == 15.0

    @pytest.mark.asyncio
    async def test_options_flow_no_api_fallback(self, hass, mock_config_entry):
        """Test options flow shows form even when API not available."""
        from custom_components.mysa.config_flow import MysaOptionsFlowHandler

        handler = MysaOptionsFlowHandler(mock_config_entry)
        handler.hass = hass

        # No API data
        hass.data[DOMAIN] = {}

        result = await handler.async_step_init()

        assert result["type"] == "form"
        assert result["step_id"] == "init"


# ===========================================================================
# async_get_options_flow Tests
# ===========================================================================


class TestGetOptionsFlow:
    """Test async_get_options_flow."""

    def test_get_options_flow(self):
        """Test async_get_options_flow returns handler."""
        from custom_components.mysa.config_flow import (
            ConfigFlow,
            MysaOptionsFlowHandler,
        )


# ===========================================================================
# ConfigFlow Tests
# ===========================================================================


class TestConfigFlow:
    """Test ConfigFlow."""

    @pytest.mark.asyncio
    async def test_show_form(self, hass):
        """Test showing the initial form."""
        from custom_components.mysa.config_flow import ConfigFlow

        flow = ConfigFlow()
        flow.hass = hass
        flow._async_current_entries = MagicMock(return_value=[])

        result = await flow.async_step_user()

        assert result["type"] == "form"
        assert result["step_id"] == "user"

    @pytest.mark.asyncio
    async def test_single_instance_abort(self, hass):
        """Test aborting when instance already exists."""
        from custom_components.mysa.config_flow import ConfigFlow

        flow = ConfigFlow()
        flow.hass = hass

        # Simulate existing entry
        mock_entry = MagicMock()
        flow._async_current_entries = MagicMock(return_value=[mock_entry])

        result = await flow.async_step_user()

        assert result["type"] == "abort"
        assert result["reason"] == "single_instance_allowed"

    @pytest.mark.asyncio
    async def test_successful_auth(self, hass):
        """Test successful authentication."""
        from custom_components.mysa.config_flow import ConfigFlow

        flow = ConfigFlow()
        flow.hass = hass
        flow._async_current_entries = MagicMock(return_value=[])

        with patch.object(
            flow, "_validate_credentials", new_callable=AsyncMock
        ) as mock_validate:
            mock_validate.return_value = MagicMock()

            result = await flow.async_step_user(
                {
                    "username": "test@example.com",
                    "password": "password123",
                }
            )

            assert result["type"] == "create_entry"
            assert result["title"] == "test@example.com"
            assert result["data"]["username"] == "test@example.com"

    @pytest.mark.asyncio
    async def test_auth_failure(self, hass):
        """Test authentication failure shows error."""
        from custom_components.mysa.config_flow import ConfigFlow

        flow = ConfigFlow()
        flow.hass = hass
        flow._async_current_entries = MagicMock(return_value=[])

        with patch.object(
            flow, "_validate_credentials", new_callable=AsyncMock
        ) as mock_validate:
            mock_validate.side_effect = Exception("Auth failed")

            result = await flow.async_step_user(
                {
                    "username": "bad@example.com",
                    "password": "wrongpass",
                }
            )

            assert result["type"] == "form"
            assert result["errors"]["base"] == "invalid_auth"

    @pytest.mark.asyncio
    async def test_validate_credentials(self, hass):
        """Test _validate_credentials calls API."""
        from custom_components.mysa.config_flow import ConfigFlow

        flow = ConfigFlow()
        flow.hass = hass

        with patch("custom_components.mysa.config_flow.MysaApi") as MockApi:
            mock_api = AsyncMock()
            mock_api.authenticate = AsyncMock()
            MockApi.return_value = mock_api

            result = await flow._validate_credentials("test@example.com", "pass123")

            MockApi.assert_called_once_with("test@example.com", "pass123", hass)
            mock_api.authenticate.assert_called_once()


# ===========================================================================
# Options Flow Tests
# ===========================================================================


class TestOptionsFlow:
    """Test MysaOptionsFlowHandler."""

    @pytest.fixture
    def mock_config_entry(self):
        """Create mock config entry."""
        entry = MagicMock()
        entry.entry_id = "test_entry_123"
        entry.options = {
            "upgraded_lite_devices": [],
            "estimated_max_current": 0,
        }
        return entry

    @pytest.mark.asyncio
    async def test_options_flow_init(self, hass, mock_config_entry):
        """Test options flow initialization."""
        from custom_components.mysa.config_flow import MysaOptionsFlowHandler

        handler = MysaOptionsFlowHandler(mock_config_entry)

        assert handler._config_entry == mock_config_entry

    @pytest.mark.asyncio
    async def test_options_flow_show_form(self, hass, mock_config_entry):
        """Test options flow shows form with devices."""
        from custom_components.mysa.config_flow import MysaOptionsFlowHandler

        handler = MysaOptionsFlowHandler(mock_config_entry)
        handler.hass = hass

        # Setup mock API with devices
        mock_api = MagicMock()
        mock_api.devices = {
            "device1": {"Name": "Living Room"},
            "device2": {"Name": "Bedroom"},
        }

        hass.data[DOMAIN] = {"test_entry_123": {"api": mock_api}}

        result = await handler.async_step_init()

        assert result["type"] == "form"
        assert result["step_id"] == "init"

    @pytest.mark.asyncio
    async def test_options_flow_submit(self, hass, mock_config_entry):
        """Test options flow submission creates entry."""
        from custom_components.mysa.config_flow import MysaOptionsFlowHandler

        handler = MysaOptionsFlowHandler(mock_config_entry)
        handler.hass = hass

        result = await handler.async_step_init(
            {
                "upgraded_lite_devices": ["device1"],
                "estimated_max_current": 15.0,
            }
        )

        assert result["type"] == "create_entry"
        assert result["data"]["upgraded_lite_devices"] == ["device1"]
        assert result["data"]["estimated_max_current"] == 15.0

    @pytest.mark.asyncio
    async def test_options_flow_no_api_fallback(self, hass, mock_config_entry):
        """Test options flow shows form even when API not available."""
        from custom_components.mysa.config_flow import MysaOptionsFlowHandler

        handler = MysaOptionsFlowHandler(mock_config_entry)
        handler.hass = hass

        # No API data
        hass.data[DOMAIN] = {}

        result = await handler.async_step_init()

        assert result["type"] == "form"
        assert result["step_id"] == "init"


# ===========================================================================
# async_get_options_flow Tests
# ===========================================================================


class TestGetOptionsFlow:
    """Test async_get_options_flow."""

    def test_get_options_flow(self):
        """Test async_get_options_flow returns handler."""
        from custom_components.mysa.config_flow import (
            ConfigFlow,
            MysaOptionsFlowHandler,
        )

        mock_entry = MagicMock()
        mock_entry.entry_id = "test_entry"

        result = ConfigFlow.async_get_options_flow(mock_entry)

        assert isinstance(result, MysaOptionsFlowHandler)


# ===========================================================================
# Reauth Flow Tests (merged from test_config_flow_reauth.py)
# ===========================================================================


class TestConfigFlowReauth:
    """Test Reauthentication Flow."""

    @pytest.mark.asyncio
    async def test_reauth_successful(self, hass):
        """Test successful reauthentication."""
        from custom_components.mysa.config_flow import ConfigFlow

        flow = ConfigFlow()
        flow.hass = hass

        # Mock existing entry
        mock_entry = MagicMock()
        mock_entry.data = {CONF_USERNAME: "test@example.com"}
        mock_entry.entry_id = "test_entry_id"

        flow.context = {"entry_id": "test_entry_id"}

        with (
            patch.object(
                hass.config_entries, "async_get_entry", return_value=mock_entry
            ),
            patch.object(hass.config_entries, "async_update_entry") as mock_update,
            patch.object(
                hass.config_entries, "async_reload", new_callable=AsyncMock
            ) as mock_reload,
            patch.object(
                flow, "_validate_credentials", new_callable=AsyncMock
            ) as mock_validate,
        ):
            # Start reauth
            await flow.async_step_reauth({})

            # Submit valid credentials for same account
            result = await flow.async_step_reauth_confirm(
                {
                    "username": "test@example.com",
                    "password": "new_password_123",
                }
            )

            assert result["type"] == "abort"
            assert result["reason"] == "reauth_successful"
            mock_validate.assert_called_once()
            mock_update.assert_called_once_with(
                mock_entry,
                data={
                    CONF_USERNAME: "test@example.com",
                    CONF_PASSWORD: "new_password_123",
                },
            )
            mock_reload.assert_called_once_with("test_entry_id")

    @pytest.mark.asyncio
    async def test_reauth_account_mismatch(self, hass):
        """Test reauth fails if trying to use different account."""
        from custom_components.mysa.config_flow import ConfigFlow

        flow = ConfigFlow()
        flow.hass = hass

        mock_entry = MagicMock()
        mock_entry.data = {CONF_USERNAME: "original@example.com"}

        flow.entry = mock_entry  # Already set by async_step_reauth

        with patch.object(flow, "_validate_credentials", new_callable=AsyncMock):
            result = await flow.async_step_reauth_confirm(
                {
                    "username": "different@example.com",
                    "password": "password",
                }
            )

            assert result["type"] == "form"
            assert result["errors"]["base"] == "reauth_account_mismatch"

    @pytest.mark.asyncio
    async def test_reauth_entry_not_found(self, hass):
        """Test reauth fails when entry is missing (edge case)."""
        from custom_components.mysa.config_flow import ConfigFlow

        flow = ConfigFlow()
        flow.hass = hass

        # entry is None (default state if async_step_reauth wasn't called or failed)
        flow.entry = None

        with patch.object(flow, "_validate_credentials", new_callable=AsyncMock):
            result = await flow.async_step_reauth_confirm(
                {
                    "username": "test@example.com",
                    "password": "password",
                }
            )

            assert result["type"] == "form"
            assert result["errors"]["base"] == "unknown"

    @pytest.mark.asyncio
    async def test_reauth_validation_exception(self, hass):
        """Test reauth handles validation exceptions."""
        from custom_components.mysa.config_flow import ConfigFlow

        flow = ConfigFlow()
        flow.hass = hass
        flow.entry = MagicMock()

        # Simulate exception during validation
        with patch.object(
            flow,
            "_validate_credentials",
            side_effect=Exception("API Error")
        ):
            result = await flow.async_step_reauth_confirm(
                {
                    "username": "test@example.com",
                    "password": "password",
                }
            )

            assert result["type"] == "form"
            assert result["errors"]["base"] == "invalid_auth"


# ===========================================================================
# Coverage Tests
# ===========================================================================


class TestConfigFlowCoverage:
    """Targeted coverage tests for config_flow.py."""

    @pytest.mark.asyncio
    async def test_options_flow_heating_device_schema(self, hass, mock_config_entry):
        """Test schema generation for heating devices (lines 163-166)."""
        from custom_components.mysa.config_flow import MysaOptionsFlowHandler

        handler = MysaOptionsFlowHandler(mock_config_entry)
        handler.hass = hass

        # Mock API with one heating device (BB-V2)
        mock_api = MagicMock()
        mock_api.devices = {
            "device1": {"Name": "Heater", "Model": "BB-V2"}
        }
        mock_api.is_ac_device.return_value = False # Key check for line 162

        hass.data[DOMAIN] = {
            mock_config_entry.entry_id: {"api": mock_api}
        }

        result = await handler.async_step_init()

        assert result["type"] == "form"
        # Check if wattage_device1 key exists in schema
        schema = result["data_schema"]
        # Voluptuous schema keys are wrapped, need to iterate/check string representation or key name
        found = False
        for key in schema.schema.keys():
            if str(key) == "wattage_device1":
                found = True
                break
        assert found

    @pytest.mark.asyncio
    async def test_config_flow_coverage_gap(self, hass):
        """Test config flow coverage (lines 168+ and loop 184-190)."""
        from custom_components.mysa.config_flow import ConfigFlow

        flow = ConfigFlow()
        flow.hass = hass
        
        # Mock entry with existing options
        entry = MagicMock()
        entry.options = {"simulated_energy": False}
        entry.entry_id = "test_id"
        
        # Mock API
        api = MagicMock()
        # Device that is NOT AC (to trigger line 169)
        # Device with Name to trigger line 172
        api.devices = {"dev1": {"Name": "Heater", "Model": "BB-V2"}}
        api.zones = {"1": "Zone1"}
        api.is_ac_device.return_value = False
        
        hass.data[DOMAIN] = {"test_id": {"api": api}}
        
        handler = flow.async_get_options_flow(entry)
        handler.hass = hass
        
        # Run step init
        result = await handler.async_step_init()
        
        assert result["type"] == "form"
        schema = result["data_schema"]
        
        # Verify Zone field (Line 184-190 coverage)
        # This proves the loop ran and added the field
        assert any(str(k) == "zone_name_1" for k in schema.schema)
