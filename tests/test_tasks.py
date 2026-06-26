"""Tests for background tasks — VPN session expiry and connectivity checks."""

from datetime import timedelta
from unittest.mock import AsyncMock, patch

from sqlmodel import select

from wiregui.auth.passwords import hash_password
from wiregui.models.configuration import Configuration
from wiregui.models.connectivity_check import ConnectivityCheck
from wiregui.models.device import Device
from wiregui.models.user import User
from wiregui.utils.time import utcnow


# --- VPN session expiry ---


async def test_vpn_session_expiry_removes_expired_peers(session, monkeypatch):
    """Users whose session expired should have their WG peers removed."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def mock_session():
        yield session

    monkeypatch.setattr("wiregui.tasks.vpn_session.async_session", mock_session)

    # Create config with 1-hour session duration
    config = Configuration(vpn_session_duration=3600)
    session.add(config)
    await session.flush()

    # Create a user who signed in 2 hours ago (expired)
    expired_user = User(
        email="expired@example.com",
        password_hash=hash_password("pw"),
        last_signed_in_at=utcnow() - timedelta(hours=2),
    )
    session.add(expired_user)
    await session.flush()

    device = Device(name="laptop", public_key="pk-expired", user_id=expired_user.id)
    session.add(device)
    await session.flush()

    # Create a user who signed in 30 min ago (still valid)
    active_user = User(
        email="active@example.com",
        password_hash=hash_password("pw"),
        last_signed_in_at=utcnow() - timedelta(minutes=30),
    )
    session.add(active_user)
    await session.flush()

    active_device = Device(name="phone", public_key="pk-active", user_id=active_user.id)
    session.add(active_device)
    await session.flush()

    # Mock WireGuard
    with patch("wiregui.tasks.vpn_session.wireguard") as mock_wg:
        mock_wg.remove_peer = AsyncMock()

        from wiregui.tasks.vpn_session import _expire_sessions
        await _expire_sessions()

        # Only expired user's peer should be removed
        mock_wg.remove_peer.assert_awaited_once_with(public_key="pk-expired")


async def test_vpn_session_no_expiry_when_duration_zero(session, monkeypatch):
    """When vpn_session_duration is 0 (unlimited), no peers should be removed."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def mock_session():
        yield session

    monkeypatch.setattr("wiregui.tasks.vpn_session.async_session", mock_session)

    config = Configuration(vpn_session_duration=0)
    session.add(config)
    await session.flush()

    user = User(
        email="unlimited@example.com",
        last_signed_in_at=utcnow() - timedelta(days=365),
    )
    session.add(user)
    await session.flush()

    with patch("wiregui.tasks.vpn_session.wireguard") as mock_wg:
        mock_wg.remove_peer = AsyncMock()

        from wiregui.tasks.vpn_session import _expire_sessions
        await _expire_sessions()

        mock_wg.remove_peer.assert_not_awaited()


async def test_vpn_session_no_expiry_when_no_config(session, monkeypatch):
    """When no Configuration exists, no peers should be removed."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def mock_session():
        yield session

    monkeypatch.setattr("wiregui.tasks.vpn_session.async_session", mock_session)

    # No Configuration row at all

    with patch("wiregui.tasks.vpn_session.wireguard") as mock_wg:
        mock_wg.remove_peer = AsyncMock()

        from wiregui.tasks.vpn_session import _expire_sessions
        await _expire_sessions()

        mock_wg.remove_peer.assert_not_awaited()


async def test_vpn_session_skips_disabled_users(session, monkeypatch):
    """Disabled users should be skipped even if their session is expired."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def mock_session():
        yield session

    monkeypatch.setattr("wiregui.tasks.vpn_session.async_session", mock_session)

    config = Configuration(vpn_session_duration=3600)
    session.add(config)
    await session.flush()

    user = User(
        email="disabled-session@example.com",
        last_signed_in_at=utcnow() - timedelta(hours=2),
        disabled_at=utcnow(),
    )
    session.add(user)
    await session.flush()

    device = Device(name="d", public_key="pk-disabled-session", user_id=user.id)
    session.add(device)
    await session.flush()

    with patch("wiregui.tasks.vpn_session.wireguard") as mock_wg:
        mock_wg.remove_peer = AsyncMock()

        from wiregui.tasks.vpn_session import _expire_sessions
        await _expire_sessions()

        mock_wg.remove_peer.assert_not_awaited()


# --- Connectivity checks ---


def test_connectivity_target_is_ip_literal_not_hostname():
    """The reachability check must target an IP literal, not a DNS hostname.

    Resolving a hostname (e.g. one.one.one.one) made the check fail with
    "[Errno -3] Temporary failure in name resolution" during transient DNS
    outages, producing false "down" reports. Targeting 1.1.1.1 by IP removes
    the DNS dependency entirely.
    """
    import ipaddress
    from urllib.parse import urlparse

    from wiregui.tasks.connectivity import DEFAULT_URL

    host = urlparse(DEFAULT_URL).hostname
    # Raises ValueError if host is a name that would require DNS resolution.
    ipaddress.ip_address(host)
    assert host == "1.1.1.1"


async def test_connectivity_check_success(session, monkeypatch):
    """Successful connectivity check should store result in DB."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def mock_session():
        yield session

    monkeypatch.setattr("wiregui.tasks.connectivity.async_session", mock_session)

    # Mock httpx to return a successful response
    import httpx

    class MockResponse:
        status_code = 200
        headers = {"content-type": "text/plain"}
        text = "203.0.113.1"

    class MockAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url):
            return MockResponse()

    monkeypatch.setattr("wiregui.tasks.connectivity.httpx.AsyncClient", lambda **kw: MockAsyncClient())

    from wiregui.tasks.connectivity import _check_connectivity
    await _check_connectivity()

    result = (await session.execute(select(ConnectivityCheck).limit(1))).scalar_one()
    assert result.response_code == 200
    assert result.response_body == "203.0.113.1"


async def test_connectivity_check_failure(session, monkeypatch):
    """Failed connectivity check should store error and create notification."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def mock_session():
        yield session

    monkeypatch.setattr("wiregui.tasks.connectivity.async_session", mock_session)

    class MockAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url):
            raise ConnectionError("Network unreachable")

    monkeypatch.setattr("wiregui.tasks.connectivity.httpx.AsyncClient", lambda **kw: MockAsyncClient())

    from wiregui.services import notifications
    notifications.clear_all()

    from wiregui.tasks.connectivity import _check_connectivity
    await _check_connectivity()

    result = (await session.execute(select(ConnectivityCheck).limit(1))).scalar_one()
    assert result.response_code is None
    assert "Network unreachable" in result.response_body

    assert notifications.count() > 0
    assert "connectivity" in notifications.current()[0].message.lower()
