"""E2E tests for admin firewall rules management page."""

from uuid import UUID

import pytest_asyncio
from playwright.async_api import Page, expect
from sqlmodel import select

from wiregui.db import async_session
from wiregui.models.rule import Rule
from wiregui.models.user import User
from tests.e2e.conftest import TEST_APP_BASE, TEST_EMAIL, login


async def _cleanup_test_rules():
    """Remove rules created by tests (identified by test-specific destinations)."""
    async with async_session() as session:
        result = await session.execute(
            select(Rule).where(Rule.destination.in_([
                "10.99.0.0/16", "10.88.0.0/16", "10.77.0.0/16",
                "10.66.0.0/16", "10.55.0.0/16",
            ]))
        )
        for rule in result.scalars().all():
            await session.delete(rule)
        await session.commit()


@pytest_asyncio.fixture(autouse=True)
async def clean_rules(app_server):
    """Clean up test rules before and after each test."""
    await _cleanup_test_rules()
    yield
    await _cleanup_test_rules()


async def _go_to_rules(page: Page):
    """Login and navigate to admin rules page."""
    await login(page)
    await expect(page.get_by_text("My Devices")).to_be_visible(timeout=10_000)
    await page.goto(f"{TEST_APP_BASE}/admin/rules")
    await expect(page.locator("role=main").get_by_text("Firewall Rules")).to_be_visible(timeout=10_000)


async def _create_rule_via_dialog(
    page: Page, *, action: str = "accept", destination: str = "10.99.0.0/16",
    protocol: str = "any", port_range: str = "", user: str = "global",
):
    """Open create dialog and fill in a rule."""
    await page.get_by_role("button", name="Add Rule").click()
    await expect(page.get_by_text("New Firewall Rule")).to_be_visible(timeout=5_000)

    # Action select
    if action != "accept":
        await page.locator(".q-dialog label:has-text('Action')").click()
        await page.get_by_role("option", name=action).click()

    # Destination
    await page.locator(".q-dialog input[aria-label='Destination (CIDR)']").fill(destination)

    # Protocol
    if protocol != "any":
        await page.locator(".q-dialog label:has-text('Protocol')").click()
        await page.get_by_role("option", name=protocol).click()

    # Port range
    if port_range:
        await page.locator(".q-dialog input[aria-label='Port Range']").fill(port_range)

    # User
    if user != "global":
        await page.locator(".q-dialog label:has-text('Applies to')").click()
        await page.get_by_role("option", name=user).click()

    await page.get_by_role("button", name="Create").click()
    await page.wait_for_timeout(500)


async def test_list_rules_table(page: Page, test_user: User):
    """Rules page renders table with correct columns."""
    # Seed a rule in DB
    async with async_session() as session:
        rule = Rule(action="accept", destination="10.99.0.0/16", port_type="tcp",
                    port_range="443", user_id=test_user.id)
        session.add(rule)
        await session.commit()

    await _go_to_rules(page)

    await expect(page.get_by_role("cell", name="accept")).to_be_visible(timeout=5_000)
    await expect(page.get_by_role("cell", name="10.99.0.0/16")).to_be_visible()
    await expect(page.get_by_role("cell", name="tcp")).to_be_visible()
    await expect(page.get_by_role("cell", name="443")).to_be_visible()
    await expect(page.get_by_role("cell", name=TEST_EMAIL)).to_be_visible()


async def test_create_accept_rule_with_cidr(page: Page, test_user: User):
    """Create an accept rule with CIDR — verify in table and DB."""
    await _go_to_rules(page)
    await _create_rule_via_dialog(page, action="accept", destination="10.88.0.0/16")

    await expect(page.get_by_role("cell", name="10.88.0.0/16")).to_be_visible(timeout=5_000)

    # Verify in DB
    async with async_session() as session:
        result = await session.execute(select(Rule).where(Rule.destination == "10.88.0.0/16"))
        rule = result.scalar_one()
        assert rule.action == "accept"
        assert rule.port_type is None
        assert rule.port_range is None
        assert rule.user_id is None


