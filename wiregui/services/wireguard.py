"""WireGuard interface management via subprocess calls to `wg` and `ip`."""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from ipaddress import IPv4Network, IPv6Network, ip_network

from loguru import logger

from wiregui.config import get_settings


def _normalize_cidr(value: str) -> str:
    """Normalize a CIDR/host into canonical network form (e.g. 10.0.0.1 -> 10.0.0.1/32)."""
    return str(ip_network(value, strict=False))


@dataclass
class PeerInfo:
    public_key: str
    endpoint: str | None = None
    allowed_ips: list[str] = field(default_factory=list)
    latest_handshake: datetime | None = None
    rx_bytes: int = 0
    tx_bytes: int = 0


async def _run(args: list[str], input_data: str | None = None) -> str:
    """Run a subprocess and return stdout. Raises on non-zero exit."""
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.PIPE if input_data else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate(input_data.encode() if input_data else None)
    if proc.returncode != 0:
        raise RuntimeError(f"{' '.join(args)} failed (rc={proc.returncode}): {stderr.decode().strip()}")
    return stdout.decode().strip()


def _server_addresses(settings) -> list[str]:
    """The server's own address in each WG network — the first host of each prefix."""
    v4 = IPv4Network(settings.wg_ipv4_network, strict=False)
    v6 = IPv6Network(settings.wg_ipv6_network, strict=False)
    return [
        f"{next(v4.hosts())}/{v4.prefixlen}",
        f"{next(v6.hosts())}/{v6.prefixlen}",
    ]


async def _interface_addresses(iface: str) -> set[str]:
    """Addresses currently configured on the interface, as `addr/prefixlen` strings."""
    try:
        out = await _run(["ip", "-json", "address", "show", "dev", iface])
    except RuntimeError:
        return set()
    return {
        f"{a['local']}/{a['prefixlen']}"
        for entry in json.loads(out or "[]")
        for a in entry.get("addr_info", [])
    }


async def ensure_interface(iface: str | None = None) -> None:
    """Ensure the interface exists, carries the server addresses and is up.

    Re-asserts addresses on every call rather than only at creation: another daemon on
    the host (dhcpcd, systemd-networkd, NetworkManager) or an operator can strip an
    address from an existing interface, and a create-once check leaves that broken
    until the link itself is deleted.
    """
    settings = get_settings()
    iface = iface or settings.wg_interface

    created = False
    try:
        await _run(["ip", "link", "show", iface])
    except RuntimeError:
        logger.info("Creating WireGuard interface {}", iface)
        await _run(["ip", "link", "add", iface, "type", "wireguard"])
        created = True

    existing = set() if created else await _interface_addresses(iface)
    addresses = _server_addresses(settings)
    restored = False
    for addr in addresses:
        if not created and addr not in existing:
            # WARNING: on an interface that already existed, a missing address means
            # something external removed it.
            logger.warning("Restoring missing address {} on {}", addr, iface)
            restored = True
        await _run(["ip", "address", "replace", addr, "dev", iface])

    await _run(["ip", "link", "set", iface, "up"])
    # DEBUG when nothing changed: this also runs periodically, not just at startup.
    log = logger.info if created or restored else logger.debug
    log("Interface {} is up with {}", iface, ", ".join(addresses))


async def configure_interface(iface: str | None = None) -> None:
    """Set the server private key and listen port on the WireGuard interface from DB config."""
    from sqlmodel import select

    from wiregui.db import async_session
    from wiregui.models.configuration import Configuration

    settings = get_settings()
    iface = iface or settings.wg_interface

    async with async_session() as session:
        result = await session.execute(select(Configuration).limit(1))
        config = result.scalar_one_or_none()

    if not config or not config.server_private_key:
        logger.error("No server private key in Configuration — WG interface not configured")
        return

    # Write private key to a temp file (stdin piping has issues with uvloop)
    import tempfile
    import os

    key_fd, key_path = tempfile.mkstemp()
    try:
        os.write(key_fd, config.server_private_key.encode())
        os.close(key_fd)
        os.chmod(key_path, 0o600)
        await _run(["wg", "set", iface, "private-key", key_path, "listen-port", str(settings.wg_endpoint_port)])
    finally:
        os.unlink(key_path)

    logger.info("WireGuard interface {} configured (listen-port={})", iface, settings.wg_endpoint_port)


async def set_private_key(private_key_path: str, iface: str | None = None) -> None:
    """Set the WireGuard private key from a file."""
    settings = get_settings()
    iface = iface or settings.wg_interface
    await _run(["wg", "set", iface, "private-key", private_key_path])


async def set_listen_port(port: int, iface: str | None = None) -> None:
    """Set the WireGuard listen port."""
    settings = get_settings()
    iface = iface or settings.wg_interface
    await _run(["wg", "set", iface, "listen-port", str(port)])


async def add_peer(
    public_key: str,
    allowed_ips: list[str],
    preshared_key: str | None = None,
    iface: str | None = None,
) -> None:
    """Add or update a WireGuard peer."""
    settings = get_settings()
    iface = iface or settings.wg_interface

    args = ["wg", "set", iface, "peer", public_key, "allowed-ips", ",".join(allowed_ips)]
    if preshared_key:
        import tempfile
        import os

        psk_fd, psk_path = tempfile.mkstemp()
        try:
            os.write(psk_fd, preshared_key.encode())
            os.close(psk_fd)
            os.chmod(psk_path, 0o600)
            await _run([
                "wg", "set", iface, "peer", public_key,
                "allowed-ips", ",".join(allowed_ips),
                "preshared-key", psk_path,
            ])
        finally:
            os.unlink(psk_path)
    else:
        await _run(args)

    logger.info("Peer added/updated: {} -> {}", public_key[:20], allowed_ips)


