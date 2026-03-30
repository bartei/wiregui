"""Shared layout — sidebar navigation + header."""

from nicegui import app, ui

from wiregui.services import notifications


def layout(title: str = "WireGUI"):
    """Render the shared app chrome (header + sidebar). Call at the top of each page."""
    user_email = app.storage.user.get("email", "")
    role = app.storage.user.get("role", "")

    def logout():
        app.storage.user.clear()
        ui.navigate.to("/login")

    # Header
    with ui.header().classes("items-center justify-between"):
        with ui.row().classes("items-center"):
            ui.button(icon="menu", on_click=lambda: drawer.toggle()).props("flat color=white")
            ui.label("WireGUI").classes("text-h6")
        with ui.row().classes("items-center"):
            if role == "admin":
                notif_count = notifications.count()
                with ui.button(
                    icon="notifications",
                    on_click=lambda: ui.navigate.to("/admin/diagnostics"),
                ).props("flat color=white"):
                    if notif_count > 0:
                        ui.badge(str(notif_count), color="red").props("floating")
            ui.label(f"{user_email}").classes("text-subtitle2")
            ui.button("Logout", on_click=logout).props("flat color=white")

    # Sidebar
    with ui.left_drawer(value=True, bordered=True).classes("bg-grey-1") as drawer:
        ui.label("Navigation").classes("text-subtitle2 q-pa-sm text-grey-7")
        ui.separator()
        ui.item("Devices", on_click=lambda: ui.navigate.to("/devices")).classes("cursor-pointer")
        ui.item("Account", on_click=lambda: ui.navigate.to("/account")).classes("cursor-pointer")

        if role == "admin":
            ui.separator()
            ui.label("Admin").classes("text-subtitle2 q-pa-sm text-grey-7")
            ui.item("Users", on_click=lambda: ui.navigate.to("/admin/users")).classes("cursor-pointer")
            ui.item("All Devices", on_click=lambda: ui.navigate.to("/admin/devices")).classes("cursor-pointer")
            ui.item("Rules", on_click=lambda: ui.navigate.to("/admin/rules")).classes("cursor-pointer")
            ui.item("Settings", on_click=lambda: ui.navigate.to("/admin/settings")).classes("cursor-pointer")
            ui.item("Diagnostics", on_click=lambda: ui.navigate.to("/admin/diagnostics")).classes("cursor-pointer")
