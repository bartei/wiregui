"""User-facing device management pages."""

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
from wiregui.pages.layout import layout
from wiregui.services.events import on_device_created, on_device_deleted, on_device_updated
from wiregui.utils.crypto import generate_keypair, generate_preshared_key
from wiregui.utils.network import allocate_ipv4, allocate_ipv6
from wiregui.utils.server_key import get_server_public_key
from wiregui.utils.wg_conf import build_client_config


def _format_bytes(b: int | None) -> str:
    if b is None:
        return "-"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} PB"


@ui.page("/devices")
async def devices_page():
    if not app.storage.user.get("authenticated"):
        return ui.navigate.to("/login")

    layout()
    user_id = UUID(app.storage.user["user_id"])

    async def load_devices() -> list[Device]:
        async with async_session() as session:
            result = await session.execute(
                select(Device).where(Device.user_id == user_id).order_by(Device.inserted_at.desc())
            )
            return list(result.scalars().all())

    async def refresh_table():
        devices = await load_devices()
        table.rows = [
            {
                "id": str(d.id),
                "name": d.name,
                "description": d.description or "",
                "ipv4": d.ipv4 or "-",
                "ipv6": d.ipv6 or "-",
                "public_key": d.public_key[:16] + "...",
                "rx": _format_bytes(d.rx_bytes),
                "tx": _format_bytes(d.tx_bytes),
                "handshake": str(d.latest_handshake)[:19] if d.latest_handshake else "-",
            }
            for d in devices
        ]
        table.update()

    # --- Create device ---
    async def create_device():
        name = create_name.value.strip()
        if not name:
            ui.notify("Device name is required", type="negative")
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
                    user_id=user_id,
                    use_default_allowed_ips=create_use_default_ips.value,
                    use_default_dns=create_use_default_dns.value,
                    use_default_endpoint=create_use_default_endpoint.value,
                    use_default_mtu=create_use_default_mtu.value,
                    use_default_persistent_keepalive=create_use_default_keepalive.value,
                    endpoint=(create_endpoint.value.strip() or None
                              if not create_use_default_endpoint.value else None),
                    dns=([s.strip() for s in create_dns.value.split(",") if s.strip()]
                         if not create_use_default_dns.value and create_dns.value else []),
                    mtu=(int(create_mtu.value)
                         if not create_use_default_mtu.value and create_mtu.value else None),
                    persistent_keepalive=(int(create_keepalive.value)
                                         if not create_use_default_keepalive.value and create_keepalive.value else None),
                    allowed_ips=([s.strip() for s in create_allowed_ips.value.split(",") if s.strip()]
                                 if not create_use_default_ips.value and create_allowed_ips.value else []),
                )
                session.add(device)
                await session.commit()
                await session.refresh(device)

            logger.info("Device created: {} ({})", device.name, device.ipv4)
            await on_device_created(device)

            server_pubkey = await get_server_public_key()
            config_text = build_client_config(device, private_key, server_pubkey)
            _show_config_dialog(device.name, config_text)

            create_dialog.close()
            _reset_create_form()
            await refresh_table()

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
        create_endpoint.value = ""
        create_dns.value = ""
        create_mtu.value = ""
        create_keepalive.value = ""
        create_allowed_ips.value = ""

    # --- Delete device ---
    async def delete_device(device_id: str):
        async with async_session() as session:
            device = await session.get(Device, UUID(device_id))
            if device and device.user_id == user_id:
                await session.delete(device)
                await session.commit()
                logger.info("Device deleted: {}", device.name)
                await on_device_deleted(device)
                ui.notify(f"Deleted {device.name}")
        await refresh_table()

    def on_row_click(e):
        ui.navigate.to(f"/devices/{e.args['id']}")

    # --- Page content ---
    with ui.column().classes("w-full p-4"):
        with ui.row().classes("w-full items-center justify-between"):
            ui.label("My Devices").classes("text-h5")
            ui.button("Add Device", icon="add", on_click=lambda: create_dialog.open()).props("color=primary")

        columns = [
            {"name": "name", "label": "Name", "field": "name", "align": "left", "sortable": True},
            {"name": "ipv4", "label": "IPv4", "field": "ipv4", "align": "left"},
            {"name": "ipv6", "label": "IPv6", "field": "ipv6", "align": "left"},
            {"name": "public_key", "label": "Public Key", "field": "public_key", "align": "left"},
            {"name": "rx", "label": "RX", "field": "rx", "align": "right"},
            {"name": "tx", "label": "TX", "field": "tx", "align": "right"},
            {"name": "handshake", "label": "Last Handshake", "field": "handshake", "align": "left"},
            {"name": "actions", "label": "", "field": "id", "align": "center"},
        ]
        table = ui.table(columns=columns, rows=[], row_key="id").classes("w-full")
        table.on("rowClick", on_row_click)
        table.add_slot(
            "body-cell-actions",
            '''
            <q-td :props="props">
                <q-btn flat dense icon="delete" color="negative"
                       @click.stop="() => $parent.$emit('delete', props.row.id)" />
            </q-td>
            ''',
        )
        table.on("delete", lambda e: delete_device(e.args))

    # --- Create device dialog (full form) ---
    with ui.dialog() as create_dialog:
        with ui.card().classes("w-[600px]"):
            ui.label("New Device").classes("text-h6")

            create_name = ui.input("Device Name").props("outlined dense").classes("w-full")
            create_desc = ui.input("Description (optional)").props("outlined dense").classes("w-full")

            ui.separator().classes("q-my-sm")
            ui.label("Configuration Overrides").classes("text-subtitle2")
            ui.label("Toggle off to set custom values instead of server defaults.").classes("text-caption text-grey-7")

            with ui.grid(columns=2).classes("w-full gap-2"):
                create_use_default_ips = ui.switch("Use default Allowed IPs", value=True)
                create_allowed_ips = ui.input("Allowed IPs", placeholder="0.0.0.0/0, ::/0").props(
                    "outlined dense"
                ).classes("w-full").bind_enabled_from(create_use_default_ips, "value", backward=lambda v: not v)

                create_use_default_dns = ui.switch("Use default DNS", value=True)
                create_dns = ui.input("DNS Servers", placeholder="1.1.1.1, 1.0.0.1").props(
                    "outlined dense"
                ).classes("w-full").bind_enabled_from(create_use_default_dns, "value", backward=lambda v: not v)

                create_use_default_endpoint = ui.switch("Use default Endpoint", value=True)
                create_endpoint = ui.input("Endpoint", placeholder="vpn.example.com").props(
                    "outlined dense"
                ).classes("w-full").bind_enabled_from(create_use_default_endpoint, "value", backward=lambda v: not v)

                create_use_default_mtu = ui.switch("Use default MTU", value=True)
                create_mtu = ui.input("MTU", placeholder="1280").props(
                    "outlined dense"
                ).classes("w-full").bind_enabled_from(create_use_default_mtu, "value", backward=lambda v: not v)

                create_use_default_keepalive = ui.switch("Use default Keepalive", value=True)
                create_keepalive = ui.input("Persistent Keepalive", placeholder="25").props(
                    "outlined dense"
                ).classes("w-full").bind_enabled_from(create_use_default_keepalive, "value", backward=lambda v: not v)

            with ui.row().classes("w-full justify-end q-mt-md"):
                ui.button("Cancel", on_click=create_dialog.close).props("flat")
                ui.button("Create", on_click=create_device).props("color=primary")

    await refresh_table()

    # Auto-refresh stats every 30 seconds
    ui.timer(30, refresh_table)


