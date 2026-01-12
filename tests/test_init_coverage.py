"""
Init and Entry Lifecycle Coverage Tests.

Tests for __init__.py: async_setup_entry, async_options_updated, async_unload_entry
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
from custom_components.mysa.const import DOMAIN, PLATFORMS


# ===========================================================================
# async_setup_entry Tests
# ===========================================================================

class TestAsyncSetupEntry:
    """Test async_setup_entry function."""

    @pytest.fixture
    def mock_entry(self):
        """Create mock config entry."""
        entry = MagicMock()
        entry.entry_id = "test_entry_123"
        entry.data = {
            "username": "test@example.com",
            "password": "password123",
        }
        entry.options = {
            "upgraded_lite_devices": ["device1"],
            "estimated_max_current": 15.0,
        }
        entry.add_update_listener = MagicMock(return_value=MagicMock())
        entry.async_on_unload = MagicMock()
        return entry

    @pytest.mark.asyncio
    async def test_setup_entry_success(self, hass, mock_entry):
        """Test successful setup entry."""
        from custom_components.mysa import async_setup_entry
        
        with patch("custom_components.mysa.MysaApi") as MockApi, \
             patch("custom_components.mysa.DataUpdateCoordinator") as MockCoordinator:
            
            # Setup mocks
            mock_api = AsyncMock()
            mock_api.authenticate = AsyncMock()
            mock_api.start_mqtt_listener = AsyncMock()
            MockApi.return_value = mock_api
            
            mock_coordinator = MagicMock()
            mock_coordinator.async_config_entry_first_refresh = AsyncMock()
            mock_coordinator.async_request_refresh = AsyncMock()
            MockCoordinator.return_value = mock_coordinator
            
            hass.config_entries = MagicMock()
            hass.config_entries.async_forward_entry_setups = AsyncMock()
            
            result = await async_setup_entry(hass, mock_entry)
            
            assert result is True
            assert DOMAIN in hass.data
            assert mock_entry.entry_id in hass.data[DOMAIN]

    @pytest.mark.asyncio
    async def test_setup_entry_auth_failure(self, hass, mock_entry):
        """Test setup entry with authentication failure."""
        from custom_components.mysa import async_setup_entry
        from homeassistant.helpers.update_coordinator import UpdateFailed
        
        with patch("custom_components.mysa.MysaApi") as MockApi, \
             patch("custom_components.mysa.DataUpdateCoordinator") as MockCoordinator:
            
            mock_api = AsyncMock()
            mock_api.authenticate = AsyncMock(side_effect=Exception("Auth failed"))
            MockApi.return_value = mock_api
            
            mock_coordinator = MagicMock()
            MockCoordinator.return_value = mock_coordinator
            
            with pytest.raises(UpdateFailed):
                await async_setup_entry(hass, mock_entry)


# ===========================================================================
# async_options_updated Tests
# ===========================================================================

class TestAsyncOptionsUpdated:
    """Test async_options_updated function."""

    @pytest.mark.asyncio
    async def test_options_updated(self, hass):
        """Test options update handler."""
        from custom_components.mysa import async_options_updated
        
        mock_api = MagicMock()
        mock_api.upgraded_lite_devices = []
        mock_api.estimated_max_current = 0
        
        hass.data[DOMAIN] = {
            "test_entry_123": {"api": mock_api}
        }
        
        mock_entry = MagicMock()
        mock_entry.entry_id = "test_entry_123"
        mock_entry.options = {
            "upgraded_lite_devices": ["device1", "device2"],
            "estimated_max_current": 20.0,
        }
        
        await async_options_updated(hass, mock_entry)
        
        assert mock_api.upgraded_lite_devices == ["device1", "device2"]
        assert mock_api.estimated_max_current == 20.0


# ===========================================================================
# async_unload_entry Tests
# ===========================================================================

class TestAsyncUnloadEntry:
    """Test async_unload_entry function."""

    @pytest.fixture
    def mock_entry(self):
        """Create mock config entry."""
        entry = MagicMock()
        entry.entry_id = "test_entry_123"
        return entry

    @pytest.mark.asyncio
    async def test_unload_entry_success(self, hass, mock_entry):
        """Test successful unload entry."""
        from custom_components.mysa import async_unload_entry
        
        mock_api = MagicMock()
        mock_api.stop_mqtt_listener = AsyncMock()
        
        hass.data[DOMAIN] = {
            "test_entry_123": {"api": mock_api, "coordinator": MagicMock()}
        }
        
        hass.config_entries = MagicMock()
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
        
        result = await async_unload_entry(hass, mock_entry)
        
        assert result is True
        mock_api.stop_mqtt_listener.assert_called_once()
        assert mock_entry.entry_id not in hass.data[DOMAIN]

    @pytest.mark.asyncio
    async def test_unload_entry_no_data(self, hass, mock_entry):
        """Test unload entry when no data exists."""
        from custom_components.mysa import async_unload_entry
        
        hass.data[DOMAIN] = {}
        
        hass.config_entries = MagicMock()
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
        
        result = await async_unload_entry(hass, mock_entry)
        
        assert result is True

    @pytest.mark.asyncio
    async def test_unload_entry_no_api(self, hass, mock_entry):
        """Test unload entry when API doesn't exist."""
        from custom_components.mysa import async_unload_entry
        
        hass.data[DOMAIN] = {
            "test_entry_123": {"coordinator": MagicMock()}  # No api
        }
        
        hass.config_entries = MagicMock()
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
        
        result = await async_unload_entry(hass, mock_entry)
        
        assert result is True

    @pytest.mark.asyncio
    async def test_unload_entry_failure(self, hass, mock_entry):
        """Test unload entry when platform unload fails."""
        from custom_components.mysa import async_unload_entry
        
        mock_api = MagicMock()
        mock_api.stop_mqtt_listener = AsyncMock()
        
        hass.data[DOMAIN] = {
            "test_entry_123": {"api": mock_api}
        }
        
        hass.config_entries = MagicMock()
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=False)
        
        result = await async_unload_entry(hass, mock_entry)
        
        assert result is False
        # Data should NOT be removed on failure
        assert mock_entry.entry_id in hass.data[DOMAIN]


# ===========================================================================
# Coordinator Update Tests
# ===========================================================================

class TestCoordinatorUpdate:
    """Test coordinator update function."""

    @pytest.mark.asyncio
    async def test_coordinator_update_failure(self, hass):
        """Test coordinator update raises ConfigEntryNotReady on exception."""
        from custom_components.mysa import async_setup_entry
        from homeassistant.exceptions import ConfigEntryNotReady
        
        mock_entry = MagicMock()
        mock_entry.entry_id = "test_entry"
        mock_entry.data = {"username": "test", "password": "pass"}
        mock_entry.options = {}
        mock_entry.add_update_listener = MagicMock(return_value=MagicMock())
        mock_entry.async_on_unload = MagicMock()
        
        with patch("custom_components.mysa.MysaApi") as MockApi:
            mock_api = AsyncMock()
            mock_api.authenticate = AsyncMock()
            mock_api.get_state = AsyncMock(side_effect=Exception("API Error"))
            mock_api.start_mqtt_listener = AsyncMock()
            MockApi.return_value = mock_api
            
            hass.config_entries = MagicMock()
            hass.config_entries.async_forward_entry_setups = AsyncMock()
            
            # This should raise because first refresh will fail
            with pytest.raises(ConfigEntryNotReady):
                await async_setup_entry(hass, mock_entry)
