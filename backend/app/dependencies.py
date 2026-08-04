from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated, cast

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database.session import DatabaseManager
from app.errors import AuthenticationError, PermissionDeniedError
from app.models import User
from app.repositories.users import UserRepository
from app.runtime import ApplicationRuntime
from app.security import TokenKind, decode_token_identity
from app.services.auth import AuthService

bearer_scheme = HTTPBearer(auto_error=False)


def get_app_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_database_manager(request: Request) -> DatabaseManager:
    return cast(DatabaseManager, request.app.state.database)


def get_application_runtime(request: Request) -> ApplicationRuntime:
    return cast(ApplicationRuntime, request.app.state.runtime)


async def get_db_session(
    manager: Annotated[DatabaseManager, Depends(get_database_manager)],
) -> AsyncIterator[AsyncSession]:
    async for session in manager.session():
        yield session


def get_auth_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> AuthService:
    return AuthService(UserRepository(session), settings)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    service: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationError("Bearer token is required")
    identity = decode_token_identity(
        credentials.credentials,
        expected_kind=TokenKind.ACCESS,
        settings=settings,
    )
    return await service.get_active_user(
        identity.user_id,
        token_version=identity.token_version,
    )


async def require_admin(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    if not user.is_superuser:
        raise PermissionDeniedError("Administrator privileges are required")
    return user


DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(require_admin)]
