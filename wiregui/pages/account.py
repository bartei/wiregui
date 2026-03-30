"""User account page — single scrollable page with all account sections."""

import json
from datetime import timedelta
from uuid import UUID

from loguru import logger
from nicegui import app, ui
from sqlmodel import func, select

from wiregui.auth.api_token import generate_api_token
from wiregui.auth.mfa import generate_totp_qr_svg, generate_totp_secret, get_totp_uri, verify_totp_code
from wiregui.auth.passwords import hash_password, verify_password
from wiregui.auth.webauthn import create_registration_options, verify_registration
from wiregui.db import async_session
from wiregui.models.api_token import ApiToken
from wiregui.models.device import Device
from wiregui.models.mfa_method import MFAMethod
from wiregui.models.oidc_connection import OIDCConnection
from wiregui.models.rule import Rule
from wiregui.models.user import User
from wiregui.pages.layout import layout
from wiregui.utils.time import utcnow


@ui.page("/account")
async def account_page():
    if not app.storage.user.get("authenticated"):
        return ui.navigate.to("/login")

    layout()
    user_id = UUID(app.storage.user["user_id"])

    async with async_session() as session:
        user = await session.get(User, user_id)
        device_count = (await session.execute(
            select(func.count()).select_from(Device).where(Device.user_id == user_id)
        )).scalar()
        oidc_conns = (await session.execute(
            select(OIDCConnection).where(OIDCConnection.user_id == user_id)
        )).scalars().all()

    with ui.column().classes("w-full max-w-3xl mx-auto p-4"):
        # Page header
        ui.label("Account Settings").classes("text-h5 text-weight-medium")
        ui.label("Manage your profile, security, and API access.").classes("text-caption text-grey-7 q-mb-lg")

        # ===== Section 1: Account Details =====
        _render_details(user, device_count)

        # ===== Section 2: Change Password =====
        await _render_password_section(user_id, user.email)

        # ===== Section 3: Connected SSO Providers =====
        _render_sso_section(oidc_conns)

        # ===== Section 4: Multi-Factor Authentication =====
        await _render_mfa_section(user_id, user.email)

        # ===== Section 5: API Tokens =====
        await _render_tokens_section(user_id)

        # ===== Section 6: Danger Zone =====
        await _render_danger_zone(user_id, user.email, user.role)


def _render_details(user: User, device_count: int):
    """Section 1: Account details table."""
    with ui.card().classes("w-full q-mt-lg"):
        ui.label("Account Details").classes("text-h6 text-weight-medium q-pa-md q-pb-none")
        ui.label("Your profile information.").classes("text-caption text-grey-7 q-px-md")
        ui.separator()

        # Table-style layout
        rows = [
            ("Email", user.email),
            ("Role", ui.badge(user.role, color="primary" if user.role == "admin" else "grey").classes("text-xs")),
            ("Last Sign-in", str(user.last_signed_in_at)[:19] if user.last_signed_in_at else "Never"),
            ("Method", user.last_signed_in_method or "-"),
            ("Devices", str(device_count)),
            ("Created", str(user.inserted_at)[:19]),
        ]

        for i, (label, value) in enumerate(rows):
            with ui.row().classes(
                "w-full items-center px-4 py-2.5 hover:bg-grey-1 transition-colors"
                + (" border-t" if i > 0 else "")
            ):
                ui.label(label).classes("w-40 text-weight-medium text-grey-8 text-sm")
                if isinstance(value, str):
                    ui.label(value).classes("text-sm")
                # Badge was already rendered inline


