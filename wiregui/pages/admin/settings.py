"""Admin settings pages — tabbed interface for configuration management."""

from uuid import UUID

from loguru import logger
from nicegui import app, ui
from sqlmodel import select

from wiregui.db import async_session
from wiregui.models.configuration import Configuration
from wiregui.pages.layout import layout
from wiregui.utils.time import utcnow


def _guard():
    if not app.storage.user.get("authenticated") or app.storage.user.get("role") != "admin":
        ui.navigate.to("/login")
        return False
    return True


async def _get_or_create_config() -> Configuration:
    async with async_session() as session:
        result = await session.execute(select(Configuration).limit(1))
        config = result.scalar_one_or_none()
        if not config:
            config = Configuration()
            session.add(config)
            await session.commit()
            await session.refresh(config)
        return config


VPN_SESSION_OPTIONS = {
    0: "Never (unlimited)",
    3600: "Every Hour",
    86400: "Every Day",
    604800: "Every Week",
    2592000: "Every 30 Days",
    7776000: "Every 90 Days",
}


@ui.page("/admin/settings")
async def settings_page():
    if not _guard():
        return

    layout()
    config = await _get_or_create_config()

    # --- Client Defaults tab ---
    async def save_defaults():
        async with async_session() as session:
            c = await session.get(Configuration, config.id)
            c.default_client_endpoint = defaults_endpoint.value.strip() or None
            c.default_client_dns = [s.strip() for s in defaults_dns.value.split(",") if s.strip()]
            c.default_client_mtu = int(defaults_mtu.value) if defaults_mtu.value else 1280
            c.default_client_persistent_keepalive = int(defaults_keepalive.value) if defaults_keepalive.value else 25
            c.default_client_allowed_ips = [s.strip() for s in defaults_allowed_ips.value.split(",") if s.strip()]
            c.updated_at = utcnow()
            session.add(c)
            await session.commit()
        logger.info("Client defaults updated")
        ui.notify("Client defaults saved", type="positive")

    # --- Security tab ---
    async def save_security():
        async with async_session() as session:
            c = await session.get(Configuration, config.id)
            c.vpn_session_duration = security_vpn_duration.value
            c.local_auth_enabled = security_local_auth.value
            c.allow_unprivileged_device_management = security_unpriv_mgmt.value
            c.allow_unprivileged_device_configuration = security_unpriv_config.value
            c.disable_vpn_on_oidc_error = security_disable_vpn_oidc.value
            c.updated_at = utcnow()
            session.add(c)
            await session.commit()
        logger.info("Security settings updated")
        ui.notify("Security settings saved", type="positive")

    # --- OIDC provider management ---
    async def save_oidc_provider():
        provider = {
            "id": oidc_id.value.strip(),
            "label": oidc_label.value.strip(),
            "scope": oidc_scope.value.strip(),
            "response_type": "code",
            "client_id": oidc_client_id.value.strip(),
            "client_secret": oidc_client_secret.value.strip(),
            "discovery_document_uri": oidc_discovery.value.strip(),
            "auto_create_users": oidc_auto_create.value,
        }
        if not all([provider["id"], provider["label"], provider["client_id"],
                     provider["client_secret"], provider["discovery_document_uri"]]):
            ui.notify("All required fields must be filled", type="negative")
            return

        async with async_session() as session:
            c = await session.get(Configuration, config.id)
            providers = list(c.openid_connect_providers or [])
            # Replace existing or add new
            providers = [p for p in providers if p.get("id") != provider["id"]]
            providers.append(provider)
            c.openid_connect_providers = providers
            c.updated_at = utcnow()
            session.add(c)
            await session.commit()

        logger.info("OIDC provider saved: {}", provider["id"])
        ui.notify(f"OIDC provider '{provider['label']}' saved", type="positive")
        oidc_dialog.close()
        await refresh_oidc_table()

    async def delete_oidc_provider(provider_id: str):
        async with async_session() as session:
            c = await session.get(Configuration, config.id)
            c.openid_connect_providers = [p for p in (c.openid_connect_providers or []) if p.get("id") != provider_id]
            c.updated_at = utcnow()
            session.add(c)
            await session.commit()
        logger.info("OIDC provider deleted: {}", provider_id)
        ui.notify("OIDC provider deleted")
        await refresh_oidc_table()

    async def refresh_oidc_table():
        async with async_session() as session:
            c = await session.get(Configuration, config.id)
            providers = c.openid_connect_providers or []
        oidc_table.rows = [
            {
                "id": p.get("id", ""),
                "label": p.get("label", ""),
                "client_id": p.get("client_id", ""),
                "discovery": p.get("discovery_document_uri", "")[:50] + "...",
                "auto_create": "Yes" if p.get("auto_create_users") else "No",
            }
            for p in providers
        ]
        oidc_table.update()

    # --- Page content ---
    with ui.column().classes("w-full p-4"):
        ui.label("Settings").classes("text-h5 q-mb-md")

        # === Client Defaults ===
        with ui.card().classes("w-full"):
            ui.label("Default Client Configuration").classes("text-subtitle1 text-bold")
            ui.label("These defaults apply to new devices unless overridden per-device.").classes("text-caption text-grey")
            ui.separator()

            defaults_endpoint = ui.input(
                "Endpoint", value=config.default_client_endpoint or "",
                placeholder="vpn.example.com",
            ).props("outlined dense").classes("w-full")
            ui.label("IPv4/IPv6 address or FQDN clients connect to").classes("text-caption text-grey")

            defaults_dns = ui.input(
                "DNS Servers", value=", ".join(config.default_client_dns),
                placeholder="1.1.1.1, 1.0.0.1",
            ).props("outlined dense").classes("w-full q-mt-sm")
            ui.label("Comma-separated. Leave blank to omit.").classes("text-caption text-grey")

            defaults_allowed_ips = ui.input(
                "Allowed IPs", value=", ".join(config.default_client_allowed_ips),
                placeholder="0.0.0.0/0, ::/0",
            ).props("outlined dense").classes("w-full q-mt-sm")
            ui.label("CIDR ranges for split or full tunnel.").classes("text-caption text-grey")

            with ui.row().classes("w-full gap-4 q-mt-sm"):
                defaults_mtu = ui.input(
                    "MTU", value=str(config.default_client_mtu),
                    placeholder="1280",
                ).props("outlined dense").classes("w-48")

                defaults_keepalive = ui.input(
                    "Persistent Keepalive", value=str(config.default_client_persistent_keepalive),
                    placeholder="25",
                ).props("outlined dense").classes("w-48")

            ui.button("Save Defaults", on_click=save_defaults).props("color=primary unelevated").classes("q-mt-md")

        # === Security ===
        with ui.card().classes("w-full q-mt-lg"):
            ui.label("Authentication & Access").classes("text-subtitle1 text-bold")
            ui.separator()

            security_vpn_duration = ui.select(
                VPN_SESSION_OPTIONS,
                value=config.vpn_session_duration,
                label="VPN Session Duration",
            ).props("outlined dense").classes("w-full")
            ui.label("How often users must re-authenticate to maintain VPN access.").classes("text-caption text-grey")

            ui.separator().classes("q-my-md")

            security_local_auth = ui.switch("Local Authentication (email/password)", value=config.local_auth_enabled)
            security_unpriv_mgmt = ui.switch("Allow Unprivileged Device Management", value=config.allow_unprivileged_device_management)
            security_unpriv_config = ui.switch("Allow Unprivileged Device Configuration", value=config.allow_unprivileged_device_configuration)

            ui.separator().classes("q-my-md")
            ui.label("SSO Behavior").classes("text-subtitle2")
            security_disable_vpn_oidc = ui.switch("Auto-disable VPN on OIDC refresh error", value=config.disable_vpn_on_oidc_error)

            ui.button("Save Security Settings", on_click=save_security).props("color=primary unelevated").classes("q-mt-md")

        # === Authentication (OIDC/SAML) ===
        with ui.card().classes("w-full q-mt-lg"):
            ui.label("OpenID Connect Providers").classes("text-subtitle1 text-bold")
            ui.separator()

            oidc_columns = [
                {"name": "id", "label": "Config ID", "field": "id", "align": "left"},
                {"name": "label", "label": "Label", "field": "label", "align": "left"},
                {"name": "client_id", "label": "Client ID", "field": "client_id", "align": "left"},
                {"name": "discovery", "label": "Discovery URI", "field": "discovery", "align": "left"},
                {"name": "auto_create", "label": "Auto-create", "field": "auto_create", "align": "center"},
                {"name": "actions", "label": "", "field": "id", "align": "center"},
            ]
            oidc_table = ui.table(columns=oidc_columns, rows=[], row_key="id").classes("w-full")
            oidc_table.add_slot(
                "body-cell-actions",
                '''
                <q-td :props="props">
                    <q-btn flat dense icon="delete" color="negative"
                           @click.stop="() => $parent.$emit('delete', props.row.id)" />
                </q-td>
                ''',
            )
            oidc_table.on("delete", lambda e: delete_oidc_provider(e.args))

            ui.button("Add OIDC Provider", icon="add", on_click=lambda: oidc_dialog.open()).props("color=primary unelevated").classes("q-mt-sm")

        with ui.card().classes("w-full q-mt-lg"):
            ui.label("SAML Identity Providers").classes("text-subtitle1 text-bold")
            ui.separator()

            saml_columns = [
                {"name": "id", "label": "Config ID", "field": "id", "align": "left"},
                {"name": "label", "label": "Label", "field": "label", "align": "left"},
                {"name": "metadata", "label": "Metadata", "field": "metadata", "align": "left"},
                {"name": "auto_create", "label": "Auto-create", "field": "auto_create", "align": "center"},
                {"name": "actions", "label": "", "field": "id", "align": "center"},
            ]
            saml_table = ui.table(columns=saml_columns, rows=[], row_key="id").classes("w-full")
            saml_table.add_slot(
                "body-cell-actions",
                '''
                <q-td :props="props">
                    <q-btn flat dense icon="delete" color="negative"
                           @click.stop="() => $parent.$emit('delete', props.row.id)" />
                </q-td>
                ''',
            )
            saml_table.on("delete", lambda e: delete_saml_provider(e.args))

            ui.button("Add SAML Provider", icon="add", on_click=lambda: saml_dialog.open()).props("color=primary unelevated").classes("q-mt-sm")

    # --- SAML provider management ---
    async def save_saml_provider():
        provider = {
            "id": saml_id.value.strip(),
            "label": saml_label.value.strip(),
            "metadata": saml_metadata_input.value.strip(),
            "base_url": f"{get_settings().external_url}/auth/saml",
            "sign_requests": saml_sign_requests.value,
            "sign_metadata": saml_sign_metadata.value,
            "signed_assertion_in_resp": saml_signed_assertion.value,
            "signed_envelopes_in_resp": saml_signed_envelopes.value,
            "auto_create_users": saml_auto_create.value,
        }
        if not all([provider["id"], provider["label"], provider["metadata"]]):
            ui.notify("Config ID, Label, and Metadata are required", type="negative")
            return

        async with async_session() as session:
            c = await session.get(Configuration, config.id)
            providers = list(c.saml_identity_providers or [])
            providers = [p for p in providers if p.get("id") != provider["id"]]
            providers.append(provider)
            c.saml_identity_providers = providers
            c.updated_at = utcnow()
            session.add(c)
            await session.commit()

        logger.info("SAML provider saved: {}", provider["id"])
        ui.notify(f"SAML provider '{provider['label']}' saved", type="positive")
        saml_dialog.close()
        await refresh_saml_table()

    async def delete_saml_provider(provider_id: str):
        async with async_session() as session:
            c = await session.get(Configuration, config.id)
            c.saml_identity_providers = [p for p in (c.saml_identity_providers or []) if p.get("id") != provider_id]
            c.updated_at = utcnow()
            session.add(c)
            await session.commit()
        logger.info("SAML provider deleted: {}", provider_id)
        ui.notify("SAML provider deleted")
        await refresh_saml_table()

    async def refresh_saml_table():
        async with async_session() as session:
            c = await session.get(Configuration, config.id)
            providers = c.saml_identity_providers or []
        saml_table.rows = [
            {
                "id": p.get("id", ""),
                "label": p.get("label", ""),
                "metadata": (p.get("metadata", ""))[:40] + "..." if len(p.get("metadata", "")) > 40 else p.get("metadata", ""),
                "auto_create": "Yes" if p.get("auto_create_users") else "No",
            }
            for p in providers
        ]
        saml_table.update()

    # --- OIDC provider dialog ---
    with ui.dialog() as oidc_dialog:
        with ui.card().classes("w-[500px]"):
            ui.label("OIDC Provider").classes("text-h6")
            oidc_id = ui.input("Config ID", placeholder="google").props("outlined dense").classes("w-full")
            oidc_label = ui.input("Label", placeholder="Sign in with Google").props("outlined dense").classes("w-full")
            oidc_scope = ui.input("Scope", value="openid email profile").props("outlined dense").classes("w-full")
            oidc_client_id = ui.input("Client ID").props("outlined dense").classes("w-full")
            oidc_client_secret = ui.input("Client Secret", password=True, password_toggle_button=True).props("outlined dense").classes("w-full")
            oidc_discovery = ui.input("Discovery Document URI", placeholder="https://accounts.google.com/.well-known/openid-configuration").props("outlined dense").classes("w-full")
            oidc_auto_create = ui.switch("Auto-create users", value=False)

            with ui.row().classes("w-full justify-end q-mt-sm"):
                ui.button("Cancel", on_click=oidc_dialog.close).props("flat")
                ui.button("Save", on_click=save_oidc_provider).props("color=primary")

    # --- SAML provider dialog ---
    with ui.dialog() as saml_dialog:
        with ui.card().classes("w-[500px]"):
            ui.label("SAML Identity Provider").classes("text-h6")
            saml_id = ui.input("Config ID", placeholder="okta-saml").props("outlined dense").classes("w-full")
            saml_label = ui.input("Label", placeholder="Sign in with Okta").props("outlined dense").classes("w-full")
            saml_metadata_input = ui.textarea("IdP Metadata (XML)").props("outlined").classes("w-full").style("min-height: 120px")
            ui.label("Paste the full XML metadata from your identity provider.").classes("text-caption text-grey")

            ui.separator().classes("q-my-sm")
            ui.label("Security Options").classes("text-subtitle2")
            saml_sign_requests = ui.switch("Sign authentication requests", value=True)
            saml_sign_metadata = ui.switch("Sign SP metadata", value=True)
            saml_signed_assertion = ui.switch("Require signed assertions in response", value=True)
            saml_signed_envelopes = ui.switch("Require signed envelopes in response", value=True)

            ui.separator().classes("q-my-sm")
            saml_auto_create = ui.switch("Auto-create users", value=False)

            with ui.row().classes("w-full justify-end q-mt-sm"):
                ui.button("Cancel", on_click=saml_dialog.close).props("flat")
                ui.button("Save", on_click=save_saml_provider).props("color=primary")

    await refresh_oidc_table()
    await refresh_saml_table()
