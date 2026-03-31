"""Build WireGuard client configuration files."""

from wiregui.config import get_settings
from wiregui.models.configuration import Configuration
from wiregui.models.device import Device


def build_client_config(
    device: Device,
    private_key: str,
    server_public_key: str,
    db_config: Configuration | None = None,
) -> str:
    """Build a WireGuard [Interface]+[Peer] config string for a device.

    Uses DB Configuration for client defaults when available,
    falls back to env-based Settings.
    """
    settings = get_settings()

    # Resolve per-device overrides → DB config defaults → env var defaults
    if device.use_default_dns:
        dns = db_config.default_client_dns if db_config and db_config.default_client_dns else settings.wg_dns
    else:
        dns = device.dns

    if device.use_default_endpoint:
        endpoint_host = db_config.default_client_endpoint if db_config and db_config.default_client_endpoint else settings.wg_endpoint_host
    else:
        endpoint_host = device.endpoint

    if device.use_default_mtu:
        mtu = db_config.default_client_mtu if db_config else settings.wg_mtu
    else:
        mtu = device.mtu

    if device.use_default_persistent_keepalive:
        keepalive = db_config.default_client_persistent_keepalive if db_config else settings.wg_persistent_keepalive
    else:
        keepalive = device.persistent_keepalive

    if device.use_default_allowed_ips:
        allowed_ips = db_config.default_client_allowed_ips if db_config and db_config.default_client_allowed_ips else settings.wg_allowed_ips
    else:
        allowed_ips = device.allowed_ips

    # Build address list
    addresses = []
    if device.ipv4:
        addresses.append(f"{device.ipv4}/32")
    if device.ipv6:
        addresses.append(f"{device.ipv6}/128")

    # Build endpoint
    endpoint_port = settings.wg_endpoint_port
    endpoint = f"{endpoint_host}:{endpoint_port}"

    lines = ["[Interface]", f"PrivateKey = {private_key}"]
    if addresses:
        lines.append(f"Address = {', '.join(addresses)}")
    if dns:
        dns_str = dns if isinstance(dns, str) else ", ".join(dns)
        lines.append(f"DNS = {dns_str}")
    if mtu:
        lines.append(f"MTU = {mtu}")

    lines.append("")
    lines.append("[Peer]")
    lines.append(f"PublicKey = {server_public_key}")
    if device.preshared_key:
        lines.append(f"PresharedKey = {device.preshared_key}")
    if allowed_ips:
        ips_str = allowed_ips if isinstance(allowed_ips, str) else ", ".join(allowed_ips)
        lines.append(f"AllowedIPs = {ips_str}")
    lines.append(f"Endpoint = {endpoint}")
    if keepalive:
        lines.append(f"PersistentKeepalive = {keepalive}")

    return "\n".join(lines) + "\n"
