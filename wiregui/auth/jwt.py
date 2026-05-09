from datetime import datetime, timedelta, timezone

import jwt

from wiregui.config import get_settings

ALGORITHM = "HS256"
DEFAULT_EXPIRE_HOURS = 8


def create_access_token(
    user_id: str,
    role: str,
    expires_delta: timedelta | None = None,
) -> str:
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(hours=DEFAULT_EXPIRE_HOURS))
    payload = {"sub": user_id, "role": role, "exp": expire}
    return jwt.encode(payload, get_settings().secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    """Decode and validate a JWT. Returns the payload dict or None if invalid/expired."""
    try:
        return jwt.decode(token, get_settings().secret_key, algorithms=[ALGORITHM])
    except (jwt.InvalidTokenError, jwt.ExpiredSignatureError):
        return None
