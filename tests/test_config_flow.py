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
