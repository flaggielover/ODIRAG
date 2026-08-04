from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, cast

import jwt
from passlib.context import CryptContext

from app.config import Settings
from app.errors import AuthenticationError


class TokenKind(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"


@dataclass(frozen=True, slots=True)
class TokenIdentity:
    user_id: int
    token_version: int
    jti: str


password_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def hash_password(password: str) -> str:
    return cast(str, password_context.hash(password))


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return cast(bool, password_context.verify(password, password_hash))
    except (TypeError, ValueError):
        return False


def create_token(
    *,
    subject: str,
    kind: TokenKind,
    settings: Settings,
    expires_delta: timedelta,
    token_version: int = 0,
) -> str:
    now = datetime.now(UTC)
    claims: dict[str, Any] = {
        "sub": subject,
        "type": kind.value,
        "iat": now,
        "nbf": now,
        "exp": now + expires_delta,
        "jti": secrets.token_urlsafe(16),
        "iss": "odirag",
        "ver": token_version,
    }
    return jwt.encode(
        claims,
        settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def decode_token(token: str, *, expected_kind: TokenKind, settings: Settings) -> int:
    return decode_token_identity(token, expected_kind=expected_kind, settings=settings).user_id


def decode_token_identity(
    token: str, *, expected_kind: TokenKind, settings: Settings
) -> TokenIdentity:
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            issuer="odirag",
            options={"require": ["sub", "type", "iat", "nbf", "exp", "jti", "iss"]},
        )
        if claims.get("type") != expected_kind.value:
            raise AuthenticationError("Token type is invalid")
        subject = claims["sub"]
        if not isinstance(subject, str) or not subject.isdecimal():
            raise AuthenticationError("Token subject is invalid")
        version = claims.get("ver", 0)
        jti = claims["jti"]
        if isinstance(version, bool) or not isinstance(version, int) or version < 0:
            raise AuthenticationError("Token version is invalid")
        if not isinstance(jti, str) or not jti:
            raise AuthenticationError("Token identifier is invalid")
        return TokenIdentity(int(subject), version, jti)
    except AuthenticationError:
        raise
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError("Token is invalid or expired") from exc
