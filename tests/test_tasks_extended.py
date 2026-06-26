"""Extended task tests — stats polling, reconciliation, OIDC refresh."""

from datetime import timedelta
from unittest.mock import AsyncMock, patch

from sqlmodel import select

from wiregui.auth.passwords import hash_password
from wiregui.models.configuration import Configuration
from wiregui.models.device import Device
from wiregui.models.oidc_connection import OIDCConnection
from wiregui.models.rule import Rule
from wiregui.models.user import User
from wiregui.services.wireguard import PeerInfo
from wiregui.utils.time import utcnow


# ========== Stats task ==========


async def test_stats_update_from_wg_peers(session, monkeypatch):
    """Stats task should update device records from WireGuard peer data."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def mock_session():
        yield session

    monkeypatch.setattr("wiregui.tasks.stats.async_session", mock_session)

    user = User(email="stats-user@test.com")
    session.add(user)
    await session.flush()

    device = Device(name="stats-dev", public_key="pk-stats-test", user_id=user.id)
    session.add(device)
    await session.flush()

    mock_peers = [
        PeerInfo(
            public_key="pk-stats-test",
            endpoint="1.2.3.4:51820",
            rx_bytes=123456,
            tx_bytes=789012,
            latest_handshake=utcnow(),
        )
    ]

    with patch("wiregui.tasks.stats.wireguard") as mock_wg:
        mock_wg.get_peers = AsyncMock(return_value=mock_peers)
        from wiregui.tasks.stats import _update_stats
        await _update_stats()

    refreshed = await session.get(Device, device.id)
    assert refreshed.rx_bytes == 123456
    assert refreshed.tx_bytes == 789012
    assert refreshed.remote_ip == "1.2.3.4"
    assert refreshed.latest_handshake is not None


async def test_stats_no_peers_is_noop(session, monkeypatch):
    """No WG peers should result in no DB changes."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def mock_session():
        yield session

    monkeypatch.setattr("wiregui.tasks.stats.async_session", mock_session)

    with patch("wiregui.tasks.stats.wireguard") as mock_wg:
        mock_wg.get_peers = AsyncMock(return_value=[])
        from wiregui.tasks.stats import _update_stats
        await _update_stats()  # Should not raise


async def test_stats_unmatched_peer_ignored(session, monkeypatch):
    """Peers not matching any device should be ignored."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def mock_session():
        yield session

    monkeypatch.setattr("wiregui.tasks.stats.async_session", mock_session)

    mock_peers = [
        PeerInfo(public_key="unknown-peer-key", rx_bytes=100, tx_bytes=200)
    ]

    with patch("wiregui.tasks.stats.wireguard") as mock_wg:
        mock_wg.get_peers = AsyncMock(return_value=mock_peers)
        from wiregui.tasks.stats import _update_stats
        await _update_stats()  # Should not raise


# ========== Metrics collector ==========


async def test_collector_persists_byte_counters_above_int32(session, monkeypatch):
    """Regression: WireGuard byte counters exceed the int32 range (~2 GB).

    On a deployment, peers transferring >2 GB caused the collector's batched
    commit to fail with asyncpg DataError ("value out of int32 range"), which
    aborted the whole transaction so latest_handshake was never written and
    every device showed as offline. The columns are BigInteger; verify a large
    counter persists and the handshake/status fields are updated.
    """
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def mock_session():
        yield session

    monkeypatch.setattr("wiregui.collector.async_session", mock_session)

    user = User(email="bigbytes@test.com")
    session.add(user)
    await session.flush()

    device = Device(name="bigdev", public_key="pk-bigbytes", user_id=user.id)
    session.add(device)
    await session.flush()

    # 12.7 GB / 13.3 GB — both well past int32 max (2_147_483_647)
    big_rx = 12_708_099_772
    big_tx = 13_345_000_000
    peers = [
        PeerInfo(
            public_key="pk-bigbytes",
            endpoint="9.9.9.9:51820",
            rx_bytes=big_rx,
            tx_bytes=big_tx,
            latest_handshake=utcnow(),
        )
    ]

    from wiregui.collector import _update_db
    labels = await _update_db(peers)

    refreshed = await session.get(Device, device.id)
    assert refreshed.rx_bytes == big_rx
    assert refreshed.tx_bytes == big_tx
    assert refreshed.remote_ip == "9.9.9.9"
    assert refreshed.latest_handshake is not None
    assert labels["pk-bigbytes"]["user_email"] == "bigbytes@test.com"


# ========== Firewall rule ordering (events bridge) ==========


async def test_rebuild_user_chain_orders_rules_by_priority(session, monkeypatch):
    """Regression: rebuilding a user's chain must pass rules to the firewall in
    ascending priority order so a 'drop all' placed last is evaluated last.
    Previously the rules were queried with no ORDER BY, so a catch-all drop could
    end up before the accept rules and block all allowed traffic.
    """
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def mock_session():
        yield session

    monkeypatch.setattr("wiregui.services.events.async_session", mock_session)

    user = User(email="ordered@test.com")
    session.add(user)
    await session.flush()

    # Insert deliberately out of priority order.
    session.add(Rule(action="drop", destination="0.0.0.0/0", priority=30, user_id=user.id))
    session.add(Rule(action="accept", destination="10.2.0.0/16", priority=20, user_id=user.id))
    session.add(Rule(action="accept", destination="10.1.0.0/16", priority=10, user_id=user.id))
    await session.flush()

    captured = {}

    async def fake_rebuild(entries):
        captured["entries"] = entries

    monkeypatch.setattr("wiregui.services.firewall.rebuild_all_rules", fake_rebuild)

    from wiregui.services.events import _rebuild_user_chain
    await _rebuild_user_chain(str(user.id))

    rules = captured["entries"][0]["rules"]
    assert [r["destination"] for r in rules] == ["10.1.0.0/16", "10.2.0.0/16", "0.0.0.0/0"]
    assert [r["priority"] for r in rules] == [10, 20, 30]


# ========== Reconciliation task ==========


async def test_reconcile_adds_missing_peers(session, monkeypatch):
    """Devices in DB but not in WG should be added."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def mock_session():
        yield session

    monkeypatch.setattr("wiregui.tasks.reconcile.async_session", mock_session)

    user = User(email="reconcile@test.com")
    session.add(user)
    await session.flush()

    device = Device(name="missing", public_key="pk-missing", ipv4="10.0.0.5", user_id=user.id)
    session.add(device)
    await session.flush()

    with patch("wiregui.tasks.reconcile.wireguard") as mock_wg:
        mock_wg.get_peers = AsyncMock(return_value=[])  # WG has no peers
        mock_wg.add_peer = AsyncMock()
        mock_wg.remove_peer = AsyncMock()

        from wiregui.tasks.reconcile import reconcile
        await reconcile()

        mock_wg.add_peer.assert_awaited_once()
        call_kwargs = mock_wg.add_peer.call_args[1]
        assert call_kwargs["public_key"] == "pk-missing"
        assert "10.0.0.5/32" in call_kwargs["allowed_ips"]
        mock_wg.remove_peer.assert_not_awaited()


