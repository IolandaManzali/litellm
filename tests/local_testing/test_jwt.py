#### What this tests ####
#    Unit tests for JWT-Auth

import asyncio
import os
import random
import sys
import time
import traceback
import uuid

from dotenv import load_dotenv

load_dotenv()
import os

sys.path.insert(
    0, os.path.abspath("../..")
)  # Adds the parent directory to the system path
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request

import litellm
from litellm.caching.caching import DualCache
from litellm.proxy._types import LiteLLM_JWTAuth, LiteLLM_UserTable, LiteLLMRoutes
from litellm.proxy.auth.handle_jwt import JWTHandler
from litellm.proxy.management_endpoints.team_endpoints import new_team
from litellm.proxy.proxy_server import chat_completion

public_key = {
    "kty": "RSA",
    "e": "AQAB",
    "n": "qIgOQfEVrrErJC0E7gsHXi6rs_V0nyFY5qPFui2-tv0o4CwpwDzgfBtLO7o_wLiguq0lnu54sMT2eLNoRiiPuLvv6bg7Iy1H9yc5_4Jf5oYEOrqN5o9ZBOoYp1q68Pv0oNJYyZdGu5ZJfd7V4y953vB2XfEKgXCsAkhVhlvIUMiDNKWoMDWsyb2xela5tRURZ2mJAXcHfSC_sYdZxIA2YYrIHfoevq_vTlaz0qVSe_uOKjEpgOAS08UUrgda4CQL11nzICiIQzc6qmjIQt2cjzB2D_9zb4BYndzEtfl0kwAT0z_I85S3mkwTqHU-1BvKe_4MG4VG3dAAeffLPXJyXQ",
    "alg": "RS256",
}


def test_load_config_with_custom_role_names():
    config = {
        "general_settings": {
            "litellm_proxy_roles": {"admin_jwt_scope": "litellm-proxy-admin"}
        }
    }
    proxy_roles = LiteLLM_JWTAuth(
        **config.get("general_settings", {}).get("litellm_proxy_roles", {})
    )

    print(f"proxy_roles: {proxy_roles}")

    assert proxy_roles.admin_jwt_scope == "litellm-proxy-admin"


# test_load_config_with_custom_role_names()


@pytest.mark.asyncio
async def test_token_single_public_key():
    import jwt

    jwt_handler = JWTHandler()
    backend_keys = {
        "keys": [
            {
                "kty": "RSA",
                "use": "sig",
                "e": "AQAB",
                "n": "qIgOQfEVrrErJC0E7gsHXi6rs_V0nyFY5qPFui2-tv0o4CwpwDzgfBtLO7o_wLiguq0lnu54sMT2eLNoRiiPuLvv6bg7Iy1H9yc5_4Jf5oYEOrqN5o9ZBOoYp1q68Pv0oNJYyZdGu5ZJfd7V4y953vB2XfEKgXCsAkhVhlvIUMiDNKWoMDWsyb2xela5tRURZ2mJAXcHfSC_sYdZxIA2YYrIHfoevq_vTlaz0qVSe_uOKjEpgOAS08UUrgda4CQL11nzICiIQzc6qmjIQt2cjzB2D_9zb4BYndzEtfl0kwAT0z_I85S3mkwTqHU-1BvKe_4MG4VG3dAAeffLPXJyXQ",
                "alg": "RS256",
            }
        ]
    }

    # set cache
    cache = DualCache()

    await cache.async_set_cache(key="litellm_jwt_auth_keys", value=backend_keys["keys"])

    jwt_handler.user_api_key_cache = cache

    public_key = await jwt_handler.get_public_key(kid=None)

    assert public_key is not None
    assert isinstance(public_key, dict)
    assert (
        public_key["n"]
        == "qIgOQfEVrrErJC0E7gsHXi6rs_V0nyFY5qPFui2-tv0o4CwpwDzgfBtLO7o_wLiguq0lnu54sMT2eLNoRiiPuLvv6bg7Iy1H9yc5_4Jf5oYEOrqN5o9ZBOoYp1q68Pv0oNJYyZdGu5ZJfd7V4y953vB2XfEKgXCsAkhVhlvIUMiDNKWoMDWsyb2xela5tRURZ2mJAXcHfSC_sYdZxIA2YYrIHfoevq_vTlaz0qVSe_uOKjEpgOAS08UUrgda4CQL11nzICiIQzc6qmjIQt2cjzB2D_9zb4BYndzEtfl0kwAT0z_I85S3mkwTqHU-1BvKe_4MG4VG3dAAeffLPXJyXQ"
    )


