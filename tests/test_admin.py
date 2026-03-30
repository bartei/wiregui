"""Tests for admin functionality — user management, configuration, cascading deletes."""

import pytest
from sqlmodel import func, select

from wiregui.auth.passwords import hash_password, verify_password
from wiregui.models.api_token import ApiToken
from wiregui.models.configuration import Configuration
from wiregui.models.device import Device
from wiregui.models.mfa_method import MFAMethod
from wiregui.models.rule import Rule
from wiregui.models.user import User
from wiregui.utils.time import utcnow


# --- User CRUD ---


async def test_create_user_with_role(session):
    user = User(email="new-admin@test.com", password_hash=hash_password("secret"), role="admin")
    session.add(user)
    await session.flush()

    fetched = await session.get(User, user.id)
    assert fetched.role == "admin"
    assert verify_password("secret", fetched.password_hash)


async def test_update_user_email(session):
    user = User(email="old@test.com", password_hash=hash_password("pw"))
    session.add(user)
    await session.flush()

    user.email = "new@test.com"
    session.add(user)
    await session.flush()

    fetched = await session.get(User, user.id)
    assert fetched.email == "new@test.com"


async def test_disable_user(session):
    user = User(email="active@test.com", password_hash=hash_password("pw"))
    session.add(user)
    await session.flush()
    assert user.disabled_at is None

    user.disabled_at = utcnow()
    session.add(user)
    await session.flush()

    fetched = await session.get(User, user.id)
    assert fetched.disabled_at is not None


async def test_promote_demote_user(session):
    user = User(email="user@test.com", role="unprivileged")
    session.add(user)
    await session.flush()
    assert user.role == "unprivileged"

    user.role = "admin"
    session.add(user)
    await session.flush()

    fetched = await session.get(User, user.id)
    assert fetched.role == "admin"

    user.role = "unprivileged"
    session.add(user)
    await session.flush()
    assert (await session.get(User, user.id)).role == "unprivileged"


# --- Cascading delete (manual, as we do it in the admin page) ---


async def test_delete_user_cascades_devices(session):
    user = User(email="cascade@test.com")
    session.add(user)
    await session.flush()

    d1 = Device(name="d1", public_key="pk-cascade-1", ipv4="10.0.0.1", user_id=user.id)
    d2 = Device(name="d2", public_key="pk-cascade-2", ipv4="10.0.0.2", user_id=user.id)
    session.add_all([d1, d2])
    await session.flush()

    # Manually delete devices then user (matching admin page behavior)
    devices = (await session.execute(select(Device).where(Device.user_id == user.id))).scalars().all()
    for d in devices:
        await session.delete(d)
    await session.delete(user)
    await session.flush()

    assert (await session.execute(select(func.count()).select_from(Device).where(Device.user_id == user.id))).scalar() == 0
    assert await session.get(User, user.id) is None


async def test_delete_user_cascades_rules(session):
    user = User(email="rule-cascade@test.com")
    session.add(user)
    await session.flush()

    rule = Rule(action="accept", destination="10.0.0.0/8", user_id=user.id)
    session.add(rule)
    await session.flush()

    # Delete rules then user
    rules = (await session.execute(select(Rule).where(Rule.user_id == user.id))).scalars().all()
    for r in rules:
        await session.delete(r)
    await session.delete(user)
    await session.flush()

    assert (await session.execute(select(func.count()).select_from(Rule).where(Rule.user_id == user.id))).scalar() == 0


# --- Configuration singleton ---


async def test_configuration_create_and_update(session):
    config = Configuration()
    session.add(config)
    await session.flush()

    assert config.default_client_mtu == 1280
    assert config.local_auth_enabled is True

    config.default_client_mtu = 1400
    config.local_auth_enabled = False
    config.vpn_session_duration = 3600
    session.add(config)
    await session.flush()

    fetched = await session.get(Configuration, config.id)
    assert fetched.default_client_mtu == 1400
    assert fetched.local_auth_enabled is False
    assert fetched.vpn_session_duration == 3600


