"""
Mysa Authentication Module

Consolidated authentication and AWS utilities for Mysa devices.
Handles Cognito authentication, token management, and MQTT URL signing.

Based on mysotherm (https://github.com/dlenski/mysotherm) by @dlenski
"""
from __future__ import annotations
import os
import logging
from functools import wraps
from time import time
from typing import Optional, Any, cast

import requests  # type: ignore[import-untyped]

# boto3 wastes 1 second trying to connect to EC2 metadata unless disabled
os.environ['AWS_EC2_METADATA_DISABLED'] = 'true'
# TODO: Refactor imports to standard position
import boto3
import botocore
import botocore.credentials
import botocore.auth
import botocore.awsrequest
import pycognito
import pycognito.exceptions


_LOGGER = logging.getLogger(__name__)

# =============================================================================
# Mysa AWS Configuration Constants
# =============================================================================

REGION = 'us-east-1'
"""Region for Mysa AWS infrastructure"""

JWKS = {"keys":[{"alg":"RS256","e":"AQAB","kid":"udQ2TtD4g3Jc3dORobozGYu/T3qqcCtJonq0dwcrF8g=","kty":"RSA","n":"pwNwcNWr0CWijS_RlmooyzRq5Ud5GBDXKiTtS_4TV9MkXmxctKwiLFa_wnWsPw2B_RyQ6aY06de1qzylabuGcDQBpWFjmSWBoMiAFa2Facbhr4RnElLrs5MZTI3KZPVQlQaL0vvOERWC-3qe3HIG3EeaPyciSXS4aB2ldZCdLd2vtVJNwlzroqKiptXay9AeyQwiF6Tk2CXq4XZ3bcC5sFl53XjofoXXyZCrkBDjHBppE9Rhm0aw7u3DSozPbkiAEK-x92xQZ-Ymrl1eTLL4J08KiBdog2gVWYJqM9DdJ1T0rTBNXxNKgpnP9M83KnN8ViRgayBfLlyLpOOFaFK5lw","use":"sig"},{"alg":"RS256","e":"AQAB","kid":"f5vP7g+ehnb4PP+90i1WVsnUNfccQZVReBmaRvrHga0=","kty":"RSA","n":"nKGdPVq3wzz8Cy8tLwZ7OP44avSrNf-fcvqLV-lRG-9ziZavn4L7an2KZy_MDmdxBSekVDUoERAJNhNRlLFVRt_ialnUwkuZw0hkzeVyRT50-jE1bieF4I_zjOm7t_QhJTMoLG2KuDZcaGZa5RpDXZJGwPGKxcFjpH_VwgxFDwlTYPc2BjofuW8OwKNdm1CMNstG94pxGZoRuak_wd3Sg20DXH1c43kmHCiy4Ish-3oVHYMhVNv-pra02HXr-fJv8Rd7E0nVfw_Iki8MfWE6C5NunMCx74rigHbMMKZrzQtnB4EdxlcqZWjkC_5Qd1AhM6-gYchXMCKq18COrPPR1w","use":"sig"}]}  # TODO: Break long line
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
# Cognito Authentication
# =============================================================================

class Cognito(pycognito.Cognito):
    """
    Extended Cognito class that handles both cognito-idp (user auth) and
    cognito-identity (AWS credentials) sides of authentication.
    """

    @wraps(pycognito.Cognito.__init__)  # type: ignore[misc]
    def __init__(self,
        session: Optional[boto3.session.Session] = None,
        pool_jwk: Optional[dict] = None,
        **kwargs
    ):

        self._session = session
        super().__init__(session=session, **kwargs)
        self.pool_jwk = pool_jwk

    def get_credentials(self,
        identity_pool_id: Optional[str] = None,
        identity_id: Optional[str] = None,
        region: Optional[str] = None,
    ) -> botocore.credentials.Credentials:
        """Get AWS credentials from Cognito Identity pool."""
        if not identity_pool_id and not identity_id:
            raise ValueError("Either identity_pool_id or identity_id must be specified")

        if region is None:
            region = self.user_pool_region

        if self._session:
            client = self._session.client('cognito-identity', region_name=region)
        else:
            client = boto3.client('cognito-identity', region_name=region)
        
        # Cast to Any because Pyrefly doesn't know specific service methods
        client = cast(Any, client)

        # pylint: disable=unsubscriptable-object
        # pylint: disable=unsubscriptable-object
        assert self.id_claims is not None
        assert self.id_claims['iss'].startswith('https://')
        logins = {self.id_claims['iss'][8:]: self.id_token}

        if not identity_id:
            r = client.get_id(IdentityPoolId=identity_pool_id, Logins=logins)
            identity_id = r['IdentityId']
        r = client.get_credentials_for_identity(IdentityId=identity_id, Logins=logins)
        c = r['Credentials']

        def _refresh_credentials():
            try:
                self.verify_token(self.id_token, "id_token", "id")
            except pycognito.TokenVerificationException:
                self.renew_access_token()
            return self.get_credentials(identity_id=identity_id, region=region)

        return botocore.credentials.RefreshableCredentials(
            c['AccessKeyId'],
            c['SecretKey'],
            c['SessionToken'],
            c['Expiration'],
            method='cognito-idp',
            refresh_using=_refresh_credentials)


def login(user: str, password: str, bsess: Optional[boto3.session.Session] = None) -> Cognito:
    """
    Authenticate with Mysa using email and password.

    Args:
        user: Mysa account email
        password: Mysa account password
        bsess: Optional boto3 session

    Returns:
        Authenticated Cognito user object
    """
    u = Cognito(
       user_pool_id=USER_POOL_ID,
       client_id=CLIENT_ID,
       username=user,
       session=bsess,
       pool_jwk=JWKS)
    u.authenticate(password=password)
    _LOGGER.debug('Successfully authenticated as user %s', user)
    return u


# =============================================================================
# HTTP Authentication Helper
# =============================================================================

def auther(u: Cognito):
    """
    Create a requests auth handler that auto-refreshes tokens.

    Args:
        u: Authenticated Cognito user object

    Returns:
        Auth callable for requests.Session
    """
    def f(request: requests.PreparedRequest) -> requests.PreparedRequest:
        # pylint: disable=unsubscriptable-object
        if u.id_claims and time() > u.id_claims['exp'] - 5:
            u.renew_access_token()
        if u.id_token:
            request.headers['authorization'] = u.id_token
        return request
    return f


# =============================================================================
# MQTT URL Signing
# =============================================================================

def sigv4_sign_mqtt_url(cred: botocore.credentials.Credentials) -> str:
    """
    Sign MQTT WebSocket URL using AWS SigV4.

    Mysa uses an unusual signing approach where the session token is added
    AFTER signing rather than being included in the signed URL.

    Args:
        cred: AWS credentials from Cognito

    Returns:
        Signed MQTT WebSocket URL
    """
    req = botocore.awsrequest.AWSRequest('GET', MQTT_WS_URL)
    # Strip session token before signing (Mysa's unusual approach)
    botocore.auth.SigV4QueryAuth(
        credentials=cred.get_frozen_credentials()._replace(token=None),
        service_name='iotdevicegateway',
        region_name='us-east-1').add_auth(req)
    # Add session token after signing
    req.params['X-Amz-Security-Token'] = cred.token
    return req.prepare().url