@pytest.mark.parametrize("audience", [None, "litellm-proxy"])
@pytest.mark.asyncio
async def test_valid_invalid_token(audience):
    """
    Tests
    - valid token
    - invalid token
    """
    import json

    import jwt
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    os.environ.pop("JWT_AUDIENCE", None)
    if audience:
        os.environ["JWT_AUDIENCE"] = audience

    # Generate a private / public key pair using RSA algorithm
    key = rsa.generate_private_key(
        public_exponent=65537, key_size=2048, backend=default_backend()
    )
    # Get private key in PEM format
    private_key = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    # Get public key in PEM format
    public_key = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    public_key_obj = serialization.load_pem_public_key(
        public_key, backend=default_backend()
    )

    # Convert RSA public key object to JWK (JSON Web Key)
    public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(public_key_obj))

    assert isinstance(public_jwk, dict)

    # set cache
    cache = DualCache()

    await cache.async_set_cache(key="litellm_jwt_auth_keys", value=[public_jwk])

    jwt_handler = JWTHandler()

    jwt_handler.user_api_key_cache = cache

    # VALID TOKEN
    ## GENERATE A TOKEN
    # Assuming the current time is in UTC
    expiration_time = int((datetime.utcnow() + timedelta(minutes=10)).timestamp())

    payload = {
        "sub": "user123",
        "exp": expiration_time,  # set the token to expire in 10 minutes
        "scope": "litellm-proxy-admin",
        "aud": audience,
    }

    # Generate the JWT token
    # But before, you should convert bytes to string
    private_key_str = private_key.decode("utf-8")
    token = jwt.encode(payload, private_key_str, algorithm="RS256")

    ## VERIFY IT WORKS

    # verify token

    response = await jwt_handler.auth_jwt(token=token)

    assert response is not None
    assert isinstance(response, dict)

    print(f"response: {response}")

    # INVALID TOKEN
    ## GENERATE A TOKEN
    # Assuming the current time is in UTC
    expiration_time = int((datetime.utcnow() + timedelta(minutes=10)).timestamp())

    payload = {
        "sub": "user123",
        "exp": expiration_time,  # set the token to expire in 10 minutes
        "scope": "litellm-NO-SCOPE",
        "aud": audience,
    }

    # Generate the JWT token
    # But before, you should convert bytes to string
    private_key_str = private_key.decode("utf-8")
    token = jwt.encode(payload, private_key_str, algorithm="RS256")

    ## VERIFY IT WORKS

    # verify token

    try:
        response = await jwt_handler.auth_jwt(token=token)
    except Exception as e:
        pytest.fail(f"An exception occurred - {str(e)}")


@pytest.fixture
def prisma_client():
    import litellm
    from litellm.proxy.proxy_cli import append_query_params
    from litellm.proxy.utils import PrismaClient, ProxyLogging

    proxy_logging_obj = ProxyLogging(user_api_key_cache=DualCache())

    ### add connection pool + pool timeout args
    params = {"connection_limit": 100, "pool_timeout": 60}
    database_url = os.getenv("DATABASE_URL")
    modified_url = append_query_params(database_url, params)
    os.environ["DATABASE_URL"] = modified_url

    # Assuming PrismaClient is a class that needs to be instantiated
    prisma_client = PrismaClient(
        database_url=os.environ["DATABASE_URL"], proxy_logging_obj=proxy_logging_obj
    )

    return prisma_client


@pytest.fixture
def team_token_tuple():
    import json
    import uuid

    import jwt
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from fastapi import Request
    from starlette.datastructures import URL

    import litellm
    from litellm.proxy._types import NewTeamRequest, UserAPIKeyAuth
    from litellm.proxy.proxy_server import user_api_key_auth

    # Generate a private / public key pair using RSA algorithm
    key = rsa.generate_private_key(
        public_exponent=65537, key_size=2048, backend=default_backend()
    )
    # Get private key in PEM format
    private_key = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    # Get public key in PEM format
    public_key = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    public_key_obj = serialization.load_pem_public_key(
        public_key, backend=default_backend()
    )

    # Convert RSA public key object to JWK (JSON Web Key)
    public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(public_key_obj))

    # VALID TOKEN
    ## GENERATE A TOKEN
    # Assuming the current time is in UTC
    expiration_time = int((datetime.utcnow() + timedelta(minutes=10)).timestamp())

    team_id = f"team123_{uuid.uuid4()}"
    payload = {
        "sub": "user123",
        "exp": expiration_time,  # set the token to expire in 10 minutes
        "scope": "litellm_team",
        "client_id": team_id,
        "aud": None,
    }

    # Generate the JWT token
    # But before, you should convert bytes to string
    private_key_str = private_key.decode("utf-8")

    ## team token
    token = jwt.encode(payload, private_key_str, algorithm="RS256")

    return team_id, token, public_jwk


