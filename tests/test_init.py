"""Tests for the Mysa integration init."""
from unittest.mock import MagicMock, patch, AsyncMock
import pytest
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntryState
from custom_components.mysa import async_setup_entry, async_unload_entry, async_service_handle
from custom_components.mysa.const import DOMAIN
from custom_components.mysa.mysa_api import MysaApi

@pytest.fixture
def mock_api():
    """Mock MysaApi."""
    api = MagicMock(spec=MysaApi)
    api.devices = {}
    api.start_mqtt_listener = AsyncMock()
    api.stop_mqtt_listener = AsyncMock()
    api.async_upgrade_lite_device = AsyncMock(return_value=True)
    api.async_downgrade_lite_device = AsyncMock(return_value=True)
    return api

@pytest.mark.asyncio
async def test_async_service_handle_success(hass: HomeAssistant, mock_api):
    """Test async_service_handle success path."""
    # Mock dependencies
    mock_entry = MagicMock()
    mock_entry.data = {}
    mock_entry.options = {}
    hass.data[DOMAIN] = {
        "mysa_account_id": {"api": mock_api}
    }
    
    # Mock Device Registry
    mock_device_registry = MagicMock()
    mock_device_entry = MagicMock()
    mock_device_entry.identifiers = {(DOMAIN, "device_id_123")}
    mock_device_registry.async_get.return_value = mock_device_entry
    
    # Ensure API has device
    mock_api.devices = {"device_id_123": {}}
    
    # Mock Config Entry
    hass.config_entries.async_get_entry = MagicMock(return_value=mock_entry)
    hass.config_entries.async_update_entry = MagicMock(return_value=True)
    
    with patch("homeassistant.helpers.device_registry.async_get", return_value=mock_device_registry):
        call = MagicMock()
        call.service = "upgrade_lite_device"
        call.data = {"device_id": "ha_device_id"}
        
        await async_service_handle(hass, call)
        
        # Verify API called
        mock_api.async_upgrade_lite_device.assert_called_with("device_id_123")
        
        # Verify Config Entry Updated
        hass.config_entries.async_update_entry.assert_called()

@pytest.mark.asyncio
async def test_async_service_handle_no_device(hass: HomeAssistant):
    """Test service handle when device not found."""
    mock_device_registry = MagicMock()
    mock_device_registry.async_get.return_value = None
    
    with patch("homeassistant.helpers.device_registry.async_get", return_value=mock_device_registry):
        call = MagicMock()
        call.data = {"device_id": "invalid_id"}
        
        # Should return/log warning but not crash
        await async_service_handle(hass, call)

@pytest.mark.asyncio
async def test_async_service_handle_no_mysa_id(hass: HomeAssistant):
    """Test service handle when device has no mysa identifier."""
    mock_device_registry = MagicMock()
    mock_device_entry = MagicMock()
    mock_device_entry.identifiers = {("other_domain", "id")}
    mock_device_registry.async_get.return_value = mock_device_entry
    
    with patch("homeassistant.helpers.device_registry.async_get", return_value=mock_device_registry):
        call = MagicMock()
        call.data = {"device_id": "ha_id"}
        
        await async_service_handle(hass, call)

@pytest.mark.asyncio
async def test_async_service_handle_api_failure(hass: HomeAssistant, mock_api):
    """Test service handle when API upgrade fails."""
    mock_api.async_upgrade_lite_device.return_value = False
    
    hass.data[DOMAIN] = {
        "mysa_account_id": {"api": mock_api}
    }
    
    mock_device_registry = MagicMock()
    mock_device_entry = MagicMock()
    mock_device_entry.identifiers = {(DOMAIN, "dev1")}
    mock_device_registry.async_get.return_value = mock_device_entry
    
    # Mock config entry linkage via some means or just rely on global lookup if code does that
    # Code likely finds entry from device registry -> config_entries
    mock_device_entry.config_entries = ["entry_id"]
    hass.config_entries.async_get_entry = MagicMock(return_value=MagicMock(data={})) 
    
    # API must have device
    mock_api.devices = {"dev1": {}}
    
    with patch("homeassistant.helpers.device_registry.async_get", return_value=mock_device_registry):
        call = MagicMock()
        call.service = "upgrade_lite_device"
        call.data = {"device_id": "ha_id"}
        
        await async_service_handle(hass, call)
        
        mock_api.async_upgrade_lite_device.assert_called()