async def _render_password_section(user_id: UUID, email: str):
    """Section 2: Change password form."""
    with ui.card().classes("w-full q-mt-lg"):
        ui.label("Change Password").classes("text-h6 text-weight-medium q-pa-md q-pb-none")
        ui.label("Update your account password.").classes("text-caption text-grey-7 q-px-md")
        ui.separator()

        with ui.column().classes("w-full q-pa-md gap-3"):
            current_pw = ui.input(
                "Current Password", password=True, password_toggle_button=True,
            ).props("outlined dense").classes("w-full")
            new_pw = ui.input(
                "New Password", password=True, password_toggle_button=True,
            ).props("outlined dense").classes("w-full")
            confirm_pw = ui.input(
                "Confirm New Password", password=True, password_toggle_button=True,
            ).props("outlined dense").classes("w-full")

            pw_hint = ui.label("").classes("text-caption text-negative").style("display: none")

            async def change_password():
                pw_hint.style("display: none")
                if not current_pw.value or not new_pw.value:
                    pw_hint.text = "All password fields are required."
                    pw_hint.style("display: block")
                    return
                if new_pw.value != confirm_pw.value:
                    pw_hint.text = "New passwords do not match."
                    pw_hint.style("display: block")
                    return
                if len(new_pw.value) < 8:
                    pw_hint.text = "Password must be at least 8 characters."
                    pw_hint.style("display: block")
                    return

                async with async_session() as session:
                    u = await session.get(User, user_id)
                    if not verify_password(current_pw.value, u.password_hash):
                        pw_hint.text = "Current password is incorrect."
                        pw_hint.style("display: block")
                        return
                    u.password_hash = hash_password(new_pw.value)
                    session.add(u)
                    await session.commit()

                logger.info("Password changed for {}", email)
                ui.notify("Password changed successfully", type="positive")
                current_pw.value = ""
                new_pw.value = ""
                confirm_pw.value = ""

            ui.button("Change Password", on_click=change_password).props("color=primary unelevated")


def _render_sso_section(oidc_conns: list[OIDCConnection]):
    """Section 3: Connected SSO providers."""
    with ui.card().classes("w-full q-mt-lg"):
        ui.label("Connected SSO Providers").classes("text-h6 text-weight-medium q-pa-md q-pb-none")
        ui.label("Single sign-on accounts linked to your profile.").classes("text-caption text-grey-7 q-px-md")
        ui.separator()

        if oidc_conns:
            for i, conn in enumerate(oidc_conns):
                with ui.row().classes(
                    "w-full items-center justify-between px-4 py-3 hover:bg-grey-1 transition-colors"
                    + (" border-t" if i > 0 else "")
                ):
                    with ui.row().classes("items-center gap-3"):
                        ui.icon("login").props("color=primary size=sm")
                        ui.label(conn.provider).classes("text-weight-medium text-sm")
                    with ui.row().classes("items-center gap-2"):
                        refreshed = str(conn.refreshed_at)[:19] if conn.refreshed_at else "Never"
                        ui.label(f"Last refreshed: {refreshed}").classes("text-caption text-grey-7")
                        ui.badge("Connected", color="positive").classes("text-xs")
        else:
            with ui.row().classes("w-full items-center justify-center q-pa-lg"):
                ui.icon("link_off").props("color=grey-5 size=lg")
                ui.label("No SSO providers connected.").classes("text-caption text-grey-5 q-ml-sm")


