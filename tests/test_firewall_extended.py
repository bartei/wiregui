"""Extended firewall tests — _nft/_nft_batch error handling, add_device_jump_rule edge cases, policies."""

from unittest.mock import AsyncMock, patch

import pytest

from wiregui.services.firewall import (
    _nft,
    _nft_batch,
    add_device_jump_rule,
    setup_base_tables,
    setup_masquerade,
    apply_peer_to_peer_policy,
    apply_lan_to_peers_policy,
    get_ruleset,
)


# ========== _nft error handling ==========


@patch("asyncio.create_subprocess_exec")
async def test_nft_raises_on_failure(mock_exec):
    """_nft raises RuntimeError on non-zero exit code."""
    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"", b"nft: error message")
    mock_proc.returncode = 1
    mock_exec.return_value = mock_proc

    with pytest.raises(RuntimeError, match="nft.*failed"):
        await _nft("list ruleset")


@patch("asyncio.create_subprocess_exec")
async def test_nft_returns_stdout_on_success(mock_exec):
    """_nft returns stdout on success."""
    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"table inet wiregui {}", b"")
    mock_proc.returncode = 0
    mock_exec.return_value = mock_proc

    result = await _nft("list ruleset")
    assert "wiregui" in result


# ========== _nft_batch error handling ==========


@patch("asyncio.create_subprocess_exec")
async def test_nft_batch_raises_on_failure(mock_exec):
    """_nft_batch raises RuntimeError on non-zero exit code."""
    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"", b"Error: syntax error")
    mock_proc.returncode = 1
    mock_exec.return_value = mock_proc

    with pytest.raises(RuntimeError, match="nft batch failed"):
        await _nft_batch(["add table inet wiregui"])


@patch("asyncio.create_subprocess_exec")
async def test_nft_batch_sends_commands_via_stdin(mock_exec):
    """_nft_batch sends all commands via stdin to nft -f -."""
    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"", b"")
    mock_proc.returncode = 0
    mock_exec.return_value = mock_proc

    cmds = ["add table inet wiregui", "add chain inet wiregui test"]
    await _nft_batch(cmds)

    mock_exec.assert_awaited_once()
    # Verify nft -f - was called
    call_args = mock_exec.call_args[0]
    assert call_args == ("nft", "-f", "-")
    # Verify stdin data
    stdin_data = mock_proc.communicate.call_args[0][0]
    assert b"add table inet wiregui" in stdin_data
    assert b"add chain inet wiregui test" in stdin_data


# ========== add_device_jump_rule edge cases ==========


@patch("wiregui.services.firewall._nft_batch", new_callable=AsyncMock)
async def test_add_device_jump_rule_ipv4_only(mock_batch):
    """Only IPv4 — generates single IPv4 jump rule."""
    await add_device_jump_rule("user-id-1", "10.0.0.5", None)
    mock_batch.assert_awaited_once()
    cmds = mock_batch.call_args[0][0]
    assert len(cmds) == 1
    assert "ip saddr 10.0.0.5" in cmds[0]
    assert "jump" in cmds[0]


@patch("wiregui.services.firewall._nft_batch", new_callable=AsyncMock)
async def test_add_device_jump_rule_ipv6_only(mock_batch):
    """Only IPv6 — generates single IPv6 jump rule."""
    await add_device_jump_rule("user-id-2", None, "fd00::5")
    mock_batch.assert_awaited_once()
    cmds = mock_batch.call_args[0][0]
    assert len(cmds) == 1
    assert "ip6 saddr fd00::5" in cmds[0]
    assert "jump" in cmds[0]


@patch("wiregui.services.firewall._nft_batch", new_callable=AsyncMock)
async def test_add_device_jump_rule_no_ips(mock_batch):
    """Neither IPv4 nor IPv6 — no nft commands issued."""
    await add_device_jump_rule("user-id-3", None, None)
    mock_batch.assert_not_awaited()


