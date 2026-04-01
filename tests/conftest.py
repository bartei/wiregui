"""Shared test fixtures — async DB session using a test database."""

import os
from collections.abc import AsyncGenerator

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from wiregui.config import get_settings

# All models must be imported so SQLModel.metadata knows about them
from wiregui.models import *  # noqa: F401, F403


def _test_database_url() -> str:
    """Use a separate test DB locally, but in CI just use the main DB (it's ephemeral)."""
    url = get_settings().database_url
    if os.environ.get("CI"):
        return url  # CI: use the service container DB directly
    base, _dbname = url.rsplit("/", 1)
    return f"{base}/wiregui_test"


TEST_DATABASE_URL = _test_database_url()


def _ensure_test_db_sync():
    """Ensure test database exists. Skip in CI (uses main DB)."""
    if os.environ.get("CI"):
        return

    import asyncio

    async def _create():
        base_url = get_settings().database_url.rsplit("/", 1)[0] + "/postgres"
        admin_engine = create_async_engine(base_url, isolation_level="AUTOCOMMIT")
        try:
            async with admin_engine.connect() as conn:
                result = await conn.execute(
                    text("SELECT 1 FROM pg_database WHERE datname = 'wiregui_test'")
                )
                if result.scalar() is None:
                    await conn.execute(text("CREATE DATABASE wiregui_test"))
        finally:
            await admin_engine.dispose()

    asyncio.run(_create())


_ensure_test_db_sync()


@pytest_asyncio.fixture
async def session() -> AsyncGenerator[AsyncSession]:
    """Fresh engine + session per test, with table setup/teardown."""
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as sess:
        yield sess
        await sess.rollback()

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    await engine.dispose()
