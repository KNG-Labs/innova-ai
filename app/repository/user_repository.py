from sqlalchemy import select, func

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_anonymous_identity(
        self, *, channel: str, anonymous_id: str
    ) -> User | None:
        stmt = select(User).where(
            User.channel == channel,
            User.anonymous_id == anonymous_id,
            User.deleted_at.is_(None),
        )

        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_anonymous_user(self, *, channel: str, anonymous_id: str) -> User:
        user = User(
            channel=channel,
            anonymous_id=anonymous_id,
        )
        self._session.add(user)
        await self._session.flush()

        return user

    async def get_or_create_anonymous_user(
        self, *, channel: str, anonymous_id: str
    ) -> User:

        user = await self.get_by_anonymous_identity(
            channel=channel,
            anonymous_id=anonymous_id,
        )

        if user is not None:
            return user

        return await self.create_anonymous_user(
            channel=channel,
            anonymous_id=anonymous_id,
        )

    async def soft_delete(self, user: User) -> None:
        user.deleted_at = func.now()
        await self._session.flush()
