"""Login page — email/password, MFA redirect, OIDC provider buttons."""

from nicegui import app, ui
from sqlmodel import select

from wiregui.auth.oidc import load_providers
from wiregui.auth.session import authenticate_user
from wiregui.db import async_session
from wiregui.models.mfa_method import MFAMethod
from wiregui.pages.style import apply_style
from wiregui.utils.time import utcnow


@ui.page("/login")
async def login_page():
    if app.storage.user.get("authenticated"):
        return ui.navigate.to("/")

    apply_style()

    # Load OIDC providers for SSO buttons
    oidc_providers = await load_providers()

    async def try_login():
        user = await authenticate_user(email.value, password.value)
        if user is None:
            ui.notify("Invalid email or password", type="negative")
            return

        # Check if user has MFA methods
        async with async_session() as session:
            result = await session.execute(
                select(MFAMethod).where(MFAMethod.user_id == user.id)
            )
            mfa_methods = result.scalars().all()

            # Update sign-in tracking
            user_record = await session.get(type(user), user.id)
            user_record.last_signed_in_at = utcnow()
            user_record.last_signed_in_method = "local"
            session.add(user_record)
            await session.commit()

        if mfa_methods:
            # Store pending auth and redirect to MFA challenge
            app.storage.user["pending_mfa"] = {
                "user_id": str(user.id),
                "email": user.email,
                "role": user.role,
                "theme_preference": user.theme_preference,
            }
            ui.navigate.to("/mfa")
        else:
            # No MFA — complete login directly
            app.storage.user.update(
                authenticated=True,
                user_id=str(user.id),
                email=user.email,
                role=user.role,
                theme_preference=user.theme_preference,
            )
            ui.navigate.to("/")

    with ui.column().classes("absolute-center items-center"):
        ui.image("/img/wiregui.svg").classes("w-20 h-20")
        ui.label("WireGUI").classes("text-h4 text-bold")
        ui.label("Sign in to your account").classes("text-subtitle1 q-mb-md")

        with ui.card().classes("w-80"):
            email = ui.input("Email").props("outlined dense").classes("w-full")
            password = ui.input("Password", password=True, password_toggle_button=True).props(
                "outlined dense"
            ).classes("w-full")
            ui.button("Sign in", on_click=try_login).classes("w-full q-mt-sm")

            password.on("keydown.enter", try_login)

            # OIDC provider buttons
            if oidc_providers:
                ui.separator().classes("q-my-md")
                ui.label("Or sign in with").classes("text-caption text-center w-full")
                for provider in oidc_providers:
                    pid = provider.get("id", "")
                    label = provider.get("label", pid)
                    ui.button(
                        label,
                        on_click=lambda p=pid: ui.run_javascript(f"window.location.href='/auth/oidc/{p}'"),
                    ).props("color=primary unelevated").classes("w-full q-mt-xs")
