"""Extended service tests — wireguard subprocess mocking, firewall nft mocking, email."""

from unittest.mock import AsyncMock, MagicMock, patch

from wiregui.services.wireguard import PeerInfo, add_peer, get_peers, remove_peer


# ========== WireGuard service (mocked subprocess) ==========


@patch("wiregui.services.wireguard._run", new_callable=AsyncMock)
async def test_add_peer_without_psk(mock_run):
    mock_run.return_value = ""
    await add_peer("pubkey123", ["10.0.0.1/32", "fd00::1/128"], iface="wg-test")
    mock_run.assert_awaited_once()
    args = mock_run.call_args[0][0]
    assert "wg" in args
    assert "set" in args
    assert "pubkey123" in args
    assert "10.0.0.1/32,fd00::1/128" in args


@patch("asyncio.create_subprocess_exec")
async def test_add_peer_with_psk(mock_exec):
    """PSK path uses subprocess directly with stdin."""
    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"", b"")
    mock_proc.returncode = 0
    mock_exec.return_value = mock_proc

    await add_peer("pubkey456", ["10.0.0.2/32"], preshared_key="psk-data", iface="wg-test")
    mock_exec.assert_awaited_once()
    call_args = mock_exec.call_args[0]
    assert "preshared-key" in call_args


@patch("wiregui.services.wireguard._run", new_callable=AsyncMock)
async def test_remove_peer(mock_run):
    mock_run.return_value = ""
    await remove_peer("pubkey789", iface="wg-test")
    mock_run.assert_awaited_once()
    args = mock_run.call_args[0][0]
    assert "remove" in args
    assert "pubkey789" in args


@patch("wiregui.services.wireguard._run", new_callable=AsyncMock)
async def test_get_peers_parses_dump(mock_run):
    dump_output = (
        "privkey\tpubkey\t51820\toff\n"
        "peerkey1\t(none)\t1.2.3.4:51820\t10.0.0.1/32\t1700000000\t12345\t67890\t25\n"
        "peerkey2\t(none)\t(none)\t10.0.0.2/32,fd00::2/128\t0\t0\t0\t0\n"
    )
    mock_run.return_value = dump_output

    peers = await get_peers(iface="wg-test")
    assert len(peers) == 2

    assert peers[0].public_key == "peerkey1"
    assert peers[0].endpoint == "1.2.3.4:51820"
    assert peers[0].rx_bytes == 12345
    assert peers[0].tx_bytes == 67890
    assert peers[0].latest_handshake is not None

    assert peers[1].public_key == "peerkey2"
    assert peers[1].endpoint is None
    assert peers[1].rx_bytes == 0
    assert peers[1].latest_handshake is None
    assert len(peers[1].allowed_ips) == 2


@patch("wiregui.services.wireguard._run", new_callable=AsyncMock)
async def test_get_peers_returns_empty_on_error(mock_run):
    mock_run.side_effect = RuntimeError("interface not found")
    peers = await get_peers(iface="wg-test")
    assert peers == []


# ========== Firewall (mocked nft) ==========


@patch("wiregui.services.firewall._nft_batch", new_callable=AsyncMock)
async def test_setup_base_tables(mock_batch):
    from wiregui.services.firewall import setup_base_tables
    await setup_base_tables()
    mock_batch.assert_awaited_once()
    cmds = mock_batch.call_args[0][0]
    assert any("add table" in c for c in cmds)
    assert any("forward" in c for c in cmds)
    assert any("postrouting" in c for c in cmds)


@patch("wiregui.services.firewall._nft_batch", new_callable=AsyncMock)
async def test_add_user_chain(mock_batch):
    from wiregui.services.firewall import add_user_chain
    await add_user_chain("a1b2c3d4-0000-0000-0000-000000000000")
    mock_batch.assert_awaited_once()
    cmds = mock_batch.call_args[0][0]
    assert any("user_a1b2c3d40000" in c for c in cmds)


@patch("wiregui.services.firewall._nft_batch", new_callable=AsyncMock)
async def test_remove_user_chain(mock_batch):
    from wiregui.services.firewall import remove_user_chain
    await remove_user_chain("a1b2c3d4-0000-0000-0000-000000000000")
    mock_batch.assert_awaited_once()
    cmds = mock_batch.call_args[0][0]
    assert any("flush" in c for c in cmds)
    assert any("delete" in c for c in cmds)


