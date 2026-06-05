"""Startup reconciliation — ensure WireGuard and firewall state matches the database."""

from loguru import logger
from sqlmodel import select

from wiregui.db import async_session
from wiregui.models.device import Device
from wiregui.models.rule import Rule
from wiregui.services import firewall, wireguard


async def reconcile() -> None:
    """Diff DB devices against WireGuard peers and apply corrections.
    Also rebuild all firewall chains from DB state."""

    # Get current WG peers
    current_peers = await wireguard.get_peers()
    current_keys = {p.public_key for p in current_peers}

    # Get all devices and rules from DB
    async with async_session() as session:
        devices = (await session.execute(select(Device))).scalars().all()
        rules = (await session.execute(select(Rule))).scalars().all()

    expected_keys = {d.public_key for d in devices}
    device_map = {d.public_key: d for d in devices}

    # Add missing peers (in DB but not in WG)
    to_add = expected_keys - current_keys
    for key in to_add:
        device = device_map[key]
        ips = []
        if device.ipv4:
            ips.append(f"{device.ipv4}/32")
        if device.ipv6:
            ips.append(f"{device.ipv6}/128")
        if device.allowed_subnets:
            ips.extend(device.allowed_subnets)
        try:
            await wireguard.add_peer(
                public_key=device.public_key,
                allowed_ips=ips,
                preshared_key=device.preshared_key,
            )
        except Exception as e:
            logger.error("Reconcile: failed to add peer {}: {}", key[:20], e)

    # Remove orphaned peers (in WG but not in DB)
    to_remove = current_keys - expected_keys
    for key in to_remove:
        try:
            await wireguard.remove_peer(public_key=key)
        except Exception as e:
            logger.error("Reconcile: failed to remove peer {}: {}", key[:20], e)

    if to_add or to_remove:
        logger.info("Reconciliation: added {} peers, removed {} orphans", len(to_add), len(to_remove))
    else:
        logger.info("Reconciliation: WireGuard state matches database")

    # Rebuild all firewall rules from DB
    await _reconcile_firewall(devices, rules)


async def _reconcile_firewall(devices: list[Device], rules: list[Rule]) -> None:
    """Rebuild all firewall chains and jump rules from current DB state."""
    # Group devices and rules by user_id
    user_ids = {str(d.user_id) for d in devices}
    for r in rules:
        if r.user_id:
            user_ids.add(str(r.user_id))

    entries = []
    for uid in user_ids:
        user_devices = [d for d in devices if str(d.user_id) == uid]
        user_rules = [r for r in rules if r.user_id and str(r.user_id) == uid]

        entries.append({
            "user_id": uid,
            "devices": [
                {"ipv4": d.ipv4, "ipv6": d.ipv6, "allowed_subnets": d.allowed_subnets}
                for d in user_devices
            ],
            "rules": [
                {"destination": r.destination, "action": r.action,
                 "port_type": r.port_type, "port_range": r.port_range}
                for r in user_rules
            ],
        })

    try:
        await firewall.rebuild_all_rules(entries)
    except Exception as e:
        logger.error("Reconcile: firewall rebuild failed: {}", e)
