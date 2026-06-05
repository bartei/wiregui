"""Event bridge — propagates database changes to WireGuard and firewall."""

from uuid import UUID

from loguru import logger

from wiregui.config import get_settings
from wiregui.db import async_session
from wiregui.models.device import Device
from wiregui.models.rule import Rule
from wiregui.services import firewall, wireguard


def _device_allowed_ips(device: Device) -> list[str]:
    """Build the allowed-ips list for a device peer (its tunnel addresses + relay subnets)."""
    ips = []
    if device.ipv4:
        ips.append(f"{device.ipv4}/32")
    if device.ipv6:
        ips.append(f"{device.ipv6}/128")
    if device.allowed_subnets:
        ips.extend(device.allowed_subnets)
    return ips


# --- Device events ---


async def on_device_created(device: Device) -> None:
    """Configure WireGuard peer, routes, and firewall after a new device is created."""
    settings = get_settings()
    if not settings.wg_enabled:
        return
    try:
        await wireguard.add_peer(
            public_key=device.public_key,
            allowed_ips=_device_allowed_ips(device),
            preshared_key=device.preshared_key,
        )
    except Exception as e:
        logger.error("Failed to add WG peer for device {}: {}", device.name, e)
    
    # Add routes for relay subnets
    if device.allowed_subnets:
        try:
            await wireguard.add_routes(device.allowed_subnets)
        except Exception as e:
            logger.error("Failed to add routes for device {}: {}", device.name, e)

    try:
        # Ensure user chain exists before adding jump rules
        await firewall.add_user_chain(str(device.user_id))
        await firewall.add_device_jump_rule(
            str(device.user_id),
            device.ipv4,
            device.ipv6,
            device.allowed_subnets,
        )
    except Exception as e:
        logger.error("Failed to add firewall jump rule for device {}: {}", device.name, e)


async def on_device_deleted(device: Device) -> None:
    """Remove WireGuard peer and routes after a device is deleted."""
    if not get_settings().wg_enabled:
        return
    try:
        await wireguard.remove_peer(public_key=device.public_key)
    except Exception as e:
        logger.error("Failed to remove WG peer for device {}: {}", device.name, e)
    
    # Remove routes for relay subnets
    if device.allowed_subnets:
        try:
            await wireguard.remove_routes(device.allowed_subnets)
        except Exception as e:
            logger.error("Failed to remove routes for device {}: {}", device.name, e)
    # Firewall jump rules are cleaned up on next rebuild


async def on_device_updated(device: Device) -> None:
    """Update WireGuard peer, routes, and firewall after a device is modified."""
    if not get_settings().wg_enabled:
        return
    try:
        await wireguard.add_peer(
            public_key=device.public_key,
            allowed_ips=_device_allowed_ips(device),
            preshared_key=device.preshared_key,
        )
    except Exception as e:
        logger.error("Failed to update WG peer for device {}: {}", device.name, e)
    
    # Note: We can't easily diff old vs new allowed_subnets here without fetching old state.
    # The reconcile task will clean up orphaned routes periodically.
    # For now, just ensure current routes exist.
    if device.allowed_subnets:
        try:
            await wireguard.add_routes(device.allowed_subnets)
        except Exception as e:
            logger.error("Failed to add routes for device {}: {}", device.name, e)
    
    # Rebuild firewall rules for this user to update allowed_subnets
    try:
        await _rebuild_user_chain(str(device.user_id))
    except Exception as e:
        logger.error("Failed to rebuild firewall rules for device {}: {}", device.name, e)


# --- Rule events ---


async def on_rule_created(rule: Rule) -> None:
    """Apply a new firewall rule."""
    if not get_settings().wg_enabled:
        return
    if rule.user_id is None:
        return  # global rules handled via rebuild
    try:
        await firewall.apply_rule(
            str(rule.user_id), rule.destination, rule.action,
            rule.port_type, rule.port_range,
        )
    except Exception as e:
        logger.error("Failed to apply firewall rule {}: {}", rule.id, e)


async def on_rule_updated(rule: Rule) -> None:
    """Firewall rule updated — rebuild the user's chain."""
    if not get_settings().wg_enabled:
        return
    if rule.user_id is None:
        return
    await _rebuild_user_chain(str(rule.user_id))


async def on_rule_deleted(rule: Rule) -> None:
    """Firewall rule removed — rebuild the user's chain."""
    if not get_settings().wg_enabled:
        return
    if rule.user_id is None:
        return
    await _rebuild_user_chain(str(rule.user_id))


async def _rebuild_user_chain(user_id: str) -> None:
    """Flush and rebuild a single user's firewall chain from current DB rules."""
    try:
        from sqlmodel import select as sel

        async with async_session() as session:
            rules = (await session.execute(
                sel(Rule).where(Rule.user_id == UUID(user_id))
            )).scalars().all()

            devices = (await session.execute(
                sel(Device).where(Device.user_id == UUID(user_id))
            )).scalars().all()

        await firewall.rebuild_all_rules([{
            "user_id": user_id,
            "devices": [
                {"ipv4": d.ipv4, "ipv6": d.ipv6, "allowed_subnets": d.allowed_subnets}
                for d in devices
            ],
            "rules": [
                {"destination": r.destination, "action": r.action,
                 "port_type": r.port_type, "port_range": r.port_range}
                for r in rules
            ],
        }])
    except Exception as e:
        logger.error("Failed to rebuild firewall chain for user {}: {}", user_id, e)
