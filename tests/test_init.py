"""Tests for the Mysa integration init."""
from unittest.mock import MagicMock, patch, AsyncMock
import pytest
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers.update_coordinator import UpdateFailed
from custom_components.mysa import async_setup_entry, async_unload_entry, MysaData
from custom_components.mysa.const import DOMAIN
from custom_components.mysa.mysa_api import MysaApi


# ===========================================================================
# Service Tests Removed
# ===========================================================================
# The upgrade_lite_device and downgrade_lite_device services have been moved
# to the mysa_extended integration. Tests for those services should be added
# to tests/test_mysa_extended.py
# ===========================================================================

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
            patch("custom_components.mysa.ir.async_delete_issue") as mock_delete_issue,
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
            assert isinstance(mock_entry.runtime_data, MysaData)
            assert mock_entry.runtime_data.api == mock_api
            assert mock_entry.runtime_data.coordinator == mock_coordinator
            # Verify auth issue was cleared on success
            mock_delete_issue.assert_called_once()

            # Verify the new Push Callback
            # 1. Ensure callback was assigned to API
            assert hasattr(mock_api, "coordinator_callback")
            push_callback = mock_api.coordinator_callback
            assert callable(push_callback)

            # 2. Simulate invoking the callback
            # Setup fake state
            mock_api.states = {"test_device": {"temp": 21}}
            await push_callback()

            # 3. Verify it pushed data to coordinator
            mock_coordinator.async_set_updated_data.assert_called_with(mock_api.states)

    @pytest.mark.asyncio
    async def test_setup_entry_auth_failure(self, hass, mock_entry):
        """Test setup entry with authentication failure."""
        from custom_components.mysa import async_setup_entry
        from homeassistant.exceptions import ConfigEntryAuthFailed

        with (
            patch("custom_components.mysa.MysaApi") as MockApi,
            patch("custom_components.mysa.DataUpdateCoordinator") as MockCoordinator,
            patch("custom_components.mysa.ir.async_create_issue") as mock_create_issue,
        ):
            mock_api = AsyncMock()
            mock_api.authenticate = AsyncMock(side_effect=Exception("Auth failed"))
            MockApi.return_value = mock_api

            mock_coordinator = MagicMock()
            MockCoordinator.return_value = mock_coordinator

            with pytest.raises(ConfigEntryAuthFailed):
                await async_setup_entry(hass, mock_entry)

            # Verify repair issue was created
            mock_create_issue.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_data_logging_and_recovery(self, hass, mock_entry):
        """Test logging and recovery logic in async_update_data."""
        from custom_components.mysa import async_setup_entry

        with (
            patch("custom_components.mysa.MysaApi") as MockApi,
            patch("custom_components.mysa.DataUpdateCoordinator") as MockCoordinator,
            patch("custom_components.mysa._LOGGER") as mock_logger,
            patch("custom_components.mysa.ir.async_delete_issue"),
        ):
            mock_api = AsyncMock()
            mock_api.authenticate = AsyncMock()
            # Initial Setup Success
            mock_api.get_state = AsyncMock(return_value={"device": "state"})
            mock_api.start_mqtt_listener = AsyncMock()
            MockApi.return_value = mock_api

            mock_coordinator = MagicMock()
            mock_coordinator.async_config_entry_first_refresh = AsyncMock()
            MockCoordinator.return_value = mock_coordinator

            hass.config_entries = MagicMock()
            hass.config_entries.async_forward_entry_setups = AsyncMock()

            # Run setup to initialize the coordinator and the inner update function
            await async_setup_entry(hass, mock_entry)

            # Capture the update_method passed to DataUpdateCoordinator
            # Call args: (hass, _LOGGER, name=..., update_method=..., ...)
            # We can grab it from kwargs
            if MockCoordinator.target == "custom_components.mysa.DataUpdateCoordinator":
                 # Verify call args
                 pass

            # MockCoordinator is a class, so return_value is the instance.
            # We want to inspect the call to the CLASS constructor.
            args, kwargs = MockCoordinator.call_args
            update_method = kwargs.get("update_method")
            assert update_method is not None

            # --- Test Scenario 1: First refresh failure (already covered mostly, but specific path needed) ---
            # But here we want to test the inner logic regarding `unavailable_logged` and `first_refresh`

            # The `async_setup_entry` execution already ran the `coordinator` creation.
            # The vars `first_refresh` and `unavailable_logged` are captured in the closure.
            # `first_refresh` starts as True.

            # We need to simulate the calls.
            # Note: The real code calls `get_state`.

            # 1. First call fails (Initial setup failure logging)
            # We need to manually control the closure state. The state is private to the closure.
            # However, we can just run the function.

            # Re-creating the setup effectively to get a fresh closure state is cleaner,
            # but we already did that above.

            # Let's mock get_state to fail.
            mock_api.get_state.side_effect = Exception("First failure")

            # Calling update_method()
            # `first_refresh` is True initially.
            try:
                await update_method()
            except UpdateFailed:
                pass

            # Should have logged ERROR (line 50)
            mock_logger.error.assert_called_with("Error communicating with API during initial setup: %s", mock_api.get_state.side_effect)

            # `unavailable_logged` is now True. `first_refresh` is still True (because it failed before setting to False? No, look at code).
            # Code:
            # except Exception:
            #   if not unavailable_logged: ... unavailable_logged = True
            #   raise
            # So `first_refresh` does NOT get set to False if it fails. Correct.

            # 2. Second call fails (Subsequent failure logging)
            # `unavailable_logged` is True.
            # It enters except block. `if not unavailable_logged` is False.
            # So it does NOT log warning or error. Just raises. This path is lines 48-54, but specifically NOT entering the if.

            # Wait, I want to test line 52: `_LOGGER.warning`.
            # This requires: `unavailable_logged` is False, but `first_refresh` is False.

            # So I need a successful run first to set `first_refresh = False`.

            # START OVER checking logic
            # To hit line 52:
            # 1. Success (sets `first_refresh` = False).
            # 2. Failure (unavailable_logged=False -> enters if -> `first_refresh` is False -> Log Warning).

            # Let's do that sequence.

            # Reset mocks
            mock_logger.reset_mock()
            mock_api.get_state.side_effect = None
            mock_api.get_state.return_value = {"ok": 1}

            # 1. Success call
            await update_method()
            # `first_refresh` is now False. `unavailable_logged` is False.

            # 2. Failure call
            mock_api.get_state.side_effect = Exception("Second failure")
            try:
                await update_method()
            except UpdateFailed:
                pass

            # check warning
            mock_logger.warning.assert_called_with("Error communicating with API: %s", mock_api.get_state.side_effect)
            # `unavailable_logged` is now True.

            # 3. Third call (Failure again)
            # Should NOT log warning/error again.
            mock_logger.reset_mock()
            try:
                await update_method()
            except UpdateFailed:
                pass
            mock_logger.warning.assert_not_called()
            mock_logger.error.assert_not_called()

            # 4. Fourth call (Success - Recovery)
            # Should log info "Communication with API restored" (Line 43)
            mock_api.get_state.side_effect = None
            await update_method()

            mock_logger.info.assert_called_with("Communication with API restored")
            # `unavailable_logged` becomes False.

    @pytest.mark.asyncio
    async def test_check_device_changes(self, hass, mock_entry):
        """Test the device change detection listener."""
        from custom_components.mysa import async_setup_entry

        with (
            patch("custom_components.mysa.MysaApi") as MockApi,
            patch("custom_components.mysa.DataUpdateCoordinator") as MockCoordinator,
            patch("custom_components.mysa._LOGGER") as mock_logger,
            patch("custom_components.mysa.ir.async_delete_issue"),
        ):
            mock_api = AsyncMock()
            mock_api.authenticate = AsyncMock()
            mock_api.get_state = AsyncMock(return_value={})
            mock_api.start_mqtt_listener = AsyncMock()
            mock_api.devices = {"dev1": "obj1"} # Initial known devices
            MockApi.return_value = mock_api

            mock_coordinator = MagicMock()
            mock_coordinator.async_config_entry_first_refresh = AsyncMock()
            mock_coordinator.async_add_listener = MagicMock()
            # Mock data property
            mock_coordinator.data = {"dev1": "data1"}
            MockCoordinator.return_value = mock_coordinator

            hass.config_entries = MagicMock()
            hass.config_entries.async_reload = AsyncMock()
            hass.config_entries.async_forward_entry_setups = AsyncMock()
            hass.async_create_task = MagicMock(side_effect=lambda x: x) # sync helper

            await async_setup_entry(hass, mock_entry)

            # Capture listener
            args, _ = mock_coordinator.async_add_listener.call_args
            listener = args[0]
            assert listener is not None

            # Test 1: No data (Line 117-118)
            mock_coordinator.data = None
            listener()
            hass.config_entries.async_reload.assert_not_called()

            # Test 2: No change
            mock_coordinator.data = {"dev1": "data1"}
            mock_api.devices = {"dev1": "obj1"}
            listener()
            hass.config_entries.async_reload.assert_not_called()

            # Test 3: New device detected - should trigger reload
            # Add a new device in coordinator data
            mock_coordinator.data = {"dev1": "data1", "dev2": "data2"}
            listener()

            mock_logger.info.assert_called()
            assert "New devices detected" in mock_logger.info.call_args[0][0]
            hass.config_entries.async_reload.assert_called_with(mock_entry.entry_id)

    @pytest.mark.asyncio
    async def test_stale_device_removal(self, hass, mock_entry):
        """Test that stale devices are removed from device registry."""
        from custom_components.mysa import async_setup_entry

        with (
            patch("custom_components.mysa.MysaApi") as MockApi,
            patch("custom_components.mysa.DataUpdateCoordinator") as MockCoordinator,
            patch("custom_components.mysa.dr.async_get") as mock_dr_get,
            patch("custom_components.mysa.ir.async_delete_issue"),
        ):
            mock_api = AsyncMock()
            mock_api.authenticate = AsyncMock()
            mock_api.get_state = AsyncMock(return_value={})
            mock_api.start_mqtt_listener = AsyncMock()
            mock_api.devices = {"dev1": "obj1", "dev2": "obj2"}
            MockApi.return_value = mock_api

            mock_coordinator = MagicMock()
            mock_coordinator.async_config_entry_first_refresh = AsyncMock()
            mock_coordinator.async_add_listener = MagicMock()
            # Initial data has both devices
            mock_coordinator.data = {"dev1": "data1", "dev2": "data2"}
            MockCoordinator.return_value = mock_coordinator

            # Mock device registry
            mock_device_registry = MagicMock()
            mock_device = MagicMock()
            mock_device.id = "device_registry_id"
            mock_device_registry.async_get_device.return_value = mock_device
            mock_dr_get.return_value = mock_device_registry

            hass.config_entries = MagicMock()
            hass.config_entries.async_reload = AsyncMock()
            hass.config_entries.async_forward_entry_setups = AsyncMock()
            hass.async_create_task = MagicMock(side_effect=lambda x: x)

            await async_setup_entry(hass, mock_entry)

            # Capture listener
            args, _ = mock_coordinator.async_add_listener.call_args
            listener = args[0]

            # Simulate device removal - dev2 disappears
            mock_coordinator.data = {"dev1": "data1"}
            listener()

            # Verify device registry was called to remove stale device
            mock_dr_get.assert_called_with(hass)
            mock_device_registry.async_update_device.assert_called()


