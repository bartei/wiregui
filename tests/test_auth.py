"""Tests for authentication modules — seed logic and JWT edge cases."""

from sqlmodel import select

from wiregui.auth.jwt import create_access_token, decode_access_token
from wiregui.auth.passwords import hash_password, verify_password
from wiregui.auth.seed import seed_admin
from wiregui.models.user import User


# --- Password hashing (format guard) ---


def test_hash_is_not_plaintext():
    hashed = hash_password("plaintext")
    assert hashed != "plaintext"
    assert hashed.startswith("$2b$")


# --- JWT edge cases ---


def test_decode_invalid_token():
    assert decode_access_token("garbage.token.value") is None


def test_decode_tampered_token():
    token = create_access_token(user_id="user-123", role="admin")
    tampered = token[:-4] + "XXXX"
    assert decode_access_token(tampered) is None


# --- Admin seed ---


async def test_seed_admin_creates_user(session, monkeypatch):
    """seed_admin should create an admin when no users exist."""
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


async def test_seed_admin_autogenerates_password(session, monkeypatch):
    """seed_admin should generate a random password and log it when admin_password is None."""
    from contextlib import asynccontextmanager

    from loguru import logger

    @asynccontextmanager
    async def mock_session():
        yield session

    monkeypatch.setattr("wiregui.auth.seed.async_session", mock_session)
    monkeypatch.setattr("wiregui.auth.seed.get_settings", lambda: type("S", (), {
        "admin_email": "autogen@example.com",
        "admin_password": None,
    })())

    log_messages = []
    sink_id = logger.add(lambda msg: log_messages.append(msg.record), level="WARNING")
    try:
        await seed_admin()
    finally:
        logger.remove(sink_id)

    # Admin user was created
    result = await session.execute(select(User).where(User.email == "autogen@example.com"))
    admin = result.scalar_one()
    assert admin.role == "admin"

    # The generated password was logged
    password_records = [r for r in log_messages if "Generated admin password" in r["message"]]
    assert len(password_records) == 1

    # The logged password actually works
    logged_password = password_records[0]["message"].split(": ", 1)[1]
    assert verify_password(logged_password, admin.password_hash)


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