@pytest.mark.parametrize("audience", [None, "litellm-proxy"])
@pytest.mark.asyncio
async def test_team_token_output(prisma_client, audience):
    import json
    import uuid

    import jwt
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from fastapi import Request
    from starlette.datastructures import URL

    import litellm
    from litellm.proxy._types import NewTeamRequest, UserAPIKeyAuth
    from litellm.proxy.proxy_server import user_api_key_auth

    setattr(litellm.proxy.proxy_server, "prisma_client", prisma_client)
    await litellm.proxy.proxy_server.prisma_client.connect()

    os.environ.pop("JWT_AUDIENCE", None)
    if audience:
        os.environ["JWT_AUDIENCE"] = audience

    # Generate a private / public key pair using RSA algorithm
    key = rsa.generate_private_key(
        public_exponent=65537, key_size=2048, backend=default_backend()
    )
    # Get private key in PEM format
    private_key = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    # Get public key in PEM format
    public_key = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    public_key_obj = serialization.load_pem_public_key(
        public_key, backend=default_backend()
    )

    # Convert RSA public key object to JWK (JSON Web Key)
    public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(public_key_obj))

    assert isinstance(public_jwk, dict)

    # set cache
    cache = DualCache()

    await cache.async_set_cache(key="litellm_jwt_auth_keys", value=[public_jwk])

    jwt_handler = JWTHandler()

    jwt_handler.user_api_key_cache = cache

    jwt_handler.litellm_jwtauth = LiteLLM_JWTAuth(team_id_jwt_field="client_id")

    # VALID TOKEN
    ## GENERATE A TOKEN
    # Assuming the current time is in UTC
    expiration_time = int((datetime.utcnow() + timedelta(minutes=10)).timestamp())

    team_id = f"team123_{uuid.uuid4()}"
    payload = {
        "sub": "user123",
        "exp": expiration_time,  # set the token to expire in 10 minutes
        "scope": "litellm_team",
        "client_id": team_id,
        "aud": audience,
    }

    # Generate the JWT token
    # But before, you should convert bytes to string
    private_key_str = private_key.decode("utf-8")

    ## team token
    token = jwt.encode(payload, private_key_str, algorithm="RS256")

    ## admin token
    payload = {
        "sub": "user123",
        "exp": expiration_time,  # set the token to expire in 10 minutes
        "scope": "litellm_proxy_admin",
        "aud": audience,
    }

    admin_token = jwt.encode(payload, private_key_str, algorithm="RS256")

    ## VERIFY IT WORKS

    # verify token

    response = await jwt_handler.auth_jwt(token=token)

    ## RUN IT THROUGH USER API KEY AUTH

    """
    - 1. Initial call should fail -> team doesn't exist
    - 2. Create team via admin token 
    - 3. 2nd call w/ same team -> call should succeed -> assert UserAPIKeyAuth object correctly formatted
    """

    bearer_token = "Bearer " + token

    request = Request(scope={"type": "http"})
    request._url = URL(url="/chat/completions")

    ## 1. INITIAL TEAM CALL - should fail
    # use generated key to auth in
    setattr(
        litellm.proxy.proxy_server,
        "general_settings",
        {
            "enable_jwt_auth": True,
        },
    )
    setattr(litellm.proxy.proxy_server, "jwt_handler", jwt_handler)
    try:
        result = await user_api_key_auth(request=request, api_key=bearer_token)
        pytest.fail("Team doesn't exist. This should fail")
    except Exception as e:
        pass

    ## 2. CREATE TEAM W/ ADMIN TOKEN - should succeed
    try:
        bearer_token = "Bearer " + admin_token

        request._url = URL(url="/team/new")
        result = await user_api_key_auth(request=request, api_key=bearer_token)
        await new_team(
            data=NewTeamRequest(
                team_id=team_id,
                tpm_limit=100,
                rpm_limit=99,
                models=["gpt-3.5-turbo", "gpt-4"],
            ),
            user_api_key_dict=result,
            http_request=Request(scope={"type": "http"}),
        )
    except Exception as e:
        pytest.fail(f"This should not fail - {str(e)}")

    ## 3. 2nd CALL W/ TEAM TOKEN - should succeed
    bearer_token = "Bearer " + token
    request._url = URL(url="/chat/completions")
    try:
        team_result: UserAPIKeyAuth = await user_api_key_auth(
            request=request, api_key=bearer_token
        )
    except Exception as e:
        pytest.fail(f"Team exists. This should not fail - {e}")

    ## 4. ASSERT USER_API_KEY_AUTH format (used for tpm/rpm limiting in parallel_request_limiter.py)

    assert team_result.team_tpm_limit == 100
    assert team_result.team_rpm_limit == 99
    assert team_result.team_models == ["gpt-3.5-turbo", "gpt-4"]