@pytest.mark.asyncio
async def test_service_handle_orphaned_device(hass: HomeAssistant, mock_api):
    """Test service handle when API does not manage the device."""
    hass.data[DOMAIN] = {
        "mysa_account_id": {"api": mock_api}
    }
    
    mock_device_registry = MagicMock()
    mock_device_entry = MagicMock()
    mock_device_entry.identifiers = {(DOMAIN, "orphaned_device")}
    mock_device_registry.async_get.return_value = mock_device_entry
    
    # API devices empty or doesn't have it
    mock_api.devices = {"other_device": {}}
    
    with patch("homeassistant.helpers.device_registry.async_get", return_value=mock_device_registry):
        call = MagicMock()
        call.data = {"device_id": "ha_orphaned"}
        
        # Should log error line 134
        await async_service_handle(hass, call)
        
        mock_api.async_upgrade_lite_device.assert_not_called()

@pytest.mark.asyncio
async def test_async_service_handle_downgrade_success(hass: HomeAssistant, mock_api):
    """Test async_service_handle downgrade success path."""
    # Mock dependencies
    mock_entry = MagicMock()
    mock_entry.data = {}
    mock_entry.options = {"upgraded_lite_devices": ["device_id_123"]}
    
    hass.data[DOMAIN] = {
        "mysa_account_id": {"api": mock_api}
    }
    
    # Mock Device Registry
    mock_device_registry = MagicMock()
    mock_device_entry = MagicMock()
    mock_device_entry.identifiers = {(DOMAIN, "device_id_123")}
    mock_device_registry.async_get.return_value = mock_device_entry
    
    # Ensure API has device
    mock_api.devices = {"device_id_123": {}}
    
    # Mock Config Entry
    hass.config_entries.async_get_entry = MagicMock(return_value=mock_entry)
    hass.config_entries.async_update_entry = MagicMock(return_value=True)
    
    with patch("homeassistant.helpers.device_registry.async_get", return_value=mock_device_registry):
        call = MagicMock()
        call.service = "downgrade_lite_device"
        call.data = {"device_id": "ha_device_id"}
        
        await async_service_handle(hass, call)
        
        # Verify API called
        mock_api.async_downgrade_lite_device.assert_called_with("device_id_123")
        
        # Verify Config Entry Updated (removed from list)
        update_call_args = hass.config_entries.async_update_entry.call_args
        assert update_call_args is not None
        assert "upgraded_lite_devices" in update_call_args[1]["options"]
        assert "device_id_123" not in update_call_args[1]["options"]["upgraded_lite_devices"]

# ===========================================================================
# async_setup_entry Tests (Merged)
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
        entry.state = ConfigEntryState.SETUP_IN_PROGRESS
        return entry

    @pytest.mark.asyncio
    async def test_setup_entry_success(self, hass, mock_entry):
        """Test successful setup entry."""
        from custom_components.mysa import async_setup_entry

        with (
            patch("custom_components.mysa.MysaApi") as MockApi,
            patch("custom_components.mysa.DataUpdateCoordinator") as MockCoordinator,
        ):
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
        from homeassistant.exceptions import ConfigEntryNotReady

        with (
            patch("custom_components.mysa.MysaApi") as MockApi,
            patch("custom_components.mysa.DataUpdateCoordinator") as MockCoordinator,
        ):
            mock_api = AsyncMock()
            mock_api.authenticate = AsyncMock(side_effect=Exception("Auth failed"))
            MockApi.return_value = mock_api

            mock_coordinator = MagicMock()
            MockCoordinator.return_value = mock_coordinator

            with pytest.raises(ConfigEntryNotReady):
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

        hass.data[DOMAIN] = {"test_entry_123": {"api": mock_api}}

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

        hass.data[DOMAIN] = {"test_entry_123": {"api": mock_api}}

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
        mock_entry.state = ConfigEntryState.SETUP_IN_PROGRESS

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