@patch("wiregui.services.firewall._nft_batch", new_callable=AsyncMock)
async def test_add_device_jump_rule_both_ips(mock_batch):
    """Both IPv4 and IPv6 — generates two jump rules."""
    await add_device_jump_rule("user-id-4", "10.0.0.7", "fd00::7")
    mock_batch.assert_awaited_once()
    cmds = mock_batch.call_args[0][0]
    assert len(cmds) == 2
    assert any("ip saddr 10.0.0.7" in c for c in cmds)
    assert any("ip6 saddr fd00::7" in c for c in cmds)


# ========== setup_base_tables — already exists ==========


@patch("wiregui.services.firewall._nft_batch", new_callable=AsyncMock)
async def test_setup_base_tables_already_exists(mock_batch):
    """If table already exists (File exists error), don't raise."""
    mock_batch.side_effect = RuntimeError("File exists")
    await setup_base_tables()  # should not raise


@patch("wiregui.services.firewall._nft_batch", new_callable=AsyncMock)
async def test_setup_base_tables_other_error_raises(mock_batch):
    """Other nft errors should propagate."""
    mock_batch.side_effect = RuntimeError("Permission denied")
    with pytest.raises(RuntimeError, match="Permission denied"):
        await setup_base_tables()


# ========== setup_masquerade — error handling ==========


@patch("wiregui.services.firewall._nft_batch", new_callable=AsyncMock)
async def test_setup_masquerade_error_swallowed(mock_batch):
    """Masquerade errors are logged but not raised."""
    mock_batch.side_effect = RuntimeError("nft error")
    await setup_masquerade(iface="wg0")  # should not raise


# ========== policy functions — command verification ==========


@patch("wiregui.services.firewall._nft_batch", new_callable=AsyncMock)
async def test_peer_to_peer_enabled(mock_batch):
    """Enabling peer-to-peer generates accept rules."""
    await apply_peer_to_peer_policy(True)
    cmds = mock_batch.call_args[0][0]
    assert any("accept" in c for c in cmds)
    assert any("peer_to_peer" in c for c in cmds)


@patch("wiregui.services.firewall._nft_batch", new_callable=AsyncMock)
async def test_peer_to_peer_disabled(mock_batch):
    """Disabling peer-to-peer generates drop rules."""
    await apply_peer_to_peer_policy(False)
    cmds = mock_batch.call_args[0][0]
    assert any("drop" in c for c in cmds)


@patch("wiregui.services.firewall._nft_batch", new_callable=AsyncMock)
async def test_lan_to_peers_enabled(mock_batch):
    """Enabling LAN-to-peers generates accept rules."""
    await apply_lan_to_peers_policy(True)
    cmds = mock_batch.call_args[0][0]
    assert any("accept" in c for c in cmds)
    assert any("lan_to_peers" in c for c in cmds)


@patch("wiregui.services.firewall._nft_batch", new_callable=AsyncMock)
async def test_lan_to_peers_disabled(mock_batch):
    """Disabling LAN-to-peers generates drop rules."""
    await apply_lan_to_peers_policy(False)
    cmds = mock_batch.call_args[0][0]
    assert any("drop" in c for c in cmds)


# ========== get_ruleset — error handling ==========


@patch("wiregui.services.firewall._nft", new_callable=AsyncMock)
async def test_get_ruleset_returns_output(mock_nft):
    """get_ruleset returns nft list ruleset output."""
    mock_nft.return_value = "table inet wiregui { ... }"
    result = await get_ruleset()
    assert "wiregui" in result


@patch("wiregui.services.firewall._nft", new_callable=AsyncMock)
async def test_get_ruleset_returns_fallback_on_error(mock_nft):
    """get_ruleset returns friendly message when nft not available."""
    mock_nft.side_effect = RuntimeError("nft not found")
    result = await get_ruleset()
    assert "not available" in result