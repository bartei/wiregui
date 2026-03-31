"""MFA challenge page — presented after password login when user has MFA enabled."""

from uuid import UUID

from loguru import logger
from nicegui import app, ui
from sqlmodel import select

from wiregui.auth.mfa import verify_totp_code
from wiregui.db import async_session
from wiregui.models.mfa_method import MFAMethod
from wiregui.pages.style import apply_style


@ui.page("/mfa")
async def mfa_challenge_page():
    # Must have passed password auth (pending_mfa set by login page)
    pending = app.storage.user.get("pending_mfa")
    if not pending:
        return ui.navigate.to("/login")

    apply_style()
    user_id = UUID(pending["user_id"])

    # Load user's MFA methods
    async with async_session() as session:
        result = await session.execute(
            select(MFAMethod).where(MFAMethod.user_id == user_id)
        )
        methods = result.scalars().all()

    totp_methods = [m for m in methods if m.type == "totp"]

    if not totp_methods:
        # No MFA methods — shouldn't be here, complete login
        _complete_login(pending)
        return

    async def verify_code():
        code = code_input.value.strip()
        if not code:
            ui.notify("Enter your authentication code", type="negative")
            return

        for method in totp_methods:
            secret = method.payload.get("secret")
            if secret and verify_totp_code(secret, code):
                # Update last used
                async with async_session() as session:
                    m = await session.get(MFAMethod, method.id)
                    if m:
                        from wiregui.utils.time import utcnow
                        m.last_used_at = utcnow()
                        session.add(m)
                        await session.commit()

                logger.info("MFA verified for user {}", pending["email"])
                _complete_login(pending)
                return

        ui.notify("Invalid code", type="negative")

    with ui.column().classes("absolute-center items-center"):
        ui.label("Two-Factor Authentication").classes("text-h5")
        ui.label(f"Enter the code from your authenticator app for {pending['email']}").classes(
            "text-subtitle1 q-mb-md"
        )

        with ui.card().classes("w-80"):
            code_input = ui.input("Authentication Code").props(
                "outlined dense maxlength=6"
            ).classes("w-full text-center font-mono text-lg")
            ui.button("Verify", on_click=verify_code).classes("w-full q-mt-sm")

        code_input.on("keydown.enter", verify_code)

        ui.button("Cancel", on_click=lambda: _cancel_mfa()).props("flat").classes("q-mt-md")


def _complete_login(pending: dict):
    """Complete the login by setting full auth state."""
    app.storage.user.update(
        authenticated=True,
        user_id=pending["user_id"],
        email=pending["email"],
        role=pending["role"],
        theme_preference=pending.get("theme_preference", "auto"),
    )
    # Clear pending state
    app.storage.user.pop("pending_mfa", None)
    ui.navigate.to("/")


def _cancel_mfa():
    app.storage.user.clear()
    ui.navigate.to("/login")