async def _render_mfa_section(user_id: UUID, email: str):
    """Section 4: Multi-factor authentication methods."""
    with ui.card().classes("w-full q-mt-lg") as mfa_card:
        ui.label("Multi-Factor Authentication").classes("text-h6 text-weight-medium q-pa-md q-pb-none")
        ui.label("Add an extra layer of security to your account.").classes("text-caption text-grey-7 q-px-md")
        ui.separator()

        methods_container = ui.column().classes("w-full")
        reg_container = ui.column().classes("w-full")
        registration = {"secret": None}
        webauthn_state = {"challenge": None}

        async def load_methods():
            async with async_session() as session:
                result = await session.execute(
                    select(MFAMethod).where(MFAMethod.user_id == user_id).order_by(MFAMethod.inserted_at)
                )
                return result.scalars().all()

        async def refresh_methods():
            methods = await load_methods()
            methods_container.clear()
            with methods_container:
                if methods:
                    for i, m in enumerate(methods):
                        with ui.row().classes(
                            "w-full items-center justify-between px-4 py-3 hover:bg-grey-1 transition-colors"
                            + (" border-t" if i > 0 else "")
                        ):
                            with ui.row().classes("items-center gap-3"):
                                icon = "fingerprint" if m.type in ("native", "portable") else "security"
                                ui.icon(icon).props("color=primary size=sm")
                                with ui.column().classes("gap-0"):
                                    ui.label(m.name).classes("text-weight-medium text-sm")
                                    ui.label(m.type.upper()).classes("text-caption text-grey-7")
                            with ui.row().classes("items-center gap-3"):
                                last_used = str(m.last_used_at)[:19] if m.last_used_at else "Never"
                                ui.label(f"Last used: {last_used}").classes("text-caption text-grey-7")
                                ui.button(icon="delete", on_click=lambda mid=m.id: confirm_delete_mfa(mid)).props(
                                    "flat dense round color=negative size=sm"
                                )
                else:
                    with ui.row().classes("w-full items-center justify-center q-pa-lg"):
                        ui.icon("shield").props("color=grey-5 size=lg")
                        ui.label("No MFA methods configured.").classes("text-caption text-grey-5 q-ml-sm")

        async def confirm_delete_mfa(method_id):
            with ui.dialog(value=True) as dlg:
                with ui.card().classes("w-80"):
                    ui.label("Remove MFA Method?").classes("text-h6")
                    ui.label("You will no longer be prompted for this method during sign-in.").classes("text-body2")
                    with ui.row().classes("w-full justify-end q-mt-sm"):
                        ui.button("Cancel", on_click=dlg.close).props("flat")
                        ui.button("Remove", on_click=lambda: _do_delete_mfa(method_id, dlg)).props("color=negative unelevated")

        async def _do_delete_mfa(method_id, dlg):
            async with async_session() as session:
                m = await session.get(MFAMethod, method_id)
                if m and m.user_id == user_id:
                    await session.delete(m)
                    await session.commit()
                    logger.info("MFA method deleted for user {}", email)
            dlg.close()
            ui.notify("MFA method removed")
            await refresh_methods()

        def start_totp_registration():
            secret = generate_totp_secret()
            registration["secret"] = secret
            uri = get_totp_uri(secret, email)
            svg = generate_totp_qr_svg(uri)

            reg_container.clear()
            with reg_container:
                with ui.card().classes("w-full q-mt-sm").props("bordered"):
                    ui.label("Set up TOTP Authenticator").classes("text-subtitle1 text-weight-medium q-pa-md q-pb-none")
                    ui.separator()
                    with ui.column().classes("q-pa-md items-center gap-3"):
                        ui.label("Scan this QR code with your authenticator app:").classes("text-body2")
                        ui.html(svg).classes("w-48")
                        with ui.row().classes("items-center gap-2"):
                            ui.label("Manual entry:").classes("text-caption text-grey-7")
                            ui.label(secret).classes("text-caption font-mono bg-grey-2 px-2 py-1 rounded")
                    ui.separator()
                    with ui.column().classes("q-pa-md gap-3"):
                        reg_name = ui.input("Method Name", value="Authenticator").props("outlined dense").classes("w-full")
                        reg_code = ui.input(
                            "Verification Code", placeholder="Enter 6-digit code",
                        ).props("outlined dense maxlength=6").classes("w-full")

                        async def verify_and_save():
                            code = reg_code.value.strip()
                            name = reg_name.value.strip() or "Authenticator"
                            if not verify_totp_code(registration["secret"], code):
                                ui.notify("Invalid code — check your authenticator", type="negative")
                                return
                            async with async_session() as session:
                                method = MFAMethod(
                                    name=name, type="totp",
                                    payload={"secret": registration["secret"]},
                                    user_id=user_id,
                                )
                                session.add(method)
                                await session.commit()
                            logger.info("MFA TOTP registered for {}", email)
                            ui.notify("TOTP method added!", type="positive")
                            registration["secret"] = None
                            reg_container.clear()
                            await refresh_methods()

                        with ui.row().classes("gap-2"):
                            ui.button("Verify & Save", on_click=verify_and_save).props("color=primary unelevated")
                            ui.button("Cancel", on_click=lambda: reg_container.clear()).props("flat")

        async def start_webauthn_registration():
            existing = []
            async with async_session() as session:
                result = await session.execute(
                    select(MFAMethod).where(MFAMethod.user_id == user_id, MFAMethod.type.in_(["native", "portable"]))
                )
                for m in result.scalars().all():
                    existing.append(m.payload)

            try:
                reg_data = create_registration_options(user_id, email, existing)
            except Exception as e:
                ui.notify(f"WebAuthn not available: {e}", type="negative")
                return

            webauthn_state["challenge"] = reg_data["challenge"]
            options_json = reg_data["options_json"]

            js = f"""
            async function() {{
                try {{
                    const options = JSON.parse('{options_json}');
                    options.challenge = Uint8Array.from(atob(options.challenge.replace(/-/g,'+').replace(/_/g,'/')), c => c.charCodeAt(0));
                    options.user.id = Uint8Array.from(atob(options.user.id.replace(/-/g,'+').replace(/_/g,'/')), c => c.charCodeAt(0));
                    if (options.excludeCredentials) {{
                        options.excludeCredentials = options.excludeCredentials.map(c => ({{
                            ...c,
                            id: Uint8Array.from(atob(c.id.replace(/-/g,'+').replace(/_/g,'/')), ch => ch.charCodeAt(0))
                        }}));
                    }}
                    const credential = await navigator.credentials.create({{publicKey: options}});
                    const response = {{
                        id: credential.id,
                        rawId: btoa(String.fromCharCode(...new Uint8Array(credential.rawId))).replace(/\\+/g,'-').replace(/\\//g,'_').replace(/=/g,''),
                        type: credential.type,
                        response: {{
                            attestationObject: btoa(String.fromCharCode(...new Uint8Array(credential.response.attestationObject))).replace(/\\+/g,'-').replace(/\\//g,'_').replace(/=/g,''),
                            clientDataJSON: btoa(String.fromCharCode(...new Uint8Array(credential.response.clientDataJSON))).replace(/\\+/g,'-').replace(/\\//g,'_').replace(/=/g,''),
                        }},
                    }};
                    return JSON.stringify(response);
                }} catch(e) {{
                    return JSON.stringify({{"error": e.message}});
                }}
            }}
            """
            result = await ui.run_javascript(f"({js})()")
            await _handle_webauthn_response(result)

        async def _handle_webauthn_response(result_json: str):
            try:
                result = json.loads(result_json)
            except (json.JSONDecodeError, TypeError):
                ui.notify("WebAuthn response error", type="negative")
                return
            if "error" in result:
                ui.notify(f"WebAuthn failed: {result['error']}", type="negative")
                return
            challenge = webauthn_state.get("challenge")
            if not challenge:
                ui.notify("No pending WebAuthn challenge", type="negative")
                return
            try:
                credential_data = verify_registration(result_json, challenge)
            except Exception as e:
                ui.notify(f"Verification failed: {e}", type="negative")
                return
            async with async_session() as session:
                method = MFAMethod(
                    name="Security Key", type="portable",
                    payload=credential_data, user_id=user_id,
                )
                session.add(method)
                await session.commit()
            logger.info("WebAuthn key registered for {}", email)
            ui.notify("Security key registered!", type="positive")
            webauthn_state["challenge"] = None
            await refresh_methods()

        await refresh_methods()

        with ui.row().classes("q-pa-md gap-2"):
            ui.button("Add TOTP Method", icon="qr_code", on_click=start_totp_registration).props("outline unelevated")
            ui.button("Add Security Key", icon="key", on_click=lambda: start_webauthn_registration()).props("outline unelevated")


