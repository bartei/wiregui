"""End-to-end tests for device management UI."""

from playwright.async_api import Page, expect

from wiregui.models.user import User as UserModel
from tests.e2e.conftest import login


async def test_add_device_via_ui(page: Page, test_user: UserModel):
    """Test the full flow: login → devices → add device → see it in table."""
    await login(page)
    await expect(page.get_by_text("My Devices")).to_be_visible(timeout=10_000)

    await page.get_by_role("button", name="Add Device").click()
    await expect(page.get_by_text("New Device")).to_be_visible(timeout=5_000)

    await page.locator("input[aria-label='Device Name']").fill("Test Laptop")
    await page.get_by_role("button", name="Create").click()

    # Should see config dialog with the device name
    await expect(page.get_by_text("Config for Test Laptop")).to_be_visible(timeout=10_000)


async def test_add_device_requires_name(page: Page, test_user: UserModel):
    """Test that creating a device without a name shows an error."""
    await login(page)
    await expect(page.get_by_text("My Devices")).to_be_visible(timeout=10_000)

    await page.get_by_role("button", name="Add Device").click()
    await expect(page.get_by_text("New Device")).to_be_visible(timeout=5_000)
    await page.get_by_role("button", name="Create").click()
    await expect(page.get_by_text("Device name is required")).to_be_visible(timeout=5_000)


async def test_user_device_dialog_has_no_relay_field(page: Page, test_user: UserModel):
    """Relay/site-to-site subnets are admin-only — the field must not appear on
    the end-user device dialog."""
    await login(page)
    await expect(page.get_by_text("My Devices")).to_be_visible(timeout=10_000)

    await page.get_by_role("button", name="Add Device").click()
    await expect(page.get_by_text("New Device")).to_be_visible(timeout=5_000)

    # The admin-only relay subnet input must be absent here.
    await expect(page.locator("input[aria-label='Routed Subnets (optional)']")).to_have_count(0)


# Note: relay subnet acceptance coverage (create + invalid rejection) lives in
# tests/e2e/test_admin_devices.py, since the capability is admin-only.