async def test_reconcile_removes_orphaned_peers(session, monkeypatch):
    """Peers in WG but not in DB should be removed."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def mock_session():
        yield session

    monkeypatch.setattr("wiregui.tasks.reconcile.async_session", mock_session)

    # No devices in DB, but WG has a peer
    orphan = PeerInfo(public_key="pk-orphan", rx_bytes=0, tx_bytes=0)

    with patch("wiregui.tasks.reconcile.wireguard") as mock_wg:
        mock_wg.get_peers = AsyncMock(return_value=[orphan])
        mock_wg.add_peer = AsyncMock()
        mock_wg.remove_peer = AsyncMock()

        from wiregui.tasks.reconcile import reconcile
        await reconcile()

        mock_wg.remove_peer.assert_awaited_once_with(public_key="pk-orphan")
        mock_wg.add_peer.assert_not_awaited()


async def test_reconcile_in_sync(session, monkeypatch):
    """When DB and WG match, nothing should happen."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def mock_session():
        yield session

    monkeypatch.setattr("wiregui.tasks.reconcile.async_session", mock_session)

    user = User(email="in-sync@test.com")
    session.add(user)
    await session.flush()

    device = Device(name="synced", public_key="pk-synced", user_id=user.id)
    session.add(device)
    await session.flush()

    peer = PeerInfo(public_key="pk-synced", rx_bytes=0, tx_bytes=0)

    with patch("wiregui.tasks.reconcile.wireguard") as mock_wg:
        mock_wg.get_peers = AsyncMock(return_value=[peer])
        mock_wg.add_peer = AsyncMock()
        mock_wg.remove_peer = AsyncMock()

        from wiregui.tasks.reconcile import reconcile
        await reconcile()

        mock_wg.add_peer.assert_not_awaited()
        mock_wg.remove_peer.assert_not_awaited()


# ========== OIDC refresh task ==========


async def test_oidc_refresh_no_connections_is_noop(session, monkeypatch):
    """No OIDC connections should result in no refresh attempts."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def mock_session():
        yield session

    monkeypatch.setattr("wiregui.tasks.oidc_refresh.async_session", mock_session)
    monkeypatch.setattr("wiregui.auth.oidc.load_providers", AsyncMock(return_value=[]))

    from wiregui.tasks.oidc_refresh import _refresh_all
    await _refresh_all()  # Should not raise


async def test_oidc_refresh_skips_unknown_provider(session, monkeypatch):
    """Connections for unknown providers should be skipped."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def mock_session():
        yield session

    monkeypatch.setattr("wiregui.tasks.oidc_refresh.async_session", mock_session)
    monkeypatch.setattr("wiregui.auth.oidc.load_providers", AsyncMock(return_value=[
        {"id": "known-provider", "client_id": "cid", "client_secret": "cs", "discovery_document_uri": "https://x"}
    ]))

    user = User(email="oidc-skip@test.com")
    session.add(user)
    await session.flush()

    conn = OIDCConnection(provider="unknown-provider", refresh_token="tok", user_id=user.id)
    session.add(conn)
    await session.flush()

    from wiregui.tasks.oidc_refresh import _refresh_all
    await _refresh_all()  # Should skip gracefully
