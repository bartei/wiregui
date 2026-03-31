"""E2E test configuration — loads NiceGUI testing plugin and app."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import select

from wiregui.auth.passwords import hash_password
from wiregui.config import get_settings
from wiregui.db import async_session
from wiregui.models.configuration import Configuration
from wiregui.models.user import User

pytest_plugins = ["nicegui.testing.user_plugin"]

FAKE_SERVER_KEY = "SFake0ServerPubKey0000000000000000000000000w="
TEST_EMAIL = "e2e-test@example.com"
TEST_PASSWORD = "testpass123"

_CHILD_TABLES = ("devices", "rules", "mfa_methods", "api_tokens", "oidc_connections")


async def _cleanup_test_user():
    """Delete the test user and all related objects using a fresh engine."""
    engine = create_async_engine(get_settings().database_url)
    async with engine.begin() as conn:
        # Find user id by email
        row = (await conn.execute(
            text("SELECT id FROM users WHERE email = :email"), {"email": TEST_EMAIL}
        )).first()
        if row:
            uid = row[0]
            for table in _CHILD_TABLES:
                await conn.execute(text(f"DELETE FROM {table} WHERE user_id = :uid"), {"uid": uid})  # noqa: S608
            await conn.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": uid})
    await engine.dispose()


@pytest.fixture
async def test_user():
    """Create a test user and ensure server config has a public key."""
    # Clean up any leftover from a previous failed run
    await _cleanup_test_user()

    async with async_session() as session:
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

    await _cleanup_test_user()