# ===========================================================================
# async_remove_config_entry_device Tests
# ===========================================================================

class TestAsyncRemoveConfigEntryDevice:
    """Test async_remove_config_entry_device function."""

    @pytest.mark.asyncio
    async def test_remove_device_not_in_cloud(self, hass):
        """Test that devices not in cloud can be removed."""
        from custom_components.mysa import async_remove_config_entry_device

        mock_api = MagicMock()
        mock_api.devices = {"dev1": "data1"}

        mock_data = MagicMock(spec=MysaData)
        mock_data.api = mock_api

        mock_entry = MagicMock()
        mock_entry.runtime_data = mock_data

        mock_device_entry = MagicMock()
        mock_device_entry.identifiers = {(DOMAIN, "dev2")}  # Not in cloud

        result = await async_remove_config_entry_device(hass, mock_entry, mock_device_entry)
        assert result is True  # Allow removal

    @pytest.mark.asyncio
    async def test_remove_device_still_in_cloud(self, hass):
        """Test that devices still in cloud cannot be removed."""
        from custom_components.mysa import async_remove_config_entry_device

        mock_api = MagicMock()
        mock_api.devices = {"dev1": "data1"}

        mock_data = MagicMock(spec=MysaData)
        mock_data.api = mock_api

        mock_entry = MagicMock()
        mock_entry.runtime_data = mock_data

        mock_device_entry = MagicMock()
        mock_device_entry.identifiers = {(DOMAIN, "dev1")}  # Still in cloud

        result = await async_remove_config_entry_device(hass, mock_entry, mock_device_entry)
        assert result is False  # Don't allow removal

    @pytest.mark.asyncio
    async def test_remove_device_no_runtime_data(self, hass):
        """Test removal allowed when no runtime data."""
        from custom_components.mysa import async_remove_config_entry_device

        mock_entry = MagicMock()
        mock_entry.runtime_data = None

        mock_device_entry = MagicMock()
        mock_device_entry.identifiers = {(DOMAIN, "dev1")}

        result = await async_remove_config_entry_device(hass, mock_entry, mock_device_entry)
        assert result is True  # Allow removal

    @pytest.mark.asyncio
    async def test_remove_device_no_api(self, hass):
        """Test removal allowed when no API."""
        from custom_components.mysa import async_remove_config_entry_device

        mock_data = MagicMock(spec=MysaData)
        mock_data.api = None

        mock_entry = MagicMock()
        mock_entry.runtime_data = mock_data

        mock_device_entry = MagicMock()
        mock_device_entry.identifiers = {(DOMAIN, "dev1")}

        result = await async_remove_config_entry_device(hass, mock_entry, mock_device_entry)
        assert result is True  # Allow removal


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

        mock_data = MagicMock(spec=MysaData)
        mock_data.api = mock_api
        mock_entry = MagicMock()
        mock_entry.runtime_data = mock_data
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

        mock_data = MagicMock(spec=MysaData)
        mock_data.api = mock_api
        mock_data.coordinator = MagicMock()
        mock_entry.runtime_data = mock_data

        hass.config_entries = MagicMock()
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)

        result = await async_unload_entry(hass, mock_entry)

        assert result is True
        mock_api.stop_mqtt_listener.assert_called_once()
        assert result is True
        mock_api.stop_mqtt_listener.assert_called_once()
        # runtime_data should typically be cleared or handled by HA,
        # but our unload explicitly returns True.
        # We don't manually clear it in unload_entry usually, HA does cleanup.

    @pytest.mark.asyncio
    async def test_unload_entry_no_data(self, hass, mock_entry):
        """Test unload entry when no data exists."""
        from custom_components.mysa import async_unload_entry

        # No setup done implies no runtime_data or None
        mock_entry.runtime_data = None

        hass.config_entries = MagicMock()
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)

        result = await async_unload_entry(hass, mock_entry)

        assert result is True

    @pytest.mark.asyncio
    async def test_unload_entry_no_api(self, hass, mock_entry):
        """Test unload entry when API doesn't exist."""
        from custom_components.mysa import async_unload_entry

        mock_data = MagicMock(spec=MysaData)
        mock_data.api = None
        mock_entry.runtime_data = mock_data

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

        mock_data = MagicMock(spec=MysaData)
        mock_data.api = mock_api
        mock_entry.runtime_data = mock_data

        hass.config_entries = MagicMock()
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=False)

        result = await async_unload_entry(hass, mock_entry)

        assert result is False
        # Data should NOT be removed on failure
        assert result is False
        # runtime_data remains
        assert mock_entry.runtime_data is not None

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
