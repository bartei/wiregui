"""Tests for WireGuard service — ensure_interface, set_private_key, set_listen_port, configure_interface."""

from unittest.mock import AsyncMock, patch, call

from wiregui.services.wireguard import (
    ensure_interface,
    set_private_key,
    set_listen_port,
    configure_interface,
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