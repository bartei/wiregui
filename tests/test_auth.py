"""Tests for authentication modules."""

from sqlmodel import select

from wiregui.auth.jwt import create_access_token, decode_access_token
from wiregui.auth.passwords import hash_password, verify_password
from wiregui.auth.seed import seed_admin
from wiregui.models.user import User


# --- Password hashing ---


def test_hash_and_verify():
    hashed = hash_password("my-secret")
    assert verify_password("my-secret", hashed) is True


def test_verify_wrong_password():
    hashed = hash_password("correct")
    assert verify_password("wrong", hashed) is False


def test_hash_is_not_plaintext():
    hashed = hash_password("plaintext")
    assert hashed != "plaintext"
    assert hashed.startswith("$2b$")


# --- JWT ---


def test_create_and_decode_token():
    token = create_access_token(user_id="user-123", role="admin")
    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == "user-123"
    assert payload["role"] == "admin"
    assert "exp" in payload


def test_decode_invalid_token():
    assert decode_access_token("garbage.token.value") is None


def test_decode_tampered_token():
    token = create_access_token(user_id="user-123", role="admin")
    tampered = token[:-4] + "XXXX"
    assert decode_access_token(tampered) is None


# --- Admin seed ---


async def test_seed_admin_creates_user(session, monkeypatch):
    """seed_admin should create an admin when no users exist."""
    # Patch async_session to use our test session
    from unittest.mock import AsyncMock
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def mock_session():
        yield session

    monkeypatch.setattr("wiregui.auth.seed.async_session", mock_session)
    monkeypatch.setattr("wiregui.auth.seed.get_settings", lambda: type("S", (), {
        "admin_email": "seed-test@example.com",
        "admin_password": "seed-pass-123",
    })())

    await seed_admin()

    result = await session.execute(select(User).where(User.email == "seed-test@example.com"))
    admin = result.scalar_one()
    assert admin.role == "admin"
    assert verify_password("seed-pass-123", admin.password_hash)


async def test_seed_admin_skips_when_users_exist(session, monkeypatch):
    """seed_admin should not create a second admin if users already exist."""
    from contextlib import asynccontextmanager

    existing = User(email="existing@example.com", role="unprivileged")
    session.add(existing)
    await session.flush()

    @asynccontextmanager
    async def mock_session():
        yield session

    monkeypatch.setattr("wiregui.auth.seed.async_session", mock_session)

    await seed_admin()

    result = await session.execute(select(User))
    users = result.scalars().all()
    assert len(users) == 1
    assert users[0].email == "existing@example.com"
