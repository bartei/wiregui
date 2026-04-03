"""OIDC authentication routes — redirect to provider and handle callback."""

from loguru import logger
from nicegui import app, ui

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

    # Extract user info: try userinfo from token, then userinfo endpoint, then ID token claims
    userinfo = token.get("userinfo")
    if not userinfo:
        try:
            userinfo = await client.userinfo(token=token)
        except Exception as e:
            logger.debug("OIDC userinfo endpoint failed for {}: {}", provider_id, e)
            userinfo = None

    # Fallback: decode the ID token for claims
    if not userinfo or not userinfo.get("email"):
        id_token = token.get("id_token")
        if id_token:
            try:
                from jose import jwt as jose_jwt
                # Decode without verification — we already verified during token exchange
                claims = jose_jwt.get_unverified_claims(id_token)
                userinfo = userinfo or {}
                if not userinfo.get("email"):
                    userinfo["email"] = claims.get("email")
                if not userinfo.get("sub"):
                    userinfo["sub"] = claims.get("sub")
                logger.debug("OIDC: extracted claims from ID token: {}", claims)
            except Exception as e:
                logger.debug("OIDC: failed to decode ID token: {}", e)

    email = (userinfo or {}).get("email")
    # Fallback: if sub looks like an email, use it
    if not email:
        sub = (userinfo or {}).get("sub", "")
        if "@" in sub:
            email = sub
            logger.debug("OIDC: using sub as email: {}", email)
    if not email:
        logger.error("OIDC provider {} did not return email. Token keys: {}, userinfo: {}",
                      provider_id, list(token.keys()), userinfo)
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

        # Store auth data in Starlette session — will be picked up by /auth/complete
        request.session["oidc_user_id"] = str(user.id)
        request.session["oidc_email"] = user.email
        request.session["oidc_role"] = user.role

    return RedirectResponse(url="/auth/complete")


@ui.page("/auth/complete")
def auth_complete_page(request: Request):
    """Bridge page: transfer OIDC auth from Starlette session to NiceGUI storage."""
    user_id = request.session.pop("oidc_user_id", None)
    email = request.session.pop("oidc_email", None)
    role = request.session.pop("oidc_role", None)

    if not user_id or not email:
        logger.warning("Auth complete page called without OIDC session data")
        return ui.navigate.to("/login")

    app.storage.user.update(
        authenticated=True,
        user_id=user_id,
        email=email,
        role=role or "unprivileged",
    )
    logger.info("OIDC auth completed for {} — session transferred to NiceGUI", email)
    ui.navigate.to("/")