@patch("wiregui.services.firewall._nft_batch", new_callable=AsyncMock)
async def test_add_device_jump_rule(mock_batch):
    from wiregui.services.firewall import add_device_jump_rule
    await add_device_jump_rule("user-id-123", "10.0.0.5", "fd00::5")
    mock_batch.assert_awaited_once()
    cmds = mock_batch.call_args[0][0]
    assert any("10.0.0.5" in c and "jump" in c for c in cmds)
    assert any("fd00::5" in c and "jump" in c for c in cmds)


@patch("wiregui.services.firewall._nft_batch", new_callable=AsyncMock)
async def test_apply_rule(mock_batch):
    from wiregui.services.firewall import apply_rule
    await apply_rule("user-123", "10.0.0.0/8", "accept", "tcp", "80-443")
    mock_batch.assert_awaited_once()
    cmds = mock_batch.call_args[0][0]
    assert any("10.0.0.0/8" in c and "accept" in c and "tcp dport 80-443" in c for c in cmds)


@patch("wiregui.services.firewall._nft_batch", new_callable=AsyncMock)
async def test_rebuild_all_rules(mock_batch):
    from wiregui.services.firewall import rebuild_all_rules
    await rebuild_all_rules([
        {
            "user_id": "user-1",
            "devices": [{"ipv4": "10.0.0.1", "ipv6": "fd00::1"}],
            "rules": [
                {"destination": "0.0.0.0/0", "action": "accept", "port_type": None, "port_range": None},
                {"destination": "192.168.0.0/16", "action": "drop", "port_type": "tcp", "port_range": "22"},
            ],
        }
    ])
    mock_batch.assert_awaited_once()
    cmds = mock_batch.call_args[0][0]
    assert any("flush chain" in c and "forward" in c for c in cmds)
    assert any("0.0.0.0/0" in c and "accept" in c for c in cmds)
    assert any("192.168.0.0/16" in c and "drop" in c for c in cmds)
    assert any("10.0.0.1" in c and "jump" in c for c in cmds)


@patch("wiregui.services.firewall._nft_batch", new_callable=AsyncMock)
async def test_setup_masquerade(mock_batch):
    from wiregui.services.firewall import setup_masquerade
    await setup_masquerade(iface="wg0")
    mock_batch.assert_awaited_once()
    cmds = mock_batch.call_args[0][0]
    assert any("masquerade" in c for c in cmds)


# ========== Email service (mocked smtp) ==========


@patch("wiregui.services.email.aiosmtplib.send", new_callable=AsyncMock)
async def test_send_email_success(mock_send, monkeypatch):
    monkeypatch.setattr("wiregui.services.email.get_settings", lambda: type("S", (), {
        "smtp_host": "smtp.test.com",
        "smtp_port": 587,
        "smtp_user": "user",
        "smtp_password": "pass",
        "smtp_from": "test@test.com",
    })())

    from wiregui.services.email import send_email
    result = await send_email("to@test.com", "Subject", "Body")
    assert result is True
    mock_send.assert_awaited_once()


async def test_send_email_no_smtp_configured(monkeypatch):
    monkeypatch.setattr("wiregui.services.email.get_settings", lambda: type("S", (), {
        "smtp_host": None,
    })())

    from wiregui.services.email import send_email
    result = await send_email("to@test.com", "Subject", "Body")
    assert result is False


@patch("wiregui.services.email.aiosmtplib.send", new_callable=AsyncMock)
async def test_send_magic_link(mock_send, monkeypatch):
    monkeypatch.setattr("wiregui.services.email.get_settings", lambda: type("S", (), {
        "smtp_host": "smtp.test.com",
        "smtp_port": 587,
        "smtp_user": "u",
        "smtp_password": "p",
        "smtp_from": "noreply@test.com",
    })())

    from wiregui.services.email import send_magic_link
    result = await send_magic_link("user@test.com", "https://app.test/magic/123/token")
    assert result is True
    mock_send.assert_awaited_once()
