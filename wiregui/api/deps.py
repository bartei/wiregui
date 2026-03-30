"""Shared FastAPI dependencies for the REST API."""

from collections.abc import AsyncGenerator

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from wiregui.auth.api_token import resolve_bearer_token
from wiregui.db import async_session
from wiregui.models.user import User


async def get_db() -> AsyncGenerator[AsyncSession]:
    async with async_session() as session:
        yield session


async def get_current_api_user(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> User:
    """Extract Bearer token from Authorization header and resolve the user."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = auth[7:]
    user = await resolve_bearer_token(session, token)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired API token")
    return user


async def require_admin(user: User = Depends(get_current_api_user)) -> User:
    """Require the authenticated user to be an admin."""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
