"""Admin diagnostics page — connectivity checks, WG status, peer stats."""

from nicegui import app, ui
from sqlmodel import select

from wiregui.config import get_settings
from wiregui.db import async_session
from wiregui.models.connectivity_check import ConnectivityCheck
from wiregui.models.device import Device
from wiregui.pages.layout import layout
from wiregui.services import notifications


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


@ui.page("/admin/diagnostics")
async def diagnostics_page():
    if not _guard():
        return

    layout()
    settings = get_settings()

    with ui.column().classes("w-full p-4"):
        ui.label("Diagnostics").classes("text-h5 q-mb-md")

        # --- WireGuard Status ---
        with ui.card().classes("w-full"):
            ui.label("WireGuard Interface").classes("text-subtitle1 text-bold")
            ui.separator()

            with ui.grid(columns=2).classes("w-full gap-2 q-pa-sm"):
                ui.label("Interface:").classes("text-bold")
                ui.label(settings.wg_interface)

                ui.label("Status:").classes("text-bold")
                ui.label("Enabled" if settings.wg_enabled else "Disabled (UI-only mode)").classes(
                    "text-positive" if settings.wg_enabled else "text-warning"
                )

                ui.label("IPv4 Network:").classes("text-bold")
                ui.label(settings.wg_ipv4_network)

                ui.label("IPv6 Network:").classes("text-bold")
                ui.label(settings.wg_ipv6_network)

                ui.label("Endpoint:").classes("text-bold")
                ui.label(f"{settings.wg_endpoint_host}:{settings.wg_endpoint_port}")

        # --- Active Peers ---
        with ui.card().classes("w-full q-mt-md"):
            ui.label("Active Peers (from DB)").classes("text-subtitle1 text-bold")
            ui.separator()

            async with async_session() as session:
                result = await session.execute(
                    select(Device).where(Device.latest_handshake.is_not(None)).order_by(Device.latest_handshake.desc())
                )
                active_devices = result.scalars().all()

            if active_devices:
                peer_columns = [
                    {"name": "name", "label": "Name", "field": "name", "align": "left"},
                    {"name": "public_key", "label": "Public Key", "field": "public_key", "align": "left"},
                    {"name": "ipv4", "label": "IPv4", "field": "ipv4", "align": "left"},
                    {"name": "endpoint", "label": "Remote IP", "field": "endpoint", "align": "left"},
                    {"name": "handshake", "label": "Last Handshake", "field": "handshake", "align": "left"},
                    {"name": "rx", "label": "RX", "field": "rx", "align": "right"},
                    {"name": "tx", "label": "TX", "field": "tx", "align": "right"},
                ]
                peer_rows = [
                    {
                        "name": d.name,
                        "public_key": d.public_key[:16] + "...",
                        "ipv4": d.ipv4 or "-",
                        "endpoint": d.remote_ip or "-",
                        "handshake": str(d.latest_handshake)[:19] if d.latest_handshake else "-",
                        "rx": _format_bytes(d.rx_bytes),
                        "tx": _format_bytes(d.tx_bytes),
                    }
                    for d in active_devices
                ]
                ui.table(columns=peer_columns, rows=peer_rows, row_key="name").classes("w-full")
            else:
                ui.label("No active peers with recent handshakes.").classes("text-caption text-grey-7 q-pa-sm")

        # --- Connectivity Checks ---
        with ui.card().classes("w-full q-mt-md"):
            ui.label("WAN Connectivity Checks").classes("text-subtitle1 text-bold")
            ui.separator()

            async with async_session() as session:
                result = await session.execute(
                    select(ConnectivityCheck).order_by(ConnectivityCheck.inserted_at.desc()).limit(20)
                )
                checks = result.scalars().all()

            if checks:
                check_columns = [
                    {"name": "time", "label": "Checked At", "field": "time", "align": "left"},
                    {"name": "url", "label": "URL", "field": "url", "align": "left"},
                    {"name": "status", "label": "Status", "field": "status", "align": "center"},
                    {"name": "body", "label": "Response", "field": "body", "align": "left"},
                ]
                check_rows = [
                    {
                        "time": str(c.inserted_at)[:19],
                        "url": c.url,
                        "status": str(c.response_code or "Error"),
                        "body": (c.response_body or "")[:50],
                    }
                    for c in checks
                ]
                ui.table(columns=check_columns, rows=check_rows, row_key="time").classes("w-full")
            else:
                ui.label("No connectivity checks recorded yet.").classes("text-caption text-grey-7 q-pa-sm")

        # --- Notifications ---
        with ui.card().classes("w-full q-mt-md"):
            ui.label("System Notifications").classes("text-subtitle1 text-bold")
            ui.separator()

            notifs = notifications.current()
            if notifs:
                for n in notifs:
                    color = {"error": "negative", "warning": "warning", "info": "info"}.get(n.severity, "grey")
                    with ui.row().classes("w-full items-center q-pa-xs"):
                        ui.icon("error" if n.severity == "error" else "warning" if n.severity == "warning" else "info").props(f"color={color}")
                        ui.label(f"{n.timestamp.strftime('%H:%M:%S')} — {n.message}").classes("text-sm")
                        if n.user:
                            ui.label(f"({n.user})").classes("text-caption text-grey-7")
                        ui.button(icon="close", on_click=lambda nid=n.id: _clear_notif(nid)).props("flat dense size=xs")
            else:
                ui.label("No notifications.").classes("text-caption text-grey-7 q-pa-sm")

            if notifs:
                ui.button("Clear All", on_click=lambda: _clear_all_notifs()).props("flat color=negative").classes("q-mt-sm")


def _clear_notif(nid: str):
    notifications.clear(nid)
    ui.navigate.to("/admin/diagnostics")


def _clear_all_notifs():
    notifications.clear_all()
    ui.navigate.to("/admin/diagnostics")
