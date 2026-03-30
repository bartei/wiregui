"""Tests for REST API routes via httpx AsyncClient against the FastAPI app."""

import hashlib
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlmodel import select

from wiregui.api.deps import get_current_api_user, get_db, require_admin
from wiregui.api.v0 import router as api_router
from wiregui.auth.api_token import generate_api_token
from wiregui.auth.passwords import hash_password
from wiregui.models.api_token import ApiToken
from wiregui.models.configuration import Configuration
from wiregui.models.device import Device
from wiregui.models.rule import Rule
from wiregui.models.user import User


def _build_app(session, admin_user=None, regular_user=None):
    """Build a test FastAPI app with overridden dependencies."""
    test_app = FastAPI()
    test_app.include_router(api_router, prefix="/api")

    async def override_get_db():
        yield session

    test_app.dependency_overrides[get_db] = override_get_db

    if admin_user:
        test_app.dependency_overrides[get_current_api_user] = lambda: admin_user
        test_app.dependency_overrides[require_admin] = lambda: admin_user

    return test_app


async def _make_admin(session) -> User:
    user = User(email="api-admin@test.com", password_hash=hash_password("pw"), role="admin")
    session.add(user)
    await session.flush()
    return user


async def _make_user(session, email="api-user@test.com") -> User:
    user = User(email=email, password_hash=hash_password("pw"), role="unprivileged")
    session.add(user)
    await session.flush()
    return user


# ========== Users API ==========


async def test_list_users(session):
    admin = await _make_admin(session)
    await _make_user(session, "user1@test.com")
    await _make_user(session, "user2@test.com")

    app = _build_app(session, admin_user=admin)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v0/users/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 3  # admin + 2 users


async def test_get_user(session):
    admin = await _make_admin(session)
    app = _build_app(session, admin_user=admin)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/api/v0/users/{admin.id}")
        assert resp.status_code == 200
        assert resp.json()["email"] == "api-admin@test.com"


async def test_get_user_not_found(session):
    admin = await _make_admin(session)
    app = _build_app(session, admin_user=admin)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/api/v0/users/{uuid4()}")
        assert resp.status_code == 404


async def test_create_user(session):
    admin = await _make_admin(session)
    app = _build_app(session, admin_user=admin)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v0/users/", json={
            "email": "new-api-user@test.com",
            "password": "secret123",
            "role": "unprivileged",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == "new-api-user@test.com"
        assert data["role"] == "unprivileged"
        assert "id" in data


async def test_update_user(session):
    admin = await _make_admin(session)
    user = await _make_user(session)
    app = _build_app(session, admin_user=admin)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.put(f"/api/v0/users/{user.id}", json={
            "role": "admin",
        })
        assert resp.status_code == 200
        assert resp.json()["role"] == "admin"


async def test_update_user_password(session):
    admin = await _make_admin(session)
    user = await _make_user(session)
    app = _build_app(session, admin_user=admin)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.put(f"/api/v0/users/{user.id}", json={
            "password": "new-password-123",
        })
        assert resp.status_code == 200

    from wiregui.auth.passwords import verify_password
    refreshed = await session.get(User, user.id)
    assert verify_password("new-password-123", refreshed.password_hash)


async def test_delete_user(session):
    admin = await _make_admin(session)
    user = await _make_user(session)
    app = _build_app(session, admin_user=admin)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.delete(f"/api/v0/users/{user.id}")
        assert resp.status_code == 204

    assert await session.get(User, user.id) is None


# ========== Devices API ==========


async def test_list_devices_admin_sees_all(session):
    admin = await _make_admin(session)
    user = await _make_user(session)
    session.add(Device(name="d1", public_key="pk-api-d1", user_id=admin.id))
    session.add(Device(name="d2", public_key="pk-api-d2", user_id=user.id))
    await session.flush()

    app = _build_app(session, admin_user=admin)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v0/devices/")
        assert resp.status_code == 200
        assert len(resp.json()) >= 2


async def test_list_devices_user_sees_own(session):
    admin = await _make_admin(session)
    user = await _make_user(session, "own-devices@test.com")
    session.add(Device(name="mine", public_key="pk-api-mine", user_id=user.id))
    session.add(Device(name="not-mine", public_key="pk-api-notmine", user_id=admin.id))
    await session.flush()

    # Override to be the regular user
    test_app = _build_app(session)
    test_app.dependency_overrides[get_current_api_user] = lambda: user
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get("/api/v0/devices/")
        assert resp.status_code == 200
        names = [d["name"] for d in resp.json()]
        assert "mine" in names
        assert "not-mine" not in names