@pytest.mark.parametrize("audience", [None, "litellm-proxy"])
@pytest.mark.parametrize(
    "team_id_set, default_team_id",
    [(True, False), (False, True)],
)
@pytest.mark.parametrize("user_id_upsert", [True, False])
@pytest.mark.asyncio
async def aaaatest_user_token_output(
    prisma_client, audience, team_id_set, default_team_id, user_id_upsert
):
    import uuid

    args = locals()
    print(f"received args - {args}")
    if default_team_id:
        default_team_id = "team_id_12344_{}".format(uuid.uuid4())
    """
    - If user required, check if it exists
    - fail initial request (when user doesn't exist)
    - create user
    - retry -> it should pass now
    """
    import json
    import uuid

    import jwt
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from fastapi import Request
    from starlette.datastructures import URL

    import litellm
    from litellm.proxy._types import NewTeamRequest, NewUserRequest, UserAPIKeyAuth
    from litellm.proxy.management_endpoints.internal_user_endpoints import (
        new_user,
        user_info,
    )
    from litellm.proxy.proxy_server import user_api_key_auth

    setattr(litellm.proxy.proxy_server, "prisma_client", prisma_client)
    await litellm.proxy.proxy_server.prisma_client.connect()

    os.environ.pop("JWT_AUDIENCE", None)
    if audience:
        os.environ["JWT_AUDIENCE"] = audience

    # Generate a private / public key pair using RSA algorithm
    key = rsa.generate_private_key(
        public_exponent=65537, key_size=2048, backend=default_backend()
    )
    # Get private key in PEM format
    private_key = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    # Get public key in PEM format
    public_key = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    public_key_obj = serialization.load_pem_public_key(
        public_key, backend=default_backend()
    )

    # Convert RSA public key object to JWK (JSON Web Key)
    public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(public_key_obj))

    assert isinstance(public_jwk, dict)

    # set cache
    cache = DualCache()

    await cache.async_set_cache(key="litellm_jwt_auth_keys", value=[public_jwk])

    jwt_handler = JWTHandler()

    jwt_handler.user_api_key_cache = cache

    jwt_handler.litellm_jwtauth = LiteLLM_JWTAuth()

    jwt_handler.litellm_jwtauth.user_id_jwt_field = "sub"
    jwt_handler.litellm_jwtauth.team_id_default = default_team_id
    jwt_handler.litellm_jwtauth.user_id_upsert = user_id_upsert

    if team_id_set:
        jwt_handler.litellm_jwtauth.team_id_jwt_field = "client_id"

    # VALID TOKEN
    ## GENERATE A TOKEN
    # Assuming the current time is in UTC
    expiration_time = int((datetime.utcnow() + timedelta(minutes=10)).timestamp())

    team_id = f"team123_{uuid.uuid4()}"
    user_id = f"user123_{uuid.uuid4()}"
    payload = {
        "sub": user_id,
        "exp": expiration_time,  # set the token to expire in 10 minutes
        "scope": "litellm_team",
        "client_id": team_id,
        "aud": audience,
    }

    # Generate the JWT token
    # But before, you should convert bytes to string
    private_key_str = private_key.decode("utf-8")

    ## team token
    token = jwt.encode(payload, private_key_str, algorithm="RS256")

    ## admin token
    payload = {
        "sub": user_id,
        "exp": expiration_time,  # set the token to expire in 10 minutes
        "scope": "litellm_proxy_admin",
        "aud": audience,
    }

    admin_token = jwt.encode(payload, private_key_str, algorithm="RS256")

    ## VERIFY IT WORKS

    # verify token

    response = await jwt_handler.auth_jwt(token=token)

    ## RUN IT THROUGH USER API KEY AUTH

    """
    - 1. Initial call should fail -> team doesn't exist
    - 2. Create team via admin token 
    - 3. 2nd call w/ same team -> call should fail -> user doesn't exist
    - 4. Create user via admin token
    - 5. 3rd call w/ same team, same user -> call should succeed
    - 6. assert user api key auth format
    """

    bearer_token = "Bearer " + token

    request = Request(scope={"type": "http"})
    request._url = URL(url="/chat/completions")

    ## 1. INITIAL TEAM CALL - should fail
    # use generated key to auth in
    setattr(litellm.proxy.proxy_server, "general_settings", {"enable_jwt_auth": True})
    setattr(litellm.proxy.proxy_server, "jwt_handler", jwt_handler)
    try:
        result = await user_api_key_auth(request=request, api_key=bearer_token)
        pytest.fail("Team doesn't exist. This should fail")
    except Exception as e:
        pass

    ## 2. CREATE TEAM W/ ADMIN TOKEN - should succeed
    try:
        bearer_token = "Bearer " + admin_token

        request._url = URL(url="/team/new")
        result = await user_api_key_auth(request=request, api_key=bearer_token)
        await new_team(
            data=NewTeamRequest(
                team_id=team_id,
                tpm_limit=100,
                rpm_limit=99,
                models=["gpt-3.5-turbo", "gpt-4"],
            ),
            user_api_key_dict=result,
            http_request=Request(scope={"type": "http"}),
        )
        if default_team_id:
            await new_team(
                data=NewTeamRequest(
                    team_id=default_team_id,
                    tpm_limit=100,
                    rpm_limit=99,
                    models=["gpt-3.5-turbo", "gpt-4"],
                ),
                user_api_key_dict=result,
                http_request=Request(scope={"type": "http"}),
            )
    except Exception as e:
        pytest.fail(f"This should not fail - {str(e)}")

    ## 3. 2nd CALL W/ TEAM TOKEN - should fail
    bearer_token = "Bearer " + token
    request._url = URL(url="/chat/completions")
    try:
        team_result: UserAPIKeyAuth = await user_api_key_auth(
            request=request, api_key=bearer_token
        )
        if user_id_upsert == False:
            pytest.fail(f"User doesn't exist. this should fail")
    except Exception as e:
        pass

    ## 4. Create user
    if user_id_upsert:
        ## check if user already exists
        try:
            bearer_token = "Bearer " + admin_token

            request._url = URL(url="/team/new")
            result = await user_api_key_auth(request=request, api_key=bearer_token)
            await user_info(user_id=user_id)
        except Exception as e:
            pytest.fail(f"This should not fail - {str(e)}")
    else:
        try:
            bearer_token = "Bearer " + admin_token

            request._url = URL(url="/team/new")
            result = await user_api_key_auth(request=request, api_key=bearer_token)
            await new_user(
                data=NewUserRequest(
                    user_id=user_id,
                ),
            )
        except Exception as e:
            pytest.fail(f"This should not fail - {str(e)}")

    ## 5. 3rd call w/ same team, same user -> call should succeed
    bearer_token = "Bearer " + token
    request._url = URL(url="/chat/completions")
    try:
        team_result: UserAPIKeyAuth = await user_api_key_auth(
            request=request, api_key=bearer_token
        )
    except Exception as e:
        pytest.fail(f"Team exists. This should not fail - {e}")

    ## 6. ASSERT USER_API_KEY_AUTH format (used for tpm/rpm limiting in parallel_request_limiter.py AND cost tracking)

    if team_id_set or default_team_id is not None:
        assert team_result.team_tpm_limit == 100
        assert team_result.team_rpm_limit == 99
        assert team_result.team_models == ["gpt-3.5-turbo", "gpt-4"]
    assert team_result.user_id == user_id


