"""Periodic WAN connectivity checks — fetch a URL and log the result."""

import asyncio

import httpx
from loguru import logger
from sqlmodel import select

from wiregui.db import async_session
from wiregui.models.configuration import Configuration
from wiregui.models.connectivity_check import ConnectivityCheck
from wiregui.services import notifications
from wiregui.utils.time import utcnow

DEFAULT_URL = "https://one.one.one.one/cdn-cgi/trace"
DEFAULT_INTERVAL = 300  # 5 minutes


async def connectivity_loop() -> None:
    """Run forever: perform connectivity checks at a configurable interval."""
    logger.info("Connectivity check task started")
    await asyncio.sleep(60)  # Initial delay to avoid startup spam
    while True:
        try:
            await _check_connectivity()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("Connectivity check failed: {}", e)
        await asyncio.sleep(DEFAULT_INTERVAL)


async def _check_connectivity() -> None:
    """Fetch the connectivity check URL and store the result."""
    url = DEFAULT_URL

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)

        check = ConnectivityCheck(
            url=url,
            response_code=resp.status_code,
            response_headers=dict(resp.headers),
            response_body=resp.text[:500],
        )
        logger.debug("Connectivity check: {} -> {}", url, resp.status_code)

    except Exception as e:
        check = ConnectivityCheck(
            url=url,
            response_code=None,
            response_body=str(e)[:500],
        )
        logger.warning("Connectivity check failed: {}", e)
        notifications.add("warning", f"WAN connectivity check failed: {e}")

    async with async_session() as session:
        session.add(check)
        await session.commit()
