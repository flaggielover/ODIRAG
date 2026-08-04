from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: int) -> User | None:
        return await self._session.get(User, user_id)

    async def get_by_username(self, username: str) -> User | None:
        result = await self._session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def create_admin(self, *, username: str, password_hash: str) -> User:
        user = User(
            username=username,
            password_hash=password_hash,
            is_active=True,
            is_superuser=True,
        )
        self._session.add(user)
        await self._session.commit()
        await self._session.refresh(user)
        return user

    async def bump_token_version(self, user: User) -> User:
        user.token_version += 1
        await self._session.commit()
        await self._session.refresh(user)
        return user
