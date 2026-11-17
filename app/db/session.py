import os
import ssl

from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)


def create_engine(database_url: str, *, null_pool: bool = False) -> AsyncEngine:
    on_vercel = os.getenv("VERCEL") == "1"
    url = make_url(database_url)
    if on_vercel and url.query.get("ssl") not in {
        "require",
        "verify-full",
    }:
        raise RuntimeError("Vercel DATABASE_URL requires TLS: use ssl=verify-full")
    connect_args = {}
    if url.query.get("ssl") == "verify-full":
        # asyncpg otherwise expects ~/.postgresql/root.crt, absent on runners.
        connect_args["ssl"] = ssl.create_default_context()
        url = url.difference_update_query(["ssl"])
    return create_async_engine(
        url,
        echo=False,
        pool_pre_ping=True,
        poolclass=NullPool if on_vercel or null_pool else None,
        connect_args=connect_args,
    )


def create_session_maker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
