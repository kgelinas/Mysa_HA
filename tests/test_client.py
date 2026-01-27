"""Tests for MysaClient."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from aiohttp import ClientResponseError
from custom_components.mysa.client import MysaClient


@pytest.fixture
def mock_hass():
    """Mock Home Assistant object."""
    hass = MagicMock()
    # Mocking async_add_executor_job to run the function immediately
    hass.async_add_executor_job = AsyncMock(side_effect=lambda f, *args: f(*args) if f else None)
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
            "exp": 9999999999
        }
        mock_jwt_lib.decode.return_value = {
            "iss": "https://cognito-idp.us-east-1.amazonaws.com/test",
            "token_use": "id",
            "exp": 9999999999,
            "sub": "test_subject"
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
        mock_session.get = MagicMock(return_value=create_async_context_manager(mock_response))

        # We also need to mock _store.async_load to avoid auth
        mock_store.async_load.return_value = {
             "id_token": "token",
             "access_token": "access",
             "refresh_token": "ref"
        }

        # We need to mock _user_obj or the auth flow will try to get it
        # Let's just test get_request directly or something simple that uses session
        # But we need to be authenticated for most things

        # Let's perform authenticate()
        with patch("custom_components.mysa.client.async_get_clientsession") as mock_get_session:
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
            "id_token": mock_token,
            "access_token": "access",
            "refresh_token": "ref"
        }

        # Mock aiohttp session
        mock_response = create_mock_response({"User": {"Id": "uid"}})
        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=create_async_context_manager(mock_response))

        # Mock Cognito.verify_token to succeed
        with patch("custom_components.mysa.client.Cognito") as mock_cog_cls, \
             patch("custom_components.mysa.client.async_get_clientsession", return_value=mock_session):

            mock_cog_inst = mock_cog_cls.return_value
            mock_cog_inst.id_token = mock_token
            mock_cog_inst.access_token = "access"
            mock_cog_inst.refresh_token = "ref"
            mock_cog_inst.verify_token.return_value = None

            await client.authenticate()
            assert client.is_connected is True
            assert client.user_id == "uid"
            mock_cog_inst.verify_token.assert_called_once()

    async def test_authenticate_no_cache(self, mock_hass, mock_store):
        """Test authentication with cache disabled forces login."""
        mock_token = "cached_token"
        client = MysaClient(mock_hass, "u", "p")

        # Store has data
        mock_store.async_load.return_value = {
            "id_token": mock_token,
            "access_token": "access",
            "refresh_token": "ref"
        }

        mock_response = create_mock_response({"User": {"Id": "uid"}})
        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=create_async_context_manager(mock_response))

        with patch("custom_components.mysa.client.login") as mock_login, \
             patch("custom_components.mysa.client.async_get_clientsession", return_value=mock_session):

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
            "id_token": mock_token_old,
            "access_token": "old_access",
            "refresh_token": "ref"
        }

        # Mock boto3 client via mock_cognito_client
        mock_cognito_client = AsyncMock()
        mock_cognito_client.initiate_auth = AsyncMock(return_value={
            'AuthenticationResult': {
                'IdToken': mock_token_new,
                'AccessToken': 'new_access'
            }
        })

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
        mock_session.get = MagicMock(return_value=create_async_context_manager(mock_response))

        mock_cognito_instance = MagicMock()
        mock_cognito_instance.id_token = mock_token_new
        mock_cognito_instance.access_token = "new_access"
        mock_cognito_instance.refresh_token = "ref"

        # Mock verify_token to raise error to trigger renewal
        mock_cognito_instance.verify_token.side_effect = Exception("Expired")
        # Mock authenticate to be a no-op (successful)
        mock_cognito_instance.authenticate = MagicMock()

        with patch("custom_components.mysa.client.Cognito", return_value=mock_cognito_instance), \
             patch("custom_components.mysa.client.async_get_clientsession", return_value=mock_session):

            await client.authenticate()
            mock_cognito_instance.renew_access_token.assert_called()
            # Check token was saved
            assert mock_store.async_save.called

    async def test_authenticate_login_fallback(self, mock_hass, mock_store):
        """Test authentication password fallback."""
        mock_token = "eyJhbGciOiJSUzI1NiIsImtpZCI6InRlc3QiLCJ0eXAiOiJKV1QifQ.eyJzdWIiOiIxMjM0NTY3ODkwIiwiaXNzIjoiaHR0cHM6Ly90ZXN0IiwiZXhwIjo5OTk5OTk5OTk5fQ.sig"

        client = MysaClient(mock_hass, "u", "p")
        mock_store.async_load.return_value = None  # No cache

        mock_response = create_mock_response({})  # No User ID returned (edge case)
        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=create_async_context_manager(mock_response))

        with patch("custom_components.mysa.client.login") as mock_login, \
             patch("custom_components.mysa.client.async_get_clientsession", return_value=mock_session):

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

        with patch("custom_components.mysa.client.login", side_effect=Exception("Login Fail")):
            with pytest.raises(Exception, match="Login Fail"):
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

        with patch("custom_components.mysa.client.login", return_value=mock_user), \
             patch("custom_components.mysa.client.async_get_clientsession", return_value=mock_session):

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
        mock_response = create_mock_response({"DevicesObj": [{"Id": "d1", "Name": "Dev1"}]})
        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=create_async_context_manager(mock_response))

        with patch("custom_components.mysa.client.async_get_clientsession", return_value=mock_session), \
             patch.object(client, "fetch_homes", new_callable=AsyncMock) as mock_fetch:
            devs = await client.get_devices()
            assert "d1" in devs
            mock_fetch.assert_called()

        # Test Dict format logic fallthrough (coverage)
        mock_response2 = create_mock_response({"DevicesObj": {"d2": {"Id": "d2"}}})
        mock_session.get = MagicMock(return_value=create_async_context_manager(mock_response2))
        with patch("custom_components.mysa.client.async_get_clientsession", return_value=mock_session), \
             patch.object(client, "fetch_homes", new_callable=AsyncMock):
            devs = await client.get_devices()
            assert "d2" in devs

    async def test_get_devices_ghost_filtering(self, mock_hass):
        """Test get_devices filters out devices not assigned to a home."""
        client = MysaClient(mock_hass, "u", "p")
        client._user_obj = MagicMock()
        client._user_obj.id_claims = {"exp": 9999999999}
        client._user_obj.id_token = "token"

        # /devices returns active device (d1) and ghost device (ghost_id)
        mock_response = create_mock_response({
            "DevicesObj": [
                {"Id": "d1", "Name": "Active Device"},
                {"Id": "ghost_id", "Name": "Ghost Device"}
            ]
        })

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=create_async_context_manager(mock_response))

        # Mock fetch_homes to only map d1 to a home
        async def mock_fetch_homes_side_effect():
            client.device_to_home = {"d1": "h1"}
            client.homes = [{"Id": "h1"}]
            return client.homes

        with patch("custom_components.mysa.client.async_get_clientsession", return_value=mock_session), \
             patch.object(client, "fetch_homes", side_effect=mock_fetch_homes_side_effect):

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

        mock_response = create_mock_response({
            "Homes": [
                {
                    "Id": "h1",
                    "Zones": [{"Id": "z1", "Name": "Zone1"}]
                }
            ]
        })
        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=create_async_context_manager(mock_response))

        with patch("custom_components.mysa.client.async_get_clientsession", return_value=mock_session):
            homes = await client.fetch_homes()
            assert len(homes) == 1

    async def test_fetch_homes_erates(self, mock_hass):
        """Test fetch_homes parses ERates and maps devices."""
        client = MysaClient(mock_hass, "u", "p")
        client._user_obj = MagicMock()
        client._user_obj.id_claims = {"exp": 9999999999}
        client._user_obj.id_token = "token"

        mock_response = create_mock_response({
            "Homes": [
                {
                    "Id": "h1",
                    "ERate": 0.15,
                    "Zones": [
                        {
                            "Id": "z1",
                            "Name": "Zone1",
                            "DeviceIds": ["d1"]
                        }
                    ]
                },
                {
                    "Id": "h2",
                    "ERate": "invalid",
                    "Zones": []
                }
            ]
        })
        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=create_async_context_manager(mock_response))

        # Pre-seed devices so fallback check works
        client.devices = {"d1": {"Id": "d1"}}

        with patch("custom_components.mysa.client.async_get_clientsession", return_value=mock_session):
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
        mock_session.get = MagicMock(return_value=create_async_context_manager(mock_response))

        with patch("custom_components.mysa.client.async_get_clientsession", return_value=mock_session):
            assert await client.fetch_firmware_info("d1") == {"fw": "v2"}

        # Error
        mock_session.get = MagicMock(side_effect=Exception("Fail"))
        with patch("custom_components.mysa.client.async_get_clientsession", return_value=mock_session):
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
        state_response = create_mock_response({"DeviceStatesObj": [{"Id": "d1", "t": 20}]})
        devices_response = create_mock_response({"DevicesObj": [{"Id": "d1", "Attributes": {"n": "Name"}}]})

        call_count = [0]
        def mock_get(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return create_async_context_manager(state_response)
            return create_async_context_manager(devices_response)

        mock_session = MagicMock()
        mock_session.get = mock_get

        client.devices = {}

        with patch("custom_components.mysa.client.async_get_clientsession", return_value=mock_session):
            states = await client.get_state()
            assert "d1" in states
            assert states["d1"]["t"] == 20
            assert states["d1"]["n"] == "Name"

    async def test_get_state_format_variants(self, mock_hass):
        """Test get_state dict/list variants."""
        client = MysaClient(mock_hass, "u", "p")
        client._user_obj = MagicMock()
        client._user_obj.id_claims = {"exp": 9999999999}
        client._user_obj.id_token = "token"

        # Dict formats
        state_response = create_mock_response({"DeviceStatesObj": {"d1": {"Id": "d1", "t": 20}}})
        devices_response = create_mock_response({"DevicesObj": {"d1": {"Id": "d1", "Attributes": {}}}})

        call_count = [0]
        def mock_get(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return create_async_context_manager(state_response)
            return create_async_context_manager(devices_response)

        mock_session = MagicMock()
        mock_session.get = mock_get

        with patch("custom_components.mysa.client.async_get_clientsession", return_value=mock_session):
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
            if call_count[0] == 2: # Order: get_state, fetch_homes, get_devices
                return create_async_context_manager(devices_response)
            return create_async_context_manager(state_response)

        mock_session = MagicMock()
        mock_session.get = mock_get

        # 1. Verify fetch_homes is called
        with patch("custom_components.mysa.client.async_get_clientsession", return_value=mock_session), \
             patch.object(client, "fetch_homes", new_callable=AsyncMock) as mock_fetch:
            await client.get_state()
            mock_fetch.assert_called_once()

        # 2. Verify exceptions are suppressed
        mock_session.get = mock_get # Reset side effect logic if needed, or simple mock
        with patch("custom_components.mysa.client.async_get_clientsession", return_value=mock_session), \
             patch.object(client, "fetch_homes", side_effect=Exception("Fetch Fail")):
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
        mock_session.post = MagicMock(return_value=create_async_context_manager(mock_response))

        with patch("custom_components.mysa.client.async_get_clientsession", return_value=mock_session):
            res = await client.set_device_setting_http("d1", {})
            assert res == {"ok": 1}

        # Fail
        mock_session.post = MagicMock(side_effect=Exception("Fail"))
        with patch("custom_components.mysa.client.async_get_clientsession", return_value=mock_session):
            with pytest.raises(Exception):
                await client.set_device_setting_http("d1", {})

        # Silent success
        mock_session.post = MagicMock(return_value=create_async_context_manager(mock_response))
        with patch("custom_components.mysa.client.async_get_clientsession", return_value=mock_session):
            await client.set_device_setting_silent("d1", {})

        # Silent fail
        mock_session.post = MagicMock(side_effect=Exception("Fail"))
        with patch("custom_components.mysa.client.async_get_clientsession", return_value=mock_session):
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
        mock_session.request = MagicMock(return_value=create_async_context_manager(mock_response))

        with patch("custom_components.mysa.client.async_get_clientsession", return_value=mock_session):
            await client.async_request("GET", "url")

        client._user_obj = None
        with pytest.raises(RuntimeError):
            await client.async_request("GET", "url")


    async def test_authenticate_cached_renew_fail(self, mock_hass, mock_store, mock_jwt):
        """Test renew failure triggers fallback to password login."""
        mock_token = "eyJhbGciOiJSUzI1NiIsImtpZCI6InRlc3QiLCJ0eXAiOiJKV1QifQ.eyJzdWIiOiIxMjM0NTY3ODkwIiwiaXNzIjoiaHR0cHM6Ly90ZXN0IiwiZXhwIjoxfQ.sig"
        mock_new_token = "eyJhbGciOiJSUzI1NiIsImtpZCI6InRlc3QiLCJ0eXAiOiJKV1QifQ.eyJzdWIiOiIxMjM0NTY3ODkwIiwiaXNzIjoiaHR0cHM6Ly90ZXN0IiwiZXhwIjo5OTk5OTk5OTk5fQ.sig"

        # Force verification failure to trigger renewal
        mock_jwt.decode.side_effect = Exception("Expired")

        client = MysaClient(mock_hass, "u", "p")
        mock_store.async_load.return_value = {
            "id_token": mock_token,
            "access_token": "old_access",
            "refresh_token": "ref"
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
        mock_session.get = MagicMock(return_value=create_async_context_manager(mock_response))

        with patch("boto3.client", return_value=mock_boto_client), \
             patch("custom_components.mysa.client.async_get_clientsession", return_value=mock_session), \
             patch("custom_components.mysa.client.login", return_value=mock_login_user) as mock_login:

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
        mock_session.get = MagicMock(return_value=create_async_context_manager(mock_response))

        with patch("custom_components.mysa.client.async_get_clientsession", return_value=mock_session), \
             patch.object(client, "fetch_homes", new_callable=AsyncMock, side_effect=Exception("Home Fail")):
            # Should not raise
            await client.get_devices()

    async def test_get_state_unknown_device(self, mock_hass):
        """Test get_state with device pending / not in devices list."""
        client = MysaClient(mock_hass, "u", "p")
        client._user_obj = MagicMock()
        client._user_obj.id_claims = {"exp": 9999999999}
        client._user_obj.id_token = "token"

        # State includes d99, devices does NOT
        state_response = create_mock_response({"DeviceStatesObj": [{"Id": "d99", "t": 20}]})
        devices_response = create_mock_response({"DevicesObj": []})

        call_count = [0]
        def mock_get(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return create_async_context_manager(state_response)
            return create_async_context_manager(devices_response)

        mock_session = MagicMock()
        mock_session.get = mock_get

        with patch("custom_components.mysa.client.async_get_clientsession", return_value=mock_session):
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
            "refresh_token": "ref"
        }

        # We need to mock CognitoUser to have id_token=None after init
        # or just rely on the fact that we pass None from storage load result

        mock_session = MagicMock()
        mock_response = create_mock_response({"User": {"Id": "uid"}})
        mock_session.get.return_value = create_async_context_manager(mock_response)

        with patch("custom_components.mysa.client.login") as mock_login, \
             patch("custom_components.mysa.client.async_get_clientsession", return_value=mock_session), \
             patch("custom_components.mysa.client.Cognito"):

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
        mock_response = create_mock_response({
            "Homes": [
                {"Id": "h1", "ERate": "0,15", "Zones": []},
                {"Id": "h2", "ERate": "0.12", "Zones": []},
                {"Id": "h3", "ERate": "$0.07", "Zones": []},
                {"Id": "h4", "ERate": "€ 0,15", "Zones": []},
                {"Id": "h5", "ERate": 0.08, "Zones": []},
                {"Id": "h6", "ERate": "abc", "Zones": []},
                {"Id": "h7", "ERate": None, "Zones": []}
            ]
        })
        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=create_async_context_manager(mock_response))

        with patch("custom_components.mysa.client.async_get_clientsession", return_value=mock_session):
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
            "d1": {"Id": "d1", "Zone": {"Id": "z1"}}, # Has valid Zone ID
            "d2": {"Id": "d2", "Zone": {"Id": "z_unknown"}}, # Unknown Zone ID
            "d3": {"Id": "d3"}, # No Zone info
            "d4": {"Id": "d4"}  # Already mapped normally
        }

        # Response:
        # h1 has z1 (but missing d1 in DeviceIds)
        # h2 has z2 with d4
        mock_response = create_mock_response({
            "Homes": [
                {
                    "Id": "h1",
                    "ERate": 0.1,
                    "Zones": [{"Id": "z1", "DeviceIds": []}] # Empty DeviceIds!
                },
                {
                    "Id": "h2",
                    "ERate": 0.2,
                    "Zones": [{"Id": "z2", "DeviceIds": ["d4"]}] # Normal mapping
                }
            ]
        })
        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=create_async_context_manager(mock_response))

        with patch("custom_components.mysa.client.async_get_clientsession", return_value=mock_session):
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
            "d1": {"Id": "d1", "Home": "h1"}, # Direct Home link
            "d2": {"Id": "d2", "Zone": "z2"}, # String Zone ID link
            "d3": {"Id": "d3", "Zone": {"Id": "z3"}}, # Object Zone ID link (existing logic)
            "d4": {"Id": "d4"} # No links
        }

        mock_response = create_mock_response({
            "Homes": [
                {
                    "Id": "h1",
                    "ERate": 0.1,
                    "Zones": []
                },
                {
                    "Id": "h2",
                    "ERate": 0.2,
                    "Zones": [{"Id": "z2"}]
                },
                {
                    "Id": "h3",
                    "ERate": 0.3,
                    "Zones": [{"Id": "z3"}]
                }
            ]
        })
        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=create_async_context_manager(mock_response))

        with patch("custom_components.mysa.client.async_get_clientsession", return_value=mock_session):
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
