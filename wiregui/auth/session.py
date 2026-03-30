"""Authentication helpers for NiceGUI pages."""

from sqlmodel import select

from wiregui.db import async_session
from wiregui.models.user import User


async def authenticate_user(email: str, password: str) -> User | None:
    """Verify email/password and return the User if valid, else None."""
    from wiregui.auth.passwords import verify_password

    async with async_session() as session:
        stmt = select(User).where(User.email == email)
        user = (await session.execute(stmt)).scalar_one_or_none()
        if user is None or user.password_hash is None:
            return None
        if not verify_password(password, user.password_hash):
            return None
        if user.disabled_at is not None:
            return None
        return user
