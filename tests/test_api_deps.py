"""Tests for API dependency injection — Bearer token auth and admin guard."""

import hashlib
from datetime import timedelta
from uuid import uuid4

import pytest
from unittest.mock import AsyncMock, MagicMock

from wiregui.auth.api_token import generate_api_token
from wiregui.auth.passwords import hash_password
from wiregui.db import async_session
from wiregui.models.api_token import ApiToken
from wiregui.models.user import User
from wiregui.utils.time import utcnow


# ========== resolve_bearer_token ==========


async def test_resolve_valid_token():
    """Valid, non-expired token resolves to user."""
    from wiregui.auth.api_token import resolve_bearer_token

    plaintext, token_hash = generate_api_token()

    async with async_session() as session:
        user = User(email="api-test@test.com", password_hash=hash_password("x"), role="admin")
        session.add(user)
        await session.commit()
        await session.refresh(user)

        api_token = ApiToken(
            token_hash=token_hash,
            user_id=user.id,
            expires_at=utcnow() + timedelta(hours=1),
        )
        session.add(api_token)
        await session.commit()

    try:
        async with async_session() as session:
            resolved = await resolve_bearer_token(session, plaintext)
            assert resolved is not None
            assert resolved.id == user.id
            assert resolved.email == "api-test@test.com"
    finally:
        async with async_session() as session:
            await session.delete(await session.get(ApiToken, api_token.id))
            await session.delete(await session.get(User, user.id))
            await session.commit()


async def test_resolve_expired_token():
    """Expired token returns None."""
    from wiregui.auth.api_token import resolve_bearer_token

    plaintext, token_hash = generate_api_token()

    async with async_session() as session:
        user = User(email="api-expired@test.com", password_hash=hash_password("x"), role="admin")
        session.add(user)
        await session.commit()
        await session.refresh(user)

        api_token = ApiToken(
            token_hash=token_hash,
            user_id=user.id,
            expires_at=utcnow() - timedelta(hours=1),  # already expired
        )
        session.add(api_token)
        await session.commit()

    try:
        async with async_session() as session:
            resolved = await resolve_bearer_token(session, plaintext)
            assert resolved is None
    finally:
        async with async_session() as session:
            await session.delete(await session.get(ApiToken, api_token.id))
            await session.delete(await session.get(User, user.id))
            await session.commit()


async def test_resolve_invalid_token():
    """Nonexistent token returns None."""
    from wiregui.auth.api_token import resolve_bearer_token

    async with async_session() as session:
        resolved = await resolve_bearer_token(session, "totally-bogus-token")
        assert resolved is None


async def test_resolve_token_disabled_user():
    """Token for disabled user returns None."""
    from wiregui.auth.api_token import resolve_bearer_token

    plaintext, token_hash = generate_api_token()

    async with async_session() as session:
        user = User(
            email="api-disabled@test.com", password_hash=hash_password("x"),
            role="admin", disabled_at=utcnow(),
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        api_token = ApiToken(
            token_hash=token_hash,
            user_id=user.id,
            expires_at=utcnow() + timedelta(hours=1),
        )
        session.add(api_token)
        await session.commit()

    try:
        async with async_session() as session:
            resolved = await resolve_bearer_token(session, plaintext)
            assert resolved is None
    finally:
        async with async_session() as session:
            await session.delete(await session.get(ApiToken, api_token.id))
            await session.delete(await session.get(User, user.id))
            await session.commit()


async def test_resolve_token_no_expiry():
    """Token without expires_at (never expires) resolves successfully."""
    from wiregui.auth.api_token import resolve_bearer_token

    plaintext, token_hash = generate_api_token()

    async with async_session() as session:
        user = User(email="api-noexp@test.com", password_hash=hash_password("x"), role="admin")
        session.add(user)
        await session.commit()
        await session.refresh(user)

        api_token = ApiToken(
            token_hash=token_hash,
            user_id=user.id,
            expires_at=None,
        )
        session.add(api_token)
        await session.commit()

    try:
        async with async_session() as session:
            resolved = await resolve_bearer_token(session, plaintext)
            assert resolved is not None
            assert resolved.id == user.id
    finally:
        async with async_session() as session:
            await session.delete(await session.get(ApiToken, api_token.id))
            await session.delete(await session.get(User, user.id))
            await session.commit()


# ========== get_current_api_user (via FastAPI deps) ==========


async def test_get_current_api_user_missing_header():
    """Missing Authorization header raises 401."""
    from fastapi import HTTPException
    from wiregui.api.deps import get_current_api_user

    request = MagicMock()
    request.headers = {}

    with pytest.raises(HTTPException) as exc_info:
        await get_current_api_user(request, session=AsyncMock())
    assert exc_info.value.status_code == 401
    assert "Missing" in exc_info.value.detail


async def test_get_current_api_user_bad_scheme():
    """Non-Bearer auth scheme raises 401."""
    from fastapi import HTTPException
    from wiregui.api.deps import get_current_api_user

    request = MagicMock()
    request.headers = {"Authorization": "Basic dXNlcjpwYXNz"}

    with pytest.raises(HTTPException) as exc_info:
        await get_current_api_user(request, session=AsyncMock())
    assert exc_info.value.status_code == 401


async def test_get_current_api_user_invalid_token():
    """Valid Bearer scheme but bogus token raises 401."""
    from fastapi import HTTPException
    from wiregui.api.deps import get_current_api_user

    request = MagicMock()
    request.headers = {"Authorization": "Bearer bogus-token-value"}

    async with async_session() as session:
        with pytest.raises(HTTPException) as exc_info:
            await get_current_api_user(request, session=session)
        assert exc_info.value.status_code == 401
        assert "Invalid" in exc_info.value.detail


async def test_get_current_api_user_valid_token():
    """Valid Bearer token resolves to user."""
    from wiregui.api.deps import get_current_api_user

    plaintext, token_hash = generate_api_token()

    async with async_session() as session:
        user = User(email="api-dep-test@test.com", password_hash=hash_password("x"), role="admin")
        session.add(user)
        await session.commit()
        await session.refresh(user)

        api_token = ApiToken(
            token_hash=token_hash,
            user_id=user.id,
            expires_at=utcnow() + timedelta(hours=1),
        )
        session.add(api_token)
        await session.commit()

    try:
        request = MagicMock()
        request.headers = {"Authorization": f"Bearer {plaintext}"}

        async with async_session() as session:
            resolved = await get_current_api_user(request, session=session)
            assert resolved.id == user.id
    finally:
        async with async_session() as session:
            await session.delete(await session.get(ApiToken, api_token.id))
            await session.delete(await session.get(User, user.id))
            await session.commit()


# ========== require_admin ==========


async def test_require_admin_allows_admin():
    """Admin user passes require_admin."""
    from wiregui.api.deps import require_admin

    admin_user = MagicMock(spec=User)
    admin_user.role = "admin"
    result = await require_admin(user=admin_user)
    assert result == admin_user


async def test_require_admin_rejects_unprivileged():
    """Non-admin user gets 403."""
    from fastapi import HTTPException
    from wiregui.api.deps import require_admin

    regular_user = MagicMock(spec=User)
    regular_user.role = "unprivileged"

    with pytest.raises(HTTPException) as exc_info:
        await require_admin(user=regular_user)
    assert exc_info.value.status_code == 403
    assert "Admin" in exc_info.value.detail