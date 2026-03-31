"""E2E tests for admin device management page."""

import pytest_asyncio
from playwright.async_api import Page, expect
from sqlmodel import select

from wiregui.auth.passwords import hash_password
from wiregui.db import async_session
from wiregui.models.device import Device
from wiregui.models.user import User
from wiregui.utils.crypto import generate_keypair, generate_preshared_key
from tests.e2e.conftest import (
    TEST_APP_BASE,
    TEST_EMAIL,
    TEST_PASSWORD,
    _cleanup_user_by_email,
    login,
)

SECOND_USER_EMAIL = "e2e-device-user2@example.com"


@pytest_asyncio.fixture
async def second_user(test_user):
    """Create a second user with a device for filtering tests."""
    await _cleanup_user_by_email(SECOND_USER_EMAIL)

    async with async_session() as session:
        user = User(
            email=SECOND_USER_EMAIL,
            password_hash=hash_password("pass12345"),
            role="unprivileged",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    yield user

    await _cleanup_user_by_email(SECOND_USER_EMAIL)


@pytest_asyncio.fixture
async def devices_for_both_users(test_user, second_user):
    """Create one device per user for table/filter tests."""
    _, pub1 = generate_keypair()
    _, pub2 = generate_keypair()
    psk1 = generate_preshared_key()
    psk2 = generate_preshared_key()

    async with async_session() as session:
        d1 = Device(
            name="admin-laptop",
            public_key=pub1,
            preshared_key=psk1,
            ipv4="10.0.0.10",
            user_id=test_user.id,
        )
        d2 = Device(
            name="user2-phone",
            public_key=pub2,
            preshared_key=psk2,
            ipv4="10.0.0.11",
            user_id=second_user.id,
        )
        session.add_all([d1, d2])
        await session.commit()

    yield d1, d2

    # Cleanup handled by user fixture cascade


async def _go_to_admin_devices(page: Page):
    """Login as admin and navigate to admin devices page."""
    await login(page)
    await expect(page.get_by_text("My Devices")).to_be_visible(timeout=10_000)
    await page.goto(f"{TEST_APP_BASE}/admin/devices")
    await expect(page.locator("role=main").get_by_text("All Devices")).to_be_visible(timeout=10_000)


async def test_list_all_devices(page: Page, devices_for_both_users):
    """Admin devices page lists devices from all users."""
    await _go_to_admin_devices(page)
    await expect(page.get_by_text("admin-laptop")).to_be_visible(timeout=5_000)
    await expect(page.get_by_text("user2-phone")).to_be_visible(timeout=5_000)


async def test_filter_by_user(page: Page, second_user, devices_for_both_users):
    """Filtering by user shows only that user's devices."""
    await _go_to_admin_devices(page)
    await expect(page.get_by_text("admin-laptop")).to_be_visible(timeout=5_000)
    await expect(page.get_by_text("user2-phone")).to_be_visible(timeout=5_000)

    # Filter to second user
    await page.locator("label:has-text('Filter by User')").click()
    await page.get_by_role("option", name=SECOND_USER_EMAIL).click()
    await page.wait_for_timeout(1000)

    await expect(page.get_by_text("user2-phone")).to_be_visible(timeout=5_000)
    await expect(page.get_by_text("admin-laptop")).not_to_be_visible()

    # Filter back to all
    await page.locator("label:has-text('Filter by User')").click()
    await page.get_by_role("option", name="All Users").click()
    await page.wait_for_timeout(1000)

    await expect(page.get_by_text("admin-laptop")).to_be_visible(timeout=5_000)
    await expect(page.get_by_text("user2-phone")).to_be_visible(timeout=5_000)


async def test_create_device_with_defaults(page: Page, test_user):
    """Create device with all defaults — config dialog appears."""
    await _go_to_admin_devices(page)
    await page.get_by_role("button", name="Add Device").click()
    await expect(page.get_by_text("New Device")).to_be_visible(timeout=5_000)

    await page.locator("input[aria-label='Device Name']").fill("default-test-device")
    await page.get_by_role("button", name="Create").click()

    # Config dialog should appear with WireGuard config
    await expect(page.get_by_text("Config for default-test-device")).to_be_visible(timeout=10_000)
    await expect(page.get_by_text("[Interface]")).to_be_visible(timeout=5_000)
    await page.get_by_role("button", name="Close").click()
    await page.wait_for_timeout(500)

    # Device should be in the table
    await expect(page.get_by_role("cell", name="default-test-device").first).to_be_visible(timeout=5_000)


async def test_create_device_with_overrides(page: Page, test_user):
    """Create device with custom config overrides."""
    await _go_to_admin_devices(page)
    await page.get_by_role("button", name="Add Device").click()
    await expect(page.get_by_text("New Device")).to_be_visible(timeout=5_000)

    await page.locator("input[aria-label='Device Name']").fill("custom-override-dev")
    await page.locator("input[aria-label='Description (optional)']").fill("Custom overrides test")

    # Toggle off DNS default and set custom — Quasar switches use .q-toggle
    await page.locator(".q-toggle", has_text="Use default DNS").click()
    dns_input = page.locator("input[aria-label='DNS Servers']")
    await dns_input.clear()
    await dns_input.fill("8.8.8.8, 8.8.4.4")

    # Toggle off MTU default and set custom
    await page.locator(".q-toggle", has_text="Use default MTU").click()
    mtu_input = page.locator("input[aria-label='MTU']")
    await mtu_input.clear()
    await mtu_input.fill("1400")

    await page.get_by_role("button", name="Create").click()

    await expect(page.get_by_text("Config for custom-override-dev")).to_be_visible(timeout=10_000)
    await page.get_by_role("button", name="Close").click()
    await page.wait_for_timeout(500)

    await expect(page.get_by_role("cell", name="custom-override-dev").first).to_be_visible(timeout=5_000)

    # Verify in DB
    async with async_session() as session:
        result = await session.execute(
            select(Device).where(Device.name == "custom-override-dev")
            .order_by(Device.inserted_at.desc()).limit(1)
        )
        device = result.scalar_one()
        assert device.use_default_dns is False
        assert "8.8.8.8" in device.dns
        assert device.use_default_mtu is False
        assert device.mtu == 1400


async def test_edit_device_name_and_description(page: Page, devices_for_both_users):
    """Edit a device name and description via the edit dialog."""
    await _go_to_admin_devices(page)
    await expect(page.get_by_text("admin-laptop")).to_be_visible(timeout=5_000)

    # Click edit button on admin-laptop row — Quasar slot buttons with icon
    row = page.locator("tr", has_text="admin-laptop")
    await row.locator(".q-btn").first.click()

    await expect(page.get_by_text("Edit Device")).to_be_visible(timeout=5_000)

    name_input = page.locator(".q-dialog input[aria-label='Device Name']")
    await name_input.clear()
    await name_input.fill("admin-laptop-renamed")

    desc_input = page.locator(".q-dialog input[aria-label='Description']")
    await desc_input.clear()
    await desc_input.fill("Updated description")

    await page.get_by_role("button", name="Save").click()
    await expect(page.get_by_text("Device updated")).to_be_visible(timeout=5_000)
    await expect(page.get_by_text("admin-laptop-renamed")).to_be_visible(timeout=5_000)


async def test_delete_device(page: Page, test_user):
    """Delete a device — removed from table."""
    _, pub = generate_keypair()
    async with async_session() as session:
        d = Device(
            name="delete-me-device",
            public_key=pub,
            preshared_key=generate_preshared_key(),
            ipv4="10.0.0.99",
            user_id=test_user.id,
        )
        session.add(d)
        await session.commit()

    await _go_to_admin_devices(page)
    await expect(page.get_by_role("cell", name="delete-me-device")).to_be_visible(timeout=5_000)

    # Click the delete (second) button in the row
    row = page.locator("tr", has_text="delete-me-device")
    await row.locator(".q-btn").nth(1).click()

    await expect(page.get_by_text("Deleted delete-me-device")).to_be_visible(timeout=5_000)
    await page.wait_for_timeout(1000)
    await expect(page.get_by_role("cell", name="delete-me-device")).not_to_be_visible()


async def test_config_dialog_shows_wg_config(page: Page, test_user):
    """Config dialog after device creation shows valid WireGuard config."""
    await _go_to_admin_devices(page)
    await page.get_by_role("button", name="Add Device").click()
    await expect(page.get_by_text("New Device")).to_be_visible(timeout=5_000)

    await page.locator("input[aria-label='Device Name']").fill("config-test-device")
    await page.get_by_role("button", name="Create").click()

    await expect(page.get_by_text("Config for config-test-device")).to_be_visible(timeout=10_000)
    await expect(page.get_by_text("[Interface]")).to_be_visible(timeout=5_000)
    await expect(page.get_by_text("[Peer]")).to_be_visible(timeout=5_000)
    await expect(page.get_by_text("PrivateKey")).to_be_visible()
    await expect(page.get_by_role("button", name="Download .conf")).to_be_visible()

    # QR code should be rendered
    await expect(page.locator(".q-dialog img")).to_be_visible(timeout=5_000)