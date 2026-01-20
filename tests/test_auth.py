"""
Authentication Module Tests.

Tests for mysa_auth.py: async Cognito authentication.
"""

import sys
import os

# Add project root to path for imports
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(TEST_DIR)
sys.path.insert(0, ROOT_DIR)

import pytest
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock
from datetime import datetime, timezone, timedelta

# Import module to be tested
from custom_components.mysa.mysa_auth import (
    CognitoUser,
    login,
    refresh_and_sign_url,
    sigv4_sign_mqtt_url,
    REGION,
    USER_POOL_ID,
    MQTT_WS_HOST,
    CLIENT_ID,
    IDENTITY_POOL_ID
)

# Valid-looking token for testing (structure only, signature ignored by mocks)
MOCK_ID_TOKEN = "header.payload.signature"

@pytest.fixture
def mock_jwt():
    """Mock python-jose jwt module."""
    with patch("custom_components.mysa.mysa_auth.jwt") as mock_jwt_lib:
        # Default behavior: token is valid
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

@pytest.fixture
def mock_cognito_client():
    """Mock pycognito.Cognito."""
    client = MagicMock()
    client.username = "test@example.com"
    client.id_token = MOCK_ID_TOKEN
    client.access_token = "access123"
    client.refresh_token = "refresh123"
    return client


class TestCognitoUser:
    """Test CognitoUser class."""

    def test_cognito_user_init(self, mock_jwt, mock_cognito_client):
        """Test CognitoUser initialization."""
        user = CognitoUser(mock_cognito_client)

        assert user.username == "test@example.com"
        assert user.id_token == MOCK_ID_TOKEN
        assert user.id_claims is not None

        # Verify jwt was called correctly (id_claims calls get_unverified_claims)
        mock_jwt.get_unverified_claims.assert_called_with(MOCK_ID_TOKEN)

    async def test_verify_token(self, mock_cognito_client):
        """Test token verification via pycognito."""
        user = CognitoUser(mock_cognito_client)

        # Test success
        with patch("jose.jwt.get_unverified_claims", return_value={"test": "claim"}):
            claims = await user.async_verify_token("some_token", "id")
            assert claims == {"test": "claim"}
            mock_cognito_client.verify_token.assert_called_with("some_token", "id", "id")

        # Test failure (pycognito raises)
        mock_cognito_client.verify_token.side_effect = ValueError("Invalid token")
        with pytest.raises(ValueError, match="Invalid token"):
            await user.async_verify_token("bad_token", "id")

    async def test_renew_access_token(self, mock_jwt, mock_cognito_client):
        """Test renewing access token."""
        mock_cognito_client.renew_access_token = MagicMock()

        user = CognitoUser(mock_cognito_client)

        await user.renew_access_token()

        mock_cognito_client.renew_access_token.assert_called_once()

    async def test_get_aws_credentials(self, mock_jwt, mock_cognito_client):
        """Test getting AWS credentials via boto3."""
        user = CognitoUser(mock_cognito_client)

        # Mock jwt to provide issuer for provider extraction
        mock_jwt.get_unverified_claims.return_value = {
            "iss": "https://cognito-idp.us-east-1.amazonaws.com/test_pool"
        }

        mock_creds = {
            'AccessKeyId': 'AKIATEST',
            'SecretKey': 'SECRETTEST',
            'SessionToken': 'SESSIONTEST'
        }

        with patch("boto3.client") as mock_boto:
            mock_identity = MagicMock()
            mock_boto.return_value = mock_identity
            mock_identity.get_id.return_value = {'IdentityId': 'us-east-1:id'}
            mock_identity.get_credentials_for_identity.return_value = {'Credentials': mock_creds}

            creds = await user.get_aws_credentials()

            assert creds['access_key'] == 'AKIATEST'
            assert creds['secret_key'] == 'SECRETTEST'
            assert creds['session_token'] == 'SESSIONTEST'

            mock_identity.get_id.assert_called_once_with(
                IdentityPoolId=IDENTITY_POOL_ID,
                Logins={"cognito-idp.us-east-1.amazonaws.com/test_pool": MOCK_ID_TOKEN}
            )

    async def test_get_aws_credentials_no_token(self, mock_cognito_client):
        """Test get_aws_credentials with no token."""
        mock_cognito_client.id_token = None
        user = CognitoUser(mock_cognito_client)
        with pytest.raises(KeyError): # id_claims will fail or return {} which has no 'iss'
            await user.get_aws_credentials()

    async def test_renew_access_token_errors(self, mock_cognito_client):
        """Test renew_access_token error paths."""
        user = CognitoUser(mock_cognito_client)

        # Client error
        mock_cognito_client.renew_access_token.side_effect = Exception("Refresh failed")
        with pytest.raises(Exception, match="Refresh failed"):
            await user.renew_access_token()

    async def test_verify_token_errors(self, mock_cognito_client):
        """Test verify_token errors."""
        user = CognitoUser(mock_cognito_client)
        mock_cognito_client.verify_token.side_effect = ValueError("Public key not found")

        with pytest.raises(ValueError, match="Public key not found"):
            await user.async_verify_token("bad_token", "id")

    async def test_get_aws_credentials_api_error(self, mock_cognito_client, mock_jwt):
        """Test get_aws_credentials handles API errors."""
        user = CognitoUser(mock_cognito_client)
        mock_jwt.get_unverified_claims.return_value = {"iss": "https://provider"}

        with patch("boto3.client") as mock_boto:
            mock_identity = MagicMock()
            mock_boto.return_value = mock_identity
            mock_identity.get_id.side_effect = Exception("API Error")

            with pytest.raises(Exception, match="API Error"):
                await user.get_aws_credentials()

    async def test_refresh_and_sign_no_id_token(self, mock_cognito_client):
        """Test refresh_and_sign_url when id_token is missing."""
        mock_cognito_client.id_token = None
        user = CognitoUser(mock_cognito_client)

        with patch.object(user, 'renew_access_token', new_callable=AsyncMock) as mock_renew, \
             patch.object(user, 'get_aws_credentials', new_callable=AsyncMock) as mock_creds:

            mock_creds.return_value = {
                "access_key": "k", "secret_key": "s", "session_token": "t"
            }

            await refresh_and_sign_url(user)
            mock_renew.assert_awaited_once()