async def _render_tokens_section(user_id: UUID):
    """Section 5: API tokens management."""
    with ui.card().classes("w-full q-mt-lg"):
        ui.label("API Tokens").classes("text-h6 text-weight-medium q-pa-md q-pb-none")
        ui.label("Use tokens for programmatic access to the REST API.").classes("text-caption text-grey-7 q-px-md")
        ui.separator()

        token_banner = ui.column().classes("w-full")
        tokens_container = ui.column().classes("w-full")

        async def load_tokens():
            async with async_session() as session:
                result = await session.execute(
                    select(ApiToken).where(ApiToken.user_id == user_id).order_by(ApiToken.inserted_at.desc())
                )
                return result.scalars().all()

        async def refresh_tokens():
            tokens = await load_tokens()
            tokens_container.clear()
            with tokens_container:
                if tokens:
                    for i, t in enumerate(tokens):
                        is_expired = t.expires_at and t.expires_at < utcnow()
                        with ui.row().classes(
                            "w-full items-center justify-between px-4 py-3 hover:bg-grey-1 transition-colors"
                            + (" border-t" if i > 0 else "")
                        ):
                            with ui.row().classes("items-center gap-3"):
                                ui.icon("vpn_key").props(f"color={'grey-5' if is_expired else 'primary'} size=sm")
                                with ui.column().classes("gap-0"):
                                    ui.label(f"Created {str(t.inserted_at)[:19]}").classes("text-sm")
                                    expires_text = str(t.expires_at)[:19] if t.expires_at else "Never expires"
                                    ui.label(f"Expires: {expires_text}").classes("text-caption text-grey-7")
                            with ui.row().classes("items-center gap-2"):
                                if is_expired:
                                    ui.badge("Expired", color="negative").classes("text-xs")
                                else:
                                    ui.badge("Active", color="positive").classes("text-xs")
                                ui.button(icon="delete", on_click=lambda tid=t.id: delete_token(tid)).props(
                                    "flat dense round color=negative size=sm"
                                )
                else:
                    with ui.row().classes("w-full items-center justify-center q-pa-lg"):
                        ui.icon("vpn_key").props("color=grey-5 size=lg")
                        ui.label("No API tokens created yet.").classes("text-caption text-grey-5 q-ml-sm")

        async def create_token():
            days = int(token_days.value) if token_days.value else 30
            plaintext, token_hash = generate_api_token()
            expires_at = utcnow() + timedelta(days=days) if days > 0 else None

            async with async_session() as session:
                token = ApiToken(token_hash=token_hash, expires_at=expires_at, user_id=user_id)
                session.add(token)
                await session.commit()

            logger.info("API token created (expires in {} days)", days)

            # Show token in a banner
            token_banner.clear()
            with token_banner:
                with ui.card().classes("w-full bg-green-1 q-ma-md").props("bordered"):
                    with ui.row().classes("items-center q-pa-sm gap-2"):
                        ui.icon("check_circle").props("color=positive")
                        ui.label("Token created — copy it now, it won't be shown again.").classes("text-sm text-weight-medium")
                    with ui.row().classes("q-pa-sm q-pt-none items-center gap-2"):
                        token_input = ui.input(value=plaintext).props("readonly outlined dense").classes("w-full font-mono text-xs")
                        ui.button(icon="content_copy", on_click=lambda: _copy_token(plaintext)).props("flat dense")

            await refresh_tokens()

        async def _copy_token(token: str):
            await ui.run_javascript(f"navigator.clipboard.writeText('{token}')")
            ui.notify("Copied to clipboard", type="positive")

        async def delete_token(token_id):
            async with async_session() as session:
                t = await session.get(ApiToken, token_id)
                if t and t.user_id == user_id:
                    await session.delete(t)
                    await session.commit()
            ui.notify("Token deleted")
            await refresh_tokens()

        await refresh_tokens()

        ui.separator()
        with ui.row().classes("items-center gap-2 q-pa-md"):
            token_days = ui.input("Expires in (days)", value="30").props("outlined dense").classes("w-40")
            ui.button("Create Token", icon="add", on_click=create_token).props("color=primary unelevated")


