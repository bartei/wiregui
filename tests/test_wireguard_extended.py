"""Tests for WireGuard service — ensure_interface, set_private_key, set_listen_port, configure_interface."""

from unittest.mock import AsyncMock, patch, call

from wiregui.services.wireguard import (
    ensure_interface,
    set_private_key,
    set_listen_port,
    configure_interface,
    add_routes,
    remove_routes,
    get_interface_routes,
    sync_routes,
)


# ========== ensure_interface ==========


@patch("wiregui.services.wireguard._run", new_callable=AsyncMock)
async def test_ensure_interface_already_exists(mock_run):
    """If interface exists (ip link show succeeds), do nothing."""
    mock_run.return_value = ""
    await ensure_interface(iface="wg-test")
    # Only called once for ip link show
    mock_run.assert_awaited_once_with(["ip", "link", "show", "wg-test"])


@patch("wiregui.services.wireguard._run", new_callable=AsyncMock)
async def test_ensure_interface_creates_new(mock_run):
    """If interface doesn't exist, create it, assign IPs, bring up."""
    call_count = 0

    async def side_effect(args, input_data=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1 and args == ["ip", "link", "show", "wg-test"]:
            raise RuntimeError("Device not found")
        return ""

    mock_run.side_effect = side_effect
    await ensure_interface(iface="wg-test")

    # Should have called: ip link show (fails), ip link add, ip addr add x2, ip link set up
    assert mock_run.await_count == 5
    calls = [c[0][0] for c in mock_run.call_args_list]
    assert calls[1] == ["ip", "link", "add", "wg-test", "type", "wireguard"]
    assert calls[2][0:3] == ["ip", "address", "add"]
    assert calls[3][0:3] == ["ip", "address", "add"]
    assert calls[4] == ["ip", "link", "set", "wg-test", "up"]


# ========== set_private_key ==========


@patch("wiregui.services.wireguard._run", new_callable=AsyncMock)
async def test_set_private_key(mock_run):
    """set_private_key calls wg set with private-key path."""
    mock_run.return_value = ""
    await set_private_key("/tmp/test.key", iface="wg-test")
    mock_run.assert_awaited_once_with(["wg", "set", "wg-test", "private-key", "/tmp/test.key"])


# ========== set_listen_port ==========


@patch("wiregui.services.wireguard._run", new_callable=AsyncMock)
async def test_set_listen_port(mock_run):
    """set_listen_port calls wg set with listen-port."""
    mock_run.return_value = ""
    await set_listen_port(51820, iface="wg-test")
    mock_run.assert_awaited_once_with(["wg", "set", "wg-test", "listen-port", "51820"])


# ========== configure_interface ==========


@patch("wiregui.services.wireguard._run", new_callable=AsyncMock)
@patch("wiregui.db.async_session")
async def test_configure_interface_no_config(mock_session_cls, mock_run):
    """If no Configuration row exists, do not call wg set."""
    from unittest.mock import MagicMock

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result
    mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

    await configure_interface(iface="wg-test")
    mock_run.assert_not_awaited()


@patch("wiregui.services.wireguard._run", new_callable=AsyncMock)
@patch("wiregui.db.async_session")
async def test_configure_interface_sets_key_and_port(mock_session_cls, mock_run):
    """With valid config, writes key to temp file and calls wg set."""
    from unittest.mock import MagicMock

    mock_config = MagicMock()
    mock_config.server_private_key = "test-private-key-value"

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_config
    mock_session.execute.return_value = mock_result
    mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

    mock_run.return_value = ""
    await configure_interface(iface="wg-test")

    mock_run.assert_awaited_once()
    args = mock_run.call_args[0][0]
    assert args[0:3] == ["wg", "set", "wg-test"]
    assert "private-key" in args
    assert "listen-port" in args


# ========== add_routes ==========


@patch("wiregui.services.wireguard._run", new_callable=AsyncMock)
async def test_add_routes_ipv4(mock_run):
    """add_routes should call ip route add for IPv4 subnets."""
    mock_run.return_value = ""
    await add_routes(["192.168.1.0/24", "10.20.0.0/16"], iface="wg-test")
    
    assert mock_run.await_count == 2
    calls = [c[0][0] for c in mock_run.call_args_list]
    assert calls[0] == ["ip", "-4", "route", "add", "192.168.1.0/24", "dev", "wg-test"]
    assert calls[1] == ["ip", "-4", "route", "add", "10.20.0.0/16", "dev", "wg-test"]


@patch("wiregui.services.wireguard._run", new_callable=AsyncMock)
async def test_add_routes_ipv6(mock_run):
    """add_routes should call ip -6 route add for IPv6 subnets."""
    mock_run.return_value = ""
    await add_routes(["fd00:1::/64", "fd00:2::/48"], iface="wg-test")
    
    assert mock_run.await_count == 2
    calls = [c[0][0] for c in mock_run.call_args_list]
    assert calls[0] == ["ip", "-6", "route", "add", "fd00:1::/64", "dev", "wg-test"]
    assert calls[1] == ["ip", "-6", "route", "add", "fd00:2::/48", "dev", "wg-test"]


@patch("wiregui.services.wireguard._run", new_callable=AsyncMock)
async def test_add_routes_mixed(mock_run):
    """add_routes should handle mixed IPv4 and IPv6."""
    mock_run.return_value = ""
    await add_routes(["192.168.1.0/24", "fd00:1::/64"], iface="wg-test")
    
    assert mock_run.await_count == 2
    calls = [c[0][0] for c in mock_run.call_args_list]
    assert calls[0] == ["ip", "-4", "route", "add", "192.168.1.0/24", "dev", "wg-test"]
    assert calls[1] == ["ip", "-6", "route", "add", "fd00:1::/64", "dev", "wg-test"]


@patch("wiregui.services.wireguard._run", new_callable=AsyncMock)
async def test_add_routes_empty_list(mock_run):
    """add_routes with empty list should not call ip route."""
    await add_routes([], iface="wg-test")
    mock_run.assert_not_awaited()


@patch("wiregui.services.wireguard._run", new_callable=AsyncMock)
async def test_add_routes_already_exists(mock_run):
    """add_routes should not fail if route already exists."""
    mock_run.side_effect = RuntimeError("RTNETLINK answers: File exists")
    # Should not raise
    await add_routes(["192.168.1.0/24"], iface="wg-test")
    mock_run.assert_awaited_once()


# ========== remove_routes ==========


@patch("wiregui.services.wireguard._run", new_callable=AsyncMock)
async def test_remove_routes_ipv4(mock_run):
    """remove_routes should call ip route del for IPv4 subnets."""
    mock_run.return_value = ""
    await remove_routes(["192.168.1.0/24", "10.20.0.0/16"], iface="wg-test")
    
    assert mock_run.await_count == 2
    calls = [c[0][0] for c in mock_run.call_args_list]
    assert calls[0] == ["ip", "-4", "route", "del", "192.168.1.0/24", "dev", "wg-test"]
    assert calls[1] == ["ip", "-4", "route", "del", "10.20.0.0/16", "dev", "wg-test"]


@patch("wiregui.services.wireguard._run", new_callable=AsyncMock)
async def test_remove_routes_ipv6(mock_run):
    """remove_routes should call ip -6 route del for IPv6 subnets."""
    mock_run.return_value = ""
    await remove_routes(["fd00:1::/64"], iface="wg-test")
    
    mock_run.assert_awaited_once_with(["ip", "-6", "route", "del", "fd00:1::/64", "dev", "wg-test"])


@patch("wiregui.services.wireguard._run", new_callable=AsyncMock)
async def test_remove_routes_not_found(mock_run):
    """remove_routes should not fail if route doesn't exist."""
    mock_run.side_effect = RuntimeError("RTNETLINK answers: No such process")
    # Should not raise
    await remove_routes(["192.168.1.0/24"], iface="wg-test")
    mock_run.assert_awaited_once()


# ========== get_interface_routes ==========


@patch("wiregui.services.wireguard.get_settings")
@patch("wiregui.services.wireguard._run", new_callable=AsyncMock)
async def test_get_interface_routes_parses_and_normalizes(mock_run, mock_settings):
    """Parses `ip route show dev` output, skips default, normalizes host routes."""
    mock_settings.return_value.wg_interface = "wg-test"
    mock_run.side_effect = [
        "10.60.1.0/24 proto kernel scope link src 10.60.1.1\n192.168.1.0/24 scope link\n10.0.0.5",
        "fd00::/106 proto kernel scope link",
    ]
    routes = await get_interface_routes(iface="wg-test")
    assert routes == {"10.60.1.0/24", "192.168.1.0/24", "10.0.0.5/32", "fd00::/106"}


# ========== sync_routes ==========


@patch("wiregui.services.wireguard.remove_routes", new_callable=AsyncMock)
@patch("wiregui.services.wireguard.add_routes", new_callable=AsyncMock)
@patch("wiregui.services.wireguard.get_interface_routes", new_callable=AsyncMock)
@patch("wiregui.services.wireguard.get_settings")
async def test_sync_routes_adds_missing_and_prunes_orphans(mock_settings, mock_get, mock_add, mock_remove):
    """sync_routes adds expected-but-missing, removes orphans, and never touches tunnel nets."""
    mock_settings.return_value.wg_interface = "wg-test"
    mock_settings.return_value.wg_ipv4_network = "10.60.1.0/24"
    mock_settings.return_value.wg_ipv6_network = "fd00::/106"
    # Interface currently has: tunnel net, one expected subnet, one orphan.
    mock_get.return_value = {"10.60.1.0/24", "192.168.1.0/24", "10.99.0.0/16"}

    await sync_routes(["192.168.1.0/24", "10.20.0.0/16"], iface="wg-test")

    mock_add.assert_awaited_once()
    assert mock_add.call_args[0][0] == ["10.20.0.0/16"]
    mock_remove.assert_awaited_once()
    # Orphan removed; tunnel network preserved.
    assert mock_remove.call_args[0][0] == ["10.99.0.0/16"]


@patch("wiregui.services.wireguard.remove_routes", new_callable=AsyncMock)
@patch("wiregui.services.wireguard.add_routes", new_callable=AsyncMock)
@patch("wiregui.services.wireguard.get_interface_routes", new_callable=AsyncMock)
@patch("wiregui.services.wireguard.get_settings")
async def test_sync_routes_noop_when_in_sync(mock_settings, mock_get, mock_add, mock_remove):
    """No add/remove calls when the interface already matches the expected set."""
    mock_settings.return_value.wg_interface = "wg-test"
    mock_settings.return_value.wg_ipv4_network = "10.60.1.0/24"
    mock_settings.return_value.wg_ipv6_network = "fd00::/106"
    mock_get.return_value = {"10.60.1.0/24", "192.168.1.0/24"}

    await sync_routes(["192.168.1.0/24"], iface="wg-test")

    mock_add.assert_not_awaited()
    mock_remove.assert_not_awaited()