@pytest.mark.parametrize("audience", [None, "litellm-proxy"])
@pytest.mark.asyncio
async def test_allowed_routes_admin(prisma_client, audience):
    """
    Add a check to make sure jwt proxy admin scope can access all allowed admin routes

    - iterate through allowed endpoints
    - check if admin passes user_api_key_auth for them
    """
    import json
    import uuid

    import jwt
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from fastapi import Request
    from starlette.datastructures import URL

    import litellm
    from litellm.proxy._types import NewTeamRequest, UserAPIKeyAuth
    from litellm.proxy.proxy_server import user_api_key_auth

    setattr(litellm.proxy.proxy_server, "prisma_client", prisma_client)
    await litellm.proxy.proxy_server.prisma_client.connect()

    os.environ.pop("JWT_AUDIENCE", None)
    if audience:
        os.environ["JWT_AUDIENCE"] = audience

    # Generate a private / public key pair using RSA algorithm
    key = rsa.generate_private_key(
        public_exponent=65537, key_size=2048, backend=default_backend()
    )
    # Get private key in PEM format
    private_key = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    # Get public key in PEM format
    public_key = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    public_key_obj = serialization.load_pem_public_key(
        public_key, backend=default_backend()
    )

    # Convert RSA public key object to JWK (JSON Web Key)
    public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(public_key_obj))

    assert isinstance(public_jwk, dict)

    # set cache
    cache = DualCache()

    await cache.async_set_cache(key="litellm_jwt_auth_keys", value=[public_jwk])

    jwt_handler = JWTHandler()

    jwt_handler.user_api_key_cache = cache

    jwt_handler.litellm_jwtauth = LiteLLM_JWTAuth(team_id_jwt_field="client_id")

    # VALID TOKEN
    ## GENERATE A TOKEN
    # Assuming the current time is in UTC
    expiration_time = int((datetime.utcnow() + timedelta(minutes=10)).timestamp())

    # Generate the JWT token
    # But before, you should convert bytes to string
    private_key_str = private_key.decode("utf-8")

    ## admin token
    payload = {
        "sub": "user123",
        "exp": expiration_time,  # set the token to expire in 10 minutes
        "scope": "litellm_proxy_admin",
        "aud": audience,
    }

    admin_token = jwt.encode(payload, private_key_str, algorithm="RS256")

    # verify token

    response = await jwt_handler.auth_jwt(token=admin_token)

    ## RUN IT THROUGH USER API KEY AUTH

    """
    - 1. Initial call should fail -> team doesn't exist
    - 2. Create team via admin token 
    - 3. 2nd call w/ same team -> call should succeed -> assert UserAPIKeyAuth object correctly formatted
    """

    bearer_token = "Bearer " + admin_token

    pseudo_routes = jwt_handler.litellm_jwtauth.admin_allowed_routes

    actual_routes = []
    for route in pseudo_routes:
        if route in LiteLLMRoutes.__members__:
            actual_routes.extend(LiteLLMRoutes[route].value)

    for route in actual_routes:
        request = Request(scope={"type": "http"})

        request._url = URL(url=route)

        ## 1. INITIAL TEAM CALL - should fail
        # use generated key to auth in
        setattr(
            litellm.proxy.proxy_server,
            "general_settings",
            {
                "enable_jwt_auth": True,
            },
        )
        setattr(litellm.proxy.proxy_server, "jwt_handler", jwt_handler)
        try:
            result = await user_api_key_auth(request=request, api_key=bearer_token)
        except Exception as e:
            raise e


import pytest


@pytest.mark.asyncio
async def test_team_cache_update_called():
    import litellm
    from litellm.proxy.proxy_server import user_api_key_cache

    # Use setattr to replace the method on the user_api_key_cache object
    cache = DualCache()

    setattr(
        litellm.proxy.proxy_server,
        "user_api_key_cache",
        cache,
    )

    with patch.object(cache, "async_get_cache", new=AsyncMock()) as mock_call_cache:
        cache.async_get_cache = mock_call_cache
        # Call the function under test
        await litellm.proxy.proxy_server.update_cache(
            token=None,
            user_id=None,
            end_user_id=None,
            team_id="1234",
            response_cost=20,
            parent_otel_span=None,
        )  # type: ignore

        await asyncio.sleep(3)
        mock_call_cache.assert_awaited_once()


@pytest.fixture
def public_jwt_key():
    import json

    import jwt
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    # Generate a private / public key pair using RSA algorithm
    key = rsa.generate_private_key(
        public_exponent=65537, key_size=2048, backend=default_backend()
    )
    # Get private key in PEM format
    private_key = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    # Get public key in PEM format
    public_key = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    public_key_obj = serialization.load_pem_public_key(
        public_key, backend=default_backend()
    )

    # Convert RSA public key object to JWK (JSON Web Key)
    public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(public_key_obj))

    return {"private_key": private_key, "public_jwk": public_jwk}


def mock_user_object(*args, **kwargs):
    print("Args: {}".format(args))
    print("kwargs: {}".format(kwargs))
    assert kwargs["user_id_upsert"] is True