async def _render_danger_zone(user_id: UUID, email: str, role: str):
    """Section 6: Danger zone — account deletion."""
    with ui.card().classes("w-full q-mt-lg").style("border-left: 4px solid var(--q-negative)"):
        ui.label("Danger Zone").classes("text-h6 text-weight-medium text-negative q-pa-md q-pb-none")
        ui.label("Irreversible actions for your account.").classes("text-caption text-grey-7 q-px-md")
        ui.separator()

        with ui.column().classes("q-pa-md"):
            # Check if user is the only admin
            async with async_session() as session:
                admin_count = (await session.execute(
                    select(func.count()).select_from(User).where(User.role == "admin")
                )).scalar()

            is_only_admin = role == "admin" and admin_count <= 1

            if is_only_admin:
                ui.label("You are the only admin — account deletion is disabled.").classes("text-caption text-grey-7")

            async def confirm_delete():
                with ui.dialog(value=True) as dlg:
                    with ui.card().classes("w-96"):
                        ui.label("Delete Your Account?").classes("text-h6 text-negative")
                        ui.label("This will permanently delete your account, all your devices, and firewall rules. This action cannot be undone.").classes("text-body2 q-my-sm")
                        ui.label(f"Type your email to confirm: {email}").classes("text-caption text-weight-medium")
                        confirm_input = ui.input(placeholder=email).props("outlined dense").classes("w-full")

                        async def do_delete():
                            if confirm_input.value.strip() != email:
                                ui.notify("Email does not match", type="negative")
                                return
                            async with async_session() as session:
                                # Delete devices
                                devices = (await session.execute(
                                    select(Device).where(Device.user_id == user_id)
                                )).scalars().all()
                                for d in devices:
                                    await session.delete(d)
                                # Delete rules
                                rules = (await session.execute(
                                    select(Rule).where(Rule.user_id == user_id)
                                )).scalars().all()
                                for r in rules:
                                    await session.delete(r)
                                # Delete user
                                u = await session.get(User, user_id)
                                if u:
                                    await session.delete(u)
                                await session.commit()

                            logger.info("User {} deleted their own account", email)
                            dlg.close()
                            app.storage.user.clear()
                            ui.navigate.to("/login")

                        with ui.row().classes("w-full justify-end q-mt-sm"):
                            ui.button("Cancel", on_click=dlg.close).props("flat")
                            ui.button("Delete My Account", on_click=do_delete).props("color=negative unelevated")

            ui.button(
                "Delete Your Account", icon="delete_forever",
                on_click=confirm_delete,
            ).props("color=negative outline" + (" disable" if is_only_admin else ""))
