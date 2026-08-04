from __future__ import annotations

from datetime import timedelta

import structlog

from app.config import Settings
from app.errors import AuthenticationError
from app.models import User
from app.repositories.users import UserRepository
from app.schemas.auth import TokenPair
from app.security import (
    TokenKind,
    create_token,
    decode_token_identity,
    hash_password,
    verify_password,
)


class AuthService:
    def __init__(self, repository: UserRepository, settings: Settings) -> None:
        self._repository = repository
        self._settings = settings

    async def authenticate(self, username: str, password: str) -> TokenPair:
        user = await self._repository.get_by_username(username)
        if user is None or not user.is_active or not verify_password(password, user.password_hash):
            raise AuthenticationError("Username or password is incorrect")
        return self._issue_token_pair(user)

    async def refresh(self, refresh_token: str) -> TokenPair:
        identity = decode_token_identity(
            refresh_token,
            expected_kind=TokenKind.REFRESH,
            settings=self._settings,
        )
        user = await self.get_active_user(
            identity.user_id,
            token_version=identity.token_version,
        )
        user = await self._repository.bump_token_version(user)
        return self._issue_token_pair(user)

    async def get_active_user(self, user_id: int, *, token_version: int | None = None) -> User:
        user = await self._repository.get_by_id(user_id)
        if user is None or not user.is_active:
            raise AuthenticationError("User is inactive or no longer exists")
        if token_version is not None and user.token_version != token_version:
            raise AuthenticationError("Token has been revoked")
        return user

    async def revoke_tokens(self, user: User) -> None:
        await self._repository.bump_token_version(user)

    async def bootstrap_admin(self) -> User | None:
        if not self._settings.bootstrap_admin:
            return None
        existing = await self._repository.get_by_username(self._settings.admin_username)
        if existing is not None:
            return existing

        password_hash = (
            self._settings.admin_password_hash.get_secret_value()
            if self._settings.admin_password_hash is not None
            else None
        )
        if password_hash is None and self._settings.admin_password is not None:
            password_hash = hash_password(self._settings.admin_password.get_secret_value())
        if password_hash is None:
            structlog.get_logger(__name__).warning(
                "admin_bootstrap_skipped",
                reason="ODIRAG_ADMIN_PASSWORD_HASH or ODIRAG_ADMIN_PASSWORD is not configured",
            )
            return None
        user = await self._repository.create_admin(
            username=self._settings.admin_username,
            password_hash=password_hash,
        )
        structlog.get_logger(__name__).info(
            "admin_bootstrapped", username=user.username, user_id=user.id
        )
        return user

    def _issue_token_pair(self, user: User) -> TokenPair:
        access_lifetime = timedelta(minutes=self._settings.access_token_expire_minutes)
        refresh_lifetime = timedelta(days=self._settings.refresh_token_expire_days)
        return TokenPair(
            access_token=create_token(
                subject=str(user.id),
                kind=TokenKind.ACCESS,
                settings=self._settings,
                expires_delta=access_lifetime,
                token_version=user.token_version,
            ),
            refresh_token=create_token(
                subject=str(user.id),
                kind=TokenKind.REFRESH,
                settings=self._settings,
                expires_delta=refresh_lifetime,
                token_version=user.token_version,
            ),
            expires_in=int(access_lifetime.total_seconds()),
        )
