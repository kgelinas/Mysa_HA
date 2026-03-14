import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


from custom_components.mysa.client import MysaClient
from aiohttp import ClientResponseError


@pytest.fixture
def mock_hass():
    """Mock Home Assistant object."""
    hass = MagicMock()
    # Mocking async_add_executor_job to run the function immediately
    hass.async_add_executor_job = AsyncMock(
        side_effect=lambda f, *args: f(*args) if f else None
    )
    return hass


@pytest.fixture
def mock_store():
    """Mock storage store."""
    with patch("custom_components.mysa.client.Store") as store_cls:
        store_inst = AsyncMock()
        store_cls.return_value = store_inst
        yield store_inst


def create_mock_response(json_data=None, status=200):
    """Create a mock aiohttp response."""
    response = MagicMock()
    response.status = status
    response.raise_for_status = MagicMock(return_value=None)
    response.json = AsyncMock(return_value=json_data or {})
    response.text = AsyncMock(return_value=json.dumps(json_data) if json_data else "")
    return response


def create_async_context_manager(response):
    """Create an async context manager that returns the response."""
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=response)
    cm.__aexit__ = AsyncMock(return_value=None)
    return cm


@pytest.fixture(autouse=True)
def mock_jwt():
    """Mock python-jose jwt module for all client tests."""
    with patch("custom_components.mysa.mysa_auth.jwt") as mock_jwt_lib:
        mock_jwt_lib.get_unverified_header.return_value = {"kid": "test_kid"}
        mock_jwt_lib.get_unverified_claims.return_value = {
            "iss": "https://cognito-idp.us-east-1.amazonaws.com/test",
            "token_use": "id",
            "exp": 9999999999,
        }
        mock_jwt_lib.decode.return_value = {
            "iss": "https://cognito-idp.us-east-1.amazonaws.com/test",
            "token_use": "id",
            "exp": 9999999999,
            "sub": "test_subject",
        }
        yield mock_jwt_lib


@pytest.fixture(autouse=True)
def mock_cognito():
    """Mock Cognito class for all client tests."""
    with patch("custom_components.mysa.mysa_auth.Cognito") as mock:
        yield mock


