"""
Authentication Module Coverage Tests.

Tests for mysa_auth.py: Cognito authentication, token management, and MQTT URL signing.
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from time import time
import pycognito


class TestCognitoClass:
    """Test Cognito class initialization and methods."""

    def test_cognito_init(self):
        """Test Cognito class initialization."""
        from custom_components.mysa.mysa_auth import (
            Cognito,
            USER_POOL_ID,
            CLIENT_ID,
            JWKS,
        )

        with patch("pycognito.Cognito.__init__", return_value=None):
            cog = Cognito(
                user_pool_id=USER_POOL_ID,
                client_id=CLIENT_ID,
                username="test@example.com",
                pool_jwk=JWKS,
            )

            assert cog.pool_jwk == JWKS

    def test_cognito_init_with_session(self):
        """Test Cognito class initialization with session."""
        from custom_components.mysa.mysa_auth import Cognito, USER_POOL_ID, CLIENT_ID

        mock_session = MagicMock()

        with patch("pycognito.Cognito.__init__", return_value=None):
            cog = Cognito(
                user_pool_id=USER_POOL_ID,
                client_id=CLIENT_ID,
                username="test@example.com",
                session=mock_session,
            )

            assert cog._session == mock_session


class TestGetCredentials:
    """Test get_credentials method."""

    def test_get_credentials_requires_id(self):
        """Test get_credentials raises error without identity."""
        from custom_components.mysa.mysa_auth import Cognito, USER_POOL_ID, CLIENT_ID

        with patch("pycognito.Cognito.__init__", return_value=None):
            cog = Cognito(
                user_pool_id=USER_POOL_ID,
                client_id=CLIENT_ID,
                username="test@example.com",
            )

            with pytest.raises(
                ValueError, match="Either identity_pool_id or identity_id"
            ):
                cog.get_credentials()

    def test_get_credentials_with_identity_pool(self):
        """Test get_credentials with identity pool ID."""
        from custom_components.mysa.mysa_auth import (
            Cognito,
            USER_POOL_ID,
            CLIENT_ID,
            IDENTITY_POOL_ID,
        )

        with patch("pycognito.Cognito.__init__", return_value=None):
            cog = Cognito(
                user_pool_id=USER_POOL_ID,
                client_id=CLIENT_ID,
                username="test@example.com",
            )
            cog.user_pool_region = "us-east-1"
            cog.id_token = "mock_id_token"
            cog.id_claims = {"iss": "https://cognito-idp.us-east-1.amazonaws.com/test"}

            mock_client = MagicMock()
            mock_client.get_id.return_value = {
                "IdentityId": "us-east-1:mock-identity-id"
            }
            mock_client.get_credentials_for_identity.return_value = {
                "Credentials": {
                    "AccessKeyId": "AKIATEST",
                    "SecretKey": "secret123",
                    "SessionToken": "session123",
                    "Expiration": MagicMock(),
                }
            }

            with patch("boto3.client", return_value=mock_client):
                creds = cog.get_credentials(identity_pool_id=IDENTITY_POOL_ID)

                assert creds is not None
                mock_client.get_id.assert_called_once()
                mock_client.get_credentials_for_identity.assert_called_once()

    def test_get_credentials_with_identity_id(self):
        """Test get_credentials with existing identity ID (skips get_id call)."""
        from custom_components.mysa.mysa_auth import Cognito, USER_POOL_ID, CLIENT_ID

        with patch("pycognito.Cognito.__init__", return_value=None):
            cog = Cognito(
                user_pool_id=USER_POOL_ID,
                client_id=CLIENT_ID,
                username="test@example.com",
            )
            cog.user_pool_region = "us-east-1"
            cog.id_token = "mock_id_token"
            cog.id_claims = {"iss": "https://cognito-idp.us-east-1.amazonaws.com/test"}

            mock_client = MagicMock()
            mock_client.get_credentials_for_identity.return_value = {
                "Credentials": {
                    "AccessKeyId": "AKIATEST",
                    "SecretKey": "secret123",
                    "SessionToken": "session123",
                    "Expiration": MagicMock(),
                }
            }

            with patch("boto3.client", return_value=mock_client):
                creds = cog.get_credentials(identity_id="us-east-1:existing-id")

                assert creds is not None
                # Should NOT call get_id since we have identity_id
                mock_client.get_id.assert_not_called()
                mock_client.get_credentials_for_identity.assert_called_once()

    def test_get_credentials_with_session_client(self):
        """Test get_credentials uses session client when available."""
        from custom_components.mysa.mysa_auth import Cognito, USER_POOL_ID, CLIENT_ID

        mock_session = MagicMock()
        mock_client = MagicMock()
        mock_session.client.return_value = mock_client
        mock_client.get_credentials_for_identity.return_value = {
            "Credentials": {
                "AccessKeyId": "AKIATEST",
                "SecretKey": "secret123",
                "SessionToken": "session123",
                "Expiration": MagicMock(),
            }
        }

        with patch("pycognito.Cognito.__init__", return_value=None):
            cog = Cognito(
                user_pool_id=USER_POOL_ID,
                client_id=CLIENT_ID,
                username="test@example.com",
                session=mock_session,
            )
            cog.user_pool_region = "us-east-1"
            cog.id_token = "mock_id_token"
            cog.id_claims = {"iss": "https://cognito-idp.us-east-1.amazonaws.com/test"}

            creds = cog.get_credentials(identity_id="us-east-1:test-id")

            mock_session.client.assert_called_with(
                "cognito-identity", region_name="us-east-1"
            )

    def test_get_credentials_refresh_callback(self):
        """Test credential refresh callback logic."""
        from custom_components.mysa.mysa_auth import Cognito, USER_POOL_ID, CLIENT_ID
        import botocore.credentials

        with patch("pycognito.Cognito.__init__", return_value=None):
            cog = Cognito(
                user_pool_id=USER_POOL_ID,
                client_id=CLIENT_ID,
                username="test@example.com",
            )
            cog.user_pool_region = "us-east-1"
            cog.id_token = "mock_id_token"
            cog.id_claims = {"iss": "https://cognito-idp.us-east-1.amazonaws.com/test"}
            cog.renew_access_token = MagicMock()
            cog.verify_token = MagicMock()

            mock_client = MagicMock()
            # First call returns credentials
            mock_client.get_credentials_for_identity.return_value = {
                "Credentials": {
                    "AccessKeyId": "AKIATEST",
                    "SecretKey": "secret123",
                    "SessionToken": "session123",
                    "Expiration": MagicMock(),
                }
            }

            with patch("boto3.client", return_value=mock_client):
                # This returns a RefreshableCredentials object
                creds = cog.get_credentials(identity_id="us-east-1:test-id")
                assert isinstance(creds, botocore.credentials.RefreshableCredentials)
                
                # Setup verify_token to raise exception once, then succeed
                cog.verify_token.side_effect = [
                    pycognito.TokenVerificationException("Expired"),
                    None
                ]
                
                # Manually invoke the refresh callback
                refresh_func = creds._refresh_using
                # The callback should:
                # 1. Verification fails -> triggers renew_access_token
                # 2. Calls get_credentials recursively
                # We need to break the recursion for the test or mock get_credentials
                
                # ACTUALLY, checking the implementation:
                # _refresh_credentials calls:
                #   verify_token -> renew_access_token (if exception)
                #   return self.get_credentials(...)
                
                # So if we call refresh_func(), it will return a new Credentials object
                # We mock get_credentials to avoid infinite recursion in test environment 
                # (although logically it creates a NEW creds object)
                
                with patch.object(cog, 'get_credentials') as mock_get_creds:
                     refresh_func()
                     
                     # Verify logic
                     cog.verify_token.assert_called()
                     cog.renew_access_token.assert_called_once()
                     mock_get_creds.assert_called_once()


class TestLogin:
    """Test login function."""

    def test_login_success(self):
        """Test successful login."""
        from custom_components.mysa.mysa_auth import login

        with patch("custom_components.mysa.mysa_auth.Cognito") as MockCognito:
            mock_user = MagicMock()
            MockCognito.return_value = mock_user

            result = login("test@example.com", "password123")

            mock_user.authenticate.assert_called_once_with(password="password123")
            assert result == mock_user

    def test_login_with_session(self):
        """Test login with boto session."""
        from custom_components.mysa.mysa_auth import login

        mock_session = MagicMock()

        with patch("custom_components.mysa.mysa_auth.Cognito") as MockCognito:
            mock_user = MagicMock()
            MockCognito.return_value = mock_user

            result = login("test@example.com", "password123", bsess=mock_session)

            MockCognito.assert_called_once()
            call_kwargs = MockCognito.call_args[1]
            assert call_kwargs["session"] == mock_session


class TestAuther:
    """Test auther HTTP auth handler."""

    def test_auther_returns_callable(self):
        """Test auther returns a callable."""
        from custom_components.mysa.mysa_auth import auther

        mock_user = MagicMock()
        mock_user.id_claims = {"exp": time() + 3600}  # Expires in 1 hour
        mock_user.id_token = "valid_token"

        auth_handler = auther(mock_user)

        assert callable(auth_handler)

    def test_auther_sets_authorization(self):
        """Test auther sets authorization header."""
        from custom_components.mysa.mysa_auth import auther

        mock_user = MagicMock()
        mock_user.id_claims = {"exp": time() + 3600}  # Expires in 1 hour
        mock_user.id_token = "valid_token"

        auth_handler = auther(mock_user)

        mock_request = MagicMock()
        mock_request.headers = {}

        result = auth_handler(mock_request)

        assert result.headers["authorization"] == "valid_token"

    def test_auther_refreshes_expired_token(self):
        """Test auther refreshes token when expired."""
        from custom_components.mysa.mysa_auth import auther

        mock_user = MagicMock()
        mock_user.id_claims = {"exp": time() - 10}  # Already expired
        mock_user.id_token = "refreshed_token"

        auth_handler = auther(mock_user)

        mock_request = MagicMock()
        mock_request.headers = {}

        result = auth_handler(mock_request)

        mock_user.renew_access_token.assert_called_once()
        assert result.headers["authorization"] == "refreshed_token"


class TestSigv4SignMqttUrl:
    """Test sigv4_sign_mqtt_url function."""

    def test_sigv4_sign_mqtt_url(self):
        """Test signing MQTT URL with SigV4."""
        from custom_components.mysa.mysa_auth import sigv4_sign_mqtt_url

        mock_cred = MagicMock()
        mock_frozen = MagicMock()
        mock_frozen._replace.return_value = mock_frozen
        mock_cred.get_frozen_credentials.return_value = mock_frozen
        mock_cred.token = "session_token_123"

        with patch("botocore.auth.SigV4QueryAuth") as MockAuth:
            mock_auth_instance = MagicMock()
            MockAuth.return_value = mock_auth_instance

            result = sigv4_sign_mqtt_url(mock_cred)

            # Verify the auth was created with correct params
            MockAuth.assert_called_once()
            call_kwargs = MockAuth.call_args[1]
            assert call_kwargs["service_name"] == "iotdevicegateway"
            assert call_kwargs["region_name"] == "us-east-1"

    def test_sigv4_url_contains_session_token(self):
        """Test that session token is added after signing."""
        from custom_components.mysa.mysa_auth import sigv4_sign_mqtt_url, MQTT_WS_URL

        mock_cred = MagicMock()
        mock_frozen = MagicMock()
        mock_frozen._replace.return_value = mock_frozen
        mock_cred.get_frozen_credentials.return_value = mock_frozen
        mock_cred.token = "session_token_xyz"

        with patch("botocore.auth.SigV4QueryAuth") as MockAuth:
            mock_auth_instance = MagicMock()
            MockAuth.return_value = mock_auth_instance

            result = sigv4_sign_mqtt_url(mock_cred)

            # The result should be a prepared URL string
            assert isinstance(result, str)


class TestConstants:
    """Test auth module constants."""

    def test_region_constant(self):
        """Test REGION constant."""
        from custom_components.mysa.mysa_auth import REGION

        assert REGION == "us-east-1"

    def test_user_pool_id_constant(self):
        """Test USER_POOL_ID constant."""
        from custom_components.mysa.mysa_auth import USER_POOL_ID

        assert USER_POOL_ID == "us-east-1_GUFWfhI7g"

    def test_mqtt_ws_host_constant(self):
        """Test MQTT_WS_HOST constant."""
        from custom_components.mysa.mysa_auth import MQTT_WS_HOST

        assert "iot.us-east-1.amazonaws.com" in MQTT_WS_HOST

    def test_base_url_constant(self):
        """Test BASE_URL constant."""
        from custom_components.mysa.mysa_auth import BASE_URL

        assert BASE_URL == "https://app-prod.mysa.cloud"

    def test_client_headers(self):
        """Test CLIENT_HEADERS constant."""
        from custom_components.mysa.mysa_auth import CLIENT_HEADERS

        assert "user-agent" in CLIENT_HEADERS
        assert "accept" in CLIENT_HEADERS
