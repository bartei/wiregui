"""SAML authentication routes — SP-initiated SSO redirect and ACS callback."""

from urllib.parse import urlparse

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from loguru import logger
from nicegui import app
from sqlmodel import select

from wiregui.auth.saml import create_saml_auth, get_login_url, get_metadata, process_response
from wiregui.config import get_settings
from wiregui.db import async_session
from wiregui.models.configuration import Configuration
from wiregui.models.user import User
from wiregui.utils.time import utcnow


async def _get_saml_provider(provider_id: str) -> dict | None:
    async with async_session() as session:
        config = (await session.execute(select(Configuration).limit(1))).scalar_one_or_none()
        if not config:
            return None
        for p in config.saml_identity_providers or []:
            if p.get("id") == provider_id:
                return p
    return None


def _request_data_from_fastapi(request: Request) -> dict:
    settings = get_settings()
    parsed = urlparse(settings.external_url)
    return {
        "http_host": parsed.hostname,
        "script_name": "",
        "server_port": parsed.port or (443 if parsed.scheme == "https" else 80),
        "get_data": dict(request.query_params),
        "post_data": {},
        "https": "on" if parsed.scheme == "https" else "off",
    }


@app.get("/auth/saml/{provider_id}")
async def saml_redirect(provider_id: str, request: Request):
    """Redirect user to the SAML IdP."""
    provider = await _get_saml_provider(provider_id)
    if not provider:
        return RedirectResponse(url="/login")

    try:
        req_data = _request_data_from_fastapi(request)
        auth = create_saml_auth(provider, req_data)
        login_url = get_login_url(auth)
        return RedirectResponse(url=login_url)
    except Exception as e:
        logger.error("SAML redirect failed for {}: {}", provider_id, e)
        return RedirectResponse(url="/login")


@app.post("/auth/saml/{provider_id}/callback")
async def saml_callback(provider_id: str, request: Request):
    """Handle the SAML ACS callback (POST with SAMLResponse)."""
    provider = await _get_saml_provider(provider_id)
    if not provider:
        return RedirectResponse(url="/login")

    try:
        form_data = await request.form()
        req_data = _request_data_from_fastapi(request)
        req_data["post_data"] = dict(form_data)

        auth = create_saml_auth(provider, req_data)
        user_data = process_response(auth)

        if not user_data or not user_data.get("email"):
            logger.warning("SAML callback: no valid user data from {}", provider_id)
            return RedirectResponse(url="/login")

        email = user_data["email"]
        auto_create = provider.get("auto_create_users", False)

        async with async_session() as session:
            result = await session.execute(select(User).where(User.email == email))
            user = result.scalar_one_or_none()

            if user is None:
                if not auto_create:
                    logger.warning("SAML: user {} not found, auto-create disabled for {}", email, provider_id)
                    return RedirectResponse(url="/login")
                user = User(email=email, role="unprivileged")
                session.add(user)
                await session.flush()
                logger.info("SAML: auto-created user {} via {}", email, provider_id)

            if user.disabled_at is not None:
                logger.warning("SAML: disabled user {} attempted login via {}", email, provider_id)
                return RedirectResponse(url="/login")

            user.last_signed_in_at = utcnow()
            user.last_signed_in_method = f"saml:{provider_id}"
            session.add(user)
            await session.commit()

            request.session["authenticated"] = True
            request.session["user_id"] = str(user.id)
            request.session["email"] = user.email
            request.session["role"] = user.role
            request.session["theme_preference"] = user.theme_preference

        logger.info("SAML login: {} via {}", email, provider_id)
        return RedirectResponse(url="/", status_code=303)

    except Exception as e:
        logger.error("SAML callback failed for {}: {}", provider_id, e)
        return RedirectResponse(url="/login")


@app.get("/auth/saml/{provider_id}/metadata")
async def saml_metadata(provider_id: str):
    """Return SP metadata XML for the SAML provider."""
    provider = await _get_saml_provider(provider_id)
    if not provider:
        return Response(status_code=404)

    try:
        metadata_xml = get_metadata(provider)
        return Response(content=metadata_xml, media_type="application/xml")
    except Exception as e:
        logger.error("SAML metadata generation failed for {}: {}", provider_id, e)
        return Response(status_code=500)
