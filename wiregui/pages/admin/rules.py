"""Admin firewall rules management page."""

from uuid import UUID

from loguru import logger
from nicegui import app, ui
from sqlmodel import select

from wiregui.db import async_session
from wiregui.models.rule import Rule
from wiregui.models.user import User
from wiregui.pages.layout import layout
from wiregui.services.events import on_rule_created, on_rule_deleted, on_rule_updated


@ui.page("/admin/rules")
async def rules_page():
    if not app.storage.user.get("authenticated") or app.storage.user.get("role") != "admin":
        return ui.navigate.to("/login")

    layout()

    # Load users for the dropdown
    async with async_session() as session:
        users = (await session.execute(select(User).order_by(User.email))).scalars().all()
    user_options = {str(u.id): u.email for u in users}

    async def load_rules() -> list[dict]:
        async with async_session() as session:
            result = await session.execute(select(Rule).order_by(Rule.inserted_at.desc()))
            rules = result.scalars().all()
            return [
                {
                    "id": str(r.id),
                    "action": r.action,
                    "destination": r.destination,
                    "port_type": r.port_type or "any",
                    "port_range": r.port_range or "any",
                    "user": user_options.get(str(r.user_id), "Global") if r.user_id else "Global",
                }
                for r in rules
            ]

    async def refresh_table():
        table.rows = await load_rules()
        table.update()

    async def create_rule():
        dest = dest_input.value.strip()
        if not dest:
            ui.notify("Destination is required", type="negative")
            return

        action_val = action_select.value
        port_type_val = port_type_select.value if port_type_select.value != "any" else None
        port_range_val = port_range_input.value.strip() or None
        user_id_val = user_select.value if user_select.value != "global" else None

        async with async_session() as session:
            rule = Rule(
                action=action_val,
                destination=dest,
                port_type=port_type_val,
                port_range=port_range_val,
                user_id=UUID(user_id_val) if user_id_val else None,
            )
            session.add(rule)
            await session.commit()
            await session.refresh(rule)

        logger.info("Rule created: {} {} -> {}", rule.action, rule.destination, user_id_val or "global")
        await on_rule_created(rule)

        create_dialog.close()
        _reset_form()
        await refresh_table()

    # --- Edit rule ---
    edit_rule_id = {"value": None}

    async def open_edit(rule_id: str):
        async with async_session() as session:
            rule = await session.get(Rule, UUID(rule_id))
            if not rule:
                return
        edit_rule_id["value"] = rule_id
        edit_action.value = rule.action
        edit_dest.value = rule.destination
        edit_port_type.value = rule.port_type or "any"
        edit_port_range.value = rule.port_range or ""
        edit_user.value = str(rule.user_id) if rule.user_id else "global"
        edit_dialog.open()

    async def save_edit():
        rid = edit_rule_id["value"]
        if not rid:
            return

        async with async_session() as session:
            rule = await session.get(Rule, UUID(rid))
            if not rule:
                return

            rule.action = edit_action.value
            rule.destination = edit_dest.value.strip()
            rule.port_type = edit_port_type.value if edit_port_type.value != "any" else None
            rule.port_range = edit_port_range.value.strip() or None
            rule.user_id = UUID(edit_user.value) if edit_user.value != "global" else None

            session.add(rule)
            await session.commit()
            await session.refresh(rule)
            await on_rule_updated(rule)

        logger.info("Rule updated: {} {}", edit_action.value, edit_dest.value)
        ui.notify("Rule updated")
        edit_dialog.close()
        await refresh_table()

    async def delete_rule(rule_id: str):
        async with async_session() as session:
            rule = await session.get(Rule, UUID(rule_id))
            if rule:
                await session.delete(rule)
                await session.commit()
                logger.info("Rule deleted: {} {}", rule.action, rule.destination)
                await on_rule_deleted(rule)
        await refresh_table()

    def _reset_form():
        dest_input.value = ""
        action_select.value = "accept"
        port_type_select.value = "any"
        port_range_input.value = ""
        user_select.value = "global"

    # Page content
    with ui.column().classes("w-full p-4"):
        with ui.row().classes("w-full items-center justify-between"):
            ui.label("Firewall Rules").classes("text-h5")
            ui.button("Add Rule", icon="add", on_click=lambda: create_dialog.open()).props("color=primary")

        columns = [
            {"name": "action", "label": "Action", "field": "action", "align": "left", "sortable": True},
            {"name": "destination", "label": "Destination", "field": "destination", "align": "left", "sortable": True},
            {"name": "port_type", "label": "Protocol", "field": "port_type", "align": "left"},
            {"name": "port_range", "label": "Port(s)", "field": "port_range", "align": "left"},
            {"name": "user", "label": "User", "field": "user", "align": "left"},
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
        table.on("delete", lambda e: delete_rule(e.args))

    # Create rule dialog
    with ui.dialog() as create_dialog:
        with ui.card().classes("w-96"):
            ui.label("New Firewall Rule").classes("text-h6")

            action_select = ui.select(
                ["accept", "drop"], value="accept", label="Action",
            ).props("outlined dense").classes("w-full")

            dest_input = ui.input("Destination (CIDR)", placeholder="e.g. 10.0.0.0/8 or 0.0.0.0/0").props(
                "outlined dense"
            ).classes("w-full")

            port_type_select = ui.select(
                ["any", "tcp", "udp"], value="any", label="Protocol",
            ).props("outlined dense").classes("w-full")

            port_range_input = ui.input("Port Range", placeholder="e.g. 80 or 80-443 (optional)").props(
                "outlined dense"
            ).classes("w-full")

            user_options_list = [{"label": "Global (all users)", "value": "global"}] + [
                {"label": email, "value": uid} for uid, email in user_options.items()
            ]
            user_select = ui.select(
                {item["value"]: item["label"] for item in user_options_list},
                value="global",
                label="Applies to",
            ).props("outlined dense").classes("w-full")

            with ui.row().classes("w-full justify-end q-mt-sm"):
                ui.button("Cancel", on_click=create_dialog.close).props("flat")
                ui.button("Create", on_click=create_rule).props("color=primary")

    # Edit rule dialog
    user_options_map = {"global": "Global (all users)"}
    user_options_map.update(user_options)

    with ui.dialog() as edit_dialog:
        with ui.card().classes("w-96"):
            ui.label("Edit Firewall Rule").classes("text-h6")

            edit_action = ui.select(
                ["accept", "drop"], value="accept", label="Action",
            ).props("outlined dense").classes("w-full")

            edit_dest = ui.input("Destination (CIDR)").props("outlined dense").classes("w-full")

            edit_port_type = ui.select(
                ["any", "tcp", "udp"], value="any", label="Protocol",
            ).props("outlined dense").classes("w-full")

            edit_port_range = ui.input("Port Range").props("outlined dense").classes("w-full")

            edit_user = ui.select(
                user_options_map, value="global", label="Applies to",
            ).props("outlined dense").classes("w-full")

            with ui.row().classes("w-full justify-end q-mt-sm"):
                ui.button("Cancel", on_click=edit_dialog.close).props("flat")
                ui.button("Save", on_click=save_edit).props("color=primary")

    await refresh_table()