@pytest.mark.parametrize(
    "user_email, should_work", [("ishaan@berri.ai", True), ("krrish@tassle.xyz", False)]
)
@pytest.mark.asyncio
async def test_allow_access_by_email(public_jwt_key, user_email, should_work):
    """
    Allow anyone with an `@xyz.com` email make a request to the proxy.

    Relevant issue: https://github.com/BerriAI/litellm/issues/5605
    """
    import jwt
    from starlette.datastructures import URL

    from litellm.proxy._types import NewTeamRequest, UserAPIKeyAuth
    from litellm.proxy.proxy_server import user_api_key_auth

    public_jwk = public_jwt_key["public_jwk"]
    private_key = public_jwt_key["private_key"]

    # set cache
    cache = DualCache()

    await cache.async_set_cache(key="litellm_jwt_auth_keys", value=[public_jwk])

    jwt_handler = JWTHandler()

    jwt_handler.user_api_key_cache = cache

    jwt_handler.litellm_jwtauth = LiteLLM_JWTAuth(
        user_email_jwt_field="email",
        user_allowed_email_domain="berri.ai",
        user_id_upsert=True,
    )

    # VALID TOKEN
    ## GENERATE A TOKEN
    # Assuming the current time is in UTC
    expiration_time = int((datetime.utcnow() + timedelta(minutes=10)).timestamp())

    team_id = f"team123_{uuid.uuid4()}"
    payload = {
        "sub": "user123",
        "exp": expiration_time,  # set the token to expire in 10 minutes
        "scope": "litellm_team",
        "client_id": team_id,
        "aud": "litellm-proxy",
        "email": user_email,
    }

    # Generate the JWT token
    # But before, you should convert bytes to string
    private_key_str = private_key.decode("utf-8")

    ## team token
    token = jwt.encode(payload, private_key_str, algorithm="RS256")

    ## VERIFY IT WORKS
    # Expect the call to succeed
    response = await jwt_handler.auth_jwt(token=token)
    assert response is not None  # Adjust this based on your actual response check

    ## RUN IT THROUGH USER API KEY AUTH
    bearer_token = "Bearer " + token

    request = Request(scope={"type": "http"})

    request._url = URL(url="/chat/completions")

    ## 1. INITIAL TEAM CALL - should fail
    # use generated key to auth in
    setattr(
        litellm.proxy.proxy_server,
        "general_settings",
        {
            "enable_jwt_auth": True,
        },
    )
    setattr(litellm.proxy.proxy_server, "jwt_handler", jwt_handler)
    setattr(litellm.proxy.proxy_server, "prisma_client", {})

    # AsyncMock(
    #     return_value=LiteLLM_UserTable(
    #         spend=0, user_id=user_email, max_budget=None, user_email=user_email
    #     )
    # ),
    with patch.object(
        litellm.proxy.auth.user_api_key_auth,
        "get_user_object",
        side_effect=mock_user_object,
    ) as mock_client:
        if should_work:
            # Expect the call to succeed
            result = await user_api_key_auth(request=request, api_key=bearer_token)
            assert result is not None  # Adjust this based on your actual response check
        else:
            # Expect the call to fail
            with pytest.raises(
                Exception
            ):  # Replace with the actual exception raised on failure
                resp = await user_api_key_auth(request=request, api_key=bearer_token)
                print(resp)


def test_get_public_key_from_jwk_url_rsa():
    import litellm
    from litellm.proxy.auth.handle_jwt import JWTHandler

    jwt_handler = JWTHandler()

    jwk_response = [
        {
            "kty": "RSA",
            "alg": "RS256",
            "kid": "RaPJB8QVptWHjHcoHkVlUWO4f0D3BtcY6iSDXgGVBgk",
            "use": "sig",
            "e": "AQAB",
            "n": "zgLDu57gLpkzzIkKrTKQVyjK8X40hvu6X_JOeFjmYmI0r3bh7FTOmre5rTEkDOL-1xvQguZAx4hjKmCzBU5Kz84FbsGiqM0ug19df4kwdTS6XOM6YEKUZrbaw4P7xTPsbZj7W2G_kxWNm3Xaxq6UKFdUF7n9snnBKKD6iUA-cE6HfsYmt9OhYZJfy44dbAbuanFmAsWw97SHrPFL3ueh3Ixt19KgpF4iSsXNg3YvoesdFM8psmivgePyyHA8k7pK1Yq7rNQX1Q9nzhvP-F7ocFbP52KYPlaSTu30YwPTVTFKYpDNmHT1fZ7LXZZNLrP_7-NSY76HS2ozSpzjsGVelQ",
        }
    ]

    public_key = jwt_handler.parse_keys(
        keys=jwk_response,
        kid="RaPJB8QVptWHjHcoHkVlUWO4f0D3BtcY6iSDXgGVBgk",
    )

    assert public_key is not None
    assert public_key == jwk_response[0]
    
def test_get_public_key_from_jwk_url_ecsda():
    from litellm.proxy.auth.handle_jwt import JWTHandler
    
    jwt_handler = JWTHandler()
    jwk_response = [
        {
            "kid":"mhRAPDi73xbe60PXUnlZ48OfoTm8VOJ9ePZ8KoL5Oto",
            "kty":"EC",
            "alg":"ES384",
            "use":"sig",
            "crv":"P-384",
            "x":"TkOFqaQSdZwNNXP6ZThKavH9h4VUmiJ-QZxlizBM8nQ3K_4ZO5ReaIRDq7VahpIT",
            "y":"YWqRQiWv_xnHcqY8iQq3AQ8wTMY02Qu3myiDE7wHpIc5s1fXUhO40AibIBbtQVL2"
        }
    ]
    
    public_key = jwt_handler.parse_keys(
        keys=jwk_response,
        kid="mhRAPDi73xbe60PXUnlZ48OfoTm8VOJ9ePZ8KoL5Oto"
    )
    
    assert public_key is not None
    assert public_key == jwk_response[0]

