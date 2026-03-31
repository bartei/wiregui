"""E2E tests for magic link request page."""

from playwright.async_api import Page, expect

from tests.e2e.conftest import TEST_APP_BASE, TEST_EMAIL
from wiregui.models.user import User


async def test_magic_link_page_renders(page: Page, test_user: User):
    """Magic link request page renders with email input and submit button."""
    await page.goto(f"{TEST_APP_BASE}/auth/magic-link")
    await page.wait_for_load_state("networkidle")
    await expect(page.get_by_text("Sign in with magic link")).to_be_visible(timeout=10_000)
    await expect(page.locator("input[aria-label='Email']")).to_be_visible()
    await expect(page.get_by_role("button", name="Send Magic Link")).to_be_visible()
    await expect(page.get_by_role("button", name="Back to login")).to_be_visible()


async def test_magic_link_shows_success_on_submit(page: Page, test_user: User):
    """Submitting an email shows success message (regardless of whether account exists)."""
    await page.goto(f"{TEST_APP_BASE}/auth/magic-link")
    await page.wait_for_load_state("networkidle")
    await page.locator("input[aria-label='Email']").fill(TEST_EMAIL)
    await page.get_by_role("button", name="Send Magic Link").click()
    await expect(page.get_by_text("a sign-in link has been sent")).to_be_visible(timeout=5_000)


async def test_magic_link_empty_email_shows_error(page: Page, test_user: User):
    """Submitting without email shows error."""
    await page.goto(f"{TEST_APP_BASE}/auth/magic-link")
    await page.wait_for_load_state("networkidle")
    await page.get_by_role("button", name="Send Magic Link").click()
    await expect(page.get_by_text("Enter your email")).to_be_visible(timeout=5_000)


async def test_magic_link_back_to_login(page: Page, test_user: User):
    """Back to login button navigates to login page."""
    await page.goto(f"{TEST_APP_BASE}/auth/magic-link")
    await page.wait_for_load_state("networkidle")
    await page.get_by_role("button", name="Back to login").click()
    await expect(page.get_by_role("button", name="Sign in", exact=True)).to_be_visible(timeout=10_000)