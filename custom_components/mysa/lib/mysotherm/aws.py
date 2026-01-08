import os
from functools import wraps
from typing import Optional

# boto3 is stupid AF and by default it wastes 1 second trying to connect to EC2 metadata
# every single time you run it, unless you set these environment variables
# https://docs.aws.amazon.com/cli/v1/userguide/cli-configure-envvars.html
#
# There's lots of inconsistent caching in boto3. For semi-sanity, these environment
# variables need to be set before importing boto3 and botocore, and persisted for
# as long as new boto3 sessions may be created.
os.environ['AWS_EC2_METADATA_DISABLED'] = 'true'        # <-- only works if boto3 hasn't yet been imported 🤬
#os.environ['AWS_METADATA_SERVICE_NUM_ATTEMPTS'] = '0'  # <-- works even after boto3 imported
#os.environ['AWS_METADATA_SERVICE_TIMEOUT'] = '0'       # <-- redundant, unnecessary
import boto3, botocore

import pycognito

class Cognito(pycognito.Cognito):
    """
    Upstream Pycognito handles the 'cognito-idp' side of things, but we need to handle the
    'cognito-identity' side as well (to get AWS API credentials).
    """

    @wraps(pycognito.Cognito.__init__)
    def __init__(self,
        session: Optional[botocore.session.Session] = None,
        pool_jwk: Optional[dict] = None,
        *args, **kwargs
    ):
        self._session = session
        super().__init__(*args, session=session, **kwargs)
        self.pool_jwk = pool_jwk

    def get_credentials(self,
        identity_pool_id: str = None,
        identity_id: str = None,
        region: Optional[str] = None,
    ) -> botocore.credentials.Credentials:
        if not identity_pool_id and not identity_id:
            raise ValueError("Either identity_pool_id or identity_id must be specified")

        if region is None:
            region = self.user_pool_region

        if self._session:
            client = self._session.client('cognito-identity', region_name=region)
        else:
            client = boto3.client('cognito-identity', region_name=region)

        # https://boto3.amazonaws.com/v1/documentation/api/1.26.93/reference/services/cognito-identity/client/get_id.html
        # "cognito-idp.<region>.amazonaws.com/<YOUR_USER_POOL_ID>"
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
                self.renew_access_token()  # despite the name, this also renews the id_token
            return self.get_credentials(identity_id=identity_id, region=region)

        return botocore.credentials.RefreshableCredentials(
            c['AccessKeyId'],
            c['SecretKey'],
            c['SessionToken'],
            c['Expiration'],
            method='cognito-idp',
            refresh_using=_refresh_credentials)
