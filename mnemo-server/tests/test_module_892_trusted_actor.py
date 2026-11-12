"""The opt-in membership mapper never treats client IDs as identity."""

import base64
import hashlib
import hmac
import json
import time

import pytest
from mnemo_server.auth import AuthError
from mnemo_server.mcp.principal import sse_principal_from_scope
from mnemo_server.services.trusted_actor import TrustedJWTActorMapper


def _token(claims: dict[str, object], secret: str = "fixture-secret") -> str:
    def encode(value: dict[str, object]) -> str:
        raw = json.dumps(value, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    payload = f"{encode({'alg': 'HS256', 'typ': 'JWT'})}.{encode(claims)}"
    signature = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest()
    return f"{payload}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"


def test_pinned_verified_actor_mapping() -> None:
    mapper = TrustedJWTActorMapper("fixture-issuer", "fixture-audience", "fixture-secret")
    common: dict[str, object] = {
        "iss": "fixture-issuer",
        "aud": "fixture-audience",
        "exp": int(time.time()) + 60,
    }
    first = mapper.from_token(_token({**common, "sub": "alice", "actor_id": "forged"}))
    again = mapper.from_token(_token({**common, "sub": "alice", "actor_id": "another"}))
    other = mapper.from_token(_token({**common, "sub": "bob"}))
    assert first.authenticated and first.actor_id == again.actor_id
    assert first.actor_id != other.actor_id


@pytest.mark.parametrize(
    "change",
    [
        {"iss": "other"},
        {"aud": "other"},
        {"sub": ""},
        {"sub": " alice "},
        {"exp": None},
    ],
)
def test_untrusted_claims_denied(change: dict[str, object]) -> None:
    mapper = TrustedJWTActorMapper("fixture-issuer", "fixture-audience", "fixture-secret")
    claims: dict[str, object] = {
        "iss": "fixture-issuer",
        "aud": "fixture-audience",
        "sub": "alice",
        "exp": int(time.time()) + 60,
    }
    with pytest.raises(AuthError):
        mapper.from_token(_token({**claims, **change}))


def test_tampered_signature_denied() -> None:
    mapper = TrustedJWTActorMapper("fixture-issuer", "fixture-audience", "fixture-secret")
    token = _token(
        {
            "iss": "fixture-issuer",
            "aud": "fixture-audience",
            "sub": "alice",
            "exp": int(time.time()) + 60,
        }
    )
    with pytest.raises(AuthError):
        mapper.from_token(token[:-2] + "xx")


def test_acl_sse_identity_is_bound_to_signed_transport_token() -> None:
    mapper = TrustedJWTActorMapper("fixture-issuer", "fixture-audience", "fixture-secret")
    claims: dict[str, object] = {
        "iss": "fixture-issuer",
        "aud": "fixture-audience",
        "sub": "alice",
        "exp": int(time.time()) + 60,
    }
    token = _token(claims)
    scope = {
        "type": "http",
        "headers": [(b"authorization", f"Bearer {token}".encode())],
        "state": {"auth": claims},
    }
    assert sse_principal_from_scope(scope, mapper) == mapper.from_token(token)
    assert mapper.from_server_subject("alice") == mapper.from_token(token)
    with pytest.raises(PermissionError):
        sse_principal_from_scope({**scope, "state": {"auth": {**claims, "sub": "bob"}}}, mapper)
    with pytest.raises(PermissionError):
        sse_principal_from_scope({**scope, "headers": []}, mapper)
    with pytest.raises(AuthError):
        mapper.from_server_subject(" alice ")
