"""User account page — password change, MFA management, API tokens."""

from uuid import UUID

from loguru import logger
from nicegui import app, ui
from sqlmodel import select

import json

from wiregui.auth.api_token import generate_api_token
from wiregui.auth.mfa import generate_totp_qr_svg, generate_totp_secret, get_totp_uri, verify_totp_code
from wiregui.auth.passwords import hash_password, verify_password
from wiregui.auth.webauthn import create_registration_options, verify_registration
from wiregui.db import async_session
from wiregui.models.api_token import ApiToken
from wiregui.models.mfa_method import MFAMethod
from wiregui.models.oidc_connection import OIDCConnection
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

    with ui.column().classes("w-full p-4"):
        ui.label("Account Settings").classes("text-h5 q-mb-md")

        with ui.tabs().classes("w-full") as tabs:
            profile_tab = ui.tab("Profile")
            mfa_tab = ui.tab("Two-Factor Auth")
            tokens_tab = ui.tab("API Tokens")

        with ui.tab_panels(tabs, value=profile_tab).classes("w-full"):

            # === Profile ===
            with ui.tab_panel(profile_tab):
                with ui.card().classes("w-full"):
                    ui.label("Account Details").classes("text-subtitle1 text-bold")
                    ui.separator()
                    with ui.grid(columns=2).classes("w-full gap-2 q-pa-sm"):
                        ui.label("Email:").classes("text-bold")
                        ui.label(user.email)
                        ui.label("Role:").classes("text-bold")
                        ui.label(user.role)
                        ui.label("Last Sign-in:").classes("text-bold")
                        ui.label(str(user.last_signed_in_at)[:19] if user.last_signed_in_at else "-")
                        ui.label("Method:").classes("text-bold")
                        ui.label(user.last_signed_in_method or "-")

                with ui.card().classes("w-full q-mt-md"):
                    ui.label("Change Password").classes("text-subtitle1 text-bold")
                    ui.separator()

                    current_pw = ui.input("Current Password", password=True, password_toggle_button=True).props("outlined dense").classes("w-full")
                    new_pw = ui.input("New Password", password=True, password_toggle_button=True).props("outlined dense").classes("w-full")
                    confirm_pw = ui.input("Confirm New Password", password=True, password_toggle_button=True).props("outlined dense").classes("w-full")

                    async def change_password():
                        if not current_pw.value or not new_pw.value:
                            ui.notify("Fill in all password fields", type="negative")
                            return
                        if new_pw.value != confirm_pw.value:
                            ui.notify("New passwords do not match", type="negative")
                            return
                        if len(new_pw.value) < 8:
                            ui.notify("Password must be at least 8 characters", type="negative")
                            return

                        async with async_session() as session:
                            u = await session.get(User, user_id)
                            if not verify_password(current_pw.value, u.password_hash):
                                ui.notify("Current password is incorrect", type="negative")
                                return
                            u.password_hash = hash_password(new_pw.value)
                            session.add(u)
                            await session.commit()

                        logger.info("Password changed for {}", user.email)
                        ui.notify("Password changed", type="positive")
                        current_pw.value = ""
                        new_pw.value = ""
                        confirm_pw.value = ""

                    ui.button("Change Password", on_click=change_password).props("color=primary").classes("q-mt-sm")

                # OIDC connections
                async with async_session() as session:
                    oidc_conns = (await session.execute(
                        select(OIDCConnection).where(OIDCConnection.user_id == user_id)
                    )).scalars().all()

                if oidc_conns:
                    with ui.card().classes("w-full q-mt-md"):
                        ui.label("Connected SSO Providers").classes("text-subtitle1 text-bold")
                        ui.separator()
                        for conn in oidc_conns:
                            with ui.row().classes("w-full items-center justify-between q-pa-xs"):
                                ui.label(f"{conn.provider}").classes("text-bold")
                                ui.label(f"Last refreshed: {str(conn.refreshed_at)[:19] if conn.refreshed_at else 'Never'}")

            # === MFA ===
            with ui.tab_panel(mfa_tab):
                await _render_mfa_panel(user_id, user.email)

            # === API Tokens ===
            with ui.tab_panel(tokens_tab):
                await _render_tokens_panel(user_id)


