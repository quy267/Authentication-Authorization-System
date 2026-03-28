from datetime import timedelta

import pytest

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_hash_and_verify_password():
    """Password hashing and verification works."""
    hashed = hash_password("secret123")
    assert hashed != "secret123"
    assert verify_password("secret123", hashed) is True
    assert verify_password("wrong", hashed) is False


def test_create_access_token():
    """Access token contains expected claims."""
    token = create_access_token("user123", ["admin", "user"])
    payload = decode_token(token)

    assert payload["sub"] == "user123"
    assert payload["roles"] == ["admin", "user"]
    assert payload["type"] == "access"
    assert "jti" in payload
    assert "exp" in payload
    assert "iat" in payload


def test_create_refresh_token():
    """Refresh token contains expected claims."""
    token = create_refresh_token("user456")
    payload = decode_token(token)

    assert payload["sub"] == "user456"
    assert payload["type"] == "refresh"
    assert "jti" in payload
    assert "roles" not in payload


def test_expired_token_rejected():
    """Expired tokens raise on decode."""
    token = create_access_token(
        "user1", ["user"], expires_delta=timedelta(seconds=-1)
    )
    with pytest.raises(Exception):
        decode_token(token)


def test_invalid_token_rejected():
    """Garbage tokens raise on decode."""
    with pytest.raises(Exception):
        decode_token("not.a.valid.token")


def test_access_and_refresh_have_different_jti():
    """Each token gets a unique jti."""
    a = decode_token(create_access_token("u", []))
    b = decode_token(create_refresh_token("u"))
    assert a["jti"] != b["jti"]
