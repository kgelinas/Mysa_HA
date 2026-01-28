"""Mysa Authentication Module.

Async authentication and AWS utilities for Mysa devices.
Replaces custom SRP implementation with pycognito (standard library) wrapped in async executors.

This module handles:
1. Cognito User Pool authentication (SRP) via pycognito
2. AWS Credential retrieval (Cognito Identity) via pycognito
3. AWS SigV4 signing for MQTT WebSocket connection
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
from datetime import UTC, datetime
from functools import partial
from typing import Any, cast
from urllib.parse import quote, urlencode

import boto3
from jose import jwt
from pycognito import Cognito

_LOGGER = logging.getLogger(__name__)

# =============================================================================
# Mysa AWS Configuration Constants
# =============================================================================

REGION = "us-east-1"
"""Region for Mysa AWS infrastructure"""

USER_POOL_ID = "us-east-1_GUFWfhI7g"
"""Mysa's Cognito IDP user pool ID"""

CLIENT_ID = "19efs8tgqe942atbqmot5m36t3"
"""Mysa's Cognito IDP client ID"""

IDENTITY_POOL_ID = "us-east-1:ebd95d52-9995-45da-b059-56b865a18379"
"""Mysa's Cognito Identity pool ID for AWS credentials"""

MQTT_WS_HOST = "a3q27gia9qg3zy-ats.iot.us-east-1.amazonaws.com"
"""Hostname for Mysa MQTT-over-WebSockets endpoint"""

MQTT_WS_URL = f"https://{MQTT_WS_HOST}/mqtt"
"""Complete HTTPS URL for MQTT-over-Websockets connection"""

CLIENT_HEADERS = {
    "user-agent": "okhttp/4.11.0",
    "accept": "application/json",
    "accept-encoding": "gzip",
}
"""HTTP headers matching Mysa Android app"""

BASE_URL = "https://app-prod.mysa.cloud"
"""Base URL for Mysa's REST API"""


# =============================================================================
# Cognito User Class (Wrapper for pycognito + boto3)
# =============================================================================


class CognitoUser:
    """Represents an authenticated Cognito user with tokens and AWS credentials."""

    def __init__(self, cognito_client: Cognito):
        """Initialize the Cognito user."""
        self._client = cognito_client
        self.username = self._client.username
        # Cache credentials
        self.aws_credentials: dict[str, Any] | None = None

    @property
    def id_token(self) -> str | None:
        """Return the ID token."""
        return cast(str | None, self._client.id_token)

    @property
    def access_token(self) -> str | None:
        """Return the access token."""
        return cast(str | None, self._client.access_token)

    @property
    def refresh_token(self) -> str | None:
        """Return the refresh token."""
        return cast(str | None, self._client.refresh_token)

    @property
    def id_claims(self) -> dict[str, Any]:
        """Return ID token claims."""
        if self.id_token:
            return cast(dict[str, Any], jwt.get_unverified_claims(self.id_token))
        return {}

    async def async_verify_token(self, token: str, token_use: str) -> dict[str, Any]:
        """Verify JWT token signature and claims.

        PyCognito handles verification internally on get_user, etc.
        But for explicit checking we can use jose still or PyCognito.
        """
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, self._client.verify_token, token, token_use, token_use
        )  # raises on fail
        return cast(dict[str, Any], jwt.get_unverified_claims(token))

    async def renew_access_token(self) -> None:
        """Refresh the access token using the refresh token."""
        loop = asyncio.get_running_loop()
        # pycognito renew_access_token is blocking
        try:
            await loop.run_in_executor(None, self._client.renew_access_token)
            _LOGGER.debug("Successfully renewed access token for %s", self.username)
        except Exception as e:
            _LOGGER.error("Failed to renew access token: %s", e)
            raise

    async def get_aws_credentials(
        self, _identity_id: str | None = None
    ) -> dict[str, Any]:
        """Get AWS credentials from Cognito Identity pool using boto3 directly."""
        loop = asyncio.get_running_loop()
        try:
            # 1. Get Identity ID
            # Logins map: 'cognito-idp.<region>.amazonaws.com/<user_pool_id>' : id_token
            # Usually: cognito-idp.us-east-1.amazonaws.com/us-east-1_GUFWfhI7g

            # The 'iss' claim is exactly the provider string we need (minus https://)
            provider = self.id_claims["iss"].replace("https://", "")
            logins = {provider: self.id_token}

            def _fetch_creds() -> dict[str, Any]:
                client = boto3.client("cognito-identity", region_name=REGION)

                # Get ID
                resp_id = client.get_id(IdentityPoolId=IDENTITY_POOL_ID, Logins=logins)
                identity_id = resp_id["IdentityId"]

                # Get Credentials
                resp_creds = client.get_credentials_for_identity(
                    IdentityId=identity_id, Logins=logins
                )
                return cast(dict[str, Any], resp_creds["Credentials"])

            creds = await loop.run_in_executor(None, _fetch_creds)

            # Extract to dict
            self.aws_credentials = {
                "access_key": creds["AccessKeyId"],
                "secret_key": creds["SecretKey"],
                "session_token": creds["SessionToken"],
            }
            return self.aws_credentials
        except Exception as e:
            _LOGGER.error("Failed to get AWS credentials: %s", e)
            raise


# =============================================================================
# Cognito Authentication Functions
# =============================================================================


