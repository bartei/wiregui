"""Seed the initial admin user and server keypair on first startup."""

import secrets

from loguru import logger
from sqlmodel import select

from wiregui.auth.passwords import hash_password
from wiregui.config import get_settings
from wiregui.db import async_session
from wiregui.models.configuration import Configuration
from wiregui.models.user import User


async def seed_admin() -> None:
    """Create admin user if no users exist in the database."""
    async with async_session() as session:
        result = await session.execute(select(User).limit(1))
        if result.scalar_one_or_none() is not None:
            return  # users already exist

        settings = get_settings()
        password = settings.admin_password or secrets.token_urlsafe(16)

        admin = User(
            email=settings.admin_email,
            password_hash=hash_password(password),
            role="admin",
        )
        session.add(admin)
        await session.commit()

        logger.info("Admin user created: {}", settings.admin_email)
        if settings.admin_password is None:
            logger.warning("Generated admin password: {}", password)


async def ensure_server_keypair() -> None:
    """Generate and store the server WireGuard keypair in Configuration if missing."""
    from wiregui.utils.crypto import generate_keypair

    async with async_session() as session:
        result = await session.execute(select(Configuration).limit(1))
        config = result.scalar_one_or_none()

        if config is None:
            config = Configuration()
            session.add(config)

        if config.server_public_key and config.server_private_key:
            return  # already have keys

        try:
            private_key, public_key = await generate_keypair()
            config.server_private_key = private_key
            config.server_public_key = public_key
            session.add(config)
            await session.commit()
            logger.info("Server WireGuard keypair generated (pubkey: {}...)", public_key[:20])
        except Exception as e:
            logger.warning("Could not generate server keypair (wg CLI not available?): {}", e)