async def _render_mfa_panel(user_id: UUID, email: str):
    """Render the MFA management tab."""
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
                for m in methods:
                    with ui.row().classes("w-full items-center justify-between q-pa-xs"):
                        with ui.row().classes("items-center gap-2"):
                            ui.icon("security").props("color=primary")
                            ui.label(m.name).classes("text-bold")
                            ui.label(f"({m.type})").classes("text-caption text-grey-7")
                        with ui.row().classes("items-center gap-2"):
                            ui.label(f"Last used: {str(m.last_used_at)[:19] if m.last_used_at else 'Never'}").classes("text-caption")
                            ui.button(icon="delete", on_click=lambda mid=m.id: delete_method(mid)).props("flat dense color=negative")
                    ui.separator()
            else:
                ui.label("No MFA methods configured.").classes("text-caption text-grey-7 q-pa-sm")

    async def delete_method(method_id):
        async with async_session() as session:
            m = await session.get(MFAMethod, method_id)
            if m and m.user_id == user_id:
                await session.delete(m)
                await session.commit()
                logger.info("MFA method deleted for user {}", email)
        ui.notify("MFA method removed")
        await refresh_methods()

    # Registration state
    registration = {"secret": None}

    def start_registration():
        secret = generate_totp_secret()
        registration["secret"] = secret
        uri = get_totp_uri(secret, email)
        svg = generate_totp_qr_svg(uri)

        reg_container.clear()
        with reg_container:
            ui.label("Scan this QR code with your authenticator app:").classes("text-body2")
            ui.html(svg).classes("w-64 q-my-sm")
            ui.label(f"Or enter this secret manually: {secret}").classes("text-caption font-mono")
            reg_name_input = ui.input("Method Name", value="Authenticator").props("outlined dense").classes("w-full")
            reg_code_input = ui.input("Verification Code", placeholder="Enter 6-digit code").props("outlined dense maxlength=6").classes("w-full")

            async def verify_and_save():
                code = reg_code_input.value.strip()
                name = reg_name_input.value.strip() or "Authenticator"
                if not verify_totp_code(registration["secret"], code):
                    ui.notify("Invalid code — check your authenticator", type="negative")
                    return

                async with async_session() as session:
                    method = MFAMethod(
                        name=name,
                        type="totp",
                        payload={"secret": registration["secret"]},
                        user_id=user_id,
                    )
                    session.add(method)
                    await session.commit()

                logger.info("MFA TOTP registered for {}", email)
                ui.notify("MFA method added!", type="positive")
                registration["secret"] = None
                reg_container.clear()
                await refresh_methods()

            ui.button("Verify & Save", on_click=verify_and_save).props("color=primary").classes("q-mt-sm")
            ui.button("Cancel", on_click=lambda: reg_container.clear()).props("flat")

    with ui.card().classes("w-full"):
        ui.label("Two-Factor Authentication Methods").classes("text-subtitle1 text-bold")
        ui.separator()

        methods_container = ui.column().classes("w-full")
        await refresh_methods()

        with ui.row().classes("q-mt-sm gap-2"):
            ui.button("Add TOTP Method", icon="add", on_click=start_registration).props("outline")
            ui.button("Add Security Key", icon="key", on_click=lambda: start_webauthn_registration()).props("outline")

    reg_container = ui.column().classes("w-full q-mt-md")
    webauthn_state = {"challenge": None}

    async def start_webauthn_registration():
        # Get existing webauthn credentials to exclude
        existing = []
        async with async_session() as session:
            from sqlmodel import select as sel
            result = await session.execute(
                sel(MFAMethod).where(MFAMethod.user_id == user_id, MFAMethod.type.in_(["native", "portable"]))
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

        # Call browser's navigator.credentials.create() via JavaScript
        js = f"""
        async function() {{
            try {{
                const options = JSON.parse('{options_json}');
                // Convert base64url strings to ArrayBuffers
                options.challenge = Uint8Array.from(atob(options.challenge.replace(/-/g,'+').replace(/_/g,'/')), c => c.charCodeAt(0));
                options.user.id = Uint8Array.from(atob(options.user.id.replace(/-/g,'+').replace(/_/g,'/')), c => c.charCodeAt(0));
                if (options.excludeCredentials) {{
                    options.excludeCredentials = options.excludeCredentials.map(c => ({{
                        ...c,
                        id: Uint8Array.from(atob(c.id.replace(/-/g,'+').replace(/_/g,'/')), ch => ch.charCodeAt(0))
                    }}));
                }}
                const credential = await navigator.credentials.create({{publicKey: options}});
                // Serialize the response
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
                name="Security Key",
                type="portable",
                payload=credential_data,
                user_id=user_id,
            )
            session.add(method)
            await session.commit()

        logger.info("WebAuthn key registered for {}", email)
        ui.notify("Security key registered!", type="positive")
        webauthn_state["challenge"] = None
        await refresh_methods()


async def _render_tokens_panel(user_id: UUID):
    """Render the API tokens tab."""
    async def load_tokens():
        async with async_session() as session:
            result = await session.execute(
                select(ApiToken).where(ApiToken.user_id == user_id).order_by(ApiToken.inserted_at.desc())
            )
            return result.scalars().all()

    async def refresh_tokens():
        tokens = await load_tokens()
        token_table.rows = [
            {
                "id": str(t.id),
                "created": str(t.inserted_at)[:19],
                "expires": str(t.expires_at)[:19] if t.expires_at else "Never",
                "status": "Expired" if t.expires_at and t.expires_at < utcnow() else "Active",
            }
            for t in tokens
        ]
        token_table.update()

    async def create_token():
        from datetime import timedelta
        days = int(token_days.value) if token_days.value else 30

        plaintext, token_hash = generate_api_token()
        expires_at = utcnow() + timedelta(days=days) if days > 0 else None

        async with async_session() as session:
            token = ApiToken(token_hash=token_hash, expires_at=expires_at, user_id=user_id)
            session.add(token)
            await session.commit()

        logger.info("API token created (expires in {} days)", days)

        # Show the token once
        with ui.dialog(value=True) as token_dialog:
            with ui.card().classes("w-96"):
                ui.label("API Token Created").classes("text-h6")
                ui.label("Copy this token now — it won't be shown again.").classes("text-caption text-negative")
                ui.input(value=plaintext).props("readonly outlined dense").classes("w-full font-mono q-mt-sm")
                ui.button("Close", on_click=token_dialog.close).props("flat").classes("w-full q-mt-sm")

        await refresh_tokens()

    async def delete_token(token_id: str):
        async with async_session() as session:
            t = await session.get(ApiToken, UUID(token_id))
            if t and t.user_id == user_id:
                await session.delete(t)
                await session.commit()
        ui.notify("Token deleted")
        await refresh_tokens()

    with ui.card().classes("w-full"):
        ui.label("API Tokens").classes("text-subtitle1 text-bold")
        ui.separator()
        ui.label("Use API tokens for programmatic access to the REST API.").classes("text-caption text-grey-7")

        token_columns = [
            {"name": "created", "label": "Created", "field": "created", "align": "left"},
            {"name": "expires", "label": "Expires", "field": "expires", "align": "left"},
            {"name": "status", "label": "Status", "field": "status", "align": "left"},
            {"name": "actions", "label": "", "field": "id", "align": "center"},
        ]
        token_table = ui.table(columns=token_columns, rows=[], row_key="id").classes("w-full")
        token_table.add_slot(
            "body-cell-actions",
            '''
            <q-td :props="props">
                <q-btn flat dense icon="delete" color="negative"
                       @click.stop="() => $parent.$emit('delete', props.row.id)" />
            </q-td>
            ''',
        )
        token_table.on("delete", lambda e: delete_token(e.args))

        with ui.row().classes("items-center gap-2 q-mt-sm"):
            token_days = ui.input("Expires in (days)", value="30").props("outlined dense").classes("w-40")
            ui.button("Create Token", icon="add", on_click=create_token).props("color=primary")

    await refresh_tokens()
