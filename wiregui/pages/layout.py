"""Shared layout — sidebar navigation + header."""

from uuid import UUID

from loguru import logger
from nicegui import app, ui

from wiregui.db import async_session
from wiregui.models.user import User
from wiregui.pages.style import apply_style
from wiregui.services import notifications

# Map theme preference to icon
_THEME_ICONS = {"light": "light_mode", "dark": "dark_mode", "auto": "brightness_auto"}
_THEME_CYCLE = {"light": "dark", "dark": "auto", "auto": "light"}


def layout(title: str = "WireGUI"):
    """Render the shared app chrome (header + sidebar). Call at the top of each page."""
    apply_style()

    user_email = app.storage.user.get("email", "")
    role = app.storage.user.get("role", "")
    theme_pref = app.storage.user.get("theme_preference", "auto")

    # Apply theme
    dark_value = {"light": False, "dark": True, "auto": None}.get(theme_pref)
    dark = ui.dark_mode(dark_value)

    def logout():
        app.storage.user.clear()
        ui.navigate.to("/login")

    async def toggle_theme():
        current = app.storage.user.get("theme_preference", "auto")
        new_pref = _THEME_CYCLE[current]
        app.storage.user["theme_preference"] = new_pref

        # Apply immediately
        new_value = {"light": False, "dark": True, "auto": None}[new_pref]
        if new_value is True:
            dark.enable()
        elif new_value is False:
            dark.disable()
        else:
            dark.auto()

        theme_btn.props(f'icon={_THEME_ICONS[new_pref]}')

        # Persist to database
        user_id = app.storage.user.get("user_id")
        if user_id:
            try:
                async with async_session() as session:
                    user = await session.get(User, UUID(user_id))
                    if user:
                        user.theme_preference = new_pref
                        session.add(user)
                        await session.commit()
            except Exception as e:
                logger.warning("Failed to persist theme preference: {}", e)

    # Header
    with ui.header().classes("items-center justify-between"):
        with ui.row().classes("items-center"):
            ui.button(icon="menu", on_click=lambda: drawer.toggle()).props("flat color=white")
            ui.image("/img/wiregui.svg").classes("w-8 h-8")
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
            theme_btn = ui.button(
                icon=_THEME_ICONS.get(theme_pref, "brightness_auto"),
                on_click=toggle_theme,
            ).props("flat color=white")
            ui.label(f"{user_email}").classes("text-subtitle2")
            ui.button("Logout", on_click=logout).props("flat color=white")

    # Sidebar
    with ui.left_drawer(value=True, bordered=True) as drawer:
        ui.label("Navigation").classes("text-subtitle2 q-pa-sm text-grey")
        ui.separator()
        ui.item("Devices", on_click=lambda: ui.navigate.to("/devices")).classes("cursor-pointer")
        ui.item("Account", on_click=lambda: ui.navigate.to("/account")).classes("cursor-pointer")

        if role == "admin":
            ui.separator()
            ui.label("Admin").classes("text-subtitle2 q-pa-sm text-grey")
            ui.item("Users", on_click=lambda: ui.navigate.to("/admin/users")).classes("cursor-pointer")
            ui.item("All Devices", on_click=lambda: ui.navigate.to("/admin/devices")).classes("cursor-pointer")
            ui.item("Rules", on_click=lambda: ui.navigate.to("/admin/rules")).classes("cursor-pointer")
            ui.item("Settings", on_click=lambda: ui.navigate.to("/admin/settings")).classes("cursor-pointer")
            ui.item("Diagnostics", on_click=lambda: ui.navigate.to("/admin/diagnostics")).classes("cursor-pointer")