@ui.page("/devices/{device_id}")
async def device_detail_page(device_id: str):
    if not app.storage.user.get("authenticated"):
        return ui.navigate.to("/login")

    layout()
    user_id = UUID(app.storage.user["user_id"])

    async with async_session() as sess:
        device = await sess.get(Device, UUID(device_id))
        if not device or device.user_id != user_id:
            ui.label("Device not found").classes("text-h5 text-negative p-4")
            return

    # --- Edit handlers ---
    async def save_edit():
        async with async_session() as session:
            d = await session.get(Device, UUID(device_id))
            if not d:
                return

            d.name = edit_name.value.strip()
            d.description = edit_desc.value.strip() or None
            d.use_default_allowed_ips = edit_use_default_ips.value
            d.use_default_dns = edit_use_default_dns.value
            d.use_default_endpoint = edit_use_default_endpoint.value
            d.use_default_mtu = edit_use_default_mtu.value
            d.use_default_persistent_keepalive = edit_use_default_keepalive.value

            if not d.use_default_endpoint:
                d.endpoint = edit_endpoint.value.strip() or None
            if not d.use_default_dns:
                d.dns = [s.strip() for s in edit_dns.value.split(",") if s.strip()]
            if not d.use_default_mtu:
                d.mtu = int(edit_mtu.value) if edit_mtu.value else None
            if not d.use_default_persistent_keepalive:
                d.persistent_keepalive = int(edit_keepalive.value) if edit_keepalive.value else None
            if not d.use_default_allowed_ips:
                d.allowed_ips = [s.strip() for s in edit_allowed_ips.value.split(",") if s.strip()]

            session.add(d)
            await session.commit()
            await session.refresh(d)
            await on_device_updated(d)

        logger.info("Device updated: {}", edit_name.value)
        ui.notify("Device updated", type="positive")
        ui.navigate.to(f"/devices/{device_id}")

    async def delete_and_redirect():
        async with async_session() as session:
            d = await session.get(Device, UUID(device_id))
            if d:
                await session.delete(d)
                await session.commit()
                logger.info("Device deleted: {}", d.name)
                await on_device_deleted(d)
        ui.navigate.to("/devices")

    settings = get_settings()

    # --- Page content ---
    with ui.column().classes("w-full p-4"):
        with ui.row().classes("items-center gap-2"):
            ui.button(icon="arrow_back", on_click=lambda: ui.navigate.to("/devices")).props("flat")
            ui.label(device.name).classes("text-h5")
            if device.description:
                ui.label(f"— {device.description}").classes("text-subtitle1 text-grey-7")

        # Device info card
        with ui.card().classes("w-full q-mt-md"):
            ui.label("Device Details").classes("text-subtitle1 text-bold")
            ui.separator()
            with ui.grid(columns=2).classes("w-full gap-2 q-pa-sm"):
                ui.label("Public Key:").classes("text-bold")
                ui.label(device.public_key).classes("font-mono text-sm")

                ui.label("IPv4:").classes("text-bold")
                ui.label(device.ipv4 or "-")

                ui.label("IPv6:").classes("text-bold")
                ui.label(device.ipv6 or "-")

                ui.label("Created:").classes("text-bold")
                ui.label(str(device.inserted_at)[:19])

        # Traffic stats (live-updating)
        with ui.card().classes("w-full q-mt-md"):
            ui.label("Traffic Stats").classes("text-subtitle1 text-bold")
            ui.label("Auto-refreshes every 30s").classes("text-caption text-grey-7")
            ui.separator()
            with ui.grid(columns=2).classes("w-full gap-2 q-pa-sm"):
                ui.label("RX:").classes("text-bold")
                stat_rx = ui.label(_format_bytes(device.rx_bytes))

                ui.label("TX:").classes("text-bold")
                stat_tx = ui.label(_format_bytes(device.tx_bytes))

                ui.label("Last Handshake:").classes("text-bold")
                stat_handshake = ui.label(str(device.latest_handshake)[:19] if device.latest_handshake else "-")

                ui.label("Remote IP:").classes("text-bold")
                stat_remote = ui.label(device.remote_ip or "-")

        async def refresh_stats():
            async with async_session() as session:
                d = await session.get(Device, UUID(device_id))
                if not d:
                    return
                stat_rx.text = _format_bytes(d.rx_bytes)
                stat_tx.text = _format_bytes(d.tx_bytes)
                stat_handshake.text = str(d.latest_handshake)[:19] if d.latest_handshake else "-"
                stat_remote.text = d.remote_ip or "-"

        ui.timer(30, refresh_stats)

        # Active configuration
        with ui.card().classes("w-full q-mt-md"):
            ui.label("Active Configuration").classes("text-subtitle1 text-bold")
            ui.separator()
            with ui.grid(columns=2).classes("w-full gap-2 q-pa-sm"):
                _ips = device.allowed_ips if not device.use_default_allowed_ips else settings.wg_allowed_ips
                ui.label("Allowed IPs:").classes("text-bold")
                ui.label(str(_ips) if isinstance(_ips, str) else ", ".join(_ips) if _ips else "-")

                _dns = device.dns if not device.use_default_dns else settings.wg_dns
                ui.label("DNS:").classes("text-bold")
                ui.label(str(_dns) if isinstance(_dns, str) else ", ".join(_dns) if _dns else "-")

                _ep = device.endpoint if not device.use_default_endpoint else settings.wg_endpoint_host
                ui.label("Endpoint:").classes("text-bold")
                ui.label(f"{_ep}:{settings.wg_endpoint_port}" if _ep else "-")

                _mtu = device.mtu if not device.use_default_mtu else settings.wg_mtu
                ui.label("MTU:").classes("text-bold")
                ui.label(str(_mtu) if _mtu else "-")

                _ka = device.persistent_keepalive if not device.use_default_persistent_keepalive else settings.wg_persistent_keepalive
                ui.label("Persistent Keepalive:").classes("text-bold")
                ui.label(str(_ka) if _ka else "-")

        # Edit form
        with ui.card().classes("w-full q-mt-md"):
            ui.label("Edit Device").classes("text-subtitle1 text-bold")
            ui.separator()

            edit_name = ui.input("Device Name", value=device.name).props("outlined dense").classes("w-full")
            edit_desc = ui.input("Description", value=device.description or "").props("outlined dense").classes("w-full")

            ui.separator().classes("q-my-sm")
            ui.label("Configuration Overrides").classes("text-subtitle2")

            with ui.grid(columns=2).classes("w-full gap-2"):
                edit_use_default_ips = ui.switch("Use default Allowed IPs", value=device.use_default_allowed_ips)
                edit_allowed_ips = ui.input(
                    "Allowed IPs", value=", ".join(device.allowed_ips) if device.allowed_ips else "",
                ).props("outlined dense").classes("w-full").bind_enabled_from(
                    edit_use_default_ips, "value", backward=lambda v: not v
                )

                edit_use_default_dns = ui.switch("Use default DNS", value=device.use_default_dns)
                edit_dns = ui.input(
                    "DNS Servers", value=", ".join(device.dns) if device.dns else "",
                ).props("outlined dense").classes("w-full").bind_enabled_from(
                    edit_use_default_dns, "value", backward=lambda v: not v
                )

                edit_use_default_endpoint = ui.switch("Use default Endpoint", value=device.use_default_endpoint)
                edit_endpoint = ui.input(
                    "Endpoint", value=device.endpoint or "",
                ).props("outlined dense").classes("w-full").bind_enabled_from(
                    edit_use_default_endpoint, "value", backward=lambda v: not v
                )

                edit_use_default_mtu = ui.switch("Use default MTU", value=device.use_default_mtu)
                edit_mtu = ui.input(
                    "MTU", value=str(device.mtu) if device.mtu else "",
                ).props("outlined dense").classes("w-full").bind_enabled_from(
                    edit_use_default_mtu, "value", backward=lambda v: not v
                )

                edit_use_default_keepalive = ui.switch("Use default Keepalive", value=device.use_default_persistent_keepalive)
                edit_keepalive = ui.input(
                    "Persistent Keepalive", value=str(device.persistent_keepalive) if device.persistent_keepalive else "",
                ).props("outlined dense").classes("w-full").bind_enabled_from(
                    edit_use_default_keepalive, "value", backward=lambda v: not v
                )

            ui.button("Save Changes", on_click=save_edit).props("color=primary").classes("q-mt-md")

        # Danger zone
        with ui.card().classes("w-full q-mt-md"):
            ui.label("Danger Zone").classes("text-subtitle1 text-bold text-negative")
            ui.separator()
            ui.button("Delete Device", icon="delete", on_click=lambda: confirm_dialog.open()).props(
                "color=negative outline"
            )

    # Confirm delete dialog
    with ui.dialog() as confirm_dialog:
        with ui.card().classes("w-80"):
            ui.label("Delete Device?").classes("text-h6")
            ui.label(f"This will permanently remove '{device.name}' and its WireGuard peer.").classes("text-body2")
            with ui.row().classes("w-full justify-end q-mt-sm"):
                ui.button("Cancel", on_click=confirm_dialog.close).props("flat")
                ui.button("Delete", on_click=delete_and_redirect).props("color=negative")


def _show_config_dialog(device_name: str, config_text: str):
    """Show a dialog with the WireGuard client configuration and QR code."""
    with ui.dialog(value=True) as dialog:
        with ui.card().classes("w-96"):
            ui.label(f"Config for {device_name}").classes("text-h6")
            ui.label("Save this — the private key won't be shown again.").classes("text-caption text-negative")

            ui.textarea(value=config_text).props("readonly outlined").classes(
                "w-full font-mono text-xs q-mt-sm"
            ).style("min-height: 200px")

            try:
                qr = qrcode.make(config_text, image_factory=qrcode.image.svg.SvgPathImage)
                buf = io.BytesIO()
                qr.save(buf)
                ui.html(buf.getvalue().decode()).classes("w-full q-mt-sm")
            except Exception:
                ui.label("QR code generation failed").classes("text-caption text-grey")

            ui.button(
                "Download .conf",
                on_click=lambda: ui.download(config_text.encode(), f"{device_name}.conf"),
            ).props("color=primary outline").classes("w-full q-mt-sm")

            ui.button("Close", on_click=dialog.close).props("flat").classes("w-full")
