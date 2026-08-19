"""Periodic WAN connectivity checks — fetch a URL and log the result."""

import asyncio

import httpx
from loguru import logger
from sqlmodel import select

from wiregui.config import get_settings
from wiregui.db import async_session
from wiregui.models.configuration import Configuration
from wiregui.models.connectivity_check import ConnectivityCheck
from wiregui.services import notifications
from wiregui.utils.time import utcnow

# Target Cloudflare by IP, not by hostname: the check must measure WAN reachability
# without depending on DNS resolution, which fails intermittently on some hosts
# ([Errno -3] Temporary failure in name resolution) and produced false "down" reports.
# Cloudflare's cert lists 1.1.1.1 as an IP SAN, so TLS verification still succeeds.
DEFAULT_URL = "https://1.1.1.1/cdn-cgi/trace"
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

        # Re-converge the WG interface so externally-caused drift (e.g. a host DHCP
        # client stripping an address) self-heals within one interval instead of
        # persisting until the next restart.
        if get_settings().wg_enabled:
            try:
                from wiregui.services.wireguard import ensure_interface

                await ensure_interface()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("Interface convergence failed: {}", e)

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