async def test_create_drop_rule_with_tcp_port_range(page: Page, test_user: User):
    """Create a drop rule with TCP port range — verify in table and DB."""
    await _go_to_rules(page)
    await _create_rule_via_dialog(
        page, action="drop", destination="10.77.0.0/16",
        protocol="tcp", port_range="80-443",
    )

    await expect(page.get_by_role("cell", name="10.77.0.0/16")).to_be_visible(timeout=5_000)
    await expect(page.get_by_role("cell", name="drop").first).to_be_visible()

    # Verify in DB
    async with async_session() as session:
        result = await session.execute(select(Rule).where(Rule.destination == "10.77.0.0/16"))
        rule = result.scalar_one()
        assert rule.action == "drop"
        assert rule.port_type == "tcp"
        assert rule.port_range == "80-443"


async def test_create_global_rule(page: Page, test_user: User):
    """Create a global rule (no user) — shows 'Global' in table and DB has null user_id."""
    await _go_to_rules(page)
    await _create_rule_via_dialog(page, destination="10.66.0.0/16", user="global")

    await expect(page.get_by_role("cell", name="10.66.0.0/16")).to_be_visible(timeout=5_000)
    await expect(page.get_by_role("cell", name="Global")).to_be_visible()

    # Verify in DB
    async with async_session() as session:
        result = await session.execute(select(Rule).where(Rule.destination == "10.66.0.0/16"))
        rule = result.scalar_one()
        assert rule.user_id is None


async def test_edit_rule_action(page: Page, test_user: User):
    """Edit rule action from accept to drop — verify in table and DB."""
    async with async_session() as session:
        rule = Rule(action="accept", destination="10.55.0.0/16")
        session.add(rule)
        await session.commit()
        rule_id = rule.id

    await _go_to_rules(page)
    await expect(page.get_by_role("cell", name="10.55.0.0/16")).to_be_visible(timeout=5_000)

    # Click edit (first button in the row)
    row = page.locator("tr", has_text="10.55.0.0/16")
    await row.locator(".q-btn").first.click()
    await expect(page.get_by_text("Edit Firewall Rule")).to_be_visible(timeout=5_000)

    # Change action to drop
    await page.locator(".q-dialog label:has-text('Action')").click()
    await page.get_by_role("option", name="drop").click()

    await page.get_by_role("button", name="Save").click()
    await expect(page.get_by_text("Rule updated")).to_be_visible(timeout=5_000)

    # Verify in DB
    async with async_session() as session:
        rule = await session.get(Rule, rule_id)
        assert rule.action == "drop"


async def test_edit_rule_destination(page: Page, test_user: User):
    """Edit rule destination — verify in table and DB."""
    async with async_session() as session:
        rule = Rule(action="accept", destination="10.99.0.0/16")
        session.add(rule)
        await session.commit()
        rule_id = rule.id

    await _go_to_rules(page)
    await expect(page.get_by_role("cell", name="10.99.0.0/16")).to_be_visible(timeout=5_000)

    row = page.locator("tr", has_text="10.99.0.0/16")
    await row.locator(".q-btn").first.click()
    await expect(page.get_by_text("Edit Firewall Rule")).to_be_visible(timeout=5_000)

    dest_input = page.locator(".q-dialog input[aria-label='Destination (CIDR)']")
    await dest_input.clear()
    await dest_input.fill("10.88.0.0/16")

    await page.get_by_role("button", name="Save").click()
    await expect(page.get_by_text("Rule updated")).to_be_visible(timeout=5_000)

    # Verify in DB
    async with async_session() as session:
        rule = await session.get(Rule, rule_id)
        assert rule.destination == "10.88.0.0/16"


async def test_delete_rule(page: Page, test_user: User):
    """Delete a rule — removed from table and DB."""
    async with async_session() as session:
        rule = Rule(action="accept", destination="10.99.0.0/16")
        session.add(rule)
        await session.commit()
        rule_id = rule.id

    await _go_to_rules(page)
    await expect(page.get_by_role("cell", name="10.99.0.0/16")).to_be_visible(timeout=5_000)

    # Click delete (second button in the row)
    row = page.locator("tr", has_text="10.99.0.0/16")
    await row.locator(".q-btn").nth(1).click()
    await page.wait_for_timeout(1000)

    await expect(page.get_by_role("cell", name="10.99.0.0/16")).not_to_be_visible()

    # Verify in DB
    async with async_session() as session:
        rule = await session.get(Rule, rule_id)
        assert rule is None