class TestLogin:
    """Test login function."""

    async def test_login_no_refresh_token(self, mock_cognito_client):
        """Test login when refresh token is missing (should not raise)."""
        mock_cognito_client.refresh_token = None
        with patch('custom_components.mysa.mysa_auth.Cognito', return_value=mock_cognito_client):
            user = await login("u", "p")
            assert user.refresh_token is None

    async def test_login_success(self, mock_jwt, mock_cognito_client):
        """Test successful login."""
        with patch('custom_components.mysa.mysa_auth.Cognito') as MockCognito:
            MockCognito.return_value = mock_cognito_client
            # authenticate is called in executor, we just need it to not raise

            user = await login("test@example.com", "password123")

            assert user.username == "test@example.com"
            assert user.id_token == MOCK_ID_TOKEN
            assert user.access_token == mock_cognito_client.access_token
            assert user._client == mock_cognito_client

            MockCognito.assert_called_with(
                USER_POOL_ID, CLIENT_ID, user_pool_region=REGION, username="test@example.com"
            )
            mock_cognito_client.authenticate.assert_called_once_with(password="password123")

    async def test_login_failure(self):
        """Test login failure."""
        with patch('custom_components.mysa.mysa_auth.Cognito') as MockCognito:
            mock_instance = MockCognito.return_value
            mock_instance.authenticate.side_effect = Exception("Autherr")

            with pytest.raises(Exception, match="Autherr"):
                await login("test@example.com", "fail")

    async def test_login_failure_unknown_service(self):
        """Test login failure with Unknown service error diagnostic logic."""
        with patch('custom_components.mysa.mysa_auth.Cognito') as MockCognito:
            MockCognito.side_effect = Exception("Unknown service: 'cognito-idp'")

            # Mock boto3.Session().get_available_services()
            with patch('custom_components.mysa.mysa_auth.boto3.Session') as MockSession:
                MockSession.return_value.get_available_services.return_value = ["s3", "sts"]

                with pytest.raises(Exception, match="Unknown service: 'cognito-idp'"):
                    await login("test@example.com", "fail")


class TestSigv4SignMqttUrl:
    """Test sigv4_sign_mqtt_url function."""

    def test_sigv4_sign_mqtt_url(self):
        """Test signing MQTT URL with SigV4."""
        aws_credentials = {
            'access_key': 'AKIATEST123',
            'secret_key': 'secret_key_test',
            'session_token': 'session/token+test='
        }

        result = sigv4_sign_mqtt_url(aws_credentials)

        # Verify the result is a signed WebSocket URL
        assert isinstance(result, str)
        assert result.startswith('wss://')
        assert 'X-Amz-Algorithm' in result
        assert 'X-Amz-Signature' in result
        assert 'X-Amz-Security-Token' in result
        # Check for URL encoded token: / -> %2F, + -> %2B, = -> %3D
        assert 'session%2Ftoken%2Btest%3D' in result


class TestRefreshAndSignUrl:
    """Test refresh_and_sign_url function."""

    async def test_refresh_and_sign_url(self, mock_jwt, mock_cognito_client):
        """Test refreshing token and signing URL with expired token."""
        user = CognitoUser(mock_cognito_client)

        # Mock id_claims to look expired
        expired_claims = {"iss": "https://prov", "exp": 100} # Very old

        with patch("custom_components.mysa.mysa_auth.jwt.get_unverified_claims", return_value=expired_claims), \
             patch.object(user, 'renew_access_token', new_callable=AsyncMock) as mock_renew, \
             patch.object(user, 'get_aws_credentials', new_callable=AsyncMock) as mock_creds:

            mock_creds.return_value = {
                "access_key": "k", "secret_key": "s", "session_token": "t"
            }

            signed_url, returned_user = await refresh_and_sign_url(user)

            assert returned_user == user
            assert "wss://" in signed_url
            assert mock_renew.called
            assert mock_creds.called

    async def test_refresh_and_sign_url_error(self, mock_jwt, mock_cognito_client):
        """Test refreshing token and signing URL when check raises exception."""
        user = CognitoUser(mock_cognito_client)

        # Mock id_claims to raise an exception
        with patch.object(user.__class__, 'id_claims', new_callable=PropertyMock) as mock_claims, \
             patch.object(user, 'renew_access_token', new_callable=AsyncMock) as mock_renew, \
             patch.object(user, 'get_aws_credentials', new_callable=AsyncMock) as mock_creds:

            mock_claims.side_effect = Exception("Claims Error")
            mock_creds.return_value = {
                "access_key": "k", "secret_key": "s", "session_token": "t"
            }

            signed_url, returned_user = await refresh_and_sign_url(user)

            assert returned_user == user
            assert "wss://" in signed_url
            assert mock_renew.called
            assert mock_creds.called


class TestConstants:
    """Test auth module constants."""

    def test_constants_values(self):
        """Test constant values."""
        assert REGION == "us-east-1"
        assert USER_POOL_ID == "us-east-1_GUFWfhI7g"
        assert "iot.us-east-1.amazonaws.com" in MQTT_WS_HOST
        assert IDENTITY_POOL_ID == "us-east-1:ebd95d52-9995-45da-b059-56b865a18379"
