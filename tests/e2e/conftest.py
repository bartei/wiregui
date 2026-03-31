"""E2E test configuration — loads NiceGUI testing plugin and app."""

import pytest
from sqlmodel import select

from wiregui.auth.passwords import hash_password
from wiregui.db import async_session
from wiregui.models.configuration import Configuration
from wiregui.models.user import User

pytest_plugins = ["nicegui.testing.user_plugin"]

FAKE_SERVER_KEY = "SFake0ServerPubKey0000000000000000000000000w="
TEST_EMAIL = "e2e-test@example.com"
TEST_PASSWORD = "testpass123"

async def _delete_user_cascade(session, user_id):
    """Delete a user and all related objects via raw SQL to avoid stale ORM cache issues."""
    from sqlalchemy import text
    for table in ("devices", "rules", "mfa_methods", "api_tokens", "oidc_connections"):
        await session.execute(text(f"DELETE FROM {table} WHERE user_id = :uid"), {"uid": user_id})  # noqa: S608
    await session.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": user_id})


@pytest.fixture
async def test_user():
    """Create a test user and ensure server config has a public key."""
    async with async_session() as session:
        # Clean up any leftover from a previous failed run
        existing = (await session.execute(select(User).where(User.email == TEST_EMAIL))).scalar_one_or_none()
        if existing:
            await _delete_user_cascade(session, existing.id)
            await session.commit()

        # Ensure a Configuration with a server key exists
        config = (await session.execute(select(Configuration).limit(1))).scalar_one_or_none()
        if config:
            if not config.server_public_key:
                config.server_public_key = FAKE_SERVER_KEY
                session.add(config)
        else:
            config = Configuration(server_public_key=FAKE_SERVER_KEY)
            session.add(config)

        user = User(
            email=TEST_EMAIL,
            password_hash=hash_password(TEST_PASSWORD),
            role="admin",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    yield user

    # Teardown
    async with async_session() as session:
        await _delete_user_cascade(session, user.id)
        await session.commit()
