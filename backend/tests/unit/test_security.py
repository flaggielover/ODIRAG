from datetime import timedelta

import pytest

from app.config import Settings
from app.errors import AuthenticationError
from app.security import (
    TokenKind,
    create_token,
    decode_token,
    decode_token_identity,
    hash_password,
    verify_password,
)


def test_password_hash_round_trip() -> None:
    encoded = hash_password("secret-value")

    assert encoded != "secret-value"
    assert verify_password("secret-value", encoded)
    assert not verify_password("wrong-value", encoded)
    assert not verify_password("secret-value", "not-a-valid-password-hash")


def test_access_token_round_trip(test_settings: Settings) -> None:
    token = create_token(
        subject="42",
        kind=TokenKind.ACCESS,
        settings=test_settings,
        expires_delta=timedelta(minutes=1),
    )

    assert decode_token(token, expected_kind=TokenKind.ACCESS, settings=test_settings) == 42
    identity = decode_token_identity(
        token,
        expected_kind=TokenKind.ACCESS,
        settings=test_settings,
    )
    assert identity.user_id == 42
    assert identity.token_version == 0
    assert identity.jti


def test_token_identity_preserves_revocation_version(test_settings: Settings) -> None:
    token = create_token(
        subject="42",
        kind=TokenKind.REFRESH,
        settings=test_settings,
        expires_delta=timedelta(minutes=1),
        token_version=7,
    )

    identity = decode_token_identity(
        token,
        expected_kind=TokenKind.REFRESH,
        settings=test_settings,
    )
    assert identity.token_version == 7


def test_refresh_token_cannot_be_used_as_access_token(test_settings: Settings) -> None:
    token = create_token(
        subject="42",
        kind=TokenKind.REFRESH,
        settings=test_settings,
        expires_delta=timedelta(minutes=1),
    )

    with pytest.raises(AuthenticationError, match="type"):
        decode_token(token, expected_kind=TokenKind.ACCESS, settings=test_settings)


def test_invalid_token_is_rejected(test_settings: Settings) -> None:
    with pytest.raises(AuthenticationError, match="invalid or expired"):
        decode_token("invalid", expected_kind=TokenKind.ACCESS, settings=test_settings)
