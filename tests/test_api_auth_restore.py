"""
Tests for MysaApi credential restoration logic.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from custom_components.mysa.mysa_api import MysaApi

@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = MagicMock()
    hass.async_add_executor_job = AsyncMock()
    return hass

@pytest.fixture
def mock_cognito():
    """Mock Cognito class imported in mysa_api."""
    with patch("custom_components.mysa.mysa_api.Cognito") as mock:
        yield mock

@pytest.fixture
def mock_login():
    """Mock login function imported in mysa_api."""
    with patch("custom_components.mysa.mysa_api.login") as mock:
        yield mock

@pytest.fixture
def mock_boto3():
    """Mock boto3 session."""
    with patch("custom_components.mysa.mysa_api.boto3") as mock:
        yield mock

@pytest.mark.asyncio
async def test_auth_restore_success(hass, mock_cognito, mock_boto3):
    """Test successful credential restoration from cache."""
    # Mock cached data
    cached_data = {
        "id_token": "valid_id_token",
        "refresh_token": "valid_refresh_token",
        "access_token": "valid_access_token",
        "user_id": "test_user_id"
    }

    # Setup mocks
    mock_cognito_instance = mock_cognito.return_value
    mock_cognito_instance.id_token = "valid_id_token"
    mock_cognito_instance.access_token = "valid_access_token"
    mock_cognito_instance.refresh_token = "valid_refresh_token"
    # verify_token returns None on success (no exception)
    mock_cognito_instance.verify_token.return_value = None 

    # Mock Store to return cached data
    with patch("custom_components.mysa.mysa_api.Store") as MockStore:
        store_instance = MockStore.return_value
        store_instance.async_load = AsyncMock(return_value=cached_data)
        store_instance.async_save = AsyncMock()
        
        # Instantiate API AFTER patching Store so it uses the mock
        api = MysaApi("user", "pass", hass)
        
        async def side_effect(func, *args):
            return func(*args)
        
        hass.async_add_executor_job.side_effect = side_effect

        await api.authenticate()

        # Verify Cognito was initialized
        assert mock_cognito.call_count >= 1
        
        # Check the calls to find the restoration attempt
        restoration_call_kwargs = None
        for call_args in mock_cognito.call_args_list:
            # call_args is (args, kwargs) tuple
            if "id_token" in call_args.kwargs:
                restoration_call_kwargs = call_args.kwargs
                break
        
        assert restoration_call_kwargs is not None, "Did not find Cognito initialization with id_token. Calls: {}".format(mock_cognito.call_args_list)
        assert restoration_call_kwargs["id_token"] == "valid_id_token"
        assert restoration_call_kwargs["refresh_token"] == "valid_refresh_token"
        
        # Verify verify_token was called
        mock_cognito_instance.verify_token.assert_called()

@pytest.mark.asyncio
async def test_auth_restore_refresh_needed(hass, mock_cognito, mock_boto3):
    """Test credential restoration requiring token refresh."""
    cached_data = {
        "id_token": "expired_id_token",
        "refresh_token": "valid_refresh_token",
    }

    mock_cognito_instance = mock_cognito.return_value
    mock_cognito_instance.id_token = "expired_id_token"
    mock_cognito_instance.refresh_token = "valid_refresh_token"
    
    # verify_token raises Exception on expiry
    mock_cognito_instance.verify_token.side_effect = Exception("Token expired")
    
    with patch("custom_components.mysa.mysa_api.Store") as MockStore:
        store_instance = MockStore.return_value
        store_instance.async_load = AsyncMock(return_value=cached_data)
        store_instance.async_save = AsyncMock()

        api = MysaApi("user", "pass", hass)
        
        async def side_effect(func, *args):
            return func(*args)
        hass.async_add_executor_job.side_effect = side_effect

        await api.authenticate()

        # Verify renew_access_token was called
        mock_cognito_instance.renew_access_token.assert_called_once()

@pytest.mark.asyncio
async def test_auth_restore_failure_fallback(hass, mock_cognito, mock_login, mock_boto3):
    """Test fallback to password login when restoration fails completely."""
    cached_data = {
        "id_token": "bad_token",
        "refresh_token": "bad_token",
    }
    
    # Restoration path uses mock_cognito
    mock_restored = mock_cognito.return_value
    mock_restored.id_token = "bad_token"
    mock_restored.refresh_token = "bad_token"
    # Verification fails
    mock_restored.verify_token.side_effect = Exception("Expired")
    # Refresh fails
    mock_restored.renew_access_token.side_effect = Exception("Refresh failed")
    
    with patch("custom_components.mysa.mysa_api.Store") as MockStore:
        store_instance = MockStore.return_value
        store_instance.async_load = AsyncMock(return_value=cached_data)
        store_instance.async_save = AsyncMock()

        api = MysaApi("user", "pass", hass)
        
        async def side_effect(func, *args):
            return func(*args)
        hass.async_add_executor_job.side_effect = side_effect

        await api.authenticate()
        
        # Verify restoration attempt happened on mock_cognito
        assert mock_cognito.call_count == 1
        _, kwargs = mock_cognito.call_args_list[0]
        assert "id_token" in kwargs
        
        # Verify fallback to login() happened
        mock_login.assert_called_once()
        args, _ = mock_login.call_args
        # login(username, password, bsess=...)
        assert args[0] == "user"
        assert args[1] == "pass"
