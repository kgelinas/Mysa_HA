"""
Mysa Authentication Module

Async authentication and AWS utilities for Mysa devices using boto3.

This module handles:
1. Cognito User Pool authentication (SRP)
2. AWS Credential retrieval (Cognito Identity)
3. AWS SigV4 signing for MQTT WebSocket connection
"""
from __future__ import annotations

import logging
import asyncio
import base64
import hashlib
import hmac
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlencode, quote

import boto3
from jose import jwt
from pycognito import Cognito


_LOGGER = logging.getLogger(__name__)

# =============================================================================
# Mysa AWS Configuration Constants
# =============================================================================

REGION = 'us-east-1'
"""Region for Mysa AWS infrastructure"""

JWKS = {
    "keys": [
        {
            # pylint: disable=line-too-long
            "alg": "RS256",
            "e": "AQAB",
            "kid": "udQ2TtD4g3Jc3dORobozGYu/T3qqcCtJonq0dwcrF8g=",
            "kty": "RSA",
            "n": "pwNwcNWr0CWijS_RlmooyzRq5Ud5GBDXKiTtS_4TV9MkXmxctKwiLFa_wnWsPw2B_RyQ6aY06de1qzylabuGcDQBpWFjmSWBoMiAFa2Facbhr4RnElLrs5MZTI3KZPVQlQaL0vvOERWC-3qe3HIG3EeaPyciSXS4aB2ldZCdLd2vtVJNwlzroqKiptXay9AeyQwiF6Tk2CXq4XZ3bcC5sFl53XjofoXXyZCrkBDjHBppE9Rhm0aw7u3DSozPbkiAEK-x92xQZ-Ymrl1eTLL4J08KiBdog2gVWYJqM9DdJ1T0rTBNXxNKgpnP9M83KnN8ViRgayBfLlyLpOOFaFK5lw",
            "use": "sig"
        },
        {
            # pylint: disable=line-too-long
            "alg": "RS256",
            "e": "AQAB",
            "kid": "f5vP7g+ehnb4PP+90i1WVsnUNfccQZVReBmaRvrHga0=",
            "kty": "RSA",
            "n": "nKGdPVq3wzz8Cy8tLwZ7OP44avSrNf-fcvqLV-lRG-9ziZavn4L7an2KZy_MDmdxBSekVDUoERAJNhNRlLFVRt_ialnUwkuZw0hkzeVyRT50-jE1bieF4I_zjOm7t_QhJTMoLG2KuDZcaGZa5RpDXZJGwPGKxcFjpH_VwgxFDwlTYPc2BjofuW8OwKNdm1CMNstG94pxGZoRuak_wd3Sg20DXH1c43kmHCiy4Ish-3oVHYMhVNv-pra02HXr-fJv8Rd7E0nVfw_Iki8MfWE6C5NunMCx74rigHbMMKZrzQtnB4EdxlcqZWjkC_5Qd1AhM6-gYchXMCKq18COrPPR1w",
            "use": "sig"
        }
    ]
}
"""Well-known JWKs for Mysa's Cognito IDP user pool (cached)"""

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
    'user-agent': 'okhttp/4.11.0',
    'accept': 'application/json',
    'accept-encoding': 'gzip',
}
"""HTTP headers matching Mysa Android app"""

BASE_URL = 'https://app-prod.mysa.cloud'
"""Base URL for Mysa's REST API"""


# =============================================================================
# Cognito User Class
# =============================================================================

