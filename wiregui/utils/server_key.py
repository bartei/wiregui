"""Retrieve the server's WireGuard public key from the Configuration table."""

from loguru import logger
from sqlmodel import select

from wiregui.db import async_session
from wiregui.models.configuration import Configuration


async def get_server_public_key() -> str:
    """Get the server's WireGuard public key. Raises if not configured."""
    async with async_session() as session:
        result = await session.execute(select(Configuration).limit(1))
        config = result.scalar_one_or_none()

    if config and config.server_public_key:
        return config.server_public_key

    raise RuntimeError("Server WireGuard keypair not configured — run setup or check wg CLI availability")
