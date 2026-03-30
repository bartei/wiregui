"""Tests for services — WireGuard and events."""

from unittest.mock import AsyncMock, patch

from wiregui.models.device import Device
from wiregui.models.rule import Rule
from wiregui.services.events import on_device_created, on_device_deleted, on_device_updated, on_rule_created


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


# --- Events (with WG enabled) ---


@patch("wiregui.services.events.get_settings")
@patch("wiregui.services.events.firewall")
@patch("wiregui.services.events.wireguard")
async def test_on_device_created_calls_add_peer(mock_wg, mock_fw, mock_settings):
    mock_settings.return_value.wg_enabled = True
    mock_wg.add_peer = AsyncMock()
    mock_fw.add_device_jump_rule = AsyncMock()

    device = _make_device()
    await on_device_created(device)

    mock_wg.add_peer.assert_awaited_once_with(
        public_key="pk-test",
        allowed_ips=["10.3.2.5/32", "fd00::3:2:5/128"],
        preshared_key="psk-test",
    )
    mock_fw.add_device_jump_rule.assert_awaited_once()


@patch("wiregui.services.events.get_settings")
@patch("wiregui.services.events.wireguard")
async def test_on_device_deleted_calls_remove_peer(mock_wg, mock_settings):
    mock_settings.return_value.wg_enabled = True
    mock_wg.remove_peer = AsyncMock()

    device = _make_device()
    await on_device_deleted(device)

    mock_wg.remove_peer.assert_awaited_once_with(public_key="pk-test")


@patch("wiregui.services.events.get_settings")
@patch("wiregui.services.events.wireguard")
async def test_on_device_updated_calls_add_peer(mock_wg, mock_settings):
    mock_settings.return_value.wg_enabled = True
    mock_wg.add_peer = AsyncMock()

    device = _make_device()
    await on_device_updated(device)

    mock_wg.add_peer.assert_awaited_once()


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


# --- Rule events ---


@patch("wiregui.services.events.get_settings")
@patch("wiregui.services.events.firewall")
async def test_on_rule_created_calls_apply_rule(mock_fw, mock_settings):
    mock_settings.return_value.wg_enabled = True
    mock_fw.apply_rule = AsyncMock()

    rule = Rule(
        action="accept",
        destination="10.0.0.0/8",
        port_type="tcp",
        port_range="80",
        user_id="00000000-0000-0000-0000-000000000000",
    )
    await on_rule_created(rule)

    mock_fw.apply_rule.assert_awaited_once_with(
        "00000000-0000-0000-0000-000000000000", "10.0.0.0/8", "accept", "tcp", "80",
    )