class CognitoUser:
    """Represents an authenticated Cognito user with tokens and AWS credentials."""

    def __init__(
        self,
        username: str,
        id_token: str,
        access_token: str,
        refresh_token: str,
    ):
        self.username = username
        self.id_token = id_token
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.id_claims: Optional[dict] = None
        self.aws_credentials: Optional[dict] = None

        # Decode ID token to get claims
        if id_token:
            self.id_claims = jwt.get_unverified_claims(id_token)

    def verify_token(self, token: str, token_use: str) -> dict:
        """Verify JWT token signature and claims."""
        # Get kid from token header
        headers = jwt.get_unverified_header(token)
        kid = headers['kid']

        # Find matching key in JWKS
        key = None
        for k in JWKS['keys']:
            if k['kid'] == kid:
                key = k
                break

        if not key:
            raise ValueError(f"Public key not found for kid: {kid}")

        # Verify token
        claims = jwt.decode(
            token,
            key,
            algorithms=['RS256'],
            audience=CLIENT_ID if token_use == 'id' else None,
            options={'verify_aud': token_use == 'id'}
        )

        # Verify token_use claim
        if claims.get('token_use') != token_use:
            raise ValueError(
                f"Token use mismatch: expected {token_use}, got {claims.get('token_use')}"
            )

        return claims

    async def renew_access_token(self) -> None:
        """Refresh the access token using the refresh token."""
        def _refresh():
            client = boto3.client('cognito-idp', region_name=REGION)
            return client.initiate_auth(
                ClientId=CLIENT_ID,
                AuthFlow='REFRESH_TOKEN_AUTH',
                AuthParameters={
                    'REFRESH_TOKEN': self.refresh_token
                }
            )

        loop = asyncio.get_running_loop()
        try:
            response = await loop.run_in_executor(None, _refresh)

            auth_result = response['AuthenticationResult']
            self.id_token = auth_result['IdToken']
            self.access_token = auth_result['AccessToken']
            # Update claims
            if self.id_token:
                self.id_claims = jwt.get_unverified_claims(self.id_token)

            _LOGGER.debug("Successfully renewed access token for %s", self.username)
        except Exception as e:

            _LOGGER.error("Failed to renew access token: %s", e)
            raise

    async def get_aws_credentials(self, identity_id: Optional[str] = None) -> dict:
        """Get AWS credentials from Cognito Identity pool."""
        # Build logins dict
        assert self.id_claims is not None
        assert self.id_claims['iss'].startswith('https://')
        logins = {self.id_claims['iss'][8:]: self.id_token}

        def _get_credentials():
            client = boto3.client('cognito-identity', region_name=REGION)

            # Get identity ID if not provided
            id_id = identity_id
            if not id_id:
                resp_id = client.get_id(
                    IdentityPoolId=IDENTITY_POOL_ID,
                    Logins=logins
                )
                id_id = resp_id['IdentityId']

            resp_creds = client.get_credentials_for_identity(
                IdentityId=id_id,
                Logins=logins
            )

            return id_id, resp_creds

        loop = asyncio.get_running_loop()
        try:
            id_id, response = await loop.run_in_executor(None, _get_credentials)

            credentials = response['Credentials']
            self.aws_credentials = {
                'access_key': credentials['AccessKeyId'],
                'secret_key': credentials['SecretKey'],
                'session_token': credentials['SessionToken'],
                'expiration': credentials['Expiration'],
                'identity_id': id_id
            }
            return self.aws_credentials
        except Exception as e:
            _LOGGER.error("Failed to get AWS credentials: %s", e)
            raise


# =============================================================================
# Cognito Authentication Functions
# =============================================================================

def _compute_secret_hash(username: str, client_id: str, client_secret: str) -> str:
    """Compute SECRET_HASH for Cognito authentication."""
    message = bytes(username + client_id, 'utf-8')
    secret = bytes(client_secret, 'utf-8')
    dig = hmac.new(secret, msg=message, digestmod=hashlib.sha256).digest()
    return base64.b64encode(dig).decode()


async def login(username: str, password: str) -> CognitoUser:
    """
    Authenticate with Mysa using email and password.

    Args:
        username: Mysa account email
        password: Mysa account password

    Returns:
        Authenticated CognitoUser object
    """

    def _authenticate():
        u = Cognito(USER_POOL_ID, CLIENT_ID, username=username)
        u.authenticate(password=password)
        return u

    loop = asyncio.get_running_loop()

    try:
        # Run synchronous SRP authentication in executor
        u = await loop.run_in_executor(None, _authenticate)
    except Exception as e:
        _LOGGER.error("Authentication failed: %s", e)
        raise

    user = CognitoUser(
        username=username,
        id_token=u.id_token,
        access_token=u.access_token,
        refresh_token=u.refresh_token
    )

    _LOGGER.debug('Successfully authenticated as user %s', username)
    return user


