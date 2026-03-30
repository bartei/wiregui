"""Periodically poll WireGuard peer stats and update device records."""

import asyncio

from loguru import logger
from sqlmodel import select

from wiregui.db import async_session
from wiregui.models.device import Device
from wiregui.services import wireguard

INTERVAL_SECONDS = 60


async def stats_loop() -> None:
    """Run forever: poll WireGuard stats every INTERVAL_SECONDS."""
    logger.info("Stats task started (interval={}s)", INTERVAL_SECONDS)
    while True:
        try:
            await _update_stats()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("Stats update failed: {}", e)
        await asyncio.sleep(INTERVAL_SECONDS)


async def _update_stats() -> None:
    """Fetch peer stats from WireGuard and update matching device rows."""
    peers = await wireguard.get_peers()
    if not peers:
        return

    peer_map = {p.public_key: p for p in peers}

    async with async_session() as session:
        result = await session.execute(
            select(Device).where(Device.public_key.in_(list(peer_map.keys())))
        )
        devices = result.scalars().all()

        updated = 0
        for device in devices:
            peer = peer_map.get(device.public_key)
            if peer is None:
                continue
            device.rx_bytes = peer.rx_bytes
            device.tx_bytes = peer.tx_bytes
            device.latest_handshake = peer.latest_handshake
            device.remote_ip = peer.endpoint.split(":")[0] if peer.endpoint else None
            session.add(device)
            updated += 1

        if updated:
            await session.commit()
            logger.debug("Updated stats for {} devices", updated)