async def remove_peer(public_key: str, iface: str | None = None) -> None:
    """Remove a WireGuard peer."""
    settings = get_settings()
    iface = iface or settings.wg_interface
    await _run(["wg", "set", iface, "peer", public_key, "remove"])
    logger.info("Peer removed: {}", public_key[:20])


async def get_peers(iface: str | None = None) -> list[PeerInfo]:
    """Parse `wg show <iface> dump` and return peer information."""
    settings = get_settings()
    iface = iface or settings.wg_interface

    try:
        output = await _run(["wg", "show", iface, "dump"])
    except RuntimeError:
        return []

    peers = []
    for line in output.splitlines()[1:]:  # skip the interface line
        parts = line.split("\t")
        if len(parts) < 8:
            continue
        pub_key = parts[0]
        # parts: public_key, preshared_key, endpoint, allowed_ips, latest_handshake, rx, tx, keepalive
        endpoint = parts[2] if parts[2] != "(none)" else None
        allowed_ips = parts[3].split(",") if parts[3] != "(none)" else []
        handshake_ts = int(parts[4]) if parts[4] != "0" else None
        latest_handshake = datetime.utcfromtimestamp(handshake_ts) if handshake_ts else None
        rx_bytes = int(parts[5])
        tx_bytes = int(parts[6])

        peers.append(PeerInfo(
            public_key=pub_key,
            endpoint=endpoint,
            allowed_ips=allowed_ips,
            latest_handshake=latest_handshake,
            rx_bytes=rx_bytes,
            tx_bytes=tx_bytes,
        ))
    return peers


async def add_routes(subnets: list[str], iface: str | None = None) -> None:
    """Add IP routes for relay subnets through the WireGuard interface.
    
    Args:
        subnets: List of CIDR subnets to route through WireGuard
        iface: WireGuard interface name (defaults to config value)
    """
    if not subnets:
        return
    
    settings = get_settings()
    iface = iface or settings.wg_interface
    
    for subnet in subnets:
        try:
            if ":" in subnet:
                # IPv6
                await _run(["ip", "-6", "route", "add", subnet, "dev", iface])
            else:
                # IPv4
                await _run(["ip", "-4", "route", "add", subnet, "dev", iface])
            logger.debug("Route added: {} via {}", subnet, iface)
        except RuntimeError as e:
            # Route might already exist, log but don't fail
            if "File exists" not in str(e):
                logger.warning("Failed to add route for {}: {}", subnet, e)


async def remove_routes(subnets: list[str], iface: str | None = None) -> None:
    """Remove IP routes for relay subnets.
    
    Args:
        subnets: List of CIDR subnets to remove routes for
        iface: WireGuard interface name (defaults to config value)
    """
    if not subnets:
        return
    
    settings = get_settings()
    iface = iface or settings.wg_interface
    
    for subnet in subnets:
        try:
            if ":" in subnet:
                # IPv6
                await _run(["ip", "-6", "route", "del", subnet, "dev", iface])
            else:
                # IPv4
                await _run(["ip", "-4", "route", "del", subnet, "dev", iface])
            logger.debug("Route removed: {} via {}", subnet, iface)
        except RuntimeError as e:
            # Route might not exist, log but don't fail
            logger.debug("Failed to remove route for {}: {}", subnet, e)


async def get_interface_routes(iface: str | None = None) -> set[str]:
    """Return the set of normalized CIDR destinations currently routed via the interface."""
    settings = get_settings()
    iface = iface or settings.wg_interface

    routes: set[str] = set()
    for family in ("-4", "-6"):
        try:
            output = await _run(["ip", family, "route", "show", "dev", iface])
        except RuntimeError:
            continue
        for line in output.splitlines():
            line = line.strip()
            if not line or line.startswith("default"):
                continue
            dest = line.split()[0]
            try:
                routes.add(_normalize_cidr(dest))
            except ValueError:
                continue
    return routes


async def sync_routes(expected_subnets, iface: str | None = None) -> None:
    """Make the interface's relay routes exactly match ``expected_subnets``.

    Adds missing routes and removes orphaned ones (e.g. left behind when a device
    or one of its subnets is removed), so the kernel routing table converges to the
    database. The WireGuard tunnel networks are never touched.
    """
    settings = get_settings()
    iface = iface or settings.wg_interface

    # Never remove the tunnel network routes managed by interface setup.
    protected: set[str] = set()
    for net in (settings.wg_ipv4_network, settings.wg_ipv6_network):
        try:
            protected.add(_normalize_cidr(net))
        except ValueError:
            pass

    expected: set[str] = set()
    for subnet in expected_subnets:
        try:
            expected.add(_normalize_cidr(subnet))
        except ValueError:
            logger.warning("Skipping invalid relay subnet during route sync: {}", subnet)

    actual = await get_interface_routes(iface)
    to_add = sorted(expected - actual)
    to_remove = sorted((actual - expected) - protected)

    if to_add:
        await add_routes(to_add, iface)
    if to_remove:
        await remove_routes(to_remove, iface)
    if to_add or to_remove:
        logger.info("Synced relay routes on {}: +{} -{}", iface, len(to_add), len(to_remove))
