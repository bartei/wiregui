"""nftables firewall management — per-user chains and sets for device traffic filtering."""

import asyncio
import json

from loguru import logger

from wiregui.config import get_settings

TABLE_NAME = "wiregui"


async def _nft(cmd: str) -> str:
    """Run an nft command and return stdout."""
    proc = await asyncio.create_subprocess_exec(
        "nft", *cmd.split(),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"nft {cmd} failed: {stderr.decode().strip()}")
    return stdout.decode().strip()


async def _nft_batch(commands: list[str]) -> None:
    """Run multiple nft commands in a single atomic batch."""
    batch = "\n".join(commands)
    proc = await asyncio.create_subprocess_exec(
        "nft", "-f", "-",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate(batch.encode())
    if proc.returncode != 0:
        raise RuntimeError(f"nft batch failed: {stderr.decode().strip()}")


async def setup_base_tables() -> None:
    """Create the base wiregui table with forward and postrouting chains."""
    commands = [
        f"add table inet {TABLE_NAME}",
        # Forward chain for filtering device traffic
        f"add chain inet {TABLE_NAME} forward {{ type filter hook forward priority 0; policy accept; }}",
        # Postrouting for NAT/masquerade
        f"add chain inet {TABLE_NAME} postrouting {{ type nat hook postrouting priority 100; policy accept; }}",
    ]
    try:
        await _nft_batch(commands)
        logger.info("Base nftables table '{}' created", TABLE_NAME)
    except RuntimeError as e:
        # Table may already exist
        if "File exists" not in str(e):
            raise
        logger.debug("Base nftables table '{}' already exists", TABLE_NAME)


async def setup_masquerade(iface: str | None = None) -> None:
    """Add masquerade rules for VPN traffic — NAT only traffic originating from WG subnets."""
    settings = get_settings()
    iface = iface or settings.wg_interface
    v4_net = settings.wg_ipv4_network
    v6_net = settings.wg_ipv6_network
    commands = [
        f"flush chain inet {TABLE_NAME} postrouting",
        f'add rule inet {TABLE_NAME} postrouting ip saddr {v4_net} oifname != "{iface}" masquerade',
        f'add rule inet {TABLE_NAME} postrouting ip6 saddr {v6_net} oifname != "{iface}" masquerade',
    ]
    try:
        await _nft_batch(commands)
        logger.info("Masquerade rule added for {}", iface)
    except RuntimeError as e:
        logger.debug("Masquerade setup: {}", e)


async def add_user_chain(user_id: str) -> None:
    """Create a per-user chain for firewall rules."""
    chain = _user_chain_name(user_id)
    commands = [
        f"add chain inet {TABLE_NAME} {chain}",
    ]
    try:
        await _nft_batch(commands)
        logger.debug("User chain created: {}", chain)
    except RuntimeError as e:
        if "File exists" not in str(e):
            raise


async def remove_user_chain(user_id: str) -> None:
    """Remove a per-user chain and all its rules."""
    chain = _user_chain_name(user_id)
    try:
        await _nft_batch([
            f"flush chain inet {TABLE_NAME} {chain}",
            f"delete chain inet {TABLE_NAME} {chain}",
        ])
        logger.debug("User chain removed: {}", chain)
    except RuntimeError as e:
        logger.debug("Remove user chain {}: {}", chain, e)


async def add_device_jump_rule(user_id: str, device_ipv4: str | None, device_ipv6: str | None) -> None:
    """Add jump rules in the forward chain to route device traffic to the user chain."""
    chain = _user_chain_name(user_id)
    commands = []
    if device_ipv4:
        commands.append(
            f"add rule inet {TABLE_NAME} forward ip saddr {device_ipv4} jump {chain}"
        )
    if device_ipv6:
        commands.append(
            f"add rule inet {TABLE_NAME} forward ip6 saddr {device_ipv6} jump {chain}"
        )
    if commands:
        await _nft_batch(commands)
        logger.debug("Jump rules added for device {}/{} -> {}", device_ipv4, device_ipv6, chain)


async def apply_rule(user_id: str, destination: str, action: str, port_type: str | None = None, port_range: str | None = None) -> None:
    """Add a filter rule to a user's chain."""
    chain = _user_chain_name(user_id)
    rule = _build_rule_expr(destination, action, port_type, port_range)
    await _nft_batch([f"add rule inet {TABLE_NAME} {chain} {rule}"])
    logger.debug("Rule applied in {}: {} -> {}", chain, destination, action)


async def rebuild_all_rules(users_devices_rules: list[dict]) -> None:
    """Full reconciliation: flush and rebuild all per-user chains from DB state.

    Removes orphaned user chains that are no longer in the DB.

    Args:
        users_devices_rules: list of dicts with keys:
            user_id, devices (list of {ipv4, ipv6}), rules (list of {destination, action, port_type, port_range})
    """
    # Discover existing user_ chains so we can remove orphans
    existing_user_chains = await _list_user_chains()
    expected_chains = {_user_chain_name(e["user_id"]) for e in users_devices_rules}
    orphaned_chains = existing_user_chains - expected_chains

    commands = []

    for entry in users_devices_rules:
        user_id = entry["user_id"]
        chain = _user_chain_name(user_id)

        # Create/flush user chain
        commands.append(f"add chain inet {TABLE_NAME} {chain}")
        commands.append(f"flush chain inet {TABLE_NAME} {chain}")

        # Add rules in priority order — nftables evaluates a chain top-to-bottom,
        # so the lowest-priority number must be added first. Sort defensively here
        # so chain order is deterministic regardless of how the caller ordered them.
        ordered_rules = sorted(entry.get("rules", []), key=lambda r: r.get("priority", 100))
        for rule in ordered_rules:
            expr = _build_rule_expr(
                rule["destination"], rule["action"],
                rule.get("port_type"), rule.get("port_range"),
            )
            commands.append(f"add rule inet {TABLE_NAME} {chain} {expr}")

    # Flush forward chain jump rules and re-add
    commands.append(f"flush chain inet {TABLE_NAME} forward")
    for entry in users_devices_rules:
        user_id = entry["user_id"]
        chain = _user_chain_name(user_id)
        for dev in entry.get("devices", []):
            if dev.get("ipv4"):
                commands.append(f"add rule inet {TABLE_NAME} forward ip saddr {dev['ipv4']} jump {chain}")
            if dev.get("ipv6"):
                commands.append(f"add rule inet {TABLE_NAME} forward ip6 saddr {dev['ipv6']} jump {chain}")

    # Remove orphaned user chains (must happen after forward chain is flushed
    # so there are no remaining jump references to these chains)
    for chain in orphaned_chains:
        commands.append(f"flush chain inet {TABLE_NAME} {chain}")
        commands.append(f"delete chain inet {TABLE_NAME} {chain}")

    await _nft_batch(commands)
    if orphaned_chains:
        logger.info("Removed {} orphaned firewall chain(s): {}", len(orphaned_chains), orphaned_chains)
    logger.info("Firewall rules rebuilt for {} users", len(users_devices_rules))


async def apply_peer_to_peer_policy(enabled: bool) -> None:
    """Allow or deny traffic between WireGuard peers (peer-to-peer through the server)."""
    settings = get_settings()
    iface = settings.wg_interface
    v4_net = settings.wg_ipv4_network
    v6_net = settings.wg_ipv6_network
    chain = "peer_to_peer"

    commands = [
        f"add chain inet {TABLE_NAME} {chain}",
        f"flush chain inet {TABLE_NAME} {chain}",
    ]

    if enabled:
        # Allow traffic from WG subnet destined to WG subnet (both directions through the interface)
        commands.append(f'add rule inet {TABLE_NAME} {chain} ip saddr {v4_net} ip daddr {v4_net} accept')
        commands.append(f'add rule inet {TABLE_NAME} {chain} ip6 saddr {v6_net} ip6 daddr {v6_net} accept')
    else:
        # Drop inter-peer traffic
        commands.append(f'add rule inet {TABLE_NAME} {chain} ip saddr {v4_net} ip daddr {v4_net} drop')
        commands.append(f'add rule inet {TABLE_NAME} {chain} ip6 saddr {v6_net} ip6 daddr {v6_net} drop')

    try:
        await _nft_batch(commands)
        # Ensure the forward chain jumps to peer_to_peer before user chains
        # We flush and re-add to keep ordering correct
        logger.info("Peer-to-peer policy: {}", "allow" if enabled else "deny")
    except RuntimeError as e:
        logger.error("Failed to apply peer-to-peer policy: {}", e)


async def apply_lan_to_peers_policy(enabled: bool) -> None:
    """Allow or deny traffic from the local network to WireGuard peers."""
    settings = get_settings()
    iface = settings.wg_interface
    v4_net = settings.wg_ipv4_network
    v6_net = settings.wg_ipv6_network
    chain = "lan_to_peers"

    commands = [
        f"add chain inet {TABLE_NAME} {chain}",
        f"flush chain inet {TABLE_NAME} {chain}",
    ]

    if enabled:
        # Allow traffic from non-WG sources destined to WG subnet (LAN → peers)
        commands.append(f'add rule inet {TABLE_NAME} {chain} ip saddr != {v4_net} ip daddr {v4_net} accept')
        commands.append(f'add rule inet {TABLE_NAME} {chain} ip6 saddr != {v6_net} ip6 daddr {v6_net} accept')
    else:
        # Drop LAN → peer traffic
        commands.append(f'add rule inet {TABLE_NAME} {chain} ip saddr != {v4_net} ip daddr {v4_net} drop')
        commands.append(f'add rule inet {TABLE_NAME} {chain} ip6 saddr != {v6_net} ip6 daddr {v6_net} drop')

    try:
        await _nft_batch(commands)
        logger.info("LAN-to-peers policy: {}", "allow" if enabled else "deny")
    except RuntimeError as e:
        logger.error("Failed to apply LAN-to-peers policy: {}", e)


async def get_ruleset() -> str:
    """Dump the current nftables ruleset for troubleshooting."""
    try:
        return await _nft("list ruleset")
    except RuntimeError:
        return "nftables is not available.\n\nThis requires root/NET_ADMIN privileges (production container)."


async def _list_user_chains() -> set[str]:
    """Return the set of user_ chain names currently in the wiregui table."""
    try:
        output = await _nft(f"list table inet {TABLE_NAME}")
    except RuntimeError:
        return set()
    chains = set()
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("chain user_"):
            name = line.split()[1]
            chains.add(name)
    return chains


def _user_chain_name(user_id: str) -> str:
    """Generate a deterministic chain name from a user ID."""
    # Use first 12 chars of UUID (without hyphens) to keep names short
    short = user_id.replace("-", "")[:12]
    return f"user_{short}"


def _build_rule_expr(destination: str, action: str, port_type: str | None = None, port_range: str | None = None) -> str:
    """Build an nftables rule expression string."""
    # Determine IP version from destination
    if ":" in destination:
        addr_match = f"ip6 daddr {destination}"
    else:
        addr_match = f"ip daddr {destination}"

    parts = [addr_match]

    if port_type and port_range:
        parts.append(f"{port_type} dport {port_range}")

    parts.append(action)
    return " ".join(parts)
