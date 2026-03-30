"""Admin user management page."""

from uuid import UUID

from loguru import logger
from nicegui import app, ui
from sqlalchemy.orm import selectinload
from sqlmodel import func, select

from wiregui.auth.passwords import hash_password
from wiregui.db import async_session
from wiregui.models.device import Device
from wiregui.models.rule import Rule
from wiregui.models.user import User
from wiregui.pages.layout import layout
from wiregui.services.events import on_device_deleted
from wiregui.utils.time import utcnow


def _guard():
    if not app.storage.user.get("authenticated") or app.storage.user.get("role") != "admin":
        ui.navigate.to("/login")
        return False
    return True


@ui.page("/admin/users")
async def users_page():
    if not _guard():
        return

    layout()

    async def load_users() -> list[dict]:
        async with async_session() as session:
            # Get users with device counts via subquery
            device_count_sq = (
                select(Device.user_id, func.count().label("device_count"))
                .group_by(Device.user_id)
                .subquery()
            )
            result = await session.execute(
                select(User).order_by(User.email)
            )
            users = result.scalars().all()

            # Get device counts separately
            counts_result = await session.execute(
                select(Device.user_id, func.count().label("cnt")).group_by(Device.user_id)
            )
            counts = {str(row[0]): row[1] for row in counts_result.all()}

            return [
                {
                    "id": str(u.id),
                    "email": u.email,
                    "role": u.role,
                    "devices": counts.get(str(u.id), 0),
                    "last_signed_in": str(u.last_signed_in_at or "-"),
                    "method": u.last_signed_in_method or "-",
                    "status": "Disabled" if u.disabled_at else "Active",
                    "created": str(u.inserted_at)[:19],
                }
                for u in users
            ]

    async def refresh_table():
        table.rows = await load_users()
        table.update()

    # --- Create user ---
    async def create_user():
        email = create_email.value.strip()
        pwd = create_password.value
        role = create_role.value

        if not email or not pwd:
            ui.notify("Email and password are required", type="negative")
            return

        async with async_session() as session:
            existing = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
            if existing:
                ui.notify(f"User {email} already exists", type="negative")
                return

            user = User(email=email, password_hash=hash_password(pwd), role=role)
            session.add(user)
            await session.commit()

        logger.info("Admin created user: {} ({})", email, role)
        ui.notify(f"User {email} created")
        create_dialog.close()
        create_email.value = ""
        create_password.value = ""
        create_role.value = "unprivileged"
        await refresh_table()

    # --- Edit user ---
    edit_user_id = {"value": None}

    async def open_edit(user_id: str):
        async with async_session() as session:
            user = await session.get(User, UUID(user_id))
            if not user:
                return
        edit_user_id["value"] = user_id
        edit_email.value = user.email
        edit_role.value = user.role
        edit_password.value = ""
        edit_disabled.value = user.disabled_at is not None
        edit_dialog.open()

    async def save_edit():
        uid = edit_user_id["value"]
        if not uid:
            return

        async with async_session() as session:
            user = await session.get(User, UUID(uid))
            if not user:
                return

            user.email = edit_email.value.strip()
            user.role = edit_role.value

            if edit_password.value:
                user.password_hash = hash_password(edit_password.value)

            if edit_disabled.value and not user.disabled_at:
                user.disabled_at = utcnow()
            elif not edit_disabled.value and user.disabled_at:
                user.disabled_at = None

            session.add(user)
            await session.commit()

        logger.info("Admin updated user: {}", edit_email.value)
        ui.notify("User updated")
        edit_dialog.close()
        await refresh_table()

    # --- Delete user ---
    async def delete_user(user_id: str):
        current_user_id = app.storage.user.get("user_id")
        if user_id == current_user_id:
            ui.notify("Cannot delete your own account", type="negative")
            return

        async with async_session() as session:
            user = await session.get(User, UUID(user_id))
            if not user:
                return

            # Delete user's devices (and fire WG events)
            devices_result = await session.execute(
                select(Device).where(Device.user_id == user.id)
            )
            for device in devices_result.scalars().all():
                await session.delete(device)
                await on_device_deleted(device)

            # Delete user's rules
            await session.execute(
                select(Rule).where(Rule.user_id == user.id)
            )
            rules_result = await session.execute(select(Rule).where(Rule.user_id == user.id))
            for rule in rules_result.scalars().all():
                await session.delete(rule)

            await session.delete(user)
            await session.commit()

        logger.info("Admin deleted user: {}", user.email)
        ui.notify(f"User {user.email} deleted")
        await refresh_table()

    def on_row_click(e):
        open_edit(e.args["id"])

    # --- Page content ---
    with ui.column().classes("w-full p-4"):
        with ui.row().classes("w-full items-center justify-between"):
            ui.label("Users").classes("text-h5")
            ui.button("Add User", icon="person_add", on_click=lambda: create_dialog.open()).props("color=primary")

        columns = [
            {"name": "email", "label": "Email", "field": "email", "align": "left", "sortable": True},
            {"name": "role", "label": "Role", "field": "role", "align": "left", "sortable": True},
            {"name": "devices", "label": "Devices", "field": "devices", "align": "center"},
            {"name": "status", "label": "Status", "field": "status", "align": "left"},
            {"name": "last_signed_in", "label": "Last Sign-in", "field": "last_signed_in", "align": "left"},
            {"name": "method", "label": "Method", "field": "method", "align": "left"},
            {"name": "created", "label": "Created", "field": "created", "align": "left"},
            {"name": "actions", "label": "", "field": "id", "align": "center"},
        ]
        table = ui.table(columns=columns, rows=[], row_key="id").classes("w-full")
        table.on("rowClick", on_row_click)
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
        table.on("delete", lambda e: delete_user(e.args))

    # --- Create dialog ---
    with ui.dialog() as create_dialog:
        with ui.card().classes("w-96"):
            ui.label("New User").classes("text-h6")
            create_email = ui.input("Email").props("outlined dense").classes("w-full")
            create_password = ui.input("Password", password=True, password_toggle_button=True).props("outlined dense").classes("w-full")
            create_role = ui.select(["unprivileged", "admin"], value="unprivileged", label="Role").props("outlined dense").classes("w-full")
            with ui.row().classes("w-full justify-end q-mt-sm"):
                ui.button("Cancel", on_click=create_dialog.close).props("flat")
                ui.button("Create", on_click=create_user).props("color=primary")

    # --- Edit dialog ---
    with ui.dialog() as edit_dialog:
        with ui.card().classes("w-96"):
            ui.label("Edit User").classes("text-h6")
            edit_email = ui.input("Email").props("outlined dense").classes("w-full")
            edit_role = ui.select(["unprivileged", "admin"], value="unprivileged", label="Role").props("outlined dense").classes("w-full")
            edit_password = ui.input("New Password (leave blank to keep)", password=True, password_toggle_button=True).props("outlined dense").classes("w-full")
            edit_disabled = ui.switch("Disabled")
            with ui.row().classes("w-full justify-end q-mt-sm"):
                ui.button("Cancel", on_click=edit_dialog.close).props("flat")
                ui.button("Save", on_click=save_edit).props("color=primary")

    await refresh_table()
