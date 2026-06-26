"""Tests for services — WireGuard event error handling and rule events."""

from unittest.mock import AsyncMock, patch

from wiregui.models.device import Device
from wiregui.models.rule import Rule
from wiregui.services.events import on_device_created, on_device_deleted, on_device_updated, on_rule_created, _device_allowed_ips


def _make_device(**kwargs) -> Device:
    defaults = dict(
        name="test",
        public_key="pk-test",
        preshared_key="psk-test",
        ipv4="10.3.2.5",
        ipv6="fd00::3:2:5",
        user_id="00000000-0000-0000-0000-000000000000",
    )
    defaults.update(kwargs)
    return Device(**defaults)


# --- _device_allowed_ips tests ---


def test_device_allowed_ips_basic():
    """Test _device_allowed_ips returns tunnel IPs with /32 and /128."""
    device = _make_device()
    ips = _device_allowed_ips(device)
    assert ips == ["10.3.2.5/32", "fd00::3:2:5/128"]


def test_device_allowed_ips_with_relay_subnets():
    """Test _device_allowed_ips includes relay subnets."""
    device = _make_device(allowed_subnets=["192.168.1.0/24", "10.20.0.0/16"])
    ips = _device_allowed_ips(device)
    assert ips == ["10.3.2.5/32", "fd00::3:2:5/128", "192.168.1.0/24", "10.20.0.0/16"]


def test_device_allowed_ips_ipv4_only():
    """Test _device_allowed_ips with only IPv4."""
    device = _make_device(ipv6=None)
    ips = _device_allowed_ips(device)
    assert ips == ["10.3.2.5/32"]


def test_device_allowed_ips_ipv6_only():
    """Test _device_allowed_ips with only IPv6."""
    device = _make_device(ipv4=None)
    ips = _device_allowed_ips(device)
    assert ips == ["fd00::3:2:5/128"]


def test_device_allowed_ips_relay_only():
    """Test _device_allowed_ips with only relay subnets (no tunnel IPs)."""
    device = _make_device(ipv4=None, ipv6=None, allowed_subnets=["192.168.1.0/24"])
    ips = _device_allowed_ips(device)
    assert ips == ["192.168.1.0/24"]


def test_device_allowed_ips_empty():
    """Test _device_allowed_ips with no IPs or subnets."""
    device = _make_device(ipv4=None, ipv6=None, allowed_subnets=[])
    ips = _device_allowed_ips(device)
    assert ips == []


# --- Events (WG disabled) ---


@patch("wiregui.services.events.get_settings")
@patch("wiregui.services.events.wireguard")
async def test_events_skip_when_wg_disabled(mock_wg, mock_settings):
    mock_settings.return_value.wg_enabled = False
    mock_wg.add_peer = AsyncMock()
    mock_wg.remove_peer = AsyncMock()

    device = _make_device()
    await on_device_created(device)
    await on_device_deleted(device)
    await on_device_updated(device)

    mock_wg.add_peer.assert_not_awaited()
    mock_wg.remove_peer.assert_not_awaited()


# --- Events (WG error handling) ---


@patch("wiregui.services.events.get_settings")
@patch("wiregui.services.events.firewall")
@patch("wiregui.services.events.wireguard")
async def test_on_device_created_handles_wg_error(mock_wg, mock_fw, mock_settings):
    mock_settings.return_value.wg_enabled = True
    mock_wg.add_peer = AsyncMock(side_effect=RuntimeError("wg failed"))
    mock_fw.add_device_jump_rule = AsyncMock()

    device = _make_device()
    # Should not raise — error is logged
    await on_device_created(device)


@patch("wiregui.services.events.get_settings")
@patch("wiregui.services.events.firewall")
@patch("wiregui.services.events.wireguard")
async def test_on_device_created_with_relay_subnets(mock_wg, mock_fw, mock_settings):
    """Test that device creation with relay subnets passes correct allowed_ips to WireGuard, adds routes, and configures firewall."""
    mock_settings.return_value.wg_enabled = True
    mock_wg.add_peer = AsyncMock()
    mock_wg.add_routes = AsyncMock()
    mock_fw.add_user_chain = AsyncMock()
    mock_fw.add_device_jump_rule = AsyncMock()

    device = _make_device(allowed_subnets=["192.168.1.0/24", "10.20.0.0/16"])
    await on_device_created(device)

    # Verify WireGuard peer was added with tunnel IPs + relay subnets
    mock_wg.add_peer.assert_awaited_once_with(
        public_key="pk-test",
        allowed_ips=["10.3.2.5/32", "fd00::3:2:5/128", "192.168.1.0/24", "10.20.0.0/16"],
        preshared_key="psk-test",
    )
    
    # Verify routes were added for relay subnets
    mock_wg.add_routes.assert_awaited_once_with(["192.168.1.0/24", "10.20.0.0/16"])
    
    # Verify firewall jump rule was added with relay subnets
    mock_fw.add_device_jump_rule.assert_awaited_once_with(
        "00000000-0000-0000-0000-000000000000",
        "10.3.2.5",
        "fd00::3:2:5",
        ["192.168.1.0/24", "10.20.0.0/16"],
    )


@patch("wiregui.services.events.get_settings")
@patch("wiregui.services.events.wireguard")
async def test_on_device_deleted_prunes_orphaned_routes(mock_wg, mock_settings, monkeypatch):
    """Deleting a device reconciles routes against the remaining DB devices, so its
    orphaned subnets are pruned while subnets still used elsewhere are kept."""
    mock_settings.return_value.wg_enabled = True
    mock_wg.remove_peer = AsyncMock()
    mock_wg.sync_routes = AsyncMock()

    # Remaining devices (after this delete) still route 10.20.0.0/16 but not the
    # deleted device's 192.168.1.0/24.
    async def fake_remaining():
        return {"10.20.0.0/16"}

    monkeypatch.setattr("wiregui.services.events._all_relay_subnets", fake_remaining)

    device = _make_device(allowed_subnets=["192.168.1.0/24", "10.20.0.0/16"])
    await on_device_deleted(device)

    # sync_routes is called with the *remaining* expected set — 192.168.1.0/24 is
    # therefore pruned, 10.20.0.0/16 is preserved.
    mock_wg.sync_routes.assert_awaited_once_with({"10.20.0.0/16"})


# --- Rule events ---


@patch("wiregui.services.events.get_settings")
@patch("wiregui.services.events._rebuild_user_chain", new_callable=AsyncMock)
async def test_on_rule_created_rebuilds_user_chain(mock_rebuild, mock_settings):
    # A new rule rebuilds the whole user chain (rather than appending) so the rule
    # is placed at its correct position according to priority order.
    mock_settings.return_value.wg_enabled = True

    rule = Rule(
        action="accept",
        destination="10.0.0.0/8",
        port_type="tcp",
        port_range="80",
        user_id="00000000-0000-0000-0000-000000000000",
    )
    await on_rule_created(rule)

    mock_rebuild.assert_awaited_once_with("00000000-0000-0000-0000-000000000000")
