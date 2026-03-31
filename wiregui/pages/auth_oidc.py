"""OIDC authentication routes — redirect to provider and handle callback."""

from loguru import logger
from nicegui import app

from fastapi import Request
from fastapi.responses import RedirectResponse

from wiregui.auth.oidc import get_client, get_provider_config
from wiregui.config import get_settings
from wiregui.db import async_session
from wiregui.models.oidc_connection import OIDCConnection
from wiregui.models.user import User
from wiregui.utils.time import utcnow

from sqlmodel import select


@app.get("/auth/oidc/{provider_id}")
async def oidc_redirect(provider_id: str, request: Request):
    """Redirect user to the OIDC provider's authorization endpoint."""
    try:
        client = get_client(provider_id)
    except ValueError:
        return RedirectResponse(url="/login")

    settings = get_settings()
    redirect_uri = f"{settings.external_url}/auth/oidc/{provider_id}/callback"
    return await client.authorize_redirect(request, redirect_uri)


@app.get("/auth/oidc/{provider_id}/callback")
async def oidc_callback(provider_id: str, request: Request):
    """Handle the OIDC provider callback — exchange code for tokens and create session."""
    try:
        client = get_client(provider_id)
    except ValueError:
        return RedirectResponse(url="/login")

    try:
        token = await client.authorize_access_token(request)
    except Exception as e:
        logger.error("OIDC token exchange failed for {}: {}", provider_id, e)
        return RedirectResponse(url="/login")

    userinfo = token.get("userinfo")
    if not userinfo:
        try:
            userinfo = await client.userinfo()
        except Exception as e:
            logger.error("OIDC userinfo failed for {}: {}", provider_id, e)
            return RedirectResponse(url="/login")

    email = userinfo.get("email")
    if not email:
        logger.error("OIDC provider {} did not return email", provider_id)
        return RedirectResponse(url="/login")

    provider_config = await get_provider_config(provider_id)
    auto_create = provider_config.get("auto_create_users", False) if provider_config else False

    async with async_session() as session:
        # Find or create user
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if user is None:
            if not auto_create:
                logger.warning("OIDC: user {} not found and auto-create disabled for {}", email, provider_id)
                return RedirectResponse(url="/login")

            user = User(email=email, role="unprivileged")
            session.add(user)
            await session.flush()
            logger.info("OIDC: auto-created user {} via {}", email, provider_id)

        if user.disabled_at is not None:
            logger.warning("OIDC: disabled user {} attempted login via {}", email, provider_id)
            return RedirectResponse(url="/login")

        # Update sign-in tracking
        user.last_signed_in_at = utcnow()
        user.last_signed_in_method = f"oidc:{provider_id}"
        session.add(user)

        # Store/update OIDC connection with refresh token
        refresh_token = token.get("refresh_token")
        existing_conn = (await session.execute(
            select(OIDCConnection).where(
                OIDCConnection.user_id == user.id,
                OIDCConnection.provider == provider_id,
            )
        )).scalar_one_or_none()

        if existing_conn:
            existing_conn.refresh_token = refresh_token
            existing_conn.refreshed_at = utcnow()
            existing_conn.refresh_response = dict(token)
            session.add(existing_conn)
        else:
            conn = OIDCConnection(
                provider=provider_id,
                refresh_token=refresh_token,
                refresh_response=dict(token),
                refreshed_at=utcnow(),
                user_id=user.id,
            )
            session.add(conn)

        await session.commit()

        logger.info("OIDC login: {} via {}", email, provider_id)

        # Set NiceGUI session — store in Starlette session since we're in a plain route
        request.session["authenticated"] = True
        request.session["user_id"] = str(user.id)
        request.session["email"] = user.email
        request.session["role"] = user.role
        request.session["theme_preference"] = user.theme_preference

    return RedirectResponse(url="/")