async def test_configuration_oidc_providers(session):
    config = Configuration()
    session.add(config)
    await session.flush()

    assert config.openid_connect_providers == []

    providers = [
        {
            "id": "google",
            "label": "Sign in with Google",
            "scope": "openid email profile",
            "response_type": "code",
            "client_id": "google-client-id",
            "client_secret": "google-secret",
            "discovery_document_uri": "https://accounts.google.com/.well-known/openid-configuration",
            "auto_create_users": True,
        },
        {
            "id": "okta",
            "label": "Okta SSO",
            "scope": "openid email profile",
            "response_type": "code",
            "client_id": "okta-client-id",
            "client_secret": "okta-secret",
            "discovery_document_uri": "https://dev-123.okta.com/.well-known/openid-configuration",
            "auto_create_users": False,
        },
    ]
    config.openid_connect_providers = providers
    session.add(config)
    await session.flush()

    fetched = await session.get(Configuration, config.id)
    assert len(fetched.openid_connect_providers) == 2
    assert fetched.openid_connect_providers[0]["id"] == "google"
    assert fetched.openid_connect_providers[1]["auto_create_users"] is False


async def test_configuration_update_client_defaults(session):
    config = Configuration()
    session.add(config)
    await session.flush()

    config.default_client_endpoint = "vpn.example.com"
    config.default_client_dns = ["8.8.8.8", "8.8.4.4"]
    config.default_client_allowed_ips = ["10.0.0.0/8"]
    config.default_client_persistent_keepalive = 30
    session.add(config)
    await session.flush()

    fetched = await session.get(Configuration, config.id)
    assert fetched.default_client_endpoint == "vpn.example.com"
    assert fetched.default_client_dns == ["8.8.8.8", "8.8.4.4"]
    assert fetched.default_client_allowed_ips == ["10.0.0.0/8"]
    assert fetched.default_client_persistent_keepalive == 30


async def test_configuration_security_toggles(session):
    config = Configuration()
    session.add(config)
    await session.flush()

    config.allow_unprivileged_device_management = False
    config.allow_unprivileged_device_configuration = False
    config.disable_vpn_on_oidc_error = True
    session.add(config)
    await session.flush()

    fetched = await session.get(Configuration, config.id)
    assert fetched.allow_unprivileged_device_management is False
    assert fetched.allow_unprivileged_device_configuration is False
    assert fetched.disable_vpn_on_oidc_error is True


# --- Device config overrides ---


async def test_device_with_custom_config(session):
    user = User(email="config-user@test.com")
    session.add(user)
    await session.flush()

    device = Device(
        name="custom-config",
        public_key="pk-custom-config",
        user_id=user.id,
        use_default_dns=False,
        use_default_endpoint=False,
        use_default_mtu=False,
        use_default_persistent_keepalive=False,
        use_default_allowed_ips=False,
        dns=["8.8.8.8"],
        endpoint="custom-vpn.example.com",
        mtu=1400,
        persistent_keepalive=15,
        allowed_ips=["10.0.0.0/8", "172.16.0.0/12"],
    )
    session.add(device)
    await session.flush()

    fetched = await session.get(Device, device.id)
    assert fetched.use_default_dns is False
    assert fetched.dns == ["8.8.8.8"]
    assert fetched.endpoint == "custom-vpn.example.com"
    assert fetched.mtu == 1400
    assert fetched.persistent_keepalive == 15
    assert fetched.allowed_ips == ["10.0.0.0/8", "172.16.0.0/12"]


async def test_device_default_flags_are_true(session):
    user = User(email="defaults@test.com")
    session.add(user)
    await session.flush()

    device = Device(name="defaults", public_key="pk-defaults", user_id=user.id)
    session.add(device)
    await session.flush()

    fetched = await session.get(Device, device.id)
    assert fetched.use_default_allowed_ips is True
    assert fetched.use_default_dns is True
    assert fetched.use_default_endpoint is True
    assert fetched.use_default_mtu is True
    assert fetched.use_default_persistent_keepalive is True


# --- User device count ---


async def test_user_device_count_query(session):
    user = User(email="count-user@test.com")
    session.add(user)
    await session.flush()

    for i in range(3):
        session.add(Device(name=f"d{i}", public_key=f"pk-count-{i}", user_id=user.id))
    await session.flush()

    count = (await session.execute(
        select(func.count()).select_from(Device).where(Device.user_id == user.id)
    )).scalar()
    assert count == 3
