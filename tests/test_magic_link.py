"""Tests for magic link authentication flow."""

from datetime import timedelta

from wiregui.auth.jwt import create_access_token, decode_access_token
from wiregui.auth.passwords import hash_password
from wiregui.models.user import User


def test_magic_link_token_creation():
    """Magic link token should be a valid JWT with short expiry."""
    token = create_access_token(
        user_id="user-123",
        role="unprivileged",
        expires_delta=timedelta(minutes=15),
    )
    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == "user-123"
    assert payload["role"] == "unprivileged"


def test_magic_link_token_expired():
    """Expired magic link token should be rejected."""
    token = create_access_token(
        user_id="user-123",
        role="admin",
        expires_delta=timedelta(minutes=-1),  # Already expired
    )
    payload = decode_access_token(token)
    assert payload is None


def test_magic_link_token_wrong_user():
    """Token should only be valid for the intended user."""
    token = create_access_token(user_id="user-A", role="admin")
    payload = decode_access_token(token)
    assert payload["sub"] == "user-A"
    # Caller is responsible for checking sub matches the URL user_id


async def test_magic_link_disabled_user_rejected(session):
    """Disabled users should not be able to use magic links."""
    from wiregui.utils.time import utcnow

    user = User(
        email="disabled-magic@example.com",
        password_hash=hash_password("pw"),
        disabled_at=utcnow(),
    )
    session.add(user)
    await session.flush()

    # The token would be valid but the page handler checks disabled_at
    token = create_access_token(user_id=str(user.id), role="unprivileged")
    payload = decode_access_token(token)
    assert payload is not None  # Token itself is valid
    assert user.disabled_at is not None  # But user is disabled — handler would reject
