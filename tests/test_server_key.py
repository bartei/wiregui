"""Tests for server public key retrieval from Configuration table."""

import pytest

from wiregui.models.configuration import Configuration
from wiregui.utils.server_key import get_server_public_key


async def test_get_server_public_key_returns_key(session, monkeypatch):
    """Returns the public key when configured."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def mock_session():
        yield session

    monkeypatch.setattr("wiregui.utils.server_key.async_session", mock_session)

    c = Configuration(server_public_key="TestServerPubKey123456789012345678901234w=")
    session.add(c)
    await session.flush()

    result = await get_server_public_key()
    assert result == "TestServerPubKey123456789012345678901234w="


async def test_get_server_public_key_raises_when_missing(session, monkeypatch):
    """Raises RuntimeError when server_public_key is None."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def mock_session():
        yield session

    monkeypatch.setattr("wiregui.utils.server_key.async_session", mock_session)

    c = Configuration(server_public_key=None)
    session.add(c)
    await session.flush()

    with pytest.raises(RuntimeError, match="not configured"):
        await get_server_public_key()


async def test_get_server_public_key_raises_when_empty_string(session, monkeypatch):
    """Raises RuntimeError when server_public_key is empty string."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def mock_session():
        yield session

    monkeypatch.setattr("wiregui.utils.server_key.async_session", mock_session)

    c = Configuration(server_public_key="")
    session.add(c)
    await session.flush()

    with pytest.raises(RuntimeError, match="not configured"):
        await get_server_public_key()
