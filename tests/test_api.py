"""Tests for REST API endpoints and token auth."""

import hashlib

from wiregui.auth.api_token import generate_api_token, resolve_bearer_token
from wiregui.auth.passwords import hash_password
from wiregui.models.api_token import ApiToken
from wiregui.models.user import User
from wiregui.utils.time import utcnow


# --- Token generation ---


def test_generate_api_token():
    plaintext, token_hash = generate_api_token()
    assert len(plaintext) > 20
    assert token_hash == hashlib.sha256(plaintext.encode()).hexdigest()


def test_generate_api_token_unique():
    t1, h1 = generate_api_token()
    t2, h2 = generate_api_token()
    assert t1 != t2
    assert h1 != h2


# --- Token resolution ---


async def test_resolve_valid_token(session):
    user = User(email="api-user@example.com", password_hash=hash_password("x"), role="admin")
    session.add(user)
    await session.flush()

    plaintext, token_hash = generate_api_token()
    token = ApiToken(token_hash=token_hash, user_id=user.id)
    session.add(token)
    await session.flush()

    resolved = await resolve_bearer_token(session, plaintext)
    assert resolved is not None
    assert resolved.id == user.id


async def test_resolve_invalid_token(session):
    resolved = await resolve_bearer_token(session, "bogus-token")
    assert resolved is None


async def test_resolve_expired_token(session):
    from datetime import timedelta

    user = User(email="expired-api@example.com", password_hash=hash_password("x"))
    session.add(user)
    await session.flush()

    plaintext, token_hash = generate_api_token()
    token = ApiToken(
        token_hash=token_hash,
        user_id=user.id,
        expires_at=utcnow() - timedelta(hours=1),
    )
    session.add(token)
    await session.flush()

    resolved = await resolve_bearer_token(session, plaintext)
    assert resolved is None


async def test_resolve_token_disabled_user(session):
    user = User(
        email="disabled-api@example.com",
        password_hash=hash_password("x"),
        disabled_at=utcnow(),
    )
    session.add(user)
    await session.flush()

    plaintext, token_hash = generate_api_token()
    token = ApiToken(token_hash=token_hash, user_id=user.id)
    session.add(token)
    await session.flush()

    resolved = await resolve_bearer_token(session, plaintext)
    assert resolved is None
