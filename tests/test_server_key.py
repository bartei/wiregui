"""Tests for server public key retrieval from Configuration table."""

import pytest

from wiregui.db import async_session
from wiregui.models.configuration import Configuration
from wiregui.utils.server_key import get_server_public_key
from sqlmodel import select


@pytest.fixture(autouse=True)
async def _snapshot_config():
    """Snapshot and restore server_public_key around each test."""
    async with async_session() as session:
        c = (await session.execute(select(Configuration).limit(1))).scalar_one_or_none()
        orig = c.server_public_key if c else None
        cid = c.id if c else None

    yield

    if cid:
        async with async_session() as session:
            c = await session.get(Configuration, cid)
            if c:
                c.server_public_key = orig
                session.add(c)
                await session.commit()


async def test_get_server_public_key_returns_key():
    """Returns the public key when configured."""
    async with async_session() as session:
        c = (await session.execute(select(Configuration).limit(1))).scalar_one_or_none()
        c.server_public_key = "TestServerPubKey123456789012345678901234w="
        session.add(c)
        await session.commit()

    result = await get_server_public_key()
    assert result == "TestServerPubKey123456789012345678901234w="


async def test_get_server_public_key_raises_when_missing():
    """Raises RuntimeError when server_public_key is None."""
    async with async_session() as session:
        c = (await session.execute(select(Configuration).limit(1))).scalar_one_or_none()
        c.server_public_key = None
        session.add(c)
        await session.commit()

    with pytest.raises(RuntimeError, match="not configured"):
        await get_server_public_key()


async def test_get_server_public_key_raises_when_empty_string():
    """Raises RuntimeError when server_public_key is empty string."""
    async with async_session() as session:
        c = (await session.execute(select(Configuration).limit(1))).scalar_one_or_none()
        c.server_public_key = ""
        session.add(c)
        await session.commit()

    with pytest.raises(RuntimeError, match="not configured"):
        await get_server_public_key()