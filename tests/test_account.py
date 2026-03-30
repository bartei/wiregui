"""Tests for account functionality — password changes, API tokens, OIDC connections."""

import hashlib
from datetime import timedelta

from sqlmodel import func, select

from wiregui.auth.api_token import generate_api_token
from wiregui.auth.passwords import hash_password, verify_password
from wiregui.models.api_token import ApiToken
from wiregui.models.oidc_connection import OIDCConnection
from wiregui.models.user import User
from wiregui.utils.time import utcnow


# --- Password change ---


async def test_password_change_flow(session):
    """Simulate the password change flow: verify old, set new."""
    user = User(email="pw-change@example.com", password_hash=hash_password("old-password"))
    session.add(user)
    await session.flush()

    # Verify old password
    assert verify_password("old-password", user.password_hash) is True

    # Change password
    user.password_hash = hash_password("new-password")
    session.add(user)
    await session.flush()

    fetched = await session.get(User, user.id)
    assert verify_password("new-password", fetched.password_hash) is True
    assert verify_password("old-password", fetched.password_hash) is False


async def test_password_change_wrong_current(session):
    """Wrong current password should not allow change."""
    user = User(email="pw-wrong@example.com", password_hash=hash_password("correct"))
    session.add(user)
    await session.flush()

    # Simulate check
    assert verify_password("wrong", user.password_hash) is False


# --- API token management ---


async def test_create_multiple_tokens(session):
    user = User(email="multi-token@example.com")
    session.add(user)
    await session.flush()

    for _ in range(3):
        _, token_hash = generate_api_token()
        session.add(ApiToken(token_hash=token_hash, user_id=user.id))
    await session.flush()

    count = (await session.execute(
        select(func.count()).select_from(ApiToken).where(ApiToken.user_id == user.id)
    )).scalar()
    assert count == 3


async def test_token_with_expiry(session):
    user = User(email="expiry-token@example.com")
    session.add(user)
    await session.flush()

    _, token_hash = generate_api_token()
    expires = utcnow() + timedelta(days=30)
    token = ApiToken(token_hash=token_hash, expires_at=expires, user_id=user.id)
    session.add(token)
    await session.flush()

    fetched = await session.get(ApiToken, token.id)
    assert fetched.expires_at is not None
    assert fetched.expires_at > utcnow()


async def test_delete_token(session):
    user = User(email="del-token@example.com")
    session.add(user)
    await session.flush()

    _, token_hash = generate_api_token()
    token = ApiToken(token_hash=token_hash, user_id=user.id)
    session.add(token)
    await session.flush()

    await session.delete(token)
    await session.flush()

    assert await session.get(ApiToken, token.id) is None


# --- OIDC connections ---


async def test_oidc_connection_create(session):
    user = User(email="oidc-conn@example.com")
    session.add(user)
    await session.flush()

    conn = OIDCConnection(
        provider="google",
        refresh_token="refresh-tok-123",
        refresh_response={"access_token": "at", "token_type": "Bearer"},
        refreshed_at=utcnow(),
        user_id=user.id,
    )
    session.add(conn)
    await session.flush()

    fetched = (await session.execute(
        select(OIDCConnection).where(OIDCConnection.user_id == user.id)
    )).scalar_one()
    assert fetched.provider == "google"
    assert fetched.refresh_token == "refresh-tok-123"
    assert fetched.refresh_response["access_token"] == "at"


async def test_multiple_oidc_providers(session):
    user = User(email="multi-oidc@example.com")
    session.add(user)
    await session.flush()

    for provider in ["google", "okta", "azure"]:
        conn = OIDCConnection(provider=provider, user_id=user.id)
        session.add(conn)
    await session.flush()

    count = (await session.execute(
        select(func.count()).select_from(OIDCConnection).where(OIDCConnection.user_id == user.id)
    )).scalar()
    assert count == 3


async def test_oidc_connection_update_refresh_token(session):
    user = User(email="oidc-refresh@example.com")
    session.add(user)
    await session.flush()

    conn = OIDCConnection(
        provider="google",
        refresh_token="old-token",
        user_id=user.id,
    )
    session.add(conn)
    await session.flush()

    conn.refresh_token = "new-token"
    conn.refreshed_at = utcnow()
    session.add(conn)
    await session.flush()

    fetched = await session.get(OIDCConnection, conn.id)
    assert fetched.refresh_token == "new-token"
    assert fetched.refreshed_at is not None
