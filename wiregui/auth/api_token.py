"""API token authentication — Bearer token via Authorization header."""

import hmac
import secrets

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from wiregui.config import get_settings
from wiregui.models.api_token import ApiToken
from wiregui.models.user import User
from wiregui.utils.time import utcnow


def _token_hmac(token: str) -> str:
    """Compute a keyed HMAC-SHA256 digest of an API token."""
    key = get_settings().secret_key.encode()
    return hmac.new(key, token.encode(), "sha256").hexdigest()


def generate_api_token() -> tuple[str, str]:
    """Generate a new API token. Returns (plaintext_token, token_hash)."""
    plaintext = secrets.token_urlsafe(32)
    return plaintext, _token_hmac(plaintext)


async def resolve_bearer_token(session: AsyncSession, token: str) -> User | None:
    """Look up a Bearer token and return the associated user, or None."""
    token_hash = _token_hmac(token)
    result = await session.execute(
        select(ApiToken).where(ApiToken.token_hash == token_hash)
    )
    api_token = result.scalar_one_or_none()
    if api_token is None:
        return None

    # Check expiry
    if api_token.expires_at and api_token.expires_at < utcnow():
        logger.debug("API token expired for user_id={}", api_token.user_id)
        return None

    # Resolve user
    user = await session.get(User, api_token.user_id)
    if user is None or user.disabled_at is not None:
        return None

    return user
