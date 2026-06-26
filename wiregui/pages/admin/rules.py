"""Admin firewall rules management page."""

import asyncio
from uuid import UUID

from loguru import logger
from nicegui import app, ui
from sqlmodel import select

from wiregui.db import async_session
from wiregui.models.configuration import Configuration
from wiregui.models.rule import Rule
from wiregui.models.user import User
from wiregui.pages.layout import layout
from wiregui.services.events import (
    on_rule_created,
    on_rule_deleted,
    on_rule_updated,
    on_rules_reordered,
)
from wiregui.services.firewall import apply_lan_to_peers_policy, apply_peer_to_peer_policy, get_ruleset
from wiregui.utils.ordering import assign_priorities
from wiregui.utils.time import utcnow


@ui.page("/admin/rules")
async def rules_page():
    if not app.storage.user.get("authenticated") or app.storage.user.get("role") != "admin":
        return ui.navigate.to("/login")

    layout()

    # Load users for the dropdowns
    async with async_session() as session:
        users = (await session.execute(select(User).order_by(User.email))).scalars().all()
        config = (await session.execute(select(Configuration).limit(1))).scalar_one_or_none()
    user_options = {str(u.id): u.email for u in users}

    # Current "filter by user" selection: "all" or a user id string.
    filter_user = {"value": "all"}

    def _rule_to_dict(r: Rule) -> dict:
        return {
            "id": str(r.id),
            "action": r.action,
            "destination": r.destination,
            "port_type": r.port_type or "any",
            "port_range": r.port_range or "any",
            "priority": r.priority,
            "user": user_options.get(str(r.user_id), "Global") if r.user_id else "Global",
        }

    async def _load_rules() -> list[dict]:
        fu = filter_user["value"]
        async with async_session() as session:
            stmt = select(Rule).order_by(Rule.priority, Rule.inserted_at)
            if fu != "all":
                stmt = stmt.where(Rule.user_id == UUID(fu))
            rules = (await session.execute(stmt)).scalars().all()
        return [_rule_to_dict(r) for r in rules]

    async def _next_priority(user_id_val: str | None) -> int:
        """Append new rules at the end of their scope (highest priority number)."""
        async with async_session() as session:
            cond = Rule.user_id == UUID(user_id_val) if user_id_val else Rule.user_id.is_(None)
            existing = (await session.execute(select(Rule.priority).where(cond))).scalars().all()
        return (max(existing) + 10) if existing else 10

    async def _persist_order(ordered_ids: list[str]) -> None:
        """Re-sequence priorities to match the dragged order, then rebuild the chain."""
        mapping = assign_priorities(ordered_ids)
        async with async_session() as session:
            for rid, prio in mapping.items():
                rule = await session.get(Rule, UUID(rid))
                if rule:
                    rule.priority = prio
                    rule.updated_at = utcnow()
                    session.add(rule)
            await session.commit()
        fu = filter_user["value"]
        if fu != "all":
            asyncio.create_task(on_rules_reordered(fu))
        logger.info("Rules reordered for {}", fu)

    # --- Rendering ---
    def _render_table(rule_dicts: list[dict]) -> None:
        columns = [
            {"name": "priority", "label": "Priority", "field": "priority", "align": "left", "sortable": True},
            {"name": "action", "label": "Action", "field": "action", "align": "left", "sortable": True},
            {"name": "destination", "label": "Destination", "field": "destination", "align": "left", "sortable": True},
            {"name": "port_type", "label": "Protocol", "field": "port_type", "align": "left"},
            {"name": "port_range", "label": "Port(s)", "field": "port_range", "align": "left"},
            {"name": "user", "label": "User", "field": "user", "align": "left", "sortable": True},
            {"name": "actions", "label": "", "field": "id", "align": "center"},
        ]
        table = ui.table(columns=columns, rows=rule_dicts, row_key="id").classes("w-full")
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

    def _render_sortable(rule_dicts: list[dict]) -> None:
        """Drag-and-drop reorderable list for a single user's rules."""
        ui.label(
            "Drag rows to reorder. Rules are evaluated top to bottom — put a "
            "\"drop\" catch-all last so the rules above it are matched first."
        ).classes("text-caption text-grey q-mb-xs")

        dragged = {"id": None}
        order = [r["id"] for r in rule_dicts]

        async def do_drop(target_id: str) -> None:
            src = dragged["id"]
            dragged["id"] = None
            if not src or src == target_id:
                return
            order.remove(src)
            order.insert(order.index(target_id), src)
            await _persist_order(order)
            await render_rules()

        # Header row
        with ui.row().classes("w-full items-center text-bold text-caption text-grey q-px-md"):
            ui.label("").classes("w-8")
            ui.label("Action").classes("w-24")
            ui.label("Destination").classes("flex-grow")
            ui.label("Protocol").classes("w-20")
            ui.label("Port(s)").classes("w-24")
            ui.label("").classes("w-24")

        with ui.column().classes("w-full gap-1"):
            for r in rule_dicts:
                rid = r["id"]
                row = (
                    ui.row()
                    .classes("w-full items-center q-px-md q-py-sm bg-grey-1 rounded-borders cursor-move")
                    .props("draggable=true")
                )
                row.on("dragstart", lambda e, _id=rid: dragged.update(id=_id))
                row.on("dragover.prevent", lambda e: None)
                row.on("drop", lambda e, _id=rid: do_drop(_id))
                with row:
                    ui.icon("drag_indicator").classes("w-8 text-grey")
                    ui.badge(
                        r["action"],
                        color="green" if r["action"] == "accept" else "red",
                    ).classes("w-24")
                    ui.label(r["destination"]).classes("flex-grow")
                    ui.label(r["port_type"]).classes("w-20")
                    ui.label(r["port_range"]).classes("w-24")
                    with ui.row().classes("w-24 justify-end gap-0"):
                        ui.button(icon="edit", on_click=lambda _, _id=rid: open_edit(_id)).props(
                            "flat dense color=primary"
                        )
                        ui.button(icon="delete", on_click=lambda _, _id=rid: delete_rule(_id)).props(
                            "flat dense color=negative"
                        )

    async def render_rules() -> None:
        rule_dicts = await _load_rules()
        rules_container.clear()
        with rules_container:
            if not rule_dicts:
                ui.label("No rules for this selection.").classes("text-caption text-grey q-pa-sm")
                return
            if filter_user["value"] == "all":
                _render_table(rule_dicts)
            else:
                _render_sortable(rule_dicts)

    async def on_filter_change(value) -> None:
        filter_user["value"] = value or "all"
        await render_rules()

    # --- Create rule ---
    def open_create() -> None:
        fu = filter_user["value"]
        # Prefill "Applies to" with the user currently being viewed.
        user_select.value = fu if fu != "all" else "global"
        create_dialog.open()

    async def create_rule():
        dest = dest_input.value.strip()
        if not dest:
            ui.notify("Destination is required", type="negative")
            return

        action_val = action_select.value
        port_type_val = port_type_select.value if port_type_select.value != "any" else None
        port_range_val = port_range_input.value.strip() or None
        user_id_val = user_select.value if user_select.value != "global" else None

        priority = await _next_priority(user_id_val)

        async with async_session() as session:
            rule = Rule(
                action=action_val,
                destination=dest,
                port_type=port_type_val,
                port_range=port_range_val,
                priority=priority,
                user_id=UUID(user_id_val) if user_id_val else None,
            )
            session.add(rule)
            await session.commit()
            await session.refresh(rule)

        logger.info("Rule created: {} {} -> {}", rule.action, rule.destination, user_id_val or "global")
        asyncio.create_task(on_rule_created(rule))

        create_dialog.close()
        _reset_form()
        await render_rules()

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
        edit_priority.value = rule.priority
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
            rule.priority = int(edit_priority.value) if edit_priority.value is not None else rule.priority
            rule.user_id = UUID(edit_user.value) if edit_user.value != "global" else None

            session.add(rule)
            await session.commit()
            await session.refresh(rule)
            asyncio.create_task(on_rule_updated(rule))

        logger.info("Rule updated: {} {}", edit_action.value, edit_dest.value)
        ui.notify("Rule updated")
        edit_dialog.close()
        await render_rules()

    async def delete_rule(rule_id: str):
        async with async_session() as session:
            rule = await session.get(Rule, UUID(rule_id))
            if rule:
                await session.delete(rule)
                await session.commit()
                logger.info("Rule deleted: {} {}", rule.action, rule.destination)
                asyncio.create_task(on_rule_deleted(rule))
        await render_rules()

    def _reset_form():
        dest_input.value = ""
        action_select.value = "accept"
        port_type_select.value = "any"
        port_range_input.value = ""
        user_select.value = "global"

    # --- Firewall policy toggles ---
    async def toggle_peer_to_peer(e):
        async with async_session() as session:
            c = (await session.execute(select(Configuration).limit(1))).scalar_one_or_none()
            if c:
                c.allow_peer_to_peer = e.value
                c.updated_at = utcnow()
                session.add(c)
                await session.commit()
        asyncio.create_task(apply_peer_to_peer_policy(e.value))
        ui.notify(f"Peer-to-peer: {'allowed' if e.value else 'denied'}")

    async def toggle_lan_to_peers(e):
        async with async_session() as session:
            c = (await session.execute(select(Configuration).limit(1))).scalar_one_or_none()
            if c:
                c.allow_lan_to_peers = e.value
                c.updated_at = utcnow()
                session.add(c)
                await session.commit()
        asyncio.create_task(apply_lan_to_peers_policy(e.value))
        ui.notify(f"LAN-to-peers: {'allowed' if e.value else 'denied'}")

    # --- Troubleshooting ---
    async def show_nft_rules():
        ruleset = await get_ruleset()
        with ui.dialog(value=True) as dlg:
            with ui.card().classes("w-[900px] max-w-[90vw]"):
                ui.label("nftables Ruleset").classes("text-subtitle1 text-bold")
                ui.label("Current system firewall rules for troubleshooting.").classes("text-caption text-grey")
                ui.separator()
                ui.code(ruleset, language="bash").classes("w-full")
                with ui.row().classes("w-full justify-end q-mt-sm"):
                    ui.button("Close", on_click=dlg.close).props("flat")

    # --- Page content ---
    with ui.column().classes("w-full p-4"):
        ui.label("Firewall Rules").classes("text-h5 q-mb-md")

        # Policy switches
        with ui.card().classes("w-full"):
            ui.label("Network Policies").classes("text-subtitle1 text-bold")
            ui.label("Control how traffic flows between peers and the local network.").classes("text-caption text-grey")
            ui.separator()

            ui.switch(
                "Allow peer-to-peer communication",
                value=config.allow_peer_to_peer if config else False,
                on_change=toggle_peer_to_peer,
            )
            ui.label("Peers can communicate with each other through the WireGuard server (hub-and-spoke).").classes("text-caption text-grey q-ml-xl")

            ui.switch(
                "Allow local network to reach peers",
                value=config.allow_lan_to_peers if config else False,
                on_change=toggle_lan_to_peers,
            ).classes("q-mt-sm")
            ui.label("Devices on the server's LAN can initiate connections to VPN peers.").classes("text-caption text-grey q-ml-xl")

        # Rules
        with ui.card().classes("w-full q-mt-md"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("Per-User Rules").classes("text-subtitle1 text-bold")
                ui.button("Add Rule", icon="add", on_click=open_create).props("color=primary unelevated")

            # User filter — searchable; pick a user to review and reorder only their rules.
            filter_options = {"all": "All users"}
            filter_options.update(user_options)
            ui.select(
                filter_options,
                value="all",
                label="Filter by user",
                with_input=True,
                on_change=lambda e: on_filter_change(e.value),
            ).props("outlined dense clearable").classes("w-80")

            ui.separator()

            rules_container = ui.column().classes("w-full")

        # Troubleshooting
        with ui.card().classes("w-full q-mt-md"):
            ui.label("Troubleshooting").classes("text-subtitle1 text-bold")
            ui.label("Inspect the raw nftables ruleset configured on this system.").classes("text-caption text-grey")
            ui.separator()
            ui.button("View nftables Rules", icon="terminal", on_click=show_nft_rules).props("color=primary unelevated")

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
                with_input=True,
            ).props("outlined dense").classes("w-full")
            ui.label("New rules are added to the end of the chain; drag to reorder.").classes(
                "text-caption text-grey"
            )

            with ui.row().classes("w-full justify-end q-mt-sm"):
                ui.button("Cancel", on_click=create_dialog.close).props("flat")
                ui.button("Create", on_click=create_rule).props("color=primary unelevated")

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

            edit_priority = ui.number("Priority (lower = evaluated first)", value=100, format="%d").props(
                "outlined dense"
            ).classes("w-full")

            edit_user = ui.select(
                user_options_map, value="global", label="Applies to", with_input=True,
            ).props("outlined dense").classes("w-full")

            with ui.row().classes("w-full justify-end q-mt-sm"):
                ui.button("Cancel", on_click=edit_dialog.close).props("flat")
                ui.button("Save", on_click=save_edit).props("color=primary unelevated")

    await render_rules()
