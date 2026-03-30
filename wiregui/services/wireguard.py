"""WireGuard interface management via subprocess calls to `wg` and `ip`."""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime

from loguru import logger

from wiregui.config import get_settings


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


async def ensure_interface(iface: str | None = None) -> None:
    """Create WireGuard interface if it doesn't exist, assign server IPs and bring it up."""
    settings = get_settings()
    iface = iface or settings.wg_interface

    # Check if interface exists
    try:
        await _run(["ip", "link", "show", iface])
        logger.debug("Interface {} already exists", iface)
        return
    except RuntimeError:
        pass

    logger.info("Creating WireGuard interface {}", iface)
    await _run(["ip", "link", "add", iface, "type", "wireguard"])

    # Assign server IP (first host in each network)
    from ipaddress import IPv4Network, IPv6Network

    v4_net = IPv4Network(settings.wg_ipv4_network, strict=False)
    v4_server = str(list(v4_net.hosts())[0])
    await _run(["ip", "address", "add", f"{v4_server}/{v4_net.prefixlen}", "dev", iface])

    v6_net = IPv6Network(settings.wg_ipv6_network, strict=False)
    v6_server = str(list(v6_net.hosts())[0])
    await _run(["ip", "address", "add", f"{v6_server}/{v6_net.prefixlen}", "dev", iface])

    await _run(["ip", "link", "set", iface, "up"])
    logger.info("Interface {} is up with {} and {}", iface, v4_server, v6_server)


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
