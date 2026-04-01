"""Shared test fixtures — async DB session using a test database.

Unit tests use the ``session`` fixture, which provides a per-test
savepoint-isolated session on a dedicated test engine.  E2E tests do NOT
use this fixture and are therefore unaffected — they keep using the real
``wiregui.db.async_session`` that talks to the app's database.
"""

import os
from collections.abc import AsyncGenerator

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
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

# Test engine — only used by the ``session`` fixture and unit tests.
# NOT assigned to wiregui.db so e2e tests are unaffected.
_test_engine = create_async_engine(TEST_DATABASE_URL)


@pytest_asyncio.fixture(scope="session")
async def _test_tables():
    """Create all tables once per test session, drop at end."""
    async with _test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield
    async with _test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    await _test_engine.dispose()


@pytest_asyncio.fixture
async def session(_test_tables) -> AsyncGenerator[AsyncSession]:
    """Per-test session with transaction isolation.

    The session is bound to a connection-level transaction that is always
    rolled back at teardown.  When tested code calls ``session.commit()``,
    SQLAlchemy only releases a SAVEPOINT — the outer transaction is never
    committed, so no test data persists between tests.
    """
    async with _test_engine.connect() as conn:
        txn = await conn.begin()
        sess = AsyncSession(bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint")
        yield sess
        await sess.close()
        await txn.rollback()
