"""Tests for MysaClient."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch, ANY
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

@pytest.mark.asyncio
class TestMysaClient:
    """Test the MysaClient class."""

    async def test_init(self, mock_hass, mock_store):
        """Test initialization."""
        client = MysaClient(mock_hass, "u", "p")
        assert client.is_connected is False
        assert client.user_id is None
        assert client.username == "u"

    async def test_authenticate_cached_success(self, mock_hass, mock_store):
        """Test authentication with cached tokens."""
        client = MysaClient(mock_hass, "u", "p")

        mock_store.async_load.return_value = {"id_token": "id", "refresh_token": "ref"}

        mock_cognito = MagicMock()
        mock_cognito.id_token = "id"
        mock_cognito.refresh_token = "ref"

        with patch("custom_components.mysa.client.boto3"), \
             patch("custom_components.mysa.client.Cognito", return_value=mock_cognito) as cog_cls, \
             patch("custom_components.mysa.client.auther"), \
             patch("custom_components.mysa.client.requests") as mock_req:

            # Mock User ID fetch
            mock_sess = mock_req.Session.return_value
            mock_sess.get.return_value.json.return_value = {"User": {"Id": "uid"}}
            mock_sess.get.return_value.raise_for_status = MagicMock()

            res = await client.authenticate()
            assert res
            assert client.is_connected is True
            assert client.user_id == "uid"

            cog_cls.assert_called()
            mock_cognito.verify_token.assert_called()

    async def test_authenticate_cached_refresh(self, mock_hass, mock_store):
        """Test authentication refresh token flow."""
        client = MysaClient(mock_hass, "u", "p")
        mock_store.async_load.return_value = {"id_token": "id", "refresh_token": "ref"}

        mock_cognito = MagicMock()
        mock_cognito.verify_token.side_effect = Exception("Expired")
        mock_cognito.id_token = "new_id"
        mock_cognito.refresh_token = "new_ref"

        with patch("custom_components.mysa.client.boto3"), \
             patch("custom_components.mysa.client.Cognito", return_value=mock_cognito), \
             patch("custom_components.mysa.client.auther"), \
             patch("custom_components.mysa.client.requests") as mock_req:

            mock_sess = mock_req.Session.return_value
            mock_sess.get.return_value.json.return_value = {"User": {"Id": "uid"}}

            await client.authenticate()
            mock_cognito.renew_access_token.assert_called()
            mock_store.async_save.assert_called_with({"id_token": "new_id", "refresh_token": "new_ref"})

    async def test_authenticate_login_fallback(self, mock_hass, mock_store):
        """Test authentication password fallback."""
        client = MysaClient(mock_hass, "u", "p")
        mock_store.async_load.return_value = None # No cache

        mock_user = MagicMock()
        mock_user.id_token = "id"
        mock_user.refresh_token = "ref"

        with patch("custom_components.mysa.client.boto3"), \
             patch("custom_components.mysa.client.login", return_value=mock_user) as mock_login, \
             patch("custom_components.mysa.client.auther"), \
             patch("custom_components.mysa.client.requests") as mock_req:

            mock_sess = mock_req.Session.return_value
            mock_sess.get.return_value.json.return_value = {} # No User ID returned (edge case)

            await client.authenticate()
            mock_login.assert_called_with("u", "p", bsess=ANY)
            mock_store.async_save.assert_called()
            assert client.user_id is None # Not found

    async def test_authenticate_fail(self, mock_hass, mock_store):
        """Test authentication failure raises."""
        client = MysaClient(mock_hass, "u", "p")
        mock_store.async_load.return_value = None

        with patch("custom_components.mysa.client.boto3"), \
             patch("custom_components.mysa.client.login", side_effect=Exception("Login Fail")):

             with pytest.raises(Exception, match="Login Fail"):
                 await client.authenticate()

    async def test_authenticate_fetch_user_id_fail(self, mock_hass, mock_store):
        """Test User ID fetch failure is logged but auth succeeds."""
        client = MysaClient(mock_hass, "u", "p")
        mock_store.async_load.return_value = None
        mock_user = MagicMock()

        with patch("custom_components.mysa.client.boto3"), \
             patch("custom_components.mysa.client.login", return_value=mock_user), \
             patch("custom_components.mysa.client.auther"), \
             patch("custom_components.mysa.client.requests") as mock_req:

             mock_sess = mock_req.Session.return_value
             mock_sess.get.side_effect = Exception("API Error")

             await client.authenticate()
             assert client.is_connected is True
             assert client.user_id is None

    async def test_get_devices(self, mock_hass):
        """Test get_devices success."""
        client = MysaClient(mock_hass, "u", "p")
        client._session = MagicMock()

        # Test List format
        client._session.get.return_value.json.return_value = {
            "DevicesObj": [{"Id": "d1", "Name": "Dev1"}]
        }

        with patch.object(client, "_fetch_homes_sync") as mock_fetch:
            devs = await client.get_devices()
            assert "d1" in devs
            mock_fetch.assert_called()

        # Test Dict format logic fallthrough (coverage)
        client._session.get.return_value.json.return_value = {
            "DevicesObj": {"d2": {"Id": "d2"}}
        }
        devs = await client.get_devices()
        assert "d2" in devs

    async def test_get_devices_no_session(self, mock_hass):
        """Test get_devices raises if no session."""
        client = MysaClient(mock_hass, "u", "p")
        with pytest.raises(RuntimeError):
            await client.get_devices()

    async def test_fetch_homes(self, mock_hass):
        """Test fetch_homes and zone mapping."""
        client = MysaClient(mock_hass, "u", "p")
        client._session = MagicMock()

        client._session.get.return_value.json.return_value = {
            "Homes": [
                {
                    "Id": "h1",
                    "Zones": [{"Id": "z1", "Name": "Zone1"}]
                }
            ]
        }

        homes = await client.fetch_homes()
        assert len(homes) == 1
        assert client.get_zone_name("z1") == "Zone1"
        assert client.get_zone_name("z1") == "Zone1"
        assert client.get_zone_name("unknown") is None

    async def test_fetch_homes_erates(self, mock_hass):
        """Test fetch_homes parses ERates and maps devices."""
        client = MysaClient(mock_hass, "u", "p")
        client._session = MagicMock()
        client._session.get.return_value.json.return_value = {
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
        }
        # Pre-seed devices so fallback check works if we test it (though map is direct here)
        client.devices = {"d1": {"Id": "d1"}}

        await client.fetch_homes()

        # Check mapping
        assert client.get_electricity_rate("d1") == 0.15
        assert client.get_electricity_rate("unknown") is None
        # Invalid rate should simply result in nothing (or strict Home lookup returning None)
        # We don't have a device under h2, so no direct check unless we map one

    async def test_get_electricity_rate_fallback(self, mock_hass):
        """Test get_electricity_rate fallback path."""
        client = MysaClient(mock_hass, "u", "p")
        # Device exists but is not mapped to a home
        client.devices = {"d_fallback": {"Id": "d_fallback"}}

        # This hits line 204: if not home_id and device_id in self.devices: pass
        rate = client.get_electricity_rate("d_fallback")
        assert rate is None

    async def test_fetch_homes_no_session(self, mock_hass):
        client = MysaClient(mock_hass, "u", "p")
        with pytest.raises(RuntimeError):
            await client.fetch_homes()

    async def test_fetch_firmware_info(self, mock_hass):
        """Test fetch firmware success/fail."""
        client = MysaClient(mock_hass, "u", "p")
        client._session = MagicMock()

        # Success
        client._session.get.return_value.json.return_value = {"fw": "v2"}
        assert client.fetch_firmware_info("d1") == {"fw": "v2"}

        # Error
        client._session.get.side_effect = Exception("Fail")
        assert client.fetch_firmware_info("d1") is None

        # No session
        client._session = None
        with pytest.raises(RuntimeError):
            client.fetch_firmware_info("d1")

    async def test_get_state(self, mock_hass):
        """Test get_state merging logic."""
        client = MysaClient(mock_hass, "u", "p")
        client._session = MagicMock()

        # 1. Live metrics
        client._session.get.side_effect = [
            MagicMock(json=lambda: {"DeviceStatesObj": [{"Id": "d1", "t": 20}]}), # State
            MagicMock(json=lambda: {"DevicesObj": [{"Id": "d1", "Attributes": {"n": "Name"}}]}) # Devices
        ]

        # Initial cached devices
        client.devices = {}

        states = await client.get_state()
        assert "d1" in states
        assert states["d1"]["t"] == 20
        assert states["d1"]["n"] == "Name"

    async def test_get_state_format_variants(self, mock_hass):
        """Test get_state dict/list variants."""
        client = MysaClient(mock_hass, "u", "p")
        client._session = MagicMock()

        # Dict formats
        client._session.get.side_effect = [
            MagicMock(json=lambda: {"DeviceStatesObj": {"d1": {"Id": "d1", "t": 20}}}),
            MagicMock(json=lambda: {"DevicesObj": {"d1": {"Id": "d1", "Attributes": {}}}})
        ]

        states = await client.get_state()
        assert "d1" in states

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
        client._session = MagicMock()

        # Success
        client._session.post.return_value.json.return_value = {"ok": 1}
        res = await client.set_device_setting_http("d1", {})
        assert res == {"ok": 1}

        # Fail
        client._session.post.side_effect = Exception("Fail")
        with pytest.raises(Exception):
            await client.set_device_setting_http("d1", {})

        # Silent success
        client._session.post.side_effect = None
        await client.set_device_setting_silent("d1", {})

        # Silent fail
        client._session.post.side_effect = Exception("Fail")
        await client.set_device_setting_silent("d1", {}) # Should not raise

    async def test_set_device_setting_http_no_session(self, mock_hass):
        """Test setting HTTP with no session."""
        client = MysaClient(mock_hass, "u", "p")
        with pytest.raises(RuntimeError):
            await client.set_device_setting_http("d1", {})

    async def test_async_request(self, mock_hass):
        """Test generic request."""
        client = MysaClient(mock_hass, "u", "p")
        client._session = MagicMock()

        client._session.request.return_value.status_code = 200
        await client.async_request("GET", "url")

        client._session = None
        with pytest.raises(RuntimeError):
             await client.async_request("GET", "url")

    async def test_authenticate_cached_renew_fail(self, mock_hass, mock_store):
        """Test renew failure triggers fallback to password login."""
        client = MysaClient(mock_hass, "u", "p")
        mock_store.async_load.return_value = {"id_token": "id", "refresh_token": "ref"}

        mock_cognito = MagicMock()
        mock_cognito.verify_token.side_effect = Exception("Expired")
        mock_cognito.renew_access_token.side_effect = Exception("Renew Fail")

        with patch("custom_components.mysa.client.boto3"), \
             patch("custom_components.mysa.client.Cognito", return_value=mock_cognito), \
             patch("custom_components.mysa.client.auther"), \
             patch("custom_components.mysa.client.requests") as mock_req, \
             patch("custom_components.mysa.client.login") as mock_login: # fallback

            # Setup login to succeed
            mock_login.return_value.id_token = "new_id"
            mock_login.return_value.refresh_token = "new_ref"

            mock_sess = mock_req.Session.return_value
            mock_sess.get.return_value.json.return_value = {"User": {"Id": "uid"}}

            await client.authenticate()

            # Verify renew was attempted
            mock_cognito.renew_access_token.assert_called()
            # Verify login fallback happened because renew failed
            mock_login.assert_called()

    async def test_get_devices_fetch_homes_fail(self, mock_hass):
        """Test failure in fetch_homes during get_devices is suppressed."""
        client = MysaClient(mock_hass, "u", "p")
        client._session = MagicMock()
        client._session.get.return_value.json.return_value = {"DevicesObj": []}

        with patch.object(client, "_fetch_homes_sync", side_effect=Exception("Home Fail")):
            # Should not raise
            await client.get_devices()

    async def test_get_state_unknown_device(self, mock_hass):
        """Test get_state with device pending / not in devices list."""
        client = MysaClient(mock_hass, "u", "p")
        client._session = MagicMock()

        # State includes d99, devices does NOT
        client._session.get.side_effect = [
            MagicMock(json=lambda: {"DeviceStatesObj": [{"Id": "d99", "t": 20}]}),
            MagicMock(json=lambda: {"DevicesObj": []})
        ]

        states = await client.get_state()
        # Should be included but without merged attributes
        assert "d99" in states
        assert states["d99"]["t"] == 20
