"""Admin device management — view and manage all devices across all users."""

import io
from uuid import UUID

import qrcode
import qrcode.image.svg
from loguru import logger
from nicegui import app, ui
from sqlmodel import select

from wiregui.config import get_settings
from wiregui.db import async_session
from wiregui.models.device import Device
from wiregui.models.user import User
from wiregui.pages.layout import layout
from wiregui.services.events import on_device_created, on_device_deleted, on_device_updated
from wiregui.utils.crypto import generate_keypair, generate_preshared_key
from wiregui.utils.network import allocate_ipv4, allocate_ipv6
from wiregui.utils.server_key import get_server_public_key
from wiregui.utils.wg_conf import build_client_config


def _guard():
    if not app.storage.user.get("authenticated") or app.storage.user.get("role") != "admin":
        ui.navigate.to("/login")
        return False
    return True


def _format_bytes(b: int | None) -> str:
    if b is None:
        return "-"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} PB"


@ui.page("/admin/devices")
async def admin_devices_page():
    if not _guard():
        return

    layout()

    # Load users for filter and create form
    async with async_session() as session:
        users = (await session.execute(select(User).order_by(User.email))).scalars().all()
    user_map = {str(u.id): u.email for u in users}

    async def load_devices(user_filter: str | None = None) -> list[dict]:
        async with async_session() as session:
            stmt = select(Device).order_by(Device.inserted_at.desc())
            if user_filter and user_filter != "all":
                stmt = stmt.where(Device.user_id == UUID(user_filter))
            result = await session.execute(stmt)
            return [
                {
                    "id": str(d.id),
                    "name": d.name,
                    "user": user_map.get(str(d.user_id), "Unknown"),
                    "ipv4": d.ipv4 or "-",
                    "ipv6": d.ipv6 or "-",
                    "public_key": d.public_key[:16] + "...",
                    "rx": _format_bytes(d.rx_bytes),
                    "tx": _format_bytes(d.tx_bytes),
                    "handshake": str(d.latest_handshake)[:19] if d.latest_handshake else "-",
                }
                for d in result.scalars().all()
            ]

    async def refresh_table():
        table.rows = await load_devices(user_filter_select.value)
        table.update()

    async def on_filter_change():
        await refresh_table()

    # --- Create device ---
    async def create_device():
        name = create_name.value.strip()
        owner_id = create_user_select.value
        if not name or not owner_id:
            ui.notify("Name and user are required", type="negative")
            return

        try:
            settings = get_settings()
            private_key, public_key = generate_keypair()
            psk = generate_preshared_key()

            async with async_session() as session:
                ipv4 = await allocate_ipv4(session, settings.wg_ipv4_network)
                ipv6 = await allocate_ipv6(session, settings.wg_ipv6_network)

                device = Device(
                    name=name,
                    description=create_desc.value.strip() or None,
                    public_key=public_key,
                    preshared_key=psk,
                    ipv4=ipv4,
                    ipv6=ipv6,
                    user_id=UUID(owner_id),
                    # Apply config overrides if not using defaults
                    use_default_allowed_ips=create_use_default_ips.value,
                    use_default_dns=create_use_default_dns.value,
                    use_default_endpoint=create_use_default_endpoint.value,
                    use_default_mtu=create_use_default_mtu.value,
                    use_default_persistent_keepalive=create_use_default_keepalive.value,
                    endpoint=create_endpoint.value.strip() or None if not create_use_default_endpoint.value else None,
                    dns=([s.strip() for s in create_dns.value.split(",") if s.strip()]
                         if not create_use_default_dns.value and create_dns.value else []),
                    mtu=int(create_mtu.value) if not create_use_default_mtu.value and create_mtu.value else None,
                    persistent_keepalive=(int(create_keepalive.value)
                                         if not create_use_default_keepalive.value and create_keepalive.value else None),
                    allowed_ips=([s.strip() for s in create_allowed_ips.value.split(",") if s.strip()]
                                 if not create_use_default_ips.value and create_allowed_ips.value else []),
                )
                session.add(device)
                await session.commit()
                await session.refresh(device)

            logger.info("Admin created device: {} for {}", device.name, user_map.get(owner_id))
            await on_device_created(device)

            # Show config
            server_pubkey = await get_server_public_key()
            config_text = build_client_config(device, private_key, server_pubkey)

            create_dialog.close()
            _reset_create_form()
            await refresh_table()
            _show_config_dialog(device.name, config_text)
        except Exception as e:
            logger.error("Failed to create device: {}", e)
            ui.notify(f"Error: {e}", type="negative")

    def _reset_create_form():
        create_name.value = ""
        create_desc.value = ""
        create_use_default_ips.value = True
        create_use_default_dns.value = True
        create_use_default_endpoint.value = True
        create_use_default_mtu.value = True
        create_use_default_keepalive.value = True

    # --- Edit device ---
    edit_device_id = {"value": None}

    async def open_edit(device_id: str):
        async with async_session() as session:
            device = await session.get(Device, UUID(device_id))
            if not device:
                return

        edit_device_id["value"] = device_id
        edit_name.value = device.name
        edit_desc.value = device.description or ""
        edit_use_default_ips.value = device.use_default_allowed_ips
        edit_use_default_dns.value = device.use_default_dns
        edit_use_default_endpoint.value = device.use_default_endpoint
        edit_use_default_mtu.value = device.use_default_mtu
        edit_use_default_keepalive.value = device.use_default_persistent_keepalive
        edit_endpoint.value = device.endpoint or ""
        edit_dns.value = ", ".join(device.dns) if device.dns else ""
        edit_mtu.value = str(device.mtu) if device.mtu else ""
        edit_keepalive.value = str(device.persistent_keepalive) if device.persistent_keepalive else ""
        edit_allowed_ips.value = ", ".join(device.allowed_ips) if device.allowed_ips else ""
        edit_dialog.open()

    async def save_edit():
        did = edit_device_id["value"]
        if not did:
            return

        async with async_session() as session:
            device = await session.get(Device, UUID(did))
            if not device:
                return

            device.name = edit_name.value.strip()
            device.description = edit_desc.value.strip() or None
            device.use_default_allowed_ips = edit_use_default_ips.value
            device.use_default_dns = edit_use_default_dns.value
            device.use_default_endpoint = edit_use_default_endpoint.value
            device.use_default_mtu = edit_use_default_mtu.value
            device.use_default_persistent_keepalive = edit_use_default_keepalive.value

            if not device.use_default_endpoint:
                device.endpoint = edit_endpoint.value.strip() or None
            if not device.use_default_dns:
                device.dns = [s.strip() for s in edit_dns.value.split(",") if s.strip()]
            if not device.use_default_mtu:
                device.mtu = int(edit_mtu.value) if edit_mtu.value else None
            if not device.use_default_persistent_keepalive:
                device.persistent_keepalive = int(edit_keepalive.value) if edit_keepalive.value else None
            if not device.use_default_allowed_ips:
                device.allowed_ips = [s.strip() for s in edit_allowed_ips.value.split(",") if s.strip()]

            session.add(device)
            await session.commit()
            await session.refresh(device)
            await on_device_updated(device)

        logger.info("Admin updated device: {}", edit_name.value)
        ui.notify("Device updated")
        edit_dialog.close()
        await refresh_table()

    # --- Delete device ---
    async def delete_device(device_id: str):
        async with async_session() as session:
            device = await session.get(Device, UUID(device_id))
            if device:
                await session.delete(device)
                await session.commit()
                logger.info("Admin deleted device: {}", device.name)
                await on_device_deleted(device)
                ui.notify(f"Deleted {device.name}")
        await refresh_table()

    # --- Page content ---
    with ui.column().classes("w-full p-4"):
        with ui.row().classes("w-full items-center justify-between"):
            ui.label("All Devices").classes("text-h5")
            with ui.row().classes("items-center gap-4"):
                filter_options = {"all": "All Users"}
                filter_options.update(user_map)
                user_filter_select = ui.select(
                    filter_options, value="all", label="Filter by User",
                    on_change=lambda: on_filter_change(),
                ).props("outlined dense").classes("w-48")
                ui.button("Add Device", icon="add", on_click=lambda: create_dialog.open()).props("color=primary")

        columns = [
            {"name": "name", "label": "Name", "field": "name", "align": "left", "sortable": True},
            {"name": "user", "label": "User", "field": "user", "align": "left", "sortable": True},
            {"name": "ipv4", "label": "IPv4", "field": "ipv4", "align": "left"},
            {"name": "ipv6", "label": "IPv6", "field": "ipv6", "align": "left"},
            {"name": "public_key", "label": "Public Key", "field": "public_key", "align": "left"},
            {"name": "rx", "label": "RX", "field": "rx", "align": "right"},
            {"name": "tx", "label": "TX", "field": "tx", "align": "right"},
            {"name": "handshake", "label": "Last Handshake", "field": "handshake", "align": "left"},
            {"name": "actions", "label": "", "field": "id", "align": "center"},
        ]
        table = ui.table(columns=columns, rows=[], row_key="id").classes("w-full")
        table.add_slot(
            "body-cell-actions",
            '''
            <q-td :props="props">
                <q-btn flat dense icon="edit" color="primary"
                       @click.stop="() => $parent.$emit('edit', props.row.id)" />
                <q-btn flat dense icon="delete" color="negative"
                       @click.stop="() => $parent.$emit('delete', props.row.id)" />
            </q-td>
            ''',
        )
        table.on("edit", lambda e: open_edit(e.args))
        table.on("delete", lambda e: delete_device(e.args))

    # --- Create dialog (full form) ---
    with ui.dialog() as create_dialog:
        with ui.card().classes("w-[600px]"):
            ui.label("New Device").classes("text-h6")

            create_user_select = ui.select(
                user_map, value=list(user_map.keys())[0] if user_map else None,
                label="Owner",
            ).props("outlined dense").classes("w-full")

            create_name = ui.input("Device Name").props("outlined dense").classes("w-full")
            create_desc = ui.input("Description (optional)").props("outlined dense").classes("w-full")

            ui.separator().classes("q-my-sm")
            ui.label("Configuration Overrides").classes("text-subtitle2")

            with ui.grid(columns=2).classes("w-full gap-2"):
                create_use_default_ips = ui.switch("Use default Allowed IPs", value=True)
                create_allowed_ips = ui.input("Allowed IPs", placeholder="0.0.0.0/0, ::/0").props("outlined dense").classes("w-full").bind_enabled_from(create_use_default_ips, "value", backward=lambda v: not v)

                create_use_default_dns = ui.switch("Use default DNS", value=True)
                create_dns = ui.input("DNS Servers", placeholder="1.1.1.1, 1.0.0.1").props("outlined dense").classes("w-full").bind_enabled_from(create_use_default_dns, "value", backward=lambda v: not v)

                create_use_default_endpoint = ui.switch("Use default Endpoint", value=True)
                create_endpoint = ui.input("Endpoint", placeholder="vpn.example.com").props("outlined dense").classes("w-full").bind_enabled_from(create_use_default_endpoint, "value", backward=lambda v: not v)

                create_use_default_mtu = ui.switch("Use default MTU", value=True)
                create_mtu = ui.input("MTU", placeholder="1280").props("outlined dense").classes("w-full").bind_enabled_from(create_use_default_mtu, "value", backward=lambda v: not v)

                create_use_default_keepalive = ui.switch("Use default Keepalive", value=True)
                create_keepalive = ui.input("Persistent Keepalive", placeholder="25").props("outlined dense").classes("w-full").bind_enabled_from(create_use_default_keepalive, "value", backward=lambda v: not v)

            with ui.row().classes("w-full justify-end q-mt-sm"):
                ui.button("Cancel", on_click=create_dialog.close).props("flat")
                ui.button("Create", on_click=create_device).props("color=primary")

    # --- Edit dialog (full form) ---
    with ui.dialog() as edit_dialog:
        with ui.card().classes("w-[600px]"):
            ui.label("Edit Device").classes("text-h6")

            edit_name = ui.input("Device Name").props("outlined dense").classes("w-full")
            edit_desc = ui.input("Description").props("outlined dense").classes("w-full")

            ui.separator().classes("q-my-sm")
            ui.label("Configuration Overrides").classes("text-subtitle2")

            with ui.grid(columns=2).classes("w-full gap-2"):
                edit_use_default_ips = ui.switch("Use default Allowed IPs", value=True)
                edit_allowed_ips = ui.input("Allowed IPs").props("outlined dense").classes("w-full").bind_enabled_from(edit_use_default_ips, "value", backward=lambda v: not v)

                edit_use_default_dns = ui.switch("Use default DNS", value=True)
                edit_dns = ui.input("DNS Servers").props("outlined dense").classes("w-full").bind_enabled_from(edit_use_default_dns, "value", backward=lambda v: not v)

                edit_use_default_endpoint = ui.switch("Use default Endpoint", value=True)
                edit_endpoint = ui.input("Endpoint").props("outlined dense").classes("w-full").bind_enabled_from(edit_use_default_endpoint, "value", backward=lambda v: not v)

                edit_use_default_mtu = ui.switch("Use default MTU", value=True)
                edit_mtu = ui.input("MTU").props("outlined dense").classes("w-full").bind_enabled_from(edit_use_default_mtu, "value", backward=lambda v: not v)

                edit_use_default_keepalive = ui.switch("Use default Keepalive", value=True)
                edit_keepalive = ui.input("Persistent Keepalive").props("outlined dense").classes("w-full").bind_enabled_from(edit_use_default_keepalive, "value", backward=lambda v: not v)

            with ui.row().classes("w-full justify-end q-mt-sm"):
                ui.button("Cancel", on_click=edit_dialog.close).props("flat")
                ui.button("Save", on_click=save_edit).props("color=primary")

    await refresh_table()

    # Auto-refresh stats every 30 seconds
    ui.timer(30, refresh_table)


def _show_config_dialog(device_name: str, config_text: str):
    with ui.dialog(value=True) as dialog:
        with ui.card().classes("w-96"):
            ui.label(f"Config for {device_name}").classes("text-h6")
            ui.label("Save this — the private key won't be shown again.").classes("text-caption text-negative")
            ui.textarea(value=config_text).props("readonly outlined").classes("w-full font-mono text-xs q-mt-sm").style("min-height: 200px")
            try:
                qr = qrcode.make(config_text, image_factory=qrcode.image.svg.SvgPathImage)
                buf = io.BytesIO()
                qr.save(buf)
                ui.html(buf.getvalue().decode()).classes("w-full q-mt-sm")
            except Exception:
                pass
            ui.button("Download .conf", on_click=lambda: ui.download(config_text.encode(), f"{device_name}.conf")).props("color=primary unelevated").classes("w-full q-mt-sm")
            ui.button("Close", on_click=dialog.close).props("flat").classes("w-full")
