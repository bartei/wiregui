"""Magic link authentication — request and verify signed JWT email links."""

from datetime import timedelta
from uuid import UUID

from loguru import logger
from nicegui import app, ui
from sqlmodel import select

from wiregui.auth.jwt import create_access_token, decode_access_token
from wiregui.config import get_settings
from wiregui.db import async_session
from wiregui.models.user import User
from wiregui.services.email import send_magic_link
from wiregui.utils.time import utcnow


@ui.page("/auth/magic-link")
async def magic_link_request_page():
    """Page to request a magic link email."""
    if app.storage.user.get("authenticated"):
        return ui.navigate.to("/")

    async def request_link():
        email_val = email_input.value.strip()
        if not email_val:
            ui.notify("Enter your email", type="negative")
            return

        # Always show success to avoid user enumeration
        ui.notify("If an account exists, a sign-in link has been sent.", type="positive")

        async with async_session() as session:
            result = await session.execute(select(User).where(User.email == email_val))
            user = result.scalar_one_or_none()

        if user and user.disabled_at is None:
            settings = get_settings()
            token = create_access_token(
                user_id=str(user.id),
                role=user.role,
                expires_delta=timedelta(minutes=15),
            )
            link = f"{settings.external_url}/auth/magic/{user.id}/{token}"
            await send_magic_link(email_val, link)
            logger.info("Magic link sent to {}", email_val)

    with ui.column().classes("absolute-center items-center"):
        ui.label("WireGUI").classes("text-h4 text-bold")
        ui.label("Sign in with magic link").classes("text-subtitle1 q-mb-md")

        with ui.card().classes("w-80"):
            email_input = ui.input("Email").props("outlined dense").classes("w-full")
            ui.button("Send Magic Link", on_click=request_link).classes("w-full q-mt-sm")
            email_input.on("keydown.enter", request_link)

        ui.button("Back to login", on_click=lambda: ui.navigate.to("/login")).props("flat").classes("q-mt-md")


@ui.page("/auth/magic/{user_id}/{token}")
async def magic_link_verify_page(user_id: str, token: str):
    """Verify a magic link token and sign the user in."""
    payload = decode_access_token(token)
    if not payload or payload.get("sub") != user_id:
        with ui.column().classes("absolute-center items-center"):
            ui.label("Invalid or expired link").classes("text-h5 text-negative")
            ui.button("Back to login", on_click=lambda: ui.navigate.to("/login")).props("flat")
        return

    async with async_session() as session:
        user = await session.get(User, UUID(user_id))
        if not user or user.disabled_at is not None:
            with ui.column().classes("absolute-center items-center"):
                ui.label("Account not found or disabled").classes("text-h5 text-negative")
                ui.button("Back to login", on_click=lambda: ui.navigate.to("/login")).props("flat")
            return

        user.last_signed_in_at = utcnow()
        user.last_signed_in_method = "magic_link"
        session.add(user)
        await session.commit()

    logger.info("Magic link login: {}", user.email)

    app.storage.user.update(
        authenticated=True,
        user_id=str(user.id),
        email=user.email,
        role=user.role,
    )
    ui.navigate.to("/")