@pytest.mark.asyncio
async def test_auth_jwt_ecsda():
    from base64 import b64decode
    from json import loads
    from litellm.proxy.auth.handle_jwt import JWTHandler
    jwt_handler = JWTHandler()
    # Deactivate expiration verification for testing purpose
    jwt_handler.decode_options["verify_exp"] = False
    
    token = "eyJhbGciOiJFUzM4NCIsInR5cCIgOiAiSldUIiwia2lkIiA6ICJtaFJBUERpNzN4YmU2MFBYVW5sWjQ4T2ZvVG04Vk9KOWVQWjhLb0w1T3RvIn0.eyJleHAiOjE3MzEwMTcwOTEsImlhdCI6MTczMTAxNjc5MSwianRpIjoiYjUwZjNiYWYtZWM1ZS00ZTI3LTlkZDAtZmI4MTRhNWRkZjBkIiwiaXNzIjoiaHR0cDovL2xvY2FsaG9zdDo4MDgwL3JlYWxtcy9saXRlbGxtLXRlc3QtZXMzODQiLCJzdWIiOiIzZjE4YWVlNi03NDk3LTQ5ZjItYjdhNS1lN2UyMmIxMWZmNDkiLCJ0eXAiOiJCZWFyZXIiLCJhenAiOiJsaXRlbGxtLXRlc3Qtb3BlbmlkLWFwcC1lczM4NCIsImFjciI6IjEiLCJhbGxvd2VkLW9yaWdpbnMiOlsiLyoiXSwic2NvcGUiOiJvcGVuaWQgZW1haWwgcHJvZmlsZSIsImNsaWVudEhvc3QiOiIxOTIuMTY4LjY1LjEiLCJlbWFpbF92ZXJpZmllZCI6ZmFsc2UsInByZWZlcnJlZF91c2VybmFtZSI6InNlcnZpY2UtYWNjb3VudC1saXRlbGxtLXRlc3Qtb3BlbmlkLWFwcC1lczM4NCIsImNsaWVudEFkZHJlc3MiOiIxOTIuMTY4LjY1LjEiLCJjbGllbnRfaWQiOiJsaXRlbGxtLXRlc3Qtb3BlbmlkLWFwcC1lczM4NCJ9.K5c_KyjDxIrC1LzjmRsLUZ2vo9Fy5Djd9pUz8RHvqKHWSLY_125neVZFgGbo4iZtAJufngdZmhPwSqJzUQk-_w_U06fJdv7ekizNZxzPQ152WJdhMgIu1WWsesWwBafb"
    jwk_response = [
        {
            "kid":"mhRAPDi73xbe60PXUnlZ48OfoTm8VOJ9ePZ8KoL5Oto",
            "kty":"EC",
            "alg":"ES384",
            "use":"sig",
            "crv":"P-384",
            "x":"TkOFqaQSdZwNNXP6ZThKavH9h4VUmiJ-QZxlizBM8nQ3K_4ZO5ReaIRDq7VahpIT",
            "y":"YWqRQiWv_xnHcqY8iQq3AQ8wTMY02Qu3myiDE7wHpIc5s1fXUhO40AibIBbtQVL2"
        }
    ]
    
    unverified_body = loads(b64decode(token.split(".")[1] + "==").decode())
    
    public_key = jwt_handler.parse_keys(keys=jwk_response, kid="mhRAPDi73xbe60PXUnlZ48OfoTm8VOJ9ePZ8KoL5Oto")
    payload = await jwt_handler.auth_jwt(token, public_key)
    
    assert unverified_body == payload

