"""Expire VPN sessions — remove WireGuard peers for users whose session has timed out."""

import asyncio

from loguru import logger
from sqlmodel import select

from wiregui.db import async_session
from wiregui.models.configuration import Configuration
from wiregui.models.device import Device
from wiregui.models.user import User
from wiregui.services import notifications, wireguard
from wiregui.utils.time import utcnow

INTERVAL_SECONDS = 60


async def vpn_session_loop() -> None:
    """Run forever: check for expired VPN sessions every INTERVAL_SECONDS."""
    logger.info("VPN session expiry task started (interval={}s)", INTERVAL_SECONDS)
    while True:
        try:
            await _expire_sessions()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("VPN session check failed: {}", e)
        await asyncio.sleep(INTERVAL_SECONDS)


async def _expire_sessions() -> None:
    """Find users with expired VPN sessions and remove their WireGuard peers."""
    async with async_session() as session:
        config = (await session.execute(select(Configuration).limit(1))).scalar_one_or_none()
        if not config or config.vpn_session_duration == 0:
            return  # 0 = unlimited, no expiry

        duration_seconds = config.vpn_session_duration
        now = utcnow()

        # Find users whose last sign-in was more than duration_seconds ago
        result = await session.execute(select(User).where(User.last_signed_in_at.is_not(None)))
        users = result.scalars().all()

        expired_count = 0
        for user in users:
            if user.disabled_at is not None:
                continue

            elapsed = (now - user.last_signed_in_at).total_seconds()
            if elapsed <= duration_seconds:
                continue

            # Session expired — remove all user's device peers
            devices = (await session.execute(
                select(Device).where(Device.user_id == user.id)
            )).scalars().all()

            for device in devices:
                try:
                    await wireguard.remove_peer(public_key=device.public_key)
                except Exception as e:
                    logger.debug("Failed to remove expired peer {}: {}", device.public_key[:16], e)

            expired_count += 1
            logger.info("VPN session expired for {} ({} devices removed)", user.email, len(devices))
            notifications.add(
                "warning",
                f"VPN session expired for {user.email}",
                user=user.email,
            )

        if expired_count:
            logger.info("Expired {} user VPN sessions", expired_count)
