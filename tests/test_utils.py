"""Tests for utility modules."""

import subprocess

import pytest
from sqlmodel import select

from wiregui.models.device import Device
from wiregui.models.user import User
from wiregui.utils.network import allocate_ipv4, allocate_ipv6
from wiregui.utils.wg_conf import build_client_config


# --- IP allocation ---


async def test_allocate_ipv4_first_device(session):
    user = User(email="net-test@example.com")
    session.add(user)
    await session.flush()

    ip = await allocate_ipv4(session, "10.3.2.0/24")
    assert ip.startswith("10.3.2.")
    # Should not be the network (.0) or gateway (.1)
    last_octet = int(ip.split(".")[-1])
    assert last_octet >= 2


async def test_allocate_ipv4_skips_used(session):
    user = User(email="net-skip@example.com")
    session.add(user)
    await session.flush()

    # Exhaust a tiny /30 network (4 addresses: .0 network, .1 gateway, .2 usable, .3 broadcast)
    d1 = Device(name="d1", public_key="pk-net-1", ipv4="10.99.0.2", user_id=user.id)
    session.add(d1)
    await session.flush()

    # Only .2 was usable in a /30 — allocation should fail
    with pytest.raises(ValueError, match="No available"):
        await allocate_ipv4(session, "10.99.0.0/30")


async def test_allocate_ipv6(session):
    user = User(email="net6-test@example.com")
    session.add(user)
    await session.flush()

    ip = await allocate_ipv6(session, "fd00::3:2:0/120")
    assert ip.startswith("fd00::3:2:")


# --- WireGuard config builder ---


def test_build_client_config():
    device = Device(
        name="test-device",
        public_key="device-pub-key",
        preshared_key="device-psk",
        ipv4="10.3.2.5",
        ipv6="fd00::3:2:5",
        use_default_allowed_ips=True,
        use_default_dns=True,
        use_default_endpoint=True,
        use_default_mtu=True,
        use_default_persistent_keepalive=True,
        user_id="00000000-0000-0000-0000-000000000000",
    )

    config = build_client_config(device, "PRIVATE_KEY_HERE", "SERVER_PUB_KEY")

    assert "[Interface]" in config
    assert "PrivateKey = PRIVATE_KEY_HERE" in config
    assert "10.3.2.5/32" in config
    assert "fd00::3:2:5/128" in config
    assert "[Peer]" in config
    assert "PublicKey = SERVER_PUB_KEY" in config
    assert "PresharedKey = device-psk" in config
    assert "Endpoint = " in config


def test_build_client_config_no_psk():
    device = Device(
        name="no-psk",
        public_key="pub",
        preshared_key=None,
        ipv4="10.3.2.6",
        ipv6=None,
        use_default_allowed_ips=True,
        use_default_dns=True,
        use_default_endpoint=True,
        use_default_mtu=True,
        use_default_persistent_keepalive=True,
        user_id="00000000-0000-0000-0000-000000000000",
    )

    config = build_client_config(device, "PRIV", "SERVPUB")
    assert "PresharedKey" not in config
    assert "fd00::" not in config  # no ipv6


# --- Crypto (only if wg is installed) ---


def test_generate_keypair():
    """Test keypair generation — requires `wg` CLI to be installed."""
    try:
        subprocess.run(["wg", "--version"], capture_output=True, check=True)
    except FileNotFoundError:
        pytest.skip("wg CLI not installed")

    from wiregui.utils.crypto import generate_keypair, generate_preshared_key

    priv, pub = generate_keypair()
    assert len(priv) == 44  # base64-encoded 32 bytes
    assert len(pub) == 44

    psk = generate_preshared_key()
    assert len(psk) == 44