@pytest.mark.asyncio
async def test_auth_jwt_rsa():
    from base64 import b64decode
    from json import loads
    from litellm.proxy.auth.handle_jwt import JWTHandler
    jwt_handler = JWTHandler()
    # Deactivate expiration verification for testing purpose
    jwt_handler.decode_options["verify_exp"] = False
    
    token = "eyJhbGciOiJSUzI1NiIsInR5cCIgOiAiSldUIiwia2lkIiA6ICJXZUIta0M5bkR1LVpic0FjRVNPUUhDTnRZaVpsektvZ1BUQ1hhT1U0Y04wIn0.eyJleHAiOjE3MzEwMTcyMjIsImlhdCI6MTczMTAxNjkyMiwianRpIjoiOWJlNjBjZDctYzZiOS00NzRhLWI0YjMtMWRkYjkwZTJkYmMyIiwiaXNzIjoiaHR0cDovL2xvY2FsaG9zdDo4MDgwL3JlYWxtcy9saXRlbGxtLXRlc3QtcnNhMjU2Iiwic3ViIjoiZjYzZTQzYjAtNDQ1YS00MTlhLWFmM2UtODBhYWJlNjUzNzA5IiwidHlwIjoiQmVhcmVyIiwiYXpwIjoibGl0ZWxsbS10ZXN0LW9wZW5pZC1hcHAtcnNhMjU2IiwiYWNyIjoiMSIsImFsbG93ZWQtb3JpZ2lucyI6WyIvKiJdLCJzY29wZSI6Im9wZW5pZCBlbWFpbCBwcm9maWxlIiwiY2xpZW50SG9zdCI6IjE5Mi4xNjguNjUuMSIsImVtYWlsX3ZlcmlmaWVkIjpmYWxzZSwicHJlZmVycmVkX3VzZXJuYW1lIjoic2VydmljZS1hY2NvdW50LWxpdGVsbG0tdGVzdC1vcGVuaWQtYXBwLXJzYTI1NiIsImNsaWVudEFkZHJlc3MiOiIxOTIuMTY4LjY1LjEiLCJjbGllbnRfaWQiOiJsaXRlbGxtLXRlc3Qtb3BlbmlkLWFwcC1yc2EyNTYifQ.Q9yKG-UTpJhvUFouzxdwOlqGZ7G-T99NE7svDZ_gPWJ2Jf1rKIJ_BxP7C7DzRpEscqZA1mARkDfWyurIu_1QS1tnQtsJBVkhX9sY1jBTJOYaZa-kxlhIBSaGn4DHj7FbNd9OJsd1BxE5OSK4Wji8eseycDiMdS26GhKXeLeazmK6Nu-LR625LpCRwZdG7EUMwMudrML8KD14eGO0G2zBncFOIlVdVrwyA8PE6ZIcR2WKW-SEGtE7nDAfDUHxL2WETt2bfAXl0UTs3UR-1HUoBLxU4LpaqmfFS2noO0KibtflhxvHZoQ9K5WUaj3_sMQV8crztE7unIiEwe89QykfgA"
    jwk_response = [
        {
            "kid": "WeB-kC9nDu-ZbsAcESOQHCNtYiZlzKogPTCXaOU4cN0",
            "kty": "RSA",
            "alg": "RS256",
            "use": "sig",
            "n": "uyl8F8oNroKz6BgpMP-u0uxhrNbj3OS3SmTtdUYHwRxGv4FCTaoPGqpWgypnRqxY2n5N_r-ac0pJobprJrijNBXT9Egd6DX2MmvBcmJp5cBNq2LqCyAiY_p4EvAetba3YP3IEjaiHrwBg9jaorob22pO07vfvkvePJyvPuecUBlpqUgAigiHZ9uwfKQymEFYqJeZIlp0BnkBOLtC6iTQSxbDLaNF56pu3ifUEZZW5t2etz_RXR1Y7SKmtg_s-8tBi5A6M9G_JBqu630NRxMei_-h5bm37pm5R_afOmg-XBoWcS-cGu-5nTmJLPsw93DhLidiJbuILcvczq_SD4Xr0Q",
            "e": "AQAB",
            "x5c": [
                "MIICtTCCAZ0CBgGS/srU1TANBgkqhkiG9w0BAQsFADAeMRwwGgYDVQQDDBNsaXRlbGxtLXRlc3QtcnNhMjU2MB4XDTI0MTEwNjAwMDQxOFoXDTM0MTEwNjAwMDU1OFowHjEcMBoGA1UEAwwTbGl0ZWxsbS10ZXN0LXJzYTI1NjCCASIwDQYJKoZIhvcNAQEBBQADggEPADCCAQoCggEBALspfBfKDa6Cs+gYKTD/rtLsYazW49zkt0pk7XVGB8EcRr+BQk2qDxqqVoMqZ0asWNp+Tf6/mnNKSaG6aya4ozQV0/RIHeg19jJrwXJiaeXATati6gsgImP6eBLwHrW2t2D9yBI2oh68AYPY2qK6G9tqTtO7375L3jycrz7nnFAZaalIAIoIh2fbsHykMphBWKiXmSJadAZ5ATi7Quok0EsWwy2jReeqbt4n1BGWVubdnrc/0V0dWO0iprYP7PvLQYuQOjPRvyQarut9DUcTHov/oeW5t+6ZuUf2nzpoPlwaFnEvnBrvuZ05iSz7MPdw4S4nYiW7iC3L3M6v0g+F69ECAwEAATANBgkqhkiG9w0BAQsFAAOCAQEAeDYgVfdXhyReUrZCOR/fpdvI3+Q3oxIS1oDYmstsuNRFyYMJzkwp5UXrwB5Yo9XPjvT/mnS2U+8Di8tps1gMA1jPmLj+kNhs+43Q6YcRDLek7GyVx/zq/ga/Rilbl66T6yKiFtxEEBIhbVRbbto+AmvycFvWTnTJRVNxT040lLqqDtUB663tfpUpZnnki9+k+mdJLdpu3zArqZA46ei7FeadU96ELbCkRY/+NDVcjrLnl+SPwjOBfDr3bM6C7nNmKOjMqsOIXOzxAfQEXVFSwqAFZaioS0vSirjcRWuE2PclEROSAfcmHMJhtBYDhkoRF0xqAr8iPdHOevRQCGwzKg=="
            ],
            "x5t": "DVcauG1QNemtqR6QUd3qH8tRyG8",
            "x5t#S256": "2OZRfb74j2YhtYfAH8oJsTeXlDqke3bjSWapzvVpLqM"
        }
    ]
    
    unverified_body = loads(b64decode(token.split(".")[1] + "==").decode())
    
    public_key = jwt_handler.parse_keys(keys=jwk_response, kid="WeB-kC9nDu-ZbsAcESOQHCNtYiZlzKogPTCXaOU4cN0")
    payload = await jwt_handler.auth_jwt(token, public_key)
    
    assert unverified_body == payload