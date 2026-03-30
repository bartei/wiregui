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
