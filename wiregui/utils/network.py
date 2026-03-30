"""IP address allocation for WireGuard tunnel addresses."""

import random
from ipaddress import IPv4Network, IPv6Network, ip_address

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from wiregui.models.device import Device


async def allocate_ipv4(session: AsyncSession, network_cidr: str) -> str:
    """Find the next available IPv4 address in the given CIDR range."""
    network = IPv4Network(network_cidr, strict=False)
    used = await _get_used_ips(session, "ipv4")
    return _find_available(network, used)


async def allocate_ipv6(session: AsyncSession, network_cidr: str) -> str:
    """Find the next available IPv6 address in the given CIDR range."""
    network = IPv6Network(network_cidr, strict=False)
    used = await _get_used_ips(session, "ipv6")
    return _find_available(network, used)


async def _get_used_ips(session: AsyncSession, field: str) -> set[str]:
    """Get all IPs currently assigned to devices for the given field."""
    col = Device.ipv4 if field == "ipv4" else Device.ipv6
    result = await session.execute(select(col).where(col.is_not(None)))
    return {row[0] for row in result.all()}


def _find_available(network: IPv4Network | IPv6Network, used: set[str]) -> str:
    """Find an available IP in the network, starting from a random offset."""
    hosts = list(network.hosts())
    if not hosts:
        raise ValueError(f"No usable hosts in {network}")

    # Skip the first host (gateway/server address)
    hosts = hosts[1:]
    if not hosts:
        raise ValueError(f"No usable hosts in {network} after reserving gateway")

    # Start from a random offset, then scan forward and backward
    start = random.randint(0, len(hosts) - 1)

    # Forward scan
    for i in range(start, len(hosts)):
        candidate = str(hosts[i])
        if candidate not in used:
            logger.debug("Allocated {} from {}", candidate, network)
            return candidate

    # Backward scan
    for i in range(start - 1, -1, -1):
        candidate = str(hosts[i])
        if candidate not in used:
            logger.debug("Allocated {} from {}", candidate, network)
            return candidate

    raise ValueError(f"No available addresses in {network}")
