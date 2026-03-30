"""Periodically refresh OIDC tokens for all active connections."""

import asyncio

from loguru import logger
from sqlmodel import select

from wiregui.db import async_session
from wiregui.models.oidc_connection import OIDCConnection
from wiregui.models.user import User
from wiregui.services import notifications
from wiregui.utils.time import utcnow

INTERVAL_SECONDS = 600  # 10 minutes


async def oidc_refresh_loop() -> None:
    """Run forever: refresh OIDC tokens every INTERVAL_SECONDS."""
    logger.info("OIDC refresh task started (interval={}s)", INTERVAL_SECONDS)
    await asyncio.sleep(60)  # Initial delay to avoid startup spam
    while True:
        try:
            await _refresh_all()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("OIDC refresh cycle failed: {}", e)
        await asyncio.sleep(INTERVAL_SECONDS)


async def _refresh_all() -> None:
    """Attempt to refresh all stored OIDC tokens."""
    from authlib.integrations.httpx_client import AsyncOAuth2Client

    from wiregui.auth.oidc import load_providers

    providers = await load_providers()
    provider_map = {p["id"]: p for p in providers}

    async with async_session() as session:
        result = await session.execute(
            select(OIDCConnection).where(OIDCConnection.refresh_token.is_not(None))
        )
        connections = result.scalars().all()

    if not connections:
        return

    refreshed = 0
    failed = 0

    for conn in connections:
        provider_config = provider_map.get(conn.provider)
        if not provider_config:
            continue

        try:
            async with AsyncOAuth2Client(
                client_id=provider_config["client_id"],
                client_secret=provider_config["client_secret"],
            ) as client:
                # Load server metadata to get token endpoint
                discovery_url = provider_config.get("discovery_document_uri")
                if discovery_url:
                    import httpx
                    resp = await client.get(discovery_url)
                    metadata = resp.json()
                    token_endpoint = metadata.get("token_endpoint")
                else:
                    continue

                new_token = await client.refresh_token(
                    url=token_endpoint,
                    refresh_token=conn.refresh_token,
                )

            # Update connection
            async with async_session() as session:
                c = await session.get(OIDCConnection, conn.id)
                if c:
                    c.refresh_token = new_token.get("refresh_token", c.refresh_token)
                    c.refresh_response = dict(new_token)
                    c.refreshed_at = utcnow()
                    session.add(c)
                    await session.commit()

            refreshed += 1

        except Exception as e:
            failed += 1
            logger.warning("OIDC refresh failed for connection {} (provider={}): {}",
                           conn.id, conn.provider, e)

            # Check if we should disable VPN
            from wiregui.models.configuration import Configuration
            async with async_session() as session:
                config = (await session.execute(select(Configuration).limit(1))).scalar_one_or_none()
                if config and config.disable_vpn_on_oidc_error:
                    user = await session.get(User, conn.user_id)
                    if user:
                        notifications.add(
                            "error",
                            f"OIDC refresh failed for {user.email} ({conn.provider}). VPN access may be affected.",
                            user=user.email,
                        )

    if refreshed or failed:
        logger.info("OIDC refresh: {} succeeded, {} failed", refreshed, failed)
