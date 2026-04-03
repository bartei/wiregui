"""User account page — card-based layout matching admin pages."""

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
        rule_count = (await session.execute(
            select(func.count()).select_from(Rule).where(Rule.user_id == user_id)
        )).scalar()
        oidc_conns = (await session.execute(
            select(OIDCConnection).where(OIDCConnection.user_id == user_id)
        )).scalars().all()

    with ui.column().classes("w-full p-4"):
        ui.label("Account Settings").classes("text-h5 q-mb-md")

        # ===== Account Details =====
        with ui.card().classes("w-full"):
            ui.label("Account Details").classes("text-subtitle1 text-bold")
            ui.separator()

            with ui.grid(columns=2).classes("w-full gap-2 q-pa-sm"):
                ui.label("Email:").classes("text-bold")
                ui.label(user.email)

                ui.label("Role:").classes("text-bold")
                ui.label(user.role.capitalize())

                ui.label("Last Signed In:").classes("text-bold")
                ui.label(str(user.last_signed_in_at)[:19] if user.last_signed_in_at else "Never")

                ui.label("Created:").classes("text-bold")
                ui.label(str(user.inserted_at)[:19])

                ui.label("Devices:").classes("text-bold")
                ui.label(str(device_count))

                ui.label("Rules:").classes("text-bold")
                ui.label(str(rule_count))

        # ===== Change Password (only for users with a local password) =====
        if user.password_hash:
            with ui.card().classes("w-full q-mt-md"):
                ui.label("Change Password").classes("text-subtitle1 text-bold")
                ui.separator()

                cur = ui.input("Current Password", password=True, password_toggle_button=True).props("outlined dense").classes("w-full")
                npw = ui.input("New Password", password=True, password_toggle_button=True).props("outlined dense").classes("w-full q-mt-sm")
                cpw = ui.input("Confirm Password", password=True, password_toggle_button=True).props("outlined dense").classes("w-full q-mt-sm")

                async def save_pw():
                    if not cur.value or not npw.value:
                        ui.notify("All fields required", type="negative")
                        return
                    if npw.value != cpw.value:
                        ui.notify("Passwords don't match", type="negative")
                        return
                    if len(npw.value) < 8:
                        ui.notify("Min 8 characters", type="negative")
                        return
                    async with async_session() as session:
                        u = await session.get(User, user_id)
                        if not verify_password(cur.value, u.password_hash):
                            ui.notify("Wrong current password", type="negative")
                            return
                        u.password_hash = hash_password(npw.value)
                        session.add(u)
                        await session.commit()
                    ui.notify("Password changed", type="positive")
                    cur.value = ""
                    npw.value = ""
                    cpw.value = ""

                ui.button("Update Password", on_click=save_pw).props("color=primary unelevated").classes("q-mt-md")

        # ===== Connected SSO Providers =====
        with ui.card().classes("w-full q-mt-md"):
            ui.label("Connected SSO Providers").classes("text-subtitle1 text-bold")
            ui.separator()

            if oidc_conns:
                cols = [
                    {"name": "provider", "label": "Provider", "field": "provider", "align": "left"},
                    {"name": "refreshed", "label": "Last Refreshed", "field": "refreshed", "align": "left"},
                ]
                rows = [{"provider": c.provider, "refreshed": str(c.refreshed_at)[:19] if c.refreshed_at else "Never"} for c in oidc_conns]
                ui.table(columns=cols, rows=rows, row_key="provider").classes("w-full")
            else:
                ui.label("No SSO providers connected.").classes("text-caption text-grey q-pa-sm")

        # ===== API Tokens =====
        with ui.card().classes("w-full q-mt-md"):
            ui.label("API Tokens").classes("text-subtitle1 text-bold")
            ui.label("Create and manage API tokens for programmatic access.").classes("text-caption text-grey")
            ui.separator()

            tokens_container = ui.column().classes("w-full")
            token_banner = ui.column().classes("w-full")

            async def refresh_tokens():
                async with async_session() as session:
                    tokens = (await session.execute(
                        select(ApiToken).where(ApiToken.user_id == user_id).order_by(ApiToken.inserted_at.desc())
                    )).scalars().all()
                tokens_container.clear()
                with tokens_container:
                    if tokens:
                        cols = [
                            {"name": "created", "label": "Created", "field": "created", "align": "left"},
                            {"name": "expires", "label": "Expires", "field": "expires", "align": "left"},
                            {"name": "status", "label": "Status", "field": "status", "align": "left"},
                            {"name": "actions", "label": "", "field": "id", "align": "center"},
                        ]
                        rows = [{
                            "id": str(t.id),
                            "created": str(t.inserted_at)[:19],
                            "expires": str(t.expires_at)[:19] if t.expires_at else "Never",
                            "status": "Expired" if t.expires_at and t.expires_at < utcnow() else "Active",
                        } for t in tokens]
                        tbl = ui.table(columns=cols, rows=rows, row_key="id").classes("w-full")
                        tbl.add_slot("body-cell-status", r'''<q-td :props="props"><q-badge :color="props.row.status === 'Active' ? 'positive' : 'negative'" :label="props.row.status" /></q-td>''')
                        tbl.add_slot("body-cell-actions", r'''<q-td :props="props"><q-btn flat dense icon="delete" color="negative" size="xs" @click.stop="() => $parent.$emit('delete', props.row.id)" /></q-td>''')
                        tbl.on("delete", lambda e: delete_token(e.args))
                    else:
                        ui.label("No API tokens.").classes("text-caption text-grey q-pa-sm")

            async def create_token():
                days = int(token_days.value) if token_days.value else 30
                plaintext, token_hash = generate_api_token()
                expires_at = utcnow() + timedelta(days=days) if days > 0 else None
                async with async_session() as session:
                    session.add(ApiToken(token_hash=token_hash, expires_at=expires_at, user_id=user_id))
                    await session.commit()
                logger.info("API token created (expires in {} days)", days)
                token_banner.clear()
                with token_banner:
                    with ui.card().classes("w-full").style("border-left: 4px solid var(--q-positive)"):
                        with ui.row().classes("items-center gap-2"):
                            ui.icon("check_circle", color="positive")
                            ui.label("Copy now — this token won't be shown again.").classes("text-weight-medium text-sm")
                        with ui.row().classes("w-full items-center gap-1 q-mt-sm"):
                            ui.input(value=plaintext).props("readonly outlined dense").classes("w-full font-mono").style("font-size: 0.75rem")
                            ui.button(icon="content_copy", on_click=lambda: _copy(plaintext)).props("flat dense size=sm")
                await refresh_tokens()

            async def _copy(text):
                await ui.run_javascript(f"navigator.clipboard.writeText('{text}')")
                ui.notify("Copied", type="positive")

            async def delete_token(token_id):
                async with async_session() as session:
                    t = await session.get(ApiToken, UUID(token_id))
                    if t and t.user_id == user_id:
                        await session.delete(t)
                        await session.commit()
                ui.notify("Token deleted")
                await refresh_tokens()

            await refresh_tokens()

            ui.separator().classes("q-my-sm")
            with ui.row().classes("items-center gap-3"):
                token_days = ui.input("Expires in days", value="30").props("outlined dense").classes("w-36")
                ui.button("Add API Token", icon="add", on_click=create_token).props("color=primary unelevated")

        # ===== Multi-Factor Authentication =====
        with ui.card().classes("w-full q-mt-md"):
            ui.label("Multi-Factor Authentication").classes("text-subtitle1 text-bold")
            ui.label("MFA methods are required when signing in with email and password.").classes("text-caption text-grey")
            ui.separator()

            methods_container = ui.column().classes("w-full")
            reg_container = ui.column().classes("w-full")
            registration = {"secret": None}
            webauthn_state = {"challenge": None}

            async def refresh_methods():
                async with async_session() as session:
                    methods = (await session.execute(
                        select(MFAMethod).where(MFAMethod.user_id == user_id).order_by(MFAMethod.inserted_at)
                    )).scalars().all()
                methods_container.clear()
                with methods_container:
                    if methods:
                        cols = [
                            {"name": "name", "label": "Name", "field": "name", "align": "left"},
                            {"name": "type", "label": "Type", "field": "type", "align": "left"},
                            {"name": "last_used", "label": "Last Used", "field": "last_used", "align": "left"},
                            {"name": "actions", "label": "", "field": "id", "align": "center"},
                        ]
                        rows = [{"id": str(m.id), "name": m.name, "type": m.type.upper(), "last_used": str(m.last_used_at)[:19] if m.last_used_at else "Never"} for m in methods]
                        tbl = ui.table(columns=cols, rows=rows, row_key="id").classes("w-full")
                        tbl.add_slot("body-cell-actions", r'''<q-td :props="props"><q-btn flat dense icon="delete" color="negative" size="xs" @click.stop="() => $parent.$emit('delete', props.row.id)" /></q-td>''')
                        tbl.on("delete", lambda e: _confirm_del_mfa(e.args))
                    else:
                        ui.label("No MFA methods configured.").classes("text-caption text-grey q-pa-sm")

            async def _confirm_del_mfa(mid):
                with ui.dialog(value=True) as dlg:
                    with ui.card().classes("w-80"):
                        ui.label("Remove MFA method?").classes("text-subtitle1 text-bold")
                        ui.label("This action cannot be undone.").classes("text-caption text-grey")
                        ui.separator()
                        with ui.row().classes("w-full justify-end q-mt-sm gap-2"):
                            ui.button("Cancel", on_click=dlg.close).props("flat")
                            ui.button("Remove", on_click=lambda: _del_mfa(mid, dlg)).props("color=negative unelevated")

            async def _del_mfa(mid, dlg):
                async with async_session() as session:
                    m = await session.get(MFAMethod, UUID(mid))
                    if m and m.user_id == user_id:
                        await session.delete(m)
                        await session.commit()
                dlg.close()
                ui.notify("MFA method removed")
                await refresh_methods()

            def start_totp():
                secret = generate_totp_secret()
                registration["secret"] = secret
                svg = generate_totp_qr_svg(get_totp_uri(secret, user.email))
                reg_container.clear()
                with reg_container:
                    ui.separator().classes("q-my-sm")
                    ui.label("Register TOTP Authenticator").classes("text-subtitle2 text-bold")
                    with ui.row().classes("items-start gap-6 q-mt-sm"):
                        ui.html(svg).style("width: 160px; height: 160px")
                        with ui.column().classes("gap-2"):
                            ui.label("Scan the QR code with your authenticator app, or enter the secret manually:").classes("text-sm")
                            ui.input(value=secret).props("readonly outlined dense").classes("w-full font-mono").style("font-size: 0.75rem")
                            reg_name = ui.input("Name", value="Authenticator").props("outlined dense").classes("w-full")
                            reg_code = ui.input("6-digit verification code").props("outlined dense maxlength=6").classes("w-full")

                            async def verify():
                                if not verify_totp_code(registration["secret"], reg_code.value.strip()):
                                    ui.notify("Invalid code", type="negative")
                                    return
                                async with async_session() as session:
                                    session.add(MFAMethod(name=reg_name.value.strip() or "Authenticator", type="totp", payload={"secret": registration["secret"]}, user_id=user_id))
                                    await session.commit()
                                ui.notify("TOTP method added", type="positive")
                                reg_container.clear()
                                await refresh_methods()

                            with ui.row().classes("gap-2"):
                                ui.button("Verify & Save", on_click=verify).props("color=primary unelevated")
                                ui.button("Cancel", on_click=lambda: reg_container.clear()).props("flat")

            async def start_webauthn():
                existing = []
                async with async_session() as session:
                    existing = [m.payload for m in (await session.execute(
                        select(MFAMethod).where(MFAMethod.user_id == user_id, MFAMethod.type.in_(["native", "portable"]))
                    )).scalars().all()]
                try:
                    reg_data = create_registration_options(user_id, user.email, existing)
                except Exception as e:
                    ui.notify(f"WebAuthn unavailable: {e}", type="negative")
                    return
                webauthn_state["challenge"] = reg_data["challenge"]
                js = f"""(async()=>{{try{{const o=JSON.parse('{reg_data["options_json"]}');o.challenge=Uint8Array.from(atob(o.challenge.replace(/-/g,'+').replace(/_/g,'/')),c=>c.charCodeAt(0));o.user.id=Uint8Array.from(atob(o.user.id.replace(/-/g,'+').replace(/_/g,'/')),c=>c.charCodeAt(0));if(o.excludeCredentials)o.excludeCredentials=o.excludeCredentials.map(c=>({{...c,id:Uint8Array.from(atob(c.id.replace(/-/g,'+').replace(/_/g,'/')),h=>h.charCodeAt(0))}}));const cr=await navigator.credentials.create({{publicKey:o}});return JSON.stringify({{id:cr.id,rawId:btoa(String.fromCharCode(...new Uint8Array(cr.rawId))).replace(/\\+/g,'-').replace(/\\//g,'_').replace(/=/g,''),type:cr.type,response:{{attestationObject:btoa(String.fromCharCode(...new Uint8Array(cr.response.attestationObject))).replace(/\\+/g,'-').replace(/\\//g,'_').replace(/=/g,''),clientDataJSON:btoa(String.fromCharCode(...new Uint8Array(cr.response.clientDataJSON))).replace(/\\+/g,'-').replace(/\\//g,'_').replace(/=/g,'')}}}})}}catch(e){{return JSON.stringify({{error:e.message}})}}}})()\n"""
                result = await ui.run_javascript(js)
                try:
                    data = json.loads(result)
                except Exception:
                    ui.notify("WebAuthn error", type="negative")
                    return
                if "error" in data:
                    ui.notify(f"WebAuthn: {data['error']}", type="negative")
                    return
                try:
                    cred = verify_registration(result, webauthn_state["challenge"])
                except Exception as e:
                    ui.notify(f"Failed: {e}", type="negative")
                    return
                async with async_session() as session:
                    session.add(MFAMethod(name="Security Key", type="portable", payload=cred, user_id=user_id))
                    await session.commit()
                ui.notify("Security key registered", type="positive")
                await refresh_methods()

            await refresh_methods()

            ui.separator().classes("q-my-sm")
            with ui.row().classes("gap-2"):
                ui.button("Add TOTP Method", icon="add", on_click=start_totp).props("color=primary unelevated")
                ui.button("Add Security Key", icon="fingerprint", on_click=lambda: start_webauthn()).props("color=primary unelevated")

        # ===== Danger Zone =====
        with ui.card().classes("w-full q-mt-md").style("border-left: 4px solid var(--q-negative)"):
            ui.label("Danger Zone").classes("text-subtitle1 text-bold text-negative")
            ui.separator()

            async with async_session() as session:
                admin_count = (await session.execute(select(func.count()).select_from(User).where(User.role == "admin"))).scalar()
            is_only_admin = user.role == "admin" and admin_count <= 1

            if is_only_admin:
                ui.label("You are the only admin — account deletion is disabled.").classes("text-caption text-grey q-pa-sm")
            else:
                ui.label("Permanently delete your account and all associated data.").classes("text-caption text-grey")

            async def confirm_delete():
                with ui.dialog(value=True) as dlg:
                    with ui.card().classes("w-96"):
                        ui.label("Delete Your Account?").classes("text-subtitle1 text-bold text-negative")
                        ui.label("This will permanently remove your account, all devices, rules, tokens, and MFA methods.").classes("text-sm q-my-sm")
                        ui.separator()
                        ui.label(f"Type your email to confirm:").classes("text-caption text-grey q-mt-sm")
                        ci = ui.input(placeholder=user.email).props("outlined dense").classes("w-full")

                        async def do_del():
                            if ci.value.strip() != user.email:
                                ui.notify("Email doesn't match", type="negative")
                                return
                            async with async_session() as session:
                                for model in (Device, Rule, MFAMethod, ApiToken, OIDCConnection):
                                    for item in (await session.execute(select(model).where(model.user_id == user_id))).scalars().all():
                                        await session.delete(item)
                                u = await session.get(User, user_id)
                                if u:
                                    await session.delete(u)
                                await session.commit()
                            dlg.close()
                            app.storage.user.clear()
                            ui.navigate.to("/login")

                        with ui.row().classes("w-full justify-end q-mt-md gap-2"):
                            ui.button("Cancel", on_click=dlg.close).props("flat")
                            ui.button("Delete My Account", on_click=do_del).props("color=negative unelevated")

            ui.button("Delete Your Account", icon="delete_forever", on_click=confirm_delete).props(
                "color=negative unelevated" + (" disable" if is_only_admin else "")
            ).classes("q-mt-sm")