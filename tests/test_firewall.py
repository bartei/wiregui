"""Tests for firewall service — rule expression building and chain naming."""

from wiregui.services.firewall import _build_rule_expr, _user_chain_name


def test_user_chain_name():
    uid = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    name = _user_chain_name(uid)
    assert name == "user_a1b2c3d4e5f6"
    assert len(name) <= 30


def test_user_chain_name_deterministic():
    uid = "12345678-1234-1234-1234-123456789abc"
    assert _user_chain_name(uid) == _user_chain_name(uid)


def test_build_rule_expr_ipv4_accept():
    expr = _build_rule_expr("10.0.0.0/8", "accept")
    assert expr == "ip daddr 10.0.0.0/8 accept"


def test_build_rule_expr_ipv6_drop():
    expr = _build_rule_expr("fd00::/64", "drop")
    assert expr == "ip6 daddr fd00::/64 drop"


def test_build_rule_expr_with_port():
    expr = _build_rule_expr("192.168.0.0/16", "accept", port_type="tcp", port_range="80-443")
    assert expr == "ip daddr 192.168.0.0/16 tcp dport 80-443 accept"


def test_build_rule_expr_single_port():
    expr = _build_rule_expr("10.0.0.1/32", "drop", port_type="udp", port_range="53")
    assert expr == "ip daddr 10.0.0.1/32 udp dport 53 drop"


def test_build_rule_expr_no_port():
    expr = _build_rule_expr("0.0.0.0/0", "accept", port_type=None, port_range=None)
    assert expr == "ip daddr 0.0.0.0/0 accept"


# --- Tests for relay subnet support ---


async def test_add_device_jump_rule_with_allowed_subnets():
    """Test that add_device_jump_rule creates rules for tunnel IPs and relay subnets."""
    from unittest.mock import AsyncMock, patch
    from wiregui.services.firewall import add_device_jump_rule
    
    with patch("wiregui.services.firewall._nft_batch") as mock_nft:
        mock_nft.return_value = None
        
        await add_device_jump_rule(
            user_id="test-user-id",
            device_ipv4="10.3.2.5",
            device_ipv6="fd00::3:2:5",
            allowed_subnets=["192.168.1.0/24", "10.20.0.0/16", "fd00:1::/64"]
        )
        
        # Verify nft_batch was called with correct commands
        mock_nft.assert_called_once()
        commands = mock_nft.call_args[0][0]
        
        # Should have 5 rules: 2 tunnel IPs + 3 subnets
        assert len(commands) == 5
        assert any("ip saddr 10.3.2.5 jump" in cmd for cmd in commands)
        assert any("ip6 saddr fd00::3:2:5 jump" in cmd for cmd in commands)
        assert any("ip saddr 192.168.1.0/24 jump" in cmd for cmd in commands)
        assert any("ip saddr 10.20.0.0/16 jump" in cmd for cmd in commands)
        assert any("ip6 saddr fd00:1::/64 jump" in cmd for cmd in commands)


async def test_add_device_jump_rule_ipv4_subnet_only():
    """Test add_device_jump_rule with only IPv4 relay subnet."""
    from unittest.mock import AsyncMock, patch
    from wiregui.services.firewall import add_device_jump_rule
    
    with patch("wiregui.services.firewall._nft_batch") as mock_nft:
        mock_nft.return_value = None
        
        await add_device_jump_rule(
            user_id="test-user-id",
            device_ipv4="10.3.2.5",
            device_ipv6=None,
            allowed_subnets=["192.168.1.0/24"]
        )
        
        commands = mock_nft.call_args[0][0]
        assert len(commands) == 2
        assert any("ip saddr 10.3.2.5 jump" in cmd for cmd in commands)
        assert any("ip saddr 192.168.1.0/24 jump" in cmd for cmd in commands)


async def test_rebuild_all_rules_with_allowed_subnets():
    """Test that rebuild_all_rules includes relay subnets in jump rules."""
    from unittest.mock import patch
    from wiregui.services.firewall import rebuild_all_rules
    
    with patch("wiregui.services.firewall._nft_batch") as mock_nft, \
         patch("wiregui.services.firewall._list_user_chains") as mock_list:
        mock_nft.return_value = None
        mock_list.return_value = set()
        
        await rebuild_all_rules([{
            "user_id": "user-123",
            "devices": [
                {
                    "ipv4": "10.3.2.5",
                    "ipv6": "fd00::3:2:5",
                    "allowed_subnets": ["192.168.1.0/24", "10.20.0.0/16"]
                }
            ],
            "rules": []
        }])
        
        # Verify nft_batch was called
        mock_nft.assert_called_once()
        commands = mock_nft.call_args[0][0]
        
        # Check that jump rules include both tunnel IPs and relay subnets
        forward_rules = [cmd for cmd in commands if "forward" in cmd and "jump" in cmd]
        assert len(forward_rules) == 4  # 2 tunnel IPs + 2 subnets
        assert any("ip saddr 10.3.2.5 jump" in cmd for cmd in forward_rules)
        assert any("ip6 saddr fd00::3:2:5 jump" in cmd for cmd in forward_rules)
        assert any("ip saddr 192.168.1.0/24 jump" in cmd for cmd in forward_rules)
        assert any("ip saddr 10.20.0.0/16 jump" in cmd for cmd in forward_rules)
