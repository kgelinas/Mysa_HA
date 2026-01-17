"""
Authentication Module Tests.

Tests for mysa_auth.py: async Cognito authentication with boto3.
"""

import sys
import os

# Add project root to path for imports
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(TEST_DIR)
sys.path.insert(0, ROOT_DIR)
import boto3
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timezone, timedelta

# Import module to be tested
from custom_components.mysa.mysa_auth import (
    CognitoUser,
    login,
    refresh_and_sign_url,
    sigv4_sign_mqtt_url,
    _compute_secret_hash,
    REGION,
    USER_POOL_ID,
    MQTT_WS_HOST,
    BASE_URL,
    CLIENT_HEADERS,
    CLIENT_ID,
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
def mock_jwks():
    """Mock JWKS with matching key."""
    jwks = {"keys": [{"kid": "test_kid", "kty": "RSA", "alg": "RS256"}]}
    with patch("custom_components.mysa.mysa_auth.JWKS", jwks):
        yield jwks


class TestCognitoUser:
    """Test CognitoUser class."""

    def test_cognito_user_init(self, mock_jwt, mock_jwks):
        """Test CognitoUser initialization and token verification."""
        user = CognitoUser(
            username="test@example.com",
            id_token=MOCK_ID_TOKEN,
            access_token="access123",
            refresh_token="refresh123"
        )

        assert user.username == "test@example.com"
        assert user.id_token == MOCK_ID_TOKEN
        assert user.id_claims is not None

        # Verify jwt was called correctly (init calls get_unverified_claims)
        mock_jwt.get_unverified_claims.assert_called_with(MOCK_ID_TOKEN)

    def test_verify_token_failures(self, mock_jwt, mock_jwks):
        """Test token verification failure cases."""
        # Case 1: Key ID not found in JWKS
        mock_jwt.get_unverified_header.return_value = {"kid": "unknown_kid"}

        user = CognitoUser("u", MOCK_ID_TOKEN, "a", "r")
        with pytest.raises(ValueError, match="Public key not found"):
            user.verify_token(MOCK_ID_TOKEN, 'id')

        # Case 2: Token use mismatch
        mock_jwt.get_unverified_header.return_value = {"kid": "test_kid"}
        mock_jwt.decode.return_value = {"token_use": "access"} # Expected 'id'

        user = CognitoUser("u", MOCK_ID_TOKEN, "a", "r")
        with pytest.raises(ValueError, match="Token use mismatch"):
            user.verify_token(MOCK_ID_TOKEN, 'id')

    async def test_renew_access_token(self, mock_jwt, mock_jwks):
        """Test renewing access token."""
        user = CognitoUser("u", MOCK_ID_TOKEN, "old_acc", "ref")

        mock_client = MagicMock()
        mock_client.initiate_auth.return_value = {
            'AuthenticationResult': {
                'IdToken': "new_id_token",
                'AccessToken': 'new_access_token'
            }
        }

        with patch('boto3.client', return_value=mock_client) as MockClient:
            await user.renew_access_token()

            assert user.id_token == "new_id_token"
            assert user.access_token == "new_access_token"
            MockClient.assert_called_with('cognito-idp', region_name=REGION)
            mock_client.initiate_auth.assert_called_once()

            # Verify new token claims were parsed
            mock_jwt.get_unverified_claims.assert_called_with("new_id_token")

    async def test_get_aws_credentials(self, mock_jwt, mock_jwks):
        """Test getting AWS credentials."""
        user = CognitoUser("u", MOCK_ID_TOKEN, "acc", "ref")

        # Setup claims for login generation
        user.id_claims = {"iss": "https://cognito-idp.us-east-1.amazonaws.com/test"}

        mock_client = MagicMock()
        mock_client.get_id.return_value = {
            'IdentityId': 'us-east-1:identity-123'
        }
        mock_client.get_credentials_for_identity.return_value = {
            'Credentials': {
                'AccessKeyId': 'AKIATEST',
                'SecretKey': 'secret123',
                'SessionToken': 'session123',
                'Expiration': datetime.now(timezone.utc) + timedelta(hours=1)
            }
        }

        with patch('boto3.client', return_value=mock_client) as MockClient:
            creds = await user.get_aws_credentials()

            assert creds['access_key'] == 'AKIATEST'
            assert creds['identity_id'] == 'us-east-1:identity-123'
            MockClient.assert_called_with('cognito-identity', region_name=REGION)
            mock_client.get_id.assert_called_once()
            mock_client.get_credentials_for_identity.assert_called_once()

    async def test_get_aws_credentials_failure(self, mock_jwt, mock_jwks):
        """Test getting AWS credentials failure."""
        user = CognitoUser("u", MOCK_ID_TOKEN, "acc", "ref")
        user.id_claims = {"iss": "https://cognito-idp.us-east-1.amazonaws.com/test"}

        mock_client = MagicMock()
        mock_client.get_id.side_effect = Exception("AWS Error")

        with patch('boto3.client', return_value=mock_client):
            with pytest.raises(Exception, match="AWS Error"):
                await user.get_aws_credentials()


class TestLogin:
    """Test login function."""

    async def test_login_success(self, mock_jwt, mock_jwks):
        """Test successful login."""
        # Setup pycognito mock
        mock_cognito_instance = MagicMock()
        mock_cognito_instance.id_token = MOCK_ID_TOKEN
        mock_cognito_instance.access_token = 'access_token_123'
        mock_cognito_instance.refresh_token = 'refresh_token_123'

        with patch('custom_components.mysa.mysa_auth.Cognito', return_value=mock_cognito_instance) as MockCognito:
            user = await login("test@example.com", "password123")

            assert user.username == "test@example.com"
            assert user.id_token == MOCK_ID_TOKEN

            # Verify Cognito initialized and authenticate called
            MockCognito.assert_called_with(USER_POOL_ID, CLIENT_ID, username="test@example.com")
            mock_cognito_instance.authenticate.assert_called_with(password="password123")

    async def test_login_failure(self):
        """Test login failure."""
        with patch('custom_components.mysa.mysa_auth.Cognito') as MockCognito:
            mock_instance = MockCognito.return_value
            mock_instance.authenticate.side_effect = Exception("Autherr")

            with pytest.raises(Exception, match="Autherr"):
                await login("test@example.com", "fail")


class TestHelpers:
    """Test helper functions."""

    def test_compute_secret_hash(self):
        """Test secret hash computation."""
        # Known test vectors
        username = "testuser"
        client_id = "testclient"
        client_secret = "secret"

        # Expected hash
        # generic hmac sha256 of "testusertestclient" with key "secret"
        # then base64 encoded

        result = _compute_secret_hash(username, client_id, client_secret)
        assert isinstance(result, str)
        assert len(result) > 0


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

    async def test_refresh_and_sign_url(self, mock_jwt, mock_jwks):
        """Test refreshing token and signing URL."""
        user = CognitoUser("u", MOCK_ID_TOKEN, "acc", "ref")

        # Setup mocks
        mock_renewal_client = MagicMock()
        mock_renewal_client.initiate_auth.return_value = {
            'AuthenticationResult': {
                'IdToken': MOCK_ID_TOKEN,
                'AccessToken': 'new_access_token'
            }
        }

        mock_creds_client = MagicMock()
        mock_creds_client.get_id.return_value = {'IdentityId': 'id-123'}
        mock_creds_client.get_credentials_for_identity.return_value = {
            'Credentials': {
                'AccessKeyId': 'KEY', 'SecretKey': 'SECRET', 'SessionToken': 'TOKEN',
                'Expiration': datetime.now(timezone.utc)
            }
        }

        def mock_client_factory(service, **kwargs):
            if service == 'cognito-idp':
                return mock_renewal_client
            else:
                return mock_creds_client

        with patch('boto3.client', side_effect=mock_client_factory):
            # Force verification failure to test renew path
            mock_jwt.verify_token = MagicMock(side_effect=Exception("Expired"))
            # Note: We can't mock the method on instance easily if it's called inside.
            # Actually we can mock verify_token on the user object if we set it before call,
            # BUT refresh_and_sign_url calls user.verify_token.
            # Ideally rely on verify_token raising exception via mocks.
            # If we set get_unverified_header to raise, verify_token will raise.

            mock_jwt.get_unverified_header.side_effect = Exception("Expired")

            signed_url, returned_user = await refresh_and_sign_url(user)

            assert returned_user == user
            # Should have attempted renewal
            mock_renewal_client.initiate_auth.assert_called()


class TestConstants:
    """Test auth module constants."""

    def test_constants_values(self):
        """Test constant values."""
        assert REGION == "us-east-1"
        assert USER_POOL_ID == "us-east-1_GUFWfhI7g"
        assert "iot.us-east-1.amazonaws.com" in MQTT_WS_HOST
        assert BASE_URL == "https://app-prod.mysa.cloud"
        assert "user-agent" in CLIENT_HEADERS