# =============================================================================
# MQTT URL Signing
# =============================================================================

def sigv4_sign_mqtt_url(aws_credentials: dict) -> str:
    """
    Sign MQTT WebSocket URL using AWS SigV4.

    Mysa uses an unusual signing approach where the session token is added
    AFTER signing rather than being included in the signed URL.

    Args:
        aws_credentials: AWS credentials dict with access_key, secret_key, session_token

    Returns:
        Signed MQTT WebSocket URL
    """
    # pylint: disable=too-many-locals
    # Parse URL
    method = 'GET'
    service = 'iotdevicegateway'
    host = MQTT_WS_HOST
    canonical_uri = '/mqtt'

    # Create timestamp
    t = datetime.now(timezone.utc)
    amz_date = t.strftime('%Y%m%dT%H%M%SZ')
    date_stamp = t.strftime('%Y%m%d')

    # Create canonical query string (without session token for signing)
    canonical_querystring = urlencode({
        'X-Amz-Algorithm': 'AWS4-HMAC-SHA256',
        'X-Amz-Credential':
            f"{aws_credentials['access_key']}/{date_stamp}/{REGION}/{service}/aws4_request",
        'X-Amz-Date': amz_date,
        'X-Amz-SignedHeaders': 'host',
    })

    # Create canonical headers
    canonical_headers = f'host:{host}\n'
    signed_headers = 'host'

    # Create payload hash (empty for GET)
    payload_hash = hashlib.sha256(b'').hexdigest()

    # Create canonical request
    canonical_request = (
        f"{method}\n{canonical_uri}\n{canonical_querystring}\n"
        f"{canonical_headers}\n{signed_headers}\n{payload_hash}"
    )

    # Create string to sign
    algorithm = 'AWS4-HMAC-SHA256'
    credential_scope = f"{date_stamp}/{REGION}/{service}/aws4_request"
    string_to_sign = (
        f"{algorithm}\n{amz_date}\n{credential_scope}\n"
        f"{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
    )

    # Calculate signature
    def _sign(key, msg):
        return hmac.new(key, msg.encode('utf-8'), hashlib.sha256).digest()

    k_date = _sign(('AWS4' + aws_credentials['secret_key']).encode('utf-8'), date_stamp)
    k_region = hmac.new(k_date, REGION.encode('utf-8'), hashlib.sha256).digest()
    k_service = hmac.new(k_region, service.encode('utf-8'), hashlib.sha256).digest()
    k_signing = hmac.new(k_service, b'aws4_request', hashlib.sha256).digest()

    signature = hmac.new(k_signing, string_to_sign.encode('utf-8'), hashlib.sha256).hexdigest()

    # Add signature to query string
    signed_querystring = canonical_querystring + f'&X-Amz-Signature={signature}'

    # Add session token AFTER signing (Mysa's unusual approach)
    # Token must be URL encoded as it contains special characters
    encoded_token = quote(aws_credentials["session_token"], safe='')
    signed_querystring += f'&X-Amz-Security-Token={encoded_token}'

    return f'wss://{host}{canonical_uri}?{signed_querystring}'


async def refresh_and_sign_url(user: CognitoUser) -> tuple[str, CognitoUser]:
    """
    Refresh user tokens if needed and return signed MQTT URL.

    Args:
        user: CognitoUser object

    Returns:
        Tuple of (signed_url, user_object)
    """
    # Refresh token if needed
    try:
        user.verify_token(user.id_token, 'id')
    except Exception:
        await user.renew_access_token()

    # Get AWS credentials
    await user.get_aws_credentials()

    # Sign URL
    signed_url = sigv4_sign_mqtt_url(user.aws_credentials)

    return (signed_url, user)
