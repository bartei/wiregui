"""End-to-end tests for login, logout, and auth guard flows."""

from playwright.async_api import Page, expect

from wiregui.db import async_session
from wiregui.models.user import User as UserModel
from wiregui.utils.time import utcnow
from tests.e2e.conftest import TEST_APP_BASE, TEST_EMAIL, TEST_PASSWORD, login


async def test_login_valid_credentials(page: Page, test_user: UserModel):
    """Valid login redirects to devices page."""
    await login(page)
    await expect(page.get_by_text("My Devices")).to_be_visible(timeout=10_000)


async def test_login_invalid_password(page: Page, test_user: UserModel):
    """Wrong password shows error and stays on login page."""
    await login(page, password="wrongpassword")
    await expect(page.get_by_text("Invalid email or password")).to_be_visible(timeout=10_000)
    await expect(page.get_by_role("button", name="Sign in", exact=True)).to_be_visible()


async def test_login_nonexistent_email(page: Page, test_user: UserModel):
    """Nonexistent email shows error."""
    await login(page, email="nobody@nowhere.com")
    await expect(page.get_by_text("Invalid email or password")).to_be_visible(timeout=10_000)
    await expect(page.get_by_role("button", name="Sign in", exact=True)).to_be_visible()


async def test_login_disabled_user(page: Page, test_user: UserModel):
    """Disabled user cannot log in."""
    async with async_session() as session:
        u = await session.get(UserModel, test_user.id)
        u.disabled_at = utcnow()
        session.add(u)
        await session.commit()

    try:
        await login(page)
        await expect(page.get_by_text("Invalid email or password")).to_be_visible(timeout=10_000)
        await expect(page.get_by_role("button", name="Sign in", exact=True)).to_be_visible()
    finally:
        async with async_session() as session:
            u = await session.get(UserModel, test_user.id)
            u.disabled_at = None
            session.add(u)
            await session.commit()


async def test_logout(page: Page, test_user: UserModel):
    """Logout clears session and redirects to login."""
    await login(page)
    await expect(page.get_by_text("My Devices")).to_be_visible(timeout=10_000)

    await page.get_by_text("Logout").click()
    await expect(page.get_by_role("button", name="Sign in", exact=True)).to_be_visible(timeout=10_000)


async def test_unauthenticated_redirect(page: Page, test_user: UserModel):
    """Accessing a protected page without auth redirects to login."""
    await page.goto(f"{TEST_APP_BASE}/devices")
    await expect(page.get_by_role("button", name="Sign in", exact=True)).to_be_visible(timeout=10_000)
