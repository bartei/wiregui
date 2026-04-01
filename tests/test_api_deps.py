"""Tests for API dependency injection — Bearer token auth and admin guard."""

from datetime import timedelta

import pytest
from unittest.mock import AsyncMock, MagicMock

from wiregui.auth.api_token import generate_api_token, resolve_bearer_token
from wiregui.auth.passwords import hash_password
from wiregui.models.api_token import ApiToken
from wiregui.models.user import User
from wiregui.utils.time import utcnow


# ========== resolve_bearer_token ==========


async def test_resolve_valid_token(session):
    """Valid, non-expired token resolves to user."""
    plaintext, token_hash = generate_api_token()

    user = User(email="api-test@test.com", password_hash=hash_password("x"), role="admin")
    session.add(user)
    await session.flush()

    api_token = ApiToken(token_hash=token_hash, user_id=user.id, expires_at=utcnow() + timedelta(hours=1))
    session.add(api_token)
    await session.flush()

    resolved = await resolve_bearer_token(session, plaintext)
    assert resolved is not None
    assert resolved.id == user.id
    assert resolved.email == "api-test@test.com"


async def test_resolve_expired_token(session):
    """Expired token returns None."""
    plaintext, token_hash = generate_api_token()

    user = User(email="api-expired@test.com", password_hash=hash_password("x"), role="admin")
    session.add(user)
    await session.flush()

    api_token = ApiToken(token_hash=token_hash, user_id=user.id, expires_at=utcnow() - timedelta(hours=1))
    session.add(api_token)
    await session.flush()

    resolved = await resolve_bearer_token(session, plaintext)
    assert resolved is None


async def test_resolve_invalid_token(session):
    """Nonexistent token returns None."""
    resolved = await resolve_bearer_token(session, "totally-bogus-token")
    assert resolved is None


async def test_resolve_token_disabled_user(session):
    """Token for disabled user returns None."""
    plaintext, token_hash = generate_api_token()

    user = User(
        email="api-disabled@test.com", password_hash=hash_password("x"),
        role="admin", disabled_at=utcnow(),
    )
    session.add(user)
    await session.flush()

    api_token = ApiToken(token_hash=token_hash, user_id=user.id, expires_at=utcnow() + timedelta(hours=1))
    session.add(api_token)
    await session.flush()

    resolved = await resolve_bearer_token(session, plaintext)
    assert resolved is None


async def test_resolve_token_no_expiry(session):
    """Token without expires_at (never expires) resolves successfully."""
    plaintext, token_hash = generate_api_token()

    user = User(email="api-noexp@test.com", password_hash=hash_password("x"), role="admin")
    session.add(user)
    await session.flush()

    api_token = ApiToken(token_hash=token_hash, user_id=user.id, expires_at=None)
    session.add(api_token)
    await session.flush()

    resolved = await resolve_bearer_token(session, plaintext)
    assert resolved is not None
    assert resolved.id == user.id


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


async def test_get_current_api_user_invalid_token(session):
    """Valid Bearer scheme but bogus token raises 401."""
    from fastapi import HTTPException
    from wiregui.api.deps import get_current_api_user

    request = MagicMock()
    request.headers = {"Authorization": "Bearer bogus-token-value"}

    with pytest.raises(HTTPException) as exc_info:
        await get_current_api_user(request, session=session)
    assert exc_info.value.status_code == 401
    assert "Invalid" in exc_info.value.detail


async def test_get_current_api_user_valid_token(session):
    """Valid Bearer token resolves to user."""
    from wiregui.api.deps import get_current_api_user

    plaintext, token_hash = generate_api_token()

    user = User(email="api-dep-test@test.com", password_hash=hash_password("x"), role="admin")
    session.add(user)
    await session.flush()

    api_token = ApiToken(token_hash=token_hash, user_id=user.id, expires_at=utcnow() + timedelta(hours=1))
    session.add(api_token)
    await session.flush()

    request = MagicMock()
    request.headers = {"Authorization": f"Bearer {plaintext}"}

    resolved = await get_current_api_user(request, session=session)
    assert resolved.id == user.id


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
