"""IP address allocation for WireGuard tunnel addresses."""

import random
from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network, ip_network

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from wiregui.models.device import Device


def parse_subnet_list(raw: str) -> list[str]:
    """Parse a comma-separated string of CIDR subnets into validated, normalized values.

    Each entry must be a valid IPv4/IPv6 network; host bits are masked off
    (e.g. ``192.168.1.5/24`` -> ``192.168.1.0/24``). Raises ``ValueError`` on any
    invalid entry. Validation is mandatory because these values are interpolated
    into ``nft`` rules and ``ip route`` commands — rejecting non-CIDR input both
    prevents command injection and stops one bad entry from failing the whole
    firewall rebuild.
    """
    subnets: list[str] = []
    for part in raw.split(","):
        candidate = part.strip()
        if not candidate:
            continue
        # ip_network raises ValueError for anything that isn't a clean CIDR.
        subnets.append(str(ip_network(candidate, strict=False)))
    return subnets


async def allocate_ipv4(session: AsyncSession, network_cidr: str) -> str:
    """Find an available IPv4 address in the given CIDR range."""
    network = IPv4Network(network_cidr, strict=False)
    used = await _get_used_ips(session, "ipv4")
    return _find_available_v4(network, used)


async def allocate_ipv6(session: AsyncSession, network_cidr: str) -> str:
    """Find an available IPv6 address in the given CIDR range."""
    network = IPv6Network(network_cidr, strict=False)
    used = await _get_used_ips(session, "ipv6")
    return _find_available_v6(network, used)


async def _get_used_ips(session: AsyncSession, field: str) -> set[str]:
    """Get all IPs currently assigned to devices for the given field."""
    col = Device.ipv4 if field == "ipv4" else Device.ipv6
    result = await session.execute(select(col).where(col.is_not(None)))
    return {row[0] for row in result.all()}


def _find_available_v4(network: IPv4Network, used: set[str]) -> str:
    """Find an available IPv4 by random sampling — O(1) per attempt, no list materialization."""
    # Usable range: network_address + 2 to broadcast - 1 (skip network, gateway, broadcast)
    first = int(network.network_address) + 2
    last = int(network.broadcast_address) - 1
    pool_size = last - first + 1

    if pool_size <= 0:
        raise ValueError(f"No usable hosts in {network}")
    if len(used) >= pool_size:
        raise ValueError(f"No available addresses in {network}")

    for _ in range(min(pool_size, 1000)):
        candidate = str(IPv4Address(random.randint(first, last)))
        if candidate not in used:
            logger.debug("Allocated {} from {}", candidate, network)
            return candidate

    # Fallback: sequential scan (only if random sampling keeps hitting used IPs)
    for offset in range(pool_size):
        candidate = str(IPv4Address(first + offset))
        if candidate not in used:
            logger.debug("Allocated {} from {}", candidate, network)
            return candidate

    raise ValueError(f"No available addresses in {network}")


def _find_available_v6(network: IPv6Network, used: set[str]) -> str:
    """Find an available IPv6 by random sampling."""
    first = int(network.network_address) + 2
    last = int(network.broadcast_address) - 1
    pool_size = last - first + 1

    if pool_size <= 0:
        raise ValueError(f"No usable hosts in {network}")
    if len(used) >= pool_size:
        raise ValueError(f"No available addresses in {network}")

    for _ in range(min(pool_size, 1000)):
        candidate = str(IPv6Address(random.randint(first, last)))
        if candidate not in used:
            logger.debug("Allocated {} from {}", candidate, network)
            return candidate

    # Fallback: sequential scan
    for offset in range(pool_size):
        candidate = str(IPv6Address(first + offset))
        if candidate not in used:
            logger.debug("Allocated {} from {}", candidate, network)
            return candidate

    raise ValueError(f"No available addresses in {network}")
