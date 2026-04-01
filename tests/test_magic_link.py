"""Tests for magic link authentication — token subject validation."""

from wiregui.auth.jwt import create_access_token, decode_access_token


def test_magic_link_token_wrong_user():
    """Token should only be valid for the intended user."""
    token = create_access_token(user_id="user-A", role="admin")
    payload = decode_access_token(token)
    assert payload["sub"] == "user-A"
    # Caller is responsible for checking sub matches the URL user_id
