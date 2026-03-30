"""Tests for SQLModel table definitions."""

import pytest  # noqa: F401 — needed for pytest.raises
from sqlmodel import select

from wiregui.models.api_token import ApiToken
from wiregui.models.configuration import Configuration
from wiregui.models.connectivity_check import ConnectivityCheck
from wiregui.models.device import Device
from wiregui.models.mfa_method import MFAMethod
from wiregui.models.oidc_connection import OIDCConnection
from wiregui.models.rule import Rule
from wiregui.models.user import User


async def test_create_user(session):
    user = User(email="alice@example.com", role="admin")
    session.add(user)
    await session.flush()

    result = await session.execute(select(User).where(User.email == "alice@example.com"))
    fetched = result.scalar_one()
    assert fetched.id == user.id
    assert fetched.role == "admin"
    assert fetched.disabled_at is None


async def test_create_device_with_user(session):
    user = User(email="bob@example.com")
    session.add(user)
    await session.flush()

    device = Device(
        name="laptop",
        public_key="pk-test-device-001",
        user_id=user.id,
    )
    session.add(device)
    await session.flush()

    result = await session.execute(select(Device).where(Device.public_key == "pk-test-device-001"))
    fetched = result.scalar_one()
    assert fetched.name == "laptop"
    assert fetched.user_id == user.id
    assert fetched.use_default_dns is True
    assert fetched.use_default_allowed_ips is True
    assert fetched.rx_bytes is None


async def test_device_unique_public_key(session):
    user = User(email="carol@example.com")
    session.add(user)
    await session.flush()

    d1 = Device(name="d1", public_key="duplicate-key", user_id=user.id)
    session.add(d1)
    await session.flush()

    d2 = Device(name="d2", public_key="duplicate-key", user_id=user.id)
    session.add(d2)
    with pytest.raises(Exception):  # IntegrityError
        await session.flush()


async def test_create_rule(session):
    user = User(email="dave@example.com")
    session.add(user)
    await session.flush()

    rule = Rule(action="accept", destination="10.0.0.0/8", user_id=user.id)
    session.add(rule)
    await session.flush()

    result = await session.execute(select(Rule).where(Rule.user_id == user.id))
    fetched = result.scalar_one()
    assert fetched.action == "accept"
    assert fetched.destination == "10.0.0.0/8"
    assert fetched.port_type is None
    assert fetched.port_range is None


async def test_create_rule_with_port(session):
    rule = Rule(
        action="drop",
        destination="192.168.0.0/16",
        port_type="tcp",
        port_range="80-443",
    )
    session.add(rule)
    await session.flush()

    fetched = (await session.execute(select(Rule).where(Rule.id == rule.id))).scalar_one()
    assert fetched.port_type == "tcp"
    assert fetched.port_range == "80-443"
    assert fetched.user_id is None  # global rule


async def test_create_mfa_method(session):
    user = User(email="eve@example.com")
    session.add(user)
    await session.flush()

    mfa = MFAMethod(
        name="My Authenticator",
        type="totp",
        payload={"secret": "JBSWY3DPEHPK3PXP"},
        user_id=user.id,
    )
    session.add(mfa)
    await session.flush()

    fetched = (await session.execute(select(MFAMethod).where(MFAMethod.user_id == user.id))).scalar_one()
    assert fetched.type == "totp"
    assert fetched.payload["secret"] == "JBSWY3DPEHPK3PXP"


async def test_create_oidc_connection(session):
    user = User(email="frank@example.com")
    session.add(user)
    await session.flush()

    conn = OIDCConnection(provider="google", refresh_token="tok_abc", user_id=user.id)
    session.add(conn)
    await session.flush()

    fetched = (await session.execute(select(OIDCConnection).where(OIDCConnection.user_id == user.id))).scalar_one()
    assert fetched.provider == "google"
    assert fetched.refresh_token == "tok_abc"


async def test_create_api_token(session):
    user = User(email="grace@example.com")
    session.add(user)
    await session.flush()

    token = ApiToken(token_hash="sha256_fake_hash", user_id=user.id)
    session.add(token)
    await session.flush()

    fetched = (await session.execute(select(ApiToken).where(ApiToken.user_id == user.id))).scalar_one()
    assert fetched.token_hash == "sha256_fake_hash"
    assert fetched.expires_at is None


async def test_create_connectivity_check(session):
    check = ConnectivityCheck(url="https://example.com", response_code=200)
    session.add(check)
    await session.flush()

    fetched = (await session.execute(select(ConnectivityCheck).where(ConnectivityCheck.id == check.id))).scalar_one()
    assert fetched.response_code == 200


async def test_configuration_defaults(session):
    config = Configuration()
    session.add(config)
    await session.flush()

    fetched = (await session.execute(select(Configuration).where(Configuration.id == config.id))).scalar_one()
    assert fetched.allow_unprivileged_device_management is True
    assert fetched.local_auth_enabled is True
    assert fetched.default_client_mtu == 1280
    assert fetched.default_client_persistent_keepalive == 25
    assert fetched.default_client_dns == ["1.1.1.1", "1.0.0.1"]
    assert fetched.default_client_allowed_ips == ["0.0.0.0/0", "::/0"]
    assert fetched.vpn_session_duration == 0
    assert fetched.openid_connect_providers == []
    assert fetched.saml_identity_providers == []
