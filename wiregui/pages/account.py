"""User account page — compact, single-page layout matching Firezone's density."""

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


def _section_header(title: str, description: str = ""):
    """Compact section header — bold title + optional subtitle."""
    ui.label(title).classes("text-lg text-weight-bold q-mt-lg q-mb-none")
    if description:
        ui.label(description).classes("text-caption text-grey-7 q-mb-sm")


def _kv_row(label: str, value):
    """Compact key-value row."""
    with ui.row().classes("w-full items-baseline gap-4"):
        ui.label(label).classes("text-sm text-grey-8 w-36 shrink-0")
        if isinstance(value, str):
            ui.label(value).classes("text-sm")


# Consistent button style: proper padding, readable size, no cramped text
BTN = "unelevated padding=8px 20px"
BTN_PRIMARY = f"color=primary {BTN}"
BTN_OUTLINE = f"outline color=primary {BTN}"
BTN_DANGER = f"color=negative {BTN}"


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

    with ui.column().classes("w-full p-6"):
        ui.label("Account Settings").classes("text-sm text-weight-bold")
        ui.label("Configure settings related to your WireGUI account.").classes("text-caption text-grey-7")

        # ===== Details =====
        _section_header("Details")
        with ui.column().classes("gap-1"):
            _kv_row("Email", user.email)
            _kv_row("Role", user.role)
            _kv_row("Last Signed In", str(user.last_signed_in_at)[:19] if user.last_signed_in_at else "-")
            _kv_row("Created", str(user.inserted_at)[:19])
            _kv_row("Number of Devices", str(device_count))
            _kv_row("Number of Rules", str(rule_count))

        ui.button("Change Email or Password", icon="edit", on_click=lambda: pw_dialog.open()).props(
            BTN_PRIMARY
        ).classes("q-mt-sm")

        # ===== SSO =====
        if oidc_conns:
            _section_header("Connected SSO Providers")
            cols = [
                {"name": "provider", "label": "Provider", "field": "provider", "align": "left"},
                {"name": "refreshed", "label": "Last Refreshed", "field": "refreshed", "align": "left"},
            ]
            rows = [{"provider": c.provider, "refreshed": str(c.refreshed_at)[:19] if c.refreshed_at else "Never"} for c in oidc_conns]
            ui.table(columns=cols, rows=rows, row_key="provider").props("dense flat bordered").classes("w-full text-xs")

        # ===== API Tokens =====
        _section_header("API Tokens", "Manage API tokens.")

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
                    tbl = ui.table(columns=cols, rows=rows, row_key="id").props("dense flat bordered").classes("w-full text-xs")
                    tbl.add_slot("body-cell-status", r'''<q-td :props="props"><q-badge :color="props.row.status === 'Active' ? 'positive' : 'negative'" :label="props.row.status" /></q-td>''')
                    tbl.add_slot("body-cell-actions", r'''<q-td :props="props"><q-btn flat dense icon="delete" color="negative" size="xs" @click.stop="() => $parent.$emit('delete', props.row.id)" /></q-td>''')
                    tbl.on("delete", lambda e: delete_token(e.args))
                else:
                    ui.label("No API tokens.").classes("text-sm text-grey-7")

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
                with ui.row().classes("w-full items-center bg-green-1 rounded px-3 py-1.5 gap-2 q-mb-xs text-xs"):
                    ui.icon("check_circle", color="positive").props("size=xs")
                    ui.label("Copy now — won't be shown again.").classes("text-weight-medium")
                with ui.row().classes("w-full items-center gap-1 q-mb-sm"):
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
        with ui.row().classes("items-center gap-3 q-mt-sm"):
            token_days = ui.input("Expires in days", value="30").props("outlined dense").classes("w-36")
            ui.button("+ Add API Token", on_click=create_token).props(BTN_OUTLINE)

        # ===== MFA =====
        _section_header("Multi Factor Authentication", "Your MFA methods are invoked when login with username and password.")

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
                    tbl = ui.table(columns=cols, rows=rows, row_key="id").props("dense flat bordered").classes("w-full text-xs")
                    tbl.add_slot("body-cell-actions", r'''<q-td :props="props"><q-btn flat dense label="Delete" color="warning" size="xs" @click.stop="() => $parent.$emit('delete', props.row.id)" /></q-td>''')
                    tbl.on("delete", lambda e: _confirm_del_mfa(e.args))
                else:
                    ui.label("No MFA methods added.").classes("text-sm text-grey-7")

        async def _confirm_del_mfa(mid):
            with ui.dialog(value=True) as dlg:
                with ui.card().classes("w-72"):
                    ui.label("Remove MFA method?").classes("text-subtitle2")
                    with ui.row().classes("w-full justify-end q-mt-sm gap-2"):
                        ui.button("Cancel", on_click=dlg.close).props("flat dense size=sm")
                        ui.button("Remove", on_click=lambda: _del_mfa(mid, dlg)).props("color=negative dense size=sm unelevated")

        async def _del_mfa(mid, dlg):
            async with async_session() as session:
                m = await session.get(MFAMethod, UUID(mid))
                if m and m.user_id == user_id:
                    await session.delete(m)
                    await session.commit()
            dlg.close()
            ui.notify("Removed")
            await refresh_methods()

        def start_totp():
            secret = generate_totp_secret()
            registration["secret"] = secret
            svg = generate_totp_qr_svg(get_totp_uri(secret, user.email))
            reg_container.clear()
            with reg_container:
                ui.separator().classes("q-my-sm")
                with ui.row().classes("items-start gap-4"):
                    ui.html(svg).style("width: 140px; height: 140px")
                    with ui.column().classes("gap-2"):
                        ui.label("Scan or enter manually:").classes("text-xs")
                        ui.label(secret).classes("text-xs font-mono bg-grey-2 px-2 py-1 rounded")
                        reg_name = ui.input("Name", value="Authenticator").props("outlined dense").classes("w-52").style("font-size: 0.8rem")
                        reg_code = ui.input("6-digit code").props("outlined dense maxlength=6").classes("w-52").style("font-size: 0.8rem")

                        async def verify():
                            if not verify_totp_code(registration["secret"], reg_code.value.strip()):
                                ui.notify("Invalid code", type="negative")
                                return
                            async with async_session() as session:
                                session.add(MFAMethod(name=reg_name.value.strip() or "Authenticator", type="totp", payload={"secret": registration["secret"]}, user_id=user_id))
                                await session.commit()
                            ui.notify("TOTP added!", type="positive")
                            reg_container.clear()
                            await refresh_methods()

                        with ui.row().classes("gap-2"):
                            ui.button("Verify & Save", on_click=verify).props(BTN_PRIMARY)
                            ui.button("Cancel", on_click=lambda: reg_container.clear()).props("flat dense size=sm")

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
            ui.notify("Security key registered!", type="positive")
            await refresh_methods()

        await refresh_methods()
        with ui.row().classes("gap-2 q-mt-xs"):
            ui.button("+ Add MFA Method", on_click=start_totp).props(BTN_OUTLINE)
            ui.button("+ Add Security Key", on_click=lambda: start_webauthn()).props(BTN_OUTLINE)

        # ===== Danger Zone =====
        _section_header("Danger Zone")
        async with async_session() as session:
            admin_count = (await session.execute(select(func.count()).select_from(User).where(User.role == "admin"))).scalar()
        is_only_admin = user.role == "admin" and admin_count <= 1

        async def confirm_delete():
            with ui.dialog(value=True) as dlg:
                with ui.card().classes("w-80"):
                    ui.label("Are you sure?").classes("text-subtitle2 text-negative")
                    ui.label(f"Type {user.email} to confirm:").classes("text-xs q-my-xs")
                    ci = ui.input().props("outlined dense").classes("w-full").style("font-size: 0.8rem")
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
                    with ui.row().classes("w-full justify-end q-mt-sm gap-2"):
                        ui.button("Cancel", on_click=dlg.close).props("flat dense size=sm")
                        ui.button("Delete", on_click=do_del).props("color=negative dense size=sm unelevated")

        ui.button("Delete Your Account", icon="delete", on_click=confirm_delete).props(
            BTN_DANGER + (" disable" if is_only_admin else "")
        )

    # Password dialog
    with ui.dialog() as pw_dialog:
        with ui.card().classes("w-96"):
            ui.label("Change Email or Password").classes("text-subtitle1 text-weight-medium")
            ui.separator()
            cur = ui.input("Current Password", password=True, password_toggle_button=True).props("outlined dense").classes("w-full")
            npw = ui.input("New Password", password=True, password_toggle_button=True).props("outlined dense").classes("w-full")
            cpw = ui.input("Confirm Password", password=True, password_toggle_button=True).props("outlined dense").classes("w-full")
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
                pw_dialog.close()
            with ui.row().classes("w-full justify-end q-mt-sm"):
                ui.button("Cancel", on_click=pw_dialog.close).props("flat")
                ui.button("Save", on_click=save_pw).props("color=primary unelevated")