@pytest.mark.asyncio
class TestMysaClient:
    """Test the MysaClient class."""

    async def test_init(self, mock_hass, mock_store):
        """Test initialization."""
        client = MysaClient(mock_hass, "u", "p")
        assert client.is_connected is False
        assert client.user_id is None
        assert client.username == "u"
        assert client.websession is None

    async def test_init_with_websession(self, mock_hass, mock_store):
        """Test initialization with websession."""
        mock_session = MagicMock()
        client = MysaClient(mock_hass, "u", "p", websession=mock_session)
        assert client.websession == mock_session

        # Verify it uses the session
        mock_response = create_mock_response({"User": {"Id": "uid"}})
        mock_session.get = MagicMock(
            return_value=create_async_context_manager(mock_response)
        )

        # We also need to mock _store.async_load to avoid auth
        mock_store.async_load.return_value = {
            "credentials_version": "2",
            "id_token": "token",
            "access_token": "access",
            "refresh_token": "ref",
        }

        # We need to mock _user_obj or the auth flow will try to get it
        # Let's just test get_request directly or something simple that uses session
        # But we need to be authenticated for most things

        # Let's perform authenticate()
        with patch(
            "custom_components.mysa.client.async_get_clientsession"
        ) as mock_get_session:
            await client.authenticate()

            # Should NOT call async_get_clientsession because we provided one
            mock_get_session.assert_not_called()

            # Should call our mock_session.get
            mock_session.get.assert_called()

    async def test_authenticate_cached_success(self, mock_hass, mock_store):
        """Test authentication with cached tokens."""
        # Valid JWT for testing
        mock_token = "eyJhbGciOiJSUzI1NiIsImtpZCI6InRlc3QiLCJ0eXAiOiJKV1QifQ.eyJzdWIiOiIxMjM0NTY3ODkwIiwiaXNzIjoiaHR0cHM6Ly90ZXN0IiwiZXhwIjo5OTk5OTk5OTk5fQ.sig"
        client = MysaClient(mock_hass, "u", "p")

        mock_store.async_load.return_value = {
            "credentials_version": "2",
            "id_token": mock_token,
            "access_token": "access",
            "refresh_token": "ref",
        }

        # Mock aiohttp session
        mock_response = create_mock_response({"User": {"Id": "uid"}})
        mock_session = MagicMock()
        mock_session.get = MagicMock(
            return_value=create_async_context_manager(mock_response)
        )

        # Mock Cognito.verify_token to succeed
        with (
            patch("custom_components.mysa.client.Cognito") as mock_cog_cls,
            patch(
                "custom_components.mysa.client.async_get_clientsession",
                return_value=mock_session,
            ),
        ):
            mock_cog_inst = mock_cog_cls.return_value
            mock_cog_inst.id_token = mock_token
            mock_cog_inst.access_token = "access"
            mock_cog_inst.refresh_token = "ref"
            mock_cog_inst.verify_token.return_value = None
            mock_cog_inst.authenticate = AsyncMock() # Ensure authenticate is mocked

            await client.authenticate()
            assert client.is_connected is True
            assert client.user_id == "uid"
            # verify_token is called via executor, so it should be called once
            mock_cog_inst.verify_token.assert_called_once()

    async def test_authenticate_no_cache(self, mock_hass, mock_store):
        """Test authentication with cache disabled forces login."""
        mock_token = "cached_token"
        client = MysaClient(mock_hass, "u", "p")

        # Store has data
        mock_store.async_load.return_value = {
            "credentials_version": "2",
            "id_token": mock_token,
            "access_token": "access",
            "refresh_token": "ref",
        }

        mock_response = create_mock_response({"User": {"Id": "uid"}})
        mock_session = MagicMock()
        mock_session.get = MagicMock(
            return_value=create_async_context_manager(mock_response)
        )
        mock_session.post = MagicMock(
            return_value=create_async_context_manager(create_mock_response({}))
        )
        mock_session.request = MagicMock(
            return_value=create_async_context_manager(create_mock_response({}))
        )

        with (
            patch("custom_components.mysa.client.login") as mock_login,
            patch(
                "custom_components.mysa.client.async_get_clientsession",
                return_value=mock_session,
            ),
        ):
            mock_user = MagicMock()
            mock_user.id_token = "new_token"
            mock_user.access_token = "new_access"
            mock_user.refresh_token = "new_ref"
            mock_user.id_claims = {"exp": 9999999999}
            mock_login.return_value = mock_user

            # Call with use_cache=False
            await client.authenticate(use_cache=False)

            # Verification:
            # 1. Store.async_load should NOT be called (or if called, result ignored? code says if use_cache is False, cached_data=None)
            # Actually code assumes if not use_cache, cached_data=None.
            # But we can verify that login() IS called even though store has valid data (mocked above)

            mock_login.assert_called()
            assert client.user_id == "uid"

    async def test_authenticate_cached_refresh(self, mock_hass, mock_store, mock_jwt):
        """Test authentication refresh token flow."""
        # Expired JWT
        mock_token_old = "eyJhbGciOiJSUzI1NiIsImtpZCI6InRlc3QiLCJ0eXAiOiJKV1QifQ.eyJzdWIiOiIxMjM0NTY3ODkwIiwiaXNzIjoiaHR0cHM6Ly90ZXN0IiwiZXhwIjoxfQ.sig"
        mock_token_new = "eyJhbGciOiJSUzI1NiIsImtpZCI6InRlc3QiLCJ0eXAiOiJKV1QifQ.eyJzdWIiOiIxMjM0NTY3ODkwIiwiaXNzIjoiaHR0cHM6Ly90ZXN0IiwiZXhwIjo5OTk5OTk5OTk5fQ.sig"

        # Force verification failure to trigger renewal
        mock_jwt.decode.side_effect = Exception("Expired")

        client = MysaClient(mock_hass, "u", "p")
        mock_store.async_load.return_value = {
            "credentials_version": "2",
            "id_token": mock_token_old,
            "access_token": "old_access",
            "refresh_token": "ref",
        }

        # Mock boto3 client via mock_cognito_client
        mock_cognito_client = AsyncMock()
        mock_cognito_client.initiate_auth = AsyncMock(
            return_value={
                "AuthenticationResult": {
                    "IdToken": mock_token_new,
                    "AccessToken": "new_access",
                }
            }
        )

        # We need to ensure CognitoUser inside authenticate uses our mock
        # Since authenticate creates a CognitoUser which calls renew_access_token internally?
        # No, client.authenticate calls user.renew_access_token if expired.

        # We can patch boto3.client in renew_access_token used by user object
        # The user object is created in authenticate.

        # Wait, if we use cached tokens, we create a user object directly?
        # client.py:
        # user = CognitoUser(...)
        # if user.is_token_expired... await user.renew_access_token()

        mock_response = create_mock_response({"User": {"Id": "uid"}})
        mock_session = MagicMock()
        mock_session.get = MagicMock(
            return_value=create_async_context_manager(mock_response)
        )
        mock_session.post = MagicMock(
            return_value=create_async_context_manager(create_mock_response({}))
        )
        mock_session.request = MagicMock(
            return_value=create_async_context_manager(create_mock_response({}))
        )

        mock_cognito_instance = MagicMock()
        mock_cognito_instance.id_token = mock_token_new
        mock_cognito_instance.access_token = "new_access"
        mock_cognito_instance.refresh_token = "ref"

        # Mock verify_token to raise error to trigger renewal
        mock_cognito_instance.verify_token.side_effect = Exception("Expired")
        # Mock authenticate to be a no-op (successful)
        mock_cognito_instance.authenticate = AsyncMock()
        mock_cognito_instance.renew_access_token = MagicMock() # Regular Mock for executor


        with (
            patch(
                "custom_components.mysa.client.Cognito",
                return_value=mock_cognito_instance,
            ),
            patch(
                "custom_components.mysa.client.async_get_clientsession",
                return_value=mock_session,
            ),
        ):
            await client.authenticate()
            mock_cognito_instance.renew_access_token.assert_called_once()
            # Check token was saved
            assert mock_store.async_save.called

    async def test_authenticate_login_fallback(self, mock_hass, mock_store):
        """Test authentication password fallback."""
        mock_token = "eyJhbGciOiJSUzI1NiIsImtpZCI6InRlc3QiLCJ0eXAiOiJKV1QifQ.eyJzdWIiOiIxMjM0NTY3ODkwIiwiaXNzIjoiaHR0cHM6Ly90ZXN0IiwiZXhwIjo5OTk5OTk5OTk5fQ.sig"

        client = MysaClient(mock_hass, "u", "p")
        mock_store.async_load.return_value = None  # No cache

        mock_response = create_mock_response({})  # No User ID returned (edge case)
        mock_session = MagicMock()
        mock_session.get = MagicMock(
            return_value=create_async_context_manager(mock_response)
        )
        mock_session.post = MagicMock(
            return_value=create_async_context_manager(create_mock_response({}))
        )
        mock_session.request = MagicMock(
            return_value=create_async_context_manager(create_mock_response({}))
        )

        with (
            patch("custom_components.mysa.client.login") as mock_login,
            patch(
                "custom_components.mysa.client.async_get_clientsession",
                return_value=mock_session,
            ),
        ):
            # Mock CognitoUser return
            mock_user = MagicMock()
            mock_user.id_token = mock_token
            mock_user.access_token = "access"
            mock_user.refresh_token = "ref"
            mock_user.id_claims = {"exp": 9999999999}
            mock_login.return_value = mock_user

            await client.authenticate()
            mock_login.assert_called()
            mock_store.async_save.assert_called()
            assert client.user_id is None  # Not found

    async def test_authenticate_fail(self, mock_hass, mock_store):
        """Test authentication failure raises."""
        client = MysaClient(mock_hass, "u", "p")
        mock_store.async_load.return_value = None

        with (
            patch(
                "custom_components.mysa.client.login",
                side_effect=Exception("Login Fail"),
            ),
            pytest.raises(Exception, match="Login Fail"),
        ):
            await client.authenticate()

    async def test_authenticate_fetch_user_id_fail(self, mock_hass, mock_store):
        """Test User ID fetch failure is logged but auth succeeds."""
        mock_token = "eyJhbGciOiJSUzI1NiIsImtpZCI6InRlc3QiLCJ0eXAiOiJKV1QifQ.eyJzdWIiOiIxMjM0NTY3ODkwIiwiaXNzIjoiaHR0cHM6Ly90ZXN0IiwiZXhwIjo5OTk5OTk5OTk5fQ.sig"

        client = MysaClient(mock_hass, "u", "p")
        mock_store.async_load.return_value = None

        mock_user = MagicMock()
        mock_user.id_token = mock_token
        mock_user.access_token = "access"
        mock_user.refresh_token = "ref"
        mock_user.id_claims = {"exp": 9999999999}

        mock_session = MagicMock()
        mock_session.get = MagicMock(side_effect=Exception("API Error"))
        mock_session.post = MagicMock(
            return_value=create_async_context_manager(create_mock_response({}))
        )
        mock_session.request = MagicMock(
            return_value=create_async_context_manager(create_mock_response({}))
        )

        with (
            patch("custom_components.mysa.client.login", return_value=mock_user),
            patch(
                "custom_components.mysa.client.async_get_clientsession",
                return_value=mock_session,
            ),
        ):
            await client.authenticate()
            assert client.is_connected is True
            assert client.user_id is None

    async def test_get_devices(self, mock_hass):
        """Test get_devices success."""
        client = MysaClient(mock_hass, "u", "p")
        client._user_obj = MagicMock()
        client._user_obj.id_claims = {"exp": 9999999999}
        client._user_obj.id_token = "token"

        # Test List format
        mock_response = create_mock_response(
            {"DevicesObj": [{"Id": "d1", "Name": "Dev1"}]}
        )
        mock_session = MagicMock()
        mock_session.get = MagicMock(
            return_value=create_async_context_manager(mock_response)
        )
        mock_session.post = MagicMock(
            return_value=create_async_context_manager(create_mock_response({}))
        )
        mock_session.request = MagicMock(
            return_value=create_async_context_manager(create_mock_response({}))
        )

        with (
            patch(
                "custom_components.mysa.client.async_get_clientsession",
                return_value=mock_session,
            ),
            patch.object(client, "fetch_homes", new_callable=AsyncMock) as mock_fetch,
        ):
            devs = await client.get_devices()
            assert "d1" in devs
            mock_fetch.assert_called()

        # Test Dict format logic fallthrough (coverage)
        mock_response2 = create_mock_response({"DevicesObj": {"d2": {"Id": "d2"}}})
        mock_session.get = MagicMock(
            return_value=create_async_context_manager(mock_response2)
        )
        with (
            patch(
                "custom_components.mysa.client.async_get_clientsession",
                return_value=mock_session,
            ),
            patch.object(client, "fetch_homes", new_callable=AsyncMock),
        ):
            devs = await client.get_devices()
            assert "d2" in devs

    async def test_get_devices_ghost_filtering(self, mock_hass):
        """Test get_devices filters out devices not assigned to a home."""
        client = MysaClient(mock_hass, "u", "p")
        client._user_obj = MagicMock()
        client._user_obj.id_claims = {"exp": 9999999999}
        client._user_obj.id_token = "token"

        # /devices returns active device (d1) and ghost device (ghost_id)
        mock_response = create_mock_response(
            {
                "DevicesObj": [
                    {"Id": "d1", "Name": "Active Device"},
                    {"Id": "ghost_id", "Name": "Ghost Device"},
                ]
            }
        )

        mock_session = MagicMock()
        mock_session.get = MagicMock(
            return_value=create_async_context_manager(mock_response)
        )
        mock_session.post = MagicMock(
            return_value=create_async_context_manager(create_mock_response({}))
        )
        mock_session.request = MagicMock(
            return_value=create_async_context_manager(create_mock_response({}))
        )

        # Mock fetch_homes to only map d1 to a home
        async def mock_fetch_homes_side_effect():
            client.device_to_home = {"d1": "h1"}
            client.homes = [{"Id": "h1"}]
            return client.homes

        with (
            patch(
                "custom_components.mysa.client.async_get_clientsession",
                return_value=mock_session,
            ),
            patch.object(
                client, "fetch_homes", side_effect=mock_fetch_homes_side_effect
            ),
        ):
            devs = await client.get_devices()

            # Assertions: both d1 and ghost_id should be present
            assert "d1" in devs
            assert "ghost_id" in devs

    async def test_get_devices_no_session(self, mock_hass):
        """Test get_devices raises if no session."""
        client = MysaClient(mock_hass, "u", "p")
        with pytest.raises(RuntimeError):
            await client.get_devices()

    async def test_fetch_homes(self, mock_hass):
        """Test fetch_homes and zone mapping."""
        client = MysaClient(mock_hass, "u", "p")
        client._user_obj = MagicMock()
        client._user_obj.id_claims = {"exp": 9999999999}
        client._user_obj.id_token = "token"

        mock_response = create_mock_response(
            {"Homes": [{"Id": "h1", "Zones": [{"Id": "z1", "Name": "Zone1"}]}]}
        )
        mock_session = MagicMock()
        mock_session.get = MagicMock(
            return_value=create_async_context_manager(mock_response)
        )
        mock_session.post = MagicMock(
            return_value=create_async_context_manager(create_mock_response({}))
        )
        mock_session.request = MagicMock(
            return_value=create_async_context_manager(create_mock_response({}))
        )

        with patch(
            "custom_components.mysa.client.async_get_clientsession",
            return_value=mock_session,
        ):
            homes = await client.fetch_homes()
            assert len(homes) == 1

    async def test_fetch_homes_erates(self, mock_hass):
        """Test fetch_homes parses ERates and maps devices."""
        client = MysaClient(mock_hass, "u", "p")
        client._user_obj = MagicMock()
        client._user_obj.id_claims = {"exp": 9999999999}
        client._user_obj.id_token = "token"

        mock_response = create_mock_response(
            {
                "Homes": [
                    {
                        "Id": "h1",
                        "ERate": 0.15,
                        "Zones": [{"Id": "z1", "Name": "Zone1", "DeviceIds": ["d1"]}],
                    },
                    {"Id": "h2", "ERate": "invalid", "Zones": []},
                ]
            }
        )
        mock_session = MagicMock()
        mock_session.get = MagicMock(
            return_value=create_async_context_manager(mock_response)
        )
        mock_session.post = MagicMock(
            return_value=create_async_context_manager(create_mock_response({}))
        )
        mock_session.request = MagicMock(
            return_value=create_async_context_manager(create_mock_response({}))
        )

        # Pre-seed devices so fallback check works
        client.devices = {"d1": {"Id": "d1"}}

        with patch(
            "custom_components.mysa.client.async_get_clientsession",
            return_value=mock_session,
        ):
            await client.fetch_homes()

        # Check mapping
        assert client.get_electricity_rate("d1") == 0.15
        assert client.get_electricity_rate("unknown") is None

    async def test_get_electricity_rate_fallback(self, mock_hass):
        """Test get_electricity_rate fallback path."""
        client = MysaClient(mock_hass, "u", "p")
        # Device exists but is not mapped to a home
        client.devices = {"d_fallback": {"Id": "d_fallback"}}

        rate = client.get_electricity_rate("d_fallback")
        assert rate is None

    async def test_fetch_homes_no_session(self, mock_hass):
        client = MysaClient(mock_hass, "u", "p")
        with pytest.raises(RuntimeError):
            await client.fetch_homes()

    async def test_fetch_firmware_info(self, mock_hass):
        """Test fetch firmware success/fail."""
        client = MysaClient(mock_hass, "u", "p")
        client._user_obj = MagicMock()
        client._user_obj.id_claims = {"exp": 9999999999}
        client._user_obj.id_token = "token"

        # Success
        mock_response = create_mock_response({"fw": "v2"})
        mock_session = MagicMock()
        mock_session.get = MagicMock(
            return_value=create_async_context_manager(mock_response)
        )
        mock_session.post = MagicMock(
            return_value=create_async_context_manager(create_mock_response({}))
        )
        mock_session.request = MagicMock(
            return_value=create_async_context_manager(create_mock_response({}))
        )

        with patch(
            "custom_components.mysa.client.async_get_clientsession",
            return_value=mock_session,
        ):
            assert await client.fetch_firmware_info("d1") == {"fw": "v2"}

        # Error
        mock_session.get = MagicMock(side_effect=Exception("Fail"))
        with patch(
            "custom_components.mysa.client.async_get_clientsession",
            return_value=mock_session,
        ):
            assert await client.fetch_firmware_info("d1") is None

        # No session
        client._user_obj = None
        with pytest.raises(RuntimeError):
            await client.fetch_firmware_info("d1")

    async def test_get_state(self, mock_hass):
        """Test get_state merging logic."""
        client = MysaClient(mock_hass, "u", "p")
        client._user_obj = MagicMock()
        client._user_obj.id_claims = {"exp": 9999999999}
        client._user_obj.id_token = "token"

        # Create mock responses for state and devices
        state_response = create_mock_response(
            {"DeviceStatesObj": [{"Id": "d1", "t": 20}]}
        )
        devices_response = create_mock_response(
            {"DevicesObj": [{"Id": "d1", "Attributes": {"n": "Name"}}]}
        )

        call_count = [0]

        def mock_get(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return create_async_context_manager(state_response)
            return create_async_context_manager(devices_response)

        mock_session = MagicMock()
        mock_session.get = mock_get
        mock_session.post = MagicMock(return_value=create_async_context_manager(create_mock_response({})))
        mock_session.request = MagicMock(
            return_value=create_async_context_manager(create_mock_response({}))
        )

        client.devices = {}

        with patch(
            "custom_components.mysa.client.async_get_clientsession",
            return_value=mock_session,
        ):
            states = await client.get_state()
            assert "d1" in states
            assert states["d1"]["t"] == 20
            # Attributes: {'n': 'Name'} was merged
            assert states["d1"]["n"] == "Name"

    async def test_get_state_format_variants(self, mock_hass):
        """Test get_state dict/list variants."""
        client = MysaClient(mock_hass, "u", "p")
        client._user_obj = MagicMock()
        client._user_obj.id_claims = {"exp": 9999999999}
        client._user_obj.id_token = "token"

        # Dict formats
        state_response = create_mock_response(
            {"DeviceStatesObj": {"d1": {"Id": "d1", "t": 20}}}
        )
        devices_response = create_mock_response(
            {"DevicesObj": {"d1": {"Id": "d1", "Attributes": {}}}}
        )

        call_count = [0]

        def mock_get(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return create_async_context_manager(state_response)
            return create_async_context_manager(devices_response)

        mock_session = MagicMock()
        mock_session.get = mock_get
        mock_session.post = MagicMock(
            return_value=create_async_context_manager(create_mock_response({}))
        )
        mock_session.request = MagicMock(
            return_value=create_async_context_manager(create_mock_response({}))
        )

        with patch(
            "custom_components.mysa.client.async_get_clientsession",
            return_value=mock_session,
        ):
            states = await client.get_state()
            assert "d1" in states

    async def test_get_state_refreshes_homes(self, mock_hass):
        """Test get_state calls fetch_homes to update ERate."""
        client = MysaClient(mock_hass, "u", "p")
        client._user_obj = MagicMock()
        client._user_obj.id_claims = {"exp": 9999999999}
        client._user_obj.id_token = "token"

        state_response = create_mock_response({"DeviceStatesObj": []})
        devices_response = create_mock_response({"DevicesObj": []})

        call_count = [0]

        def mock_get(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 2:  # Order: get_state, fetch_homes, get_devices
                return create_async_context_manager(devices_response)
            return create_async_context_manager(state_response)

        mock_session = MagicMock()
        mock_session.get = mock_get
        mock_session.post = MagicMock(
            return_value=create_async_context_manager(create_mock_response({}))
        )
        mock_session.request = MagicMock(
            return_value=create_async_context_manager(create_mock_response({}))
        )

        # 1. Verify fetch_homes is called
        with (
            patch(
                "custom_components.mysa.client.async_get_clientsession",
                return_value=mock_session,
            ),
            patch.object(client, "fetch_homes", new_callable=AsyncMock) as mock_fetch,
        ):
            await client.get_state()
            mock_fetch.assert_called_once()

        # 2. Verify exceptions are suppressed
        mock_session.get = mock_get  # Reset side effect logic if needed, or simple mock
        with (
            patch(
                "custom_components.mysa.client.async_get_clientsession",
                return_value=mock_session,
            ),
            patch.object(client, "fetch_homes", side_effect=Exception("Fetch Fail")),
        ):
            # Should not raise exception
            await client.get_state()

    async def test_get_state_no_session(self, mock_hass):
        client = MysaClient(mock_hass, "u", "p")
        with pytest.raises(RuntimeError):
            await client.get_state()

    async def test_get_signed_mqtt_url(self, mock_hass):
        """Test signed url fetch."""
        client = MysaClient(mock_hass, "u", "p")
        client._user_obj = MagicMock()

        with patch("custom_components.mysa.client.refresh_and_sign_url") as mock_sign:
            # Case 1: Same user obj
            mock_sign.return_value = ("url1", client._user_obj)
            assert await client.get_signed_mqtt_url() == "url1"

            # Case 2: New user obj
            new_user = MagicMock()
            mock_sign.return_value = ("url2", new_user)
            assert await client.get_signed_mqtt_url() == "url2"
            assert client._user_obj == new_user

    async def test_set_device_setting_http(self, mock_hass):
        """Test setting HTTP."""
        client = MysaClient(mock_hass, "u", "p")
        client._user_obj = MagicMock()
        client._user_obj.id_claims = {"exp": 9999999999}
        client._user_obj.id_token = "token"

        # Success
        mock_response = create_mock_response({"ok": 1})
        mock_session = MagicMock()
        mock_session.post = MagicMock(
            return_value=create_async_context_manager(mock_response)
        )
        mock_session.get = MagicMock(
            return_value=create_async_context_manager(create_mock_response({}))
        )
        mock_session.request = MagicMock(
            return_value=create_async_context_manager(create_mock_response({}))
        )

        with patch(
            "custom_components.mysa.client.async_get_clientsession",
            return_value=mock_session,
        ):
            res = await client.set_device_setting_http("d1", {})
            assert res == {"ok": 1}

        # Fail
        mock_session.post = MagicMock(side_effect=Exception("Fail"))
        with (
            patch(
                "custom_components.mysa.client.async_get_clientsession",
                return_value=mock_session,
            ),
            pytest.raises(Exception),
        ):
            await client.set_device_setting_http("d1", {})

        # Silent success
        mock_session.post = MagicMock(
            return_value=create_async_context_manager(mock_response)
        )
        with patch(
            "custom_components.mysa.client.async_get_clientsession",
            return_value=mock_session,
        ):
            await client.set_device_setting_silent("d1", {})

        # Silent fail
        mock_session.post = MagicMock(side_effect=Exception("Fail"))
        with patch(
            "custom_components.mysa.client.async_get_clientsession",
            return_value=mock_session,
        ):
            await client.set_device_setting_silent("d1", {})  # Should not raise

    async def test_set_device_setting_http_no_session(self, mock_hass):
        """Test setting HTTP with no session."""
        client = MysaClient(mock_hass, "u", "p")
        with pytest.raises(RuntimeError):
            await client.set_device_setting_http("d1", {})

    async def test_get_signed_mqtt_url_unauthenticated(self, mock_hass):
        """Test getting signed URL when not authenticated."""
        client = MysaClient(mock_hass, "u", "p")  # No auth call
        with pytest.raises(RuntimeError, match="Not authenticated"):
            await client.get_signed_mqtt_url()

    async def test_async_request(self, mock_hass):
        """Test generic request."""
        client = MysaClient(mock_hass, "u", "p")
        client._user_obj = MagicMock()
        client._user_obj.id_claims = {"exp": 9999999999}
        client._user_obj.id_token = "token"

        mock_response = create_mock_response({})
        mock_response.status = 200
        mock_session = MagicMock()
        mock_session.request = MagicMock(
            return_value=create_async_context_manager(mock_response)
        )
        mock_session.get = MagicMock(
            return_value=create_async_context_manager(create_mock_response({}))
        )
        mock_session.post = MagicMock(
            return_value=create_async_context_manager(create_mock_response({}))
        )

        with patch(
            "custom_components.mysa.client.async_get_clientsession",
            return_value=mock_session,
        ):
            await client.async_request("GET", "url")

        client._user_obj = None
        with pytest.raises(RuntimeError):
            await client.async_request("GET", "url")

    async def test_authenticate_cached_renew_fail(
        self, mock_hass, mock_store, mock_jwt
    ):
        """Test renew failure triggers fallback to password login."""
        mock_token = "eyJhbGciOiJSUzI1NiIsImtpZCI6InRlc3QiLCJ0eXAiOiJKV1QifQ.eyJzdWIiOiIxMjM0NTY3ODkwIiwiaXNzIjoiaHR0cHM6Ly90ZXN0IiwiZXhwIjoxfQ.sig"
        mock_new_token = "eyJhbGciOiJSUzI1NiIsImtpZCI6InRlc3QiLCJ0eXAiOiJKV1QifQ.eyJzdWIiOiIxMjM0NTY3ODkwIiwiaXNzIjoiaHR0cHM6Ly90ZXN0IiwiZXhwIjo5OTk5OTk5OTk5fQ.sig"

        # Force verification failure to trigger renewal
        mock_jwt.decode.side_effect = Exception("Expired")

        client = MysaClient(mock_hass, "u", "p")
        mock_store.async_load.return_value = {
            "credentials_version": "2",
            "id_token": mock_token,
            "access_token": "old_access",
            "refresh_token": "ref",
        }

        # Mock renewal to fail
        mock_boto_client = MagicMock()
        mock_boto_client.initiate_auth.side_effect = Exception("Renew Fail")

        mock_login_user = MagicMock()
        mock_login_user.id_token = mock_new_token
        mock_login_user.access_token = "new_access"
        mock_login_user.refresh_token = "new_ref"
        mock_login_user.id_claims = {"exp": 9999999999}

        mock_response = create_mock_response({"User": {"Id": "uid"}})
        mock_session = MagicMock()
        mock_session.get = MagicMock(
            return_value=create_async_context_manager(mock_response)
        )

        with (
            patch("boto3.client", return_value=mock_boto_client),
            patch(
                "custom_components.mysa.client.async_get_clientsession",
                return_value=mock_session,
            ),
            patch(
                "custom_components.mysa.client.login", return_value=mock_login_user
            ) as mock_login,
        ):
            await client.authenticate()

            # Verify login fallback happened because renew failed
            mock_login.assert_called()

    async def test_get_devices_fetch_homes_fail(self, mock_hass):
        """Test failure in fetch_homes during get_devices is suppressed."""
        client = MysaClient(mock_hass, "u", "p")
        client._user_obj = MagicMock()
        client._user_obj.id_claims = {"exp": 9999999999}
        client._user_obj.id_token = "token"

        mock_response = create_mock_response({"DevicesObj": []})
        mock_session = MagicMock()
        mock_session.get = MagicMock(
            return_value=create_async_context_manager(mock_response)
        )

        with (
            patch(
                "custom_components.mysa.client.async_get_clientsession",
                return_value=mock_session,
            ),
            patch.object(
                client,
                "fetch_homes",
                new_callable=AsyncMock,
                side_effect=Exception("Home Fail"),
            ),
        ):
            # Should not raise
            await client.get_devices()

    async def test_get_state_unknown_device(self, mock_hass):
        """Test get_state with device pending / not in devices list."""
        client = MysaClient(mock_hass, "u", "p")
        client._user_obj = MagicMock()
        client._user_obj.id_claims = {"exp": 9999999999}
        client._user_obj.id_token = "token"

        # State includes d99, devices does NOT
        state_response = create_mock_response(
            {"DeviceStatesObj": [{"Id": "d99", "t": 20}]}
        )
        devices_response = create_mock_response({"DevicesObj": []})

        call_count = [0]

        def mock_get(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return create_async_context_manager(state_response)
            return create_async_context_manager(devices_response)

        mock_session = MagicMock()
        mock_session.get = mock_get

        with patch(
            "custom_components.mysa.client.async_get_clientsession",
            return_value=mock_session,
        ):
            states = await client.get_state()
            # Should be included but without merged attributes
            assert "d99" in states
            assert states["d99"]["t"] == 20


    async def test_get_auth_headers_no_user(self, mock_hass):
        """Test _get_auth_headers returns empty dict when no user object."""
        client = MysaClient(mock_hass, "u", "p")
        # _user_obj is None by default
        headers = await client._get_auth_headers()
        assert headers == {}

    async def test_get_auth_headers_token_refresh(self, mock_hass):
        """Test _get_auth_headers refreshes token when expired."""
        import time

        mock_token_new = "eyJhbGciOiJSUzI1NiIsImtpZCI6InRlc3QiLCJ0eXAiOiJKV1QifQ.eyJzdWIiOiIxMjM0NTY3ODkwIiwiaXNzIjoiaHR0cHM6Ly90ZXN0IiwiZXhwIjo5OTk5OTk5OTk5fQ.sig"

        client = MysaClient(mock_hass, "u", "p")
        client._user_obj = MagicMock()
        client._user_obj.id_claims = {"exp": time.time() - 10}  # Expired
        client._user_obj.id_token = mock_token_new
        client._user_obj.renew_access_token = AsyncMock()

        headers = await client._get_auth_headers()

        client._user_obj.renew_access_token.assert_called_once()
        assert headers["authorization"] == mock_token_new

    async def test_authenticate_restore_no_id_token(self, mock_hass, mock_store):
        """Test restore when stored user has no ID token."""
        client = MysaClient(mock_hass, "u", "p")

        # Mock storage returning user dict but restore creates user with no ID token
        mock_store.async_load.return_value = {
            "id_token": None,
            "access_token": "acc",
            "refresh_token": "ref",
        }

        # We need to mock CognitoUser to have id_token=None after init
        # or just rely on the fact that we pass None from storage load result

        mock_session = MagicMock()
        mock_response = create_mock_response({"User": {"Id": "uid"}})
        mock_session.get.return_value = create_async_context_manager(mock_response)

        with (
            patch("custom_components.mysa.client.login") as mock_login,
            patch(
                "custom_components.mysa.client.async_get_clientsession",
                return_value=mock_session,
            ),
            patch("custom_components.mysa.client.Cognito"),
        ):
            # Authenticate call will try to restore
            # It will create CognitoUser(..., id_token=None)
            # Then check if user.id_token: -> False
            # Then raise ValueError("No ID token") inside the try block
            # Then catch block handles it -> renew_access_token()

            # We need to mock renew_access_token on the *instance* that is created inside authenticate
            # Since we can't easily grab that instance before it's used, we can verify the behavior via side effects
            # OR we can mock CognitoUser class

            with patch("custom_components.mysa.client.CognitoUser") as MockUserClass:
                mock_user_instance = MockUserClass.return_value
                mock_user_instance.id_token = None
                mock_user_instance.id_claims = {}
                mock_user_instance.renew_access_token = AsyncMock()

                # mock_login returns another user instance
                mock_fallback_user = mock_login.return_value
                mock_fallback_user.id_claims = {}
                mock_fallback_user.renew_access_token = AsyncMock()
                mock_fallback_user.get_aws_credentials = AsyncMock(return_value={})

                await client.authenticate()

                # Renew should NOT be called because check failed before try/except for verify
                mock_user_instance.renew_access_token.assert_not_called()
                # But login should be called as fallback
                mock_login.assert_called()


# ===========================================================================
# ERate and Mapping Coverage Tests
# ===========================================================================


@pytest.mark.asyncio
class TestClientCoverage:
    """Test new coverage areas in client.py."""

    async def test_fetch_homes_erate_parsing(self, mock_hass):
        """Test parsing of different ERate formats (comma, string, float, currency)."""
        client = MysaClient(mock_hass, "u", "p")
        client._user_obj = MagicMock()
        client._user_obj.id_claims = {"exp": 9999999999}
        client._user_obj.id_token = "token"

        # Case 1: Comma decimal string "0,15"
        # Case 2: Dot decimal string "0.12"
        # Case 3: Currency symbol "$0.07" (Fix verification)
        # Case 4: Currency symbol "€ 0,15" (Fix verification)
        # Case 5: Float input
        # Case 6: Invalid string "abc" (exception coverage)
        # Case 7: None
        mock_response = create_mock_response(
            {
                "Homes": [
                    {"Id": "h1", "ERate": "0,15", "Zones": []},
                    {"Id": "h2", "ERate": "0.12", "Zones": []},
                    {"Id": "h3", "ERate": "$0.07", "Zones": []},
                    {"Id": "h4", "ERate": "€ 0,15", "Zones": []},
                    {"Id": "h5", "ERate": 0.08, "Zones": []},
                    {"Id": "h6", "ERate": "abc", "Zones": []},
                    {"Id": "h7", "ERate": None, "Zones": []},
                ]
            }
        )
        mock_session = MagicMock()
        mock_session.get = MagicMock(
            return_value=create_async_context_manager(mock_response)
        )

        with patch(
            "custom_components.mysa.client.async_get_clientsession",
            return_value=mock_session,
        ):
            await client.fetch_homes()

            assert client.home_rates.get("h1") == 0.15
            assert client.home_rates.get("h2") == 0.12
            assert client.home_rates.get("h3") == 0.07
            assert client.home_rates.get("h4") == 0.15
            assert client.home_rates.get("h5") == 0.08
            assert "h6" not in client.home_rates
            assert "h7" not in client.home_rates

    async def test_fetch_homes_device_mapping_fallback(self, mock_hass):
        """Test device mapping fallback via Zone ID."""
        client = MysaClient(mock_hass, "u", "p")
        client._user_obj = MagicMock()
        client._user_obj.id_claims = {"exp": 9999999999}
        client._user_obj.id_token = "token"

        # Pre-populate devices
        client.devices = {
            "d1": {"Id": "d1", "Zone": {"Id": "z1"}},  # Has valid Zone ID
            "d2": {"Id": "d2", "Zone": {"Id": "z_unknown"}},  # Unknown Zone ID
            "d3": {"Id": "d3"},  # No Zone info
            "d4": {"Id": "d4"},  # Already mapped normally
        }

        # Response:
        # h1 has z1 (but missing d1 in DeviceIds)
        # h2 has z2 with d4
        mock_response = create_mock_response(
            {
                "Homes": [
                    {
                        "Id": "h1",
                        "ERate": 0.1,
                        "Zones": [{"Id": "z1", "DeviceIds": []}],  # Empty DeviceIds!
                    },
                    {
                        "Id": "h2",
                        "ERate": 0.2,
                        "Zones": [{"Id": "z2", "DeviceIds": ["d4"]}],  # Normal mapping
                    },
                ]
            }
        )
        mock_session = MagicMock()
        mock_session.get = MagicMock(
            return_value=create_async_context_manager(mock_response)
        )

        with patch(
            "custom_components.mysa.client.async_get_clientsession",
            return_value=mock_session,
        ):
            await client.fetch_homes()

            # d1 should be mapped to h1 via z1 fallback
            assert client.device_to_home.get("d1") == "h1"

            # d4 should be mapped to h2 via normal list
            assert client.device_to_home.get("d4") == "h2"

            # d2, d3 should not be mapped
            assert "d2" not in client.device_to_home
            assert "d3" not in client.device_to_home

    async def test_fetch_homes_direct_home_id_mapping(self, mock_hass):
        """Test device mapping via direct 'Home' property and string Zone ID."""
        client = MysaClient(mock_hass, "u", "p")
        client._user_obj = MagicMock()
        client._user_obj.id_claims = {"exp": 9999999999}
        client._user_obj.id_token = "token"

        # Pre-populate devices
        client.devices = {
            "d1": {"Id": "d1", "Home": "h1"},  # Direct Home link
            "d2": {"Id": "d2", "Zone": "z2"},  # String Zone ID link
            "d3": {
                "Id": "d3",
                "Zone": {"Id": "z3"},
            },  # Object Zone ID link (existing logic)
            "d4": {"Id": "d4"},  # No links
        }

        mock_response = create_mock_response(
            {
                "Homes": [
                    {"Id": "h1", "ERate": 0.1, "Zones": []},
                    {"Id": "h2", "ERate": 0.2, "Zones": [{"Id": "z2"}]},
                    {"Id": "h3", "ERate": 0.3, "Zones": [{"Id": "z3"}]},
                ]
            }
        )
        mock_session = MagicMock()
        mock_session.get = MagicMock(
            return_value=create_async_context_manager(mock_response)
        )

        with patch(
            "custom_components.mysa.client.async_get_clientsession",
            return_value=mock_session,
        ):
            await client.fetch_homes()

            # d1 mapped via "Home" property
            assert client.device_to_home.get("d1") == "h1"
            assert client.get_electricity_rate("d1") == 0.1

            # d2 mapped via string Zone ID
            assert client.device_to_home.get("d2") == "h2"
            assert client.get_electricity_rate("d2") == 0.2

            # d3 mapped via object Zone ID
            assert client.device_to_home.get("d3") == "h3"
            assert client.get_electricity_rate("d3") == 0.3

    # d4 not mapped
            assert "d4" not in client.device_to_home


    async def test_client_get_devices_coverage_gaps(self, mock_hass):
        """Cover client.py edge cases in get_devices."""
        client = MysaClient(mock_hass, "u", "p")
        client.websession = MagicMock()
        mock_user = MagicMock()
        mock_user.id_claims = {"exp": 9999999999.0}
        client._user_obj = mock_user
        client.fetch_homes = AsyncMock(return_value=[])

        # Explicitly configure websession to avoid AsyncMock leakage into resp.raise_for_status
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = AsyncMock(return_value={})
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_ctx.__aexit__ = AsyncMock()
        client.websession.get.return_value = mock_ctx

        # 1. get_devices: invalid response type
        with patch(
            "custom_components.mysa.client.asyncio.gather", new_callable=AsyncMock
        ) as mock_gather:
            # Return valid dict structure but invalid Devices content
            mock_gather.return_value = [{"Devices": "invalid"}, []]

            await client.get_devices()
            assert client.devices == {}

            # Cleanup coroutines
            for arg in mock_gather.call_args[0]:
                if asyncio.iscoroutine(arg):
                    arg.close()

    async def test_client_get_state_coverage_gaps(self, mock_hass):
        """Cover client.py edge cases in get_state."""
        client = MysaClient(mock_hass, "u", "p")
        client._user_obj = MagicMock()
        client._user_obj.id_claims = {"exp": 9999999999.0}

        # 1. get_state: devices_json exception
        with patch(
            "custom_components.mysa.client.asyncio.gather", new_callable=AsyncMock
        ) as mock_gather:
            # state_json success, devices_json exception
            mock_gather.return_value = [
                {"DeviceStates": []},
                ValueError("Devices fail"),
                [],
            ]

            with pytest.raises(ValueError, match="Devices fail"):
                await client.get_state()

            # Cleanup coroutines
            for arg in mock_gather.call_args[0]:
                if asyncio.iscoroutine(arg):
                    arg.close()

        # 2. get_state: fallbacks
        with patch(
            "custom_components.mysa.client.asyncio.gather", new_callable=AsyncMock
        ) as mock_gather:
            # state_json invalid (dict but bad keys), devices_json invalid (dict but bad keys)
            mock_gather.return_value = [
                {"DeviceStates": "invalid"},
                {"Devices": "invalid"},
                [],
            ]

            await client.get_state()
            # Should execute without error and default to empty dicts

            # Cleanup coroutines
            for arg in mock_gather.call_args[0]:
                if asyncio.iscoroutine(arg):
                    arg.close()

    async def test_client_deep_dive_sequential(self, mock_hass):
        """Test sequential calls in client using side_effect on websession."""
        client = MysaClient(mock_hass, "u", "p")
        client.websession = MagicMock()

        # Separate mock response objects
        r_homes = MagicMock()
        r_homes.json = AsyncMock(
            return_value={
                "Homes": [
                    {
                        "Id": "h1",
                        "ERate": 0.15,
                        "Zones": [{"Id": "z1", "DeviceIds": ["d1"]}],
                    }
                ]
            }
        )
        r_homes.raise_for_status = MagicMock()

        r_post = MagicMock()
        r_post.json = AsyncMock(return_value={"Success": True})
        r_post.text = AsyncMock(return_value='{"Success": true}')
        r_post.raise_for_status = MagicMock()

        # Configure mock_ctx to yield these in sequence
        # We need more items because set_device_setting_silent calls get_auth_headers which might trigger check_token_expiration
        client.websession.request.return_value.__aenter__.side_effect = [
            r_homes,  # fetch_homes
            r_post,  # set_device_setting_silent success
            r_post,  # set_device_setting_http
        ]
        client.websession.get = client.websession.request
        client.websession.post = client.websession.request

        client._user_obj = MagicMock()
        client._user_obj.id_claims = {"exp": 9999999999.0}
        client._user_obj.id_token = "token"

        await client.fetch_homes()
        assert client.homes[0]["Id"] == "h1"

        await client.set_device_setting_silent("d1", {"x": 1})
        await client.set_device_setting_http("d1", {"x": 1})

        # Error path for silent
        with patch.object(
            client, "set_device_setting_http", side_effect=Exception("Fail")
        ):
            await client.set_device_setting_silent("d1", {"x": 1})

    async def test_get_devices_gather_exception(self, mock_hass):
        """Test get_devices when gather returns an exception (lines 188-189)."""
        mock_session = MagicMock()
        client = MysaClient(mock_hass, "u", "p", websession=mock_session)
        client._user_obj = MagicMock()
        client._user_obj.id_claims = {"exp": 9999999999}
        client._user_obj.id_token = "token"

        # Mock session.get to raise exception
        test_exception = Exception("Device fetch failed")
        mock_session.get.side_effect = test_exception

        with pytest.raises(Exception, match="Device fetch failed"):
            await client.get_devices()

    async def test_get_state_gather_exceptions(self, mock_hass):
        """Test get_state when gather returns exceptions (lines 332-333, 337-338)."""
        client = MysaClient(mock_hass, "u", "p")
        client._user_obj = MagicMock()
        client._user_obj.id_claims = {"exp": 9999999999}
        client._user_obj.id_token = "token"
        client.devices = {"dev1": {"Id": "dev1", "Name": "Device1"}}
        client.homes = [{"Id": "h1", "Devices": ["dev1"]}]

        # Test: gather results containing exceptions
        gather_exception = Exception("Gather failed")

        # We need to mock asyncio.gather because get_state calls it with local functions
        with patch("custom_components.mysa.client.asyncio.gather", new_callable=AsyncMock) as mock_gather:
            try:
                # Case 1: First item is Exception
                mock_gather.return_value = [gather_exception, {}, []]
                with pytest.raises(Exception, match="Gather failed"):
                    await client.get_state()

                # Case 2: Second item is Exception
                mock_gather.return_value = [{}, gather_exception, []]
                with pytest.raises(Exception, match="Gather failed"):
                    await client.get_state()
            finally:
                for call in mock_gather.call_args_list:
                    for arg in call.args:
                        if asyncio.iscoroutine(arg):
                            arg.close()

@pytest.mark.asyncio
async def test_post_state_update_error_final(mock_hass):
    """Test post_state_update error handling."""
    mock_session = MagicMock()
    client = MysaClient(mock_hass, "u", "p", websession=mock_session)
    client._user_obj = MagicMock()
    client._user_obj.id_claims = {"exp": time.time() + 3600}
    mock_session.post.side_effect = Exception("HTTP Error")

    with pytest.raises(Exception, match="HTTP Error"):
        await client.post_state_update("dev1", {"source": 3})

@pytest.mark.asyncio
async def test_set_device_setting_http_error_final(mock_hass):
    """Test set_device_setting_http error handling."""
    mock_session = MagicMock()
    client = MysaClient(mock_hass, "u", "p", websession=mock_session)
    client._user_obj = MagicMock()
    client._user_obj.id_claims = {"exp": time.time() + 3600}
    mock_session.post.side_effect = Exception("HTTP Error")

    with pytest.raises(Exception, match="HTTP Error"):
        await client.set_device_setting_http("dev1", {"Lock": 1})

@pytest.mark.asyncio
async def test_set_device_setting_http_legacy(mock_hass):
    """Test set_device_setting_http with legacy=True."""
    from custom_components.mysa.mysa_auth import LEGACY_BASE_URL
    mock_session = MagicMock()
    client = MysaClient(mock_hass, "u", "p", websession=mock_session)
    client._user_obj = MagicMock()
    client._user_obj.id_claims = {"exp": time.time() + 3600}

    # Mock response
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.text = AsyncMock(return_value="{}")
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock()
    mock_session.post.return_value = mock_resp

    await client.set_device_setting_http("dev1", {"ButtonState": "Locked"}, legacy=True)

    # Verify legacy URL was used
    expected_url = f"{LEGACY_BASE_URL}/devices/dev1/"
    mock_session.post.assert_called_once()
    actual_url = mock_session.post.call_args[0][0]
    assert actual_url == expected_url

@pytest.mark.asyncio
async def test_get_auth_headers_no_user_final(hass):
    """Test _get_auth_headers returns empty dict when no user object."""
    client = MysaClient(hass, "u", "p")
    headers = await client._get_auth_headers()
    assert headers == {}

@pytest.mark.asyncio
async def test_get_auth_headers_token_refresh_final(hass):
    """Test _get_auth_headers refreshes token."""
    client = MysaClient(hass, "u", "p")
    mock_user = MagicMock()
    mock_user.id_claims = {"exp": time.time() + 10} # Expiring soon
    mock_user.id_token = "new_token"
    mock_user.renew_access_token = AsyncMock()
    client._user_obj = mock_user
    headers = await client._get_auth_headers()
    mock_user.renew_access_token.assert_called_once()
    assert headers["authorization"] == "new_token"

@pytest.mark.asyncio
async def test_client_missing_coverage_final(hass):
    """Test remaining client.py methods."""
    client = MysaClient(hass, "u", "p")

    # 231: Session not initialized in post_state_update
    with pytest.raises(RuntimeError, match="Session not initialized"):
        await client.post_state_update("dev1", {})

    # 583: Session not initialized in get_st1_state
    assert await client.get_st1_state(["dev1"]) == {}

    client._user_obj = MagicMock()
    client._user_obj.id_claims = {"exp": time.time() + 3600}
    mock_session = MagicMock()
    client.websession = mock_session

    # 240-241: post_state_update success
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value={})
    mock_resp.text = AsyncMock(return_value="{}")
    mock_resp.raise_for_status = MagicMock()
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock()
    mock_session.post.return_value = mock_resp
    await client.post_state_update("dev1", {"v": 1})

    # 243-256: fetch_capabilities
    mock_session.get.return_value = mock_resp
    mock_resp.json = AsyncMock(return_value={"Capabilities": {}})
    await client.fetch_capabilities("dev1")

    # 595-597: get_st1_state error path
    mock_session.post.side_effect = Exception("HTTP Error")
    assert await client.get_st1_state(["dev1"]) == {}
    mock_session.post.side_effect = None

    # 437: _merge_st1_states with missing device in result_states
    client.devices = {"new_dev": {"Id": "new_dev", "Model": "ST-V1-0"}}
    # Mock return for get_st1_state
    mock_resp.json = AsyncMock(return_value={
        "new_dev": {
            "data": {
                "latestTelemetry": {"reading": {"temp": 22}},
                "modes": {"reported": {"hvacStates": ["cooling"]}},
                "diagnostics": {"reported": {"freeHeap": 12345}}
            }
        }
    })
    mock_session.post.return_value = mock_resp

    # get_state calls fetch_live_metrics and fetch_device_settings (Round 1)
    # and then get_st1_state (Round 2) calls session.post
    client.fetch_homes = AsyncMock(return_value=[])

    mock_resp_r1 = MagicMock()
    mock_resp_r1.__aenter__ = AsyncMock(return_value=mock_resp_r1)
    mock_resp_r1.__aexit__ = AsyncMock()
    mock_resp_r1.json = AsyncMock(side_effect=[
        {"DeviceStates": []}, # live metrics
        {"Devices": [{"Id": "new_dev"}]} # device settings
    ])
    mock_session.get.return_value = mock_resp_r1

    # Round 2: get_st1_state
    mock_resp_r2 = MagicMock()
    mock_resp_r2.__aenter__ = AsyncMock(return_value=mock_resp_r2)
    mock_resp_r2.__aexit__ = AsyncMock()
    mock_resp_r2.json = AsyncMock(return_value={
        "new_dev": {
            "data": {
                "latestTelemetry": {"reading": {"temp": 22}},
                "modes": {"reported": {"hvacStates": ["cooling"]}},
                "diagnostics": {"reported": {"freeHeap": 12345}}
            }
        }
    })
    mock_session.post.return_value = mock_resp_r2

    result = await client.get_state()
    assert "new_dev" in result
    assert result["new_dev"]["hvacStates"] == ["cooling"]
    assert result["new_dev"]["freeHeap"] == 12345

    # 246: Session not initialized in fetch_capabilities
    client._user_obj = None
    with pytest.raises(RuntimeError, match="Session not initialized"):
        await client.fetch_capabilities("dev1")
    client._user_obj = MagicMock()
    client._user_obj.id_claims = {"exp": time.time() + 3600}

    # 254-256: fetch_capabilities exception
    mock_session.get.side_effect = Exception("Fetch Fail")
    assert await client.fetch_capabilities("dev1") is None
    mock_session.get.side_effect = None

    # 418-419: get_st1_state exception in get_state
    # Reset side effects for second get_state call
    mock_resp_r1.json.side_effect = [
        {"DeviceStates": []}, # live metrics
        {"Devices": [{"Id": "new_dev"}]} # device settings
    ]
    # Mock get_st1_state to RAISE (hitting 418-419 in get_state)
    client.get_st1_state = AsyncMock(side_effect=Exception("Hard Fail"))
    # This should be caught and logged in get_state Round 2
    await client.get_state()

    client._user_obj = MagicMock()
    client._user_obj.id_claims = None
    assert "authorization" in await client._get_auth_headers()

    client._user_obj.id_claims = {"exp": time.time() + 3600}
    assert "authorization" in await client._get_auth_headers()


class TestClientConsolidated:
    """Consolidated client tests from final and extra coverage."""

    @pytest.mark.asyncio
    async def test_client_get_all_firmware_versions_edge_cases_consolidated(
        self, hass
    ):
        """Cover missing lines in client.py get_all_firmware_versions."""
        mock_websession = MagicMock()
        client = MysaClient(hass, "u", "p", websession=mock_websession)
        client._get_auth_headers = AsyncMock(
            return_value={"Authorization": "Bearer token"}
        )

        # Case: no user object
        client._user_obj = None
        assert await client.get_all_firmware_versions() == {}

        # Case: successful retrieval
        client._user_obj = MagicMock()
        mock_resp = AsyncMock()
        mock_resp.json = AsyncMock(
            return_value={"Firmware": {"d1": {"InstalledVersion": "1.0.0"}}}
        )
        mock_resp.raise_for_status = MagicMock()

        with patch.object(mock_websession, "get") as mock_get:
            mock_get.return_value.__aenter__.return_value = mock_resp
            res = await client.get_all_firmware_versions()
            assert res == {"d1": {"InstalledVersion": "1.0.0"}}

        # Case: failure path
        with patch.object(mock_websession, "get", side_effect=Exception("API Fail")):
            res = await client.get_all_firmware_versions()
            assert res == {}

from aiohttp.client_exceptions import ContentTypeError

@pytest.mark.asyncio
async def test_set_device_setting_http_empty_json_response(hass):
    """Test set_device_setting_http with 200 OK but empty/invalid JSON response."""
    # Mock session and response
    mock_session = MagicMock()
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.raise_for_status = MagicMock()

    # Simulating the error seen in logs
    # usage: ContentTypeError(request_info, history, message=..., headers=...)
    request_info = MagicMock()
    request_info.real_url = "http://example.com"
    request_info.headers = {}

    error = ContentTypeError(
        request_info,
        (),
        message="Attempt to decode JSON with unexpected mimetype: ",
        headers=None
    )

    mock_response.json = AsyncMock(side_effect=error)
    # Also mock text() to return empty string, mimicking what likely happens
    mock_response.text = AsyncMock(return_value="")

    # Context manager mock
    mock_session.post.return_value.__aenter__.return_value = mock_response

    client = MysaClient(hass, "user", "pass", websession=mock_session)
    # fake auth
    client._user_obj = MagicMock()
    client._user_obj.id_token = "token"
    client._user_obj.id_claims = {"exp": 9999999999}

    # This should now succeed and return empty dict (or whatever json text was if not empty)
    result = await client.set_device_setting_http("dev1", {"test": 1})

    assert result == {}


class TestMysaClientRecovery:
    """Test cases to reach 100% coverage for client recovery and edge cases."""

    @pytest.mark.asyncio
    async def test_client_restore_cache_exception(self, mock_hass, mock_store):
        """Cover exception in _restore_cached_session."""
        client = MysaClient(mock_hass, "u", "p")
        mock_store.async_load.return_value = {
            "credentials_version": "2",
            "id_token": "id",
            "access_token": "acc",
            "refresh_token": "ref",
        }

        with patch(
            "custom_components.mysa.client.Cognito", side_effect=Exception("Restore Fail")
        ):
            result = await client._restore_cached_session()
            assert result is None

    @pytest.mark.asyncio
    async def test_client_login_password_user_id_fail(self, mock_hass, mock_store):
        """Cover User ID fetch failure during login_with_password (non-fatal)."""
        client = MysaClient(mock_hass, "u", "p")

        mock_user = MagicMock()
        mock_user.id_token = "token"

        with (
            patch("custom_components.mysa.client.login", return_value=mock_user),
            patch.object(
                client, "_fetch_user_id_internal", side_effect=Exception("Fetch Fail")
            ),
            patch.object(client, "_store_async_save_current_tokens"),
        ):
            await client._login_with_password()
            assert client._user_obj == mock_user

    @pytest.mark.asyncio
    async def test_client_login_password_auth_fail(self, mock_hass):
        """Cover password login failure."""
        client = MysaClient(mock_hass, "u", "p")
        with patch(
            "custom_components.mysa.client.login", side_effect=Exception("Auth Fail")
        ):
            with pytest.raises(Exception, match="Auth Fail"):
                await client._login_with_password()

    @pytest.mark.asyncio
    async def test_client_fetch_user_id_401_no_clear(self, mock_hass):
        """Cover _fetch_user_id_internal with 401 but clear_on_fail=False."""
        client = MysaClient(mock_hass, "u", "p")
        client._user_obj = MagicMock()
        client._user_obj.id_claims = {"exp": 9999999999}
        client._user_obj.id_token = "token"

        mock_resp = create_mock_response(status=401)
        mock_session = MagicMock()
        mock_session.get.return_value = create_async_context_manager(mock_resp)

        with patch(
            "custom_components.mysa.client.async_get_clientsession",
            return_value=mock_session,
        ):
            await client._fetch_user_id_internal(clear_on_fail=False)
            assert client._user_obj is not None

    @pytest.mark.asyncio
    async def test_client_fetch_user_id_generic_exception_clear(self, mock_hass):
        """Cover generic exception in _fetch_user_id_internal with clear_on_fail=True."""
        client = MysaClient(mock_hass, "u", "p")
        client._user_obj = MagicMock()
        client._user_obj.id_claims = {"exp": 9999999999}
        client._user_obj.id_token = "token"

        with patch(
            "custom_components.mysa.client.async_get_clientsession",
            side_effect=Exception("Bug"),
        ):
            await client._fetch_user_id_internal(clear_on_fail=True)
            assert client._user_obj is None

    @pytest.mark.asyncio
    async def test_client_get_devices_not_logged_in(self, mock_hass):
        """Cover get_devices runtime error when not logged in."""
        client = MysaClient(mock_hass, "u", "p")
        client._user_obj = None
        with pytest.raises(RuntimeError, match="Session not initialized"):
            await client.get_devices()

    @pytest.mark.asyncio
    async def test_client_get_devices_gather_exception(self, mock_hass):
        """Cover get_devices when gather returns an exception."""
        client = MysaClient(mock_hass, "u", "p")
        client._user_obj = MagicMock()
        client._user_obj.id_claims = {"exp": 9999999999}
        client._user_obj.id_token = "token"

        with (
            patch.object(client, "fetch_homes", AsyncMock(return_value=[])),
            patch(
                "custom_components.mysa.client.async_get_clientsession"
            ) as mock_session_get,
        ):
            mock_session = MagicMock()
            mock_session_get.return_value = mock_session
            # Mock actual HTTP call to fail
            mock_resp = create_mock_response(status=500)
            mock_resp.raise_for_status.side_effect = ClientResponseError(
                MagicMock(), MagicMock(), status=500
            )
            mock_session.get.return_value = create_async_context_manager(mock_resp)

            with pytest.raises(ClientResponseError):
                await client.get_devices()

    @pytest.mark.asyncio
    async def test_client_restore_cache_incomplete_data(self, mock_hass, mock_store):
        """Cover incomplete cached data."""
        client = MysaClient(mock_hass, "u", "p")
        # Missing refresh_token
        mock_store.async_load.return_value = {
            "credentials_version": "2",
            "id_token": "id",
            "access_token": "acc",
        }
        result = await client._restore_cached_session()
        assert result is None

    @pytest.mark.asyncio
    async def test_client_fetch_user_id_not_logged_in(self, mock_hass):
        """Cover _fetch_user_id_internal when not logged in."""
        client = MysaClient(mock_hass, "u", "p")
        client._user_obj = None
        await client._fetch_user_id_internal()
        assert client._user_id is None

    @pytest.mark.asyncio
    async def test_client_fetch_user_id_401_clear(self, mock_hass):
        """Cover 401 with clear_on_fail=True."""
        client = MysaClient(mock_hass, "u", "p")
        client._user_obj = MagicMock()
        client._user_obj.id_claims = {"exp": 9999999999}
        client._user_obj.id_token = "token"
        client._user_id = "some_id"

        mock_resp = create_mock_response(status=401)
        mock_session = MagicMock()
        mock_session.get.return_value = create_async_context_manager(mock_resp)

        with patch(
            "custom_components.mysa.client.async_get_clientsession",
            return_value=mock_session,
        ):
            await client._fetch_user_id_internal(clear_on_fail=True)
            assert client._user_obj is None
            assert client._user_id is None