async def test_get_device(session):
    admin = await _make_admin(session)
    device = Device(name="detail", public_key="pk-api-detail", user_id=admin.id, ipv4="10.0.0.5")
    session.add(device)
    await session.flush()

    app = _build_app(session, admin_user=admin)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/api/v0/devices/{device.id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "detail"
        assert resp.json()["ipv4"] == "10.0.0.5"


async def test_get_device_forbidden_for_other_user(session):
    admin = await _make_admin(session)
    user = await _make_user(session, "other-dev@test.com")
    device = Device(name="admin-dev", public_key="pk-api-forbid", user_id=admin.id)
    session.add(device)
    await session.flush()

    test_app = _build_app(session)
    test_app.dependency_overrides[get_current_api_user] = lambda: user
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get(f"/api/v0/devices/{device.id}")
        assert resp.status_code == 403


async def test_update_device(session):
    admin = await _make_admin(session)
    device = Device(name="old-name", public_key="pk-api-update", user_id=admin.id)
    session.add(device)
    await session.flush()

    app = _build_app(session, admin_user=admin)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.put(f"/api/v0/devices/{device.id}", json={"name": "new-name"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "new-name"


async def test_delete_device(session):
    admin = await _make_admin(session)
    device = Device(name="to-delete", public_key="pk-api-del", user_id=admin.id)
    session.add(device)
    await session.flush()
    did = device.id

    app = _build_app(session, admin_user=admin)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.delete(f"/api/v0/devices/{did}")
        assert resp.status_code == 204

    assert await session.get(Device, did) is None


# ========== Rules API ==========


async def test_list_rules(session):
    admin = await _make_admin(session)
    session.add(Rule(action="accept", destination="10.0.0.0/8"))
    session.add(Rule(action="drop", destination="192.168.0.0/16", user_id=admin.id))
    await session.flush()

    app = _build_app(session, admin_user=admin)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v0/rules/")
        assert resp.status_code == 200
        assert len(resp.json()) >= 2


async def test_create_rule(session):
    admin = await _make_admin(session)
    app = _build_app(session, admin_user=admin)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v0/rules/", json={
            "action": "accept",
            "destination": "172.16.0.0/12",
            "port_type": "tcp",
            "port_range": "443",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["action"] == "accept"
        assert data["destination"] == "172.16.0.0/12"
        assert data["port_type"] == "tcp"
        assert data["port_range"] == "443"


async def test_update_rule(session):
    admin = await _make_admin(session)
    rule = Rule(action="accept", destination="10.0.0.0/8")
    session.add(rule)
    await session.flush()

    app = _build_app(session, admin_user=admin)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.put(f"/api/v0/rules/{rule.id}", json={"action": "drop"})
        assert resp.status_code == 200
        assert resp.json()["action"] == "drop"


async def test_delete_rule(session):
    admin = await _make_admin(session)
    rule = Rule(action="drop", destination="0.0.0.0/0")
    session.add(rule)
    await session.flush()
    rid = rule.id

    app = _build_app(session, admin_user=admin)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.delete(f"/api/v0/rules/{rid}")
        assert resp.status_code == 204

    assert await session.get(Rule, rid) is None


# ========== Configuration API ==========


async def test_get_configuration_auto_creates(session):
    admin = await _make_admin(session)
    app = _build_app(session, admin_user=admin)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v0/configuration/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["default_client_mtu"] == 1280
        assert data["local_auth_enabled"] is True


async def test_update_configuration(session):
    admin = await _make_admin(session)
    # Pre-create config
    config = Configuration()
    session.add(config)
    await session.flush()

    app = _build_app(session, admin_user=admin)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.put("/api/v0/configuration/", json={
            "default_client_mtu": 1400,
            "vpn_session_duration": 3600,
            "default_client_dns": ["8.8.8.8"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["default_client_mtu"] == 1400
        assert data["vpn_session_duration"] == 3600
        assert data["default_client_dns"] == ["8.8.8.8"]