async def login(username: str, password: str) -> CognitoUser:
    """Authenticate with Mysa using email and password.

    Args:
        username: Mysa account email
        password: Mysa account password

    Returns:
        Authenticated CognitoUser object

    """
    loop = asyncio.get_running_loop()

    # Initialize PyCognito client
    # Initialize PyCognito client in executor to avoid blocking I/O (AWS metadata lookup)
    # Note: We do NOT pass identity_pool_id as it causes TypeError in this version
    try:
        # Initialize PyCognito client in executor to avoid blocking I/O (AWS metadata lookup)
        # Note: We do NOT pass identity_pool_id as it causes TypeError in this version
        client = await loop.run_in_executor(
            None,
            partial(
                Cognito,
                USER_POOL_ID,
                CLIENT_ID,
                user_pool_region=REGION,
                username=username,
                # identity_pool_id=IDENTITY_POOL_ID  <-- REMOVED
            ),
        )

        # authenticate() handles SRP
        await loop.run_in_executor(
            None, partial(client.authenticate, password=password)
        )
    except Exception as e:
        if "Unknown service: 'cognito-idp'" in str(e):
            try:
                available = boto3.Session().get_available_services()
                _LOGGER.error(
                    "cognito-idp service missing. Available services: %s",
                    sorted(available),
                )
            except Exception:
                pass
        _LOGGER.error("Authentication failed: %s", e)
        raise

    user = CognitoUser(client)

    _LOGGER.debug("Successfully authenticated as user %s", username)
    return user


async def refresh_and_sign_url(user: CognitoUser) -> tuple[str, CognitoUser]:
    """Refresh user tokens if needed and return signed MQTT URL.

    Args:
        user: CognitoUser object

    Returns:
        Tuple of (signed_url, user_object)

    """
    # Refresh token if needed
    try:
        # Check if expired? PyCognito check_token_expiration?
        # Just blindly verify or renew
        if user.id_token:
            # Simple expiry check via claims
            claims = user.id_claims
            exp = claims.get("exp", 0)
            now = datetime.now(UTC).timestamp()
            if now > exp - 60:  # buffer
                await user.renew_access_token()
        else:
            await user.renew_access_token()
    except Exception:
        await user.renew_access_token()

    # Get AWS credentials
    creds = await user.get_aws_credentials()

    # Sign URL
    signed_url = sigv4_sign_mqtt_url(creds)

    return (signed_url, user)


# =============================================================================
# MQTT URL Signing
# =============================================================================


def sigv4_sign_mqtt_url(aws_credentials: dict[str, Any]) -> str:
    """Sign MQTT WebSocket URL using AWS SigV4.

    Mysa uses an unusual signing approach where the session token is added
    AFTER signing rather than being included in the signed URL.

    Args:
        aws_credentials: AWS credentials dict with access_key, secret_key, session_token

    Returns:
        Signed MQTT WebSocket URL

    """
    # pylint: disable=too-many-locals
    # Justification: Auth flow requires handling many token parameters.
    # Parse URL
    method = "GET"
    service = "iotdevicegateway"
    host = MQTT_WS_HOST
    canonical_uri = "/mqtt"

    # Create timestamp
    t = datetime.now(UTC)
    amz_date = t.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = t.strftime("%Y%m%d")

    # Create canonical query string (without session token for signing)
    canonical_querystring = urlencode(
        {
            "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
            "X-Amz-Credential": (
                f"{aws_credentials['access_key']}/{date_stamp}/{REGION}/{service}/aws4_request"
            ),
            "X-Amz-Date": amz_date,
            "X-Amz-SignedHeaders": "host",
        }
    )

    # Create canonical headers
    canonical_headers = f"host:{host}\n"
    signed_headers = "host"

    # Create payload hash (empty for GET)
    payload_hash = hashlib.sha256(b"").hexdigest()

    # Create canonical request
    canonical_request = (
        f"{method}\n{canonical_uri}\n{canonical_querystring}\n"
        f"{canonical_headers}\n{signed_headers}\n{payload_hash}"
    )

    # Create string to sign
    algorithm = "AWS4-HMAC-SHA256"
    credential_scope = f"{date_stamp}/{REGION}/{service}/aws4_request"
    string_to_sign = (
        f"{algorithm}\n{amz_date}\n{credential_scope}\n"
        f"{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
    )

    # Calculate signature
    def _sign(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    k_date = _sign(("AWS4" + aws_credentials["secret_key"]).encode("utf-8"), date_stamp)
    k_region = hmac.new(k_date, REGION.encode("utf-8"), hashlib.sha256).digest()
    k_service = hmac.new(k_region, service.encode("utf-8"), hashlib.sha256).digest()
    k_signing = hmac.new(k_service, b"aws4_request", hashlib.sha256).digest()

    signature = hmac.new(
        k_signing, string_to_sign.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    # Add signature to query string
    signed_querystring = canonical_querystring + f"&X-Amz-Signature={signature}"

    # Add session token AFTER signing (Mysa's unusual approach)
    # Token must be URL encoded as it contains special characters
    encoded_token = quote(aws_credentials["session_token"], safe="")
    signed_querystring += f"&X-Amz-Security-Token={encoded_token}"

    # IMPORTANT: Ensure host is correct in final URL (should be a3q...)
    return f"wss://{host}{canonical_uri}?{signed_querystring}"
