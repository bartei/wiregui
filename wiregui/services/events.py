"""Event bridge — propagates database changes to WireGuard and firewall."""

from uuid import UUID

from loguru import logger

from wiregui.config import get_settings
from wiregui.db import async_session
from wiregui.models.device import Device
from wiregui.models.rule import Rule
from wiregui.services import firewall, wireguard


def _device_allowed_ips(device: Device) -> list[str]:
    """Build the allowed-ips list for a device peer (its tunnel addresses)."""
    ips = []
    if device.ipv4:
        ips.append(f"{device.ipv4}/32")
    if device.ipv6:
        ips.append(f"{device.ipv6}/128")
    return ips


# --- Device events ---


async def on_device_created(device: Device) -> None:
    """Configure WireGuard peer and firewall after a new device is created."""
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

    try:
        # Ensure user chain exists before adding jump rules
        await firewall.add_user_chain(str(device.user_id))
        await firewall.add_device_jump_rule(
            str(device.user_id), device.ipv4, device.ipv6,
        )
    except Exception as e:
        logger.error("Failed to add firewall jump rule for device {}: {}", device.name, e)


async def on_device_deleted(device: Device) -> None:
    """Remove WireGuard peer after a device is deleted."""
    if not get_settings().wg_enabled:
        return
    try:
        await wireguard.remove_peer(public_key=device.public_key)
    except Exception as e:
        logger.error("Failed to remove WG peer for device {}: {}", device.name, e)
    # Firewall jump rules are cleaned up on next rebuild


async def on_device_updated(device: Device) -> None:
    """Update WireGuard peer after a device is modified."""
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


# --- Rule events ---


async def on_rule_created(rule: Rule) -> None:
    """Apply a new firewall rule by rebuilding the user's chain.

    Rebuilding (rather than appending) ensures the new rule lands at its
    correct position according to its priority, not just at the end of the chain.
    """
    if not get_settings().wg_enabled:
        return
    if rule.user_id is None:
        return  # global rules handled via rebuild
    await _rebuild_user_chain(str(rule.user_id))


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


async def on_rules_reordered(user_id: str) -> None:
    """Rebuild a user's chain after their rules were reordered (priorities changed)."""
    if not get_settings().wg_enabled:
        return
    await _rebuild_user_chain(user_id)


async def _rebuild_user_chain(user_id: str) -> None:
    """Flush and rebuild a single user's firewall chain from current DB rules."""
    try:
        from sqlmodel import select as sel

        async with async_session() as session:
            rules = (await session.execute(
                sel(Rule).where(Rule.user_id == UUID(user_id))
                .order_by(Rule.priority, Rule.inserted_at)
            )).scalars().all()

            devices = (await session.execute(
                sel(Device).where(Device.user_id == UUID(user_id))
            )).scalars().all()

        await firewall.rebuild_all_rules([{
            "user_id": user_id,
            "devices": [{"ipv4": d.ipv4, "ipv6": d.ipv6} for d in devices],
            "rules": [
                {"destination": r.destination, "action": r.action,
                 "port_type": r.port_type, "port_range": r.port_range,
                 "priority": r.priority}
                for r in rules
            ],
        }])
    except Exception as e:
        logger.error("Failed to rebuild firewall chain for user {}: {}", user_id, e)
