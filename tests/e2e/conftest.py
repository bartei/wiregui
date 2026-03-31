"""E2E test configuration — loads NiceGUI testing plugin and app."""

import pytest
from sqlmodel import select

from wiregui.auth.passwords import hash_password
from wiregui.db import async_session
from wiregui.models.api_token import ApiToken
from wiregui.models.configuration import Configuration
from wiregui.models.device import Device
from wiregui.models.mfa_method import MFAMethod
from wiregui.models.oidc_connection import OIDCConnection
from wiregui.models.rule import Rule
from wiregui.models.user import User

pytest_plugins = ["nicegui.testing.user_plugin"]

FAKE_SERVER_KEY = "SFake0ServerPubKey0000000000000000000000000w="
TEST_EMAIL = "e2e-test@example.com"
TEST_PASSWORD = "testpass123"

RELATED_MODELS = (Device, Rule, MFAMethod, ApiToken, OIDCConnection)


async def _delete_user_cascade(session, user_id):
    """Delete a user and all related objects."""
    for model in RELATED_MODELS:
        for obj in (await session.execute(select(model).where(model.user_id == user_id))).scalars().all():
            await session.delete(obj)
    u = await session.get(User, user_id)
    if u:
        await session.delete(u)


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
