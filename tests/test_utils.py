"""Tests for utility modules."""

import subprocess

import pytest
from sqlmodel import select

from wiregui.models.device import Device
from wiregui.models.rule import Rule
from wiregui.models.user import User
from wiregui.utils.network import allocate_ipv4, allocate_ipv6, parse_subnet_list
from wiregui.utils.ordering import assign_priorities
from wiregui.utils.wg_conf import build_client_config


# --- Relay subnet parsing/validation ---


def test_parse_subnet_list_valid_v4_and_v6():
    assert parse_subnet_list("192.168.1.0/24, 10.20.0.0/16, fd00:1::/64") == [
        "192.168.1.0/24", "10.20.0.0/16", "fd00:1::/64",
    ]


def test_parse_subnet_list_empty_and_whitespace():
    assert parse_subnet_list("") == []
    assert parse_subnet_list("  ,  ,") == []


def test_parse_subnet_list_normalizes_host_bits():
    # Host bits are masked off so the value is a clean network.
    assert parse_subnet_list("192.168.1.5/24") == ["192.168.1.0/24"]


def test_parse_subnet_list_bare_ip_becomes_host_route():
    assert parse_subnet_list("10.0.0.1") == ["10.0.0.1/32"]


def test_parse_subnet_list_rejects_invalid_cidr():
    with pytest.raises(ValueError):
        parse_subnet_list("not-a-subnet")


def test_parse_subnet_list_rejects_injection_attempt():
    # A value crafted to inject an extra nft command must be rejected, not passed through.
    with pytest.raises(ValueError):
        parse_subnet_list("10.0.0.0/24 jump evil")


# --- Rule priority ordering ---


def test_assign_priorities_spaces_in_order():
    result = assign_priorities(["a", "b", "c"])
    assert result == {"a": 10, "b": 20, "c": 30}


def test_assign_priorities_empty():
    assert assign_priorities([]) == {}


def test_assign_priorities_preserves_given_order():
    # Order of the input sequence is what determines priority, not the id values.
    result = assign_priorities(["z", "a", "m"])
    assert result["z"] < result["a"] < result["m"]


async def test_rule_priority_defaults_to_100(session):
    user = User(email="rule-default@example.com")
    session.add(user)
    await session.flush()

    rule = Rule(action="drop", destination="0.0.0.0/0", user_id=user.id)
    session.add(rule)
    await session.flush()
    await session.refresh(rule)

    assert rule.priority == 100


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
    """Test keypair generation (pure Python, no wg CLI needed)."""
    from wiregui.utils.crypto import generate_keypair, generate_preshared_key

    priv, pub = generate_keypair()
    assert len(priv) == 44  # base64-encoded 32 bytes
    assert len(pub) == 44

    psk = generate_preshared_key()
    assert len(psk) == 44

    psk = generate_preshared_key()
    assert len(psk) == 44
