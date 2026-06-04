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


async def test_add_device_with_relay_subnets(page: Page, test_user: UserModel):
    """Test creating a device with relay subnets for site-to-site VPN."""
    await login(page)
    await expect(page.get_by_text("My Devices")).to_be_visible(timeout=10_000)

    await page.get_by_role("button", name="Add Device").click()
    await expect(page.get_by_text("New Device")).to_be_visible(timeout=5_000)

    await page.locator("input[aria-label='Device Name']").fill("Gateway Router")
    
    # Scroll to relay configuration section
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    
    # Fill in relay subnets
    await page.locator("input[aria-label='Routed Subnets (optional)']").fill("192.168.1.0/24, 10.20.0.0/16")
    
    await page.get_by_role("button", name="Create").click()

    # Should see config dialog with the device name
    await expect(page.get_by_text("Config for Gateway Router")).to_be_visible(timeout=10_000)
