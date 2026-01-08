import configparser
import getpass
import logging
import os
from time import time
from typing import Optional

import jwt
import pycognito.exceptions
from botocore.exceptions import ClientError

from .aws import boto3, botocore, Cognito
from . import mysa_stuff

logger = logging.getLogger(__name__)

CONFIG_FILE = '~/.config/mysotherm'

def authenticate(
    user: Optional[str] = None,
    cf: str = CONFIG_FILE,
    bsess: Optional[boto3.session.Session] = None,
    writeback: bool = True,
):
    try:
        return load_credentials(user, cf, bsess, writeback)
    except NotImplementedError:
        print(f'No Mysa login credentials found in {cf}' + ('' if user is None else f' for user {user!r}'))
        while True:
            try:
                user_ = input('Username: ') if user is None else user
                password = getpass.getpass('Password: ')
                return login(user_, password, bsess, (cf if writeback else None))
            except ClientError as exc:
                code = exc.response['Error']['Code']
                if code == 'UserNotFoundException':
                    if user is not None:
                        raise NotImplementedError(f'User account {user!r} does not exist') from exc
                    print('Username does not exist')
                elif code == 'NotAuthorizedException':
                    print('Incorrect username or password')
                else:
                    raise


def load_credentials(
    user: Optional[str] = None,
    cf: str = CONFIG_FILE,
    bsess: Optional[boto3.session.Session] = None,
    writeback: bool = True
):
    config = configparser.ConfigParser()
    cf = os.path.expanduser(cf)
    try:
        config.read(cf)
    except configparser.Error as exc:
        raise NotImplementedError(f"Could not read config file {cf!r}") from exc

    if user is None:
        section = next((s for s in config.sections() if s.startswith('mysa:')), None)
        if section is None:
            raise NotImplementedError(f'Did not find any section named "mysa:USERNAME" in config file {cf!r}')
        user = section[5:] #.removeprefix('mysa:')
        logger.debug(f'Using credentials from section {section!r} of config file {cf!r}')
    else:
        section = f'mysa:{user}'

    id_token = config.get(section, 'id_token', fallback=None)
    refresh_token = config.get(section, 'refresh_token', fallback=None)
    if not (id_token or refresh_token):
        raise NotImplementedError(f'Did not find id_token and/or refresh_token in section {section!r} of config file {cf!r}')

    # Authenticate with pycognito
    u = Cognito(
        user_pool_id=mysa_stuff.USER_POOL_ID,
        client_id=mysa_stuff.CLIENT_ID,
        id_token=id_token, refresh_token=refresh_token,
        session=bsess,
        pool_jwk=mysa_stuff.JWKS)

    try:
        u.verify_token(u.id_token, "id_token", "id")
    except (pycognito.TokenVerificationException, jwt.exceptions.PyJWTError):
        try:
            old = dict(id_token=u.id_token, access_token=u.access_token, refresh_token=u.refresh_token)
            u.renew_access_token()  # despite the name, this also renews the id_token
        except ClientError as exc:
            code = exc.response['Error']['Code']
            if code == 'NotAuthorizedException':
                raise NotImplementedError('New login needed because refresh_token has expired.')
            else:
                raise
        else:
            refreshed = [tn for tn, oldt in old.items() if oldt != getattr(u, tn)]
            logger.debug(f'Successfully refreshed {", ".join(refreshed)} for user {user!r}')
            if writeback:
                write_credentials(cf, u)
    else:
        # FIXME: What if it has been revoked prematurely. How can we check?
        logger.debug(f'Using unexpired tokens for user {user!r}')
        u.token_type = 'Bearer'  # Shouldn't u.verify_token() do this?)

    assert u.id_claims['cognito:username'] == user, f"Expected user {user!r} but token is for user {u.id_claims['cognito:username']!r}"
    return u


def login(user: str, password: str, bsess: Optional[boto3.session.Session] = None, cf: Optional[str] = None):
    u = Cognito(
       user_pool_id=mysa_stuff.USER_POOL_ID,
       client_id=mysa_stuff.CLIENT_ID,
       username=user,
       session=bsess,
       pool_jwk=mysa_stuff.JWKS)
    u.authenticate(password=password)
    logger.debug('Successfully authenticated as user {user!r}')
    if cf:
        write_credentials(cf, u)
    return u


def write_credentials(cf: str, u: Cognito):
    config = configparser.ConfigParser()
    cf = os.path.expanduser(cf)
    user = u.id_claims["cognito:username"]
    try:
        config.read(cf)
    except configparser.Error as exc:
        logger.warning('Discarding unparseable contents of {cf!r}: {exc}')

    with open(cf, 'w') as cf:
        section = f'mysa:{user}'
        if not config.has_section(section):
            config.add_section(section)
        config.set(section, 'id_token', u.id_token)
        config.set(section, 'refresh_token', u.refresh_token)
        config.write(cf)
    logger.info(f'Successfully wrote credentials for user {user!r} to {cf.name!r}')
