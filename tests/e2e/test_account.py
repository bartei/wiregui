"""End-to-end tests for account page — password, API tokens, TOTP, deletion."""

from playwright.async_api import Page, expect
from sqlmodel import select

from wiregui.auth.passwords import hash_password
from wiregui.db import async_session
from wiregui.models.user import User as UserModel
from tests.e2e.conftest import TEST_APP_BASE, TEST_EMAIL, TEST_PASSWORD, login


async def _login_to_account(page: Page):
    """Log in and navigate to account page."""
    await login(page)
    await expect(page.get_by_text("My Devices")).to_be_visible(timeout=10_000)
    await page.goto(f"{TEST_APP_BASE}/account")
    await expect(page.get_by_text("Account Settings")).to_be_visible(timeout=10_000)


async def test_change_password(page: Page, test_user: UserModel):
    await _login_to_account(page)
    await page.locator("input[aria-label='Current Password']").fill(TEST_PASSWORD)
    await page.locator("input[aria-label='New Password']").fill("newpass12345")
    await page.locator("input[aria-label='Confirm Password']").fill("newpass12345")
    await page.get_by_role("button", name="Update Password").click()
    await expect(page.get_by_text("Password changed")).to_be_visible(timeout=5_000)


async def test_change_password_wrong_current(page: Page, test_user: UserModel):
    await _login_to_account(page)
    await page.locator("input[aria-label='Current Password']").fill("wrongpassword")
    await page.locator("input[aria-label='New Password']").fill("newpass12345")
    await page.locator("input[aria-label='Confirm Password']").fill("newpass12345")
    await page.get_by_role("button", name="Update Password").click()
    await expect(page.get_by_text("Wrong current password")).to_be_visible(timeout=5_000)


async def test_change_password_mismatch(page: Page, test_user: UserModel):
    await _login_to_account(page)
    await page.locator("input[aria-label='Current Password']").fill(TEST_PASSWORD)
    await page.locator("input[aria-label='New Password']").fill("newpass12345")
    await page.locator("input[aria-label='Confirm Password']").fill("differentpass")
    await page.get_by_role("button", name="Update Password").click()
    await expect(page.get_by_text("Passwords don't match")).to_be_visible(timeout=5_000)


async def test_change_password_too_short(page: Page, test_user: UserModel):
    await _login_to_account(page)
    await page.locator("input[aria-label='Current Password']").fill(TEST_PASSWORD)
    await page.locator("input[aria-label='New Password']").fill("short")
    await page.locator("input[aria-label='Confirm Password']").fill("short")
    await page.get_by_role("button", name="Update Password").click()
    await expect(page.get_by_text("Min 8 characters")).to_be_visible(timeout=5_000)


async def test_create_api_token(page: Page, test_user: UserModel):
    await _login_to_account(page)
    await expect(page.get_by_text("No API tokens.")).to_be_visible()
    await page.get_by_role("button", name="Add API Token").click()
    await expect(page.get_by_text("Copy now")).to_be_visible(timeout=5_000)


async def test_totp_registration_flow(page: Page, test_user: UserModel):
    """Test starting TOTP registration shows QR and verify form."""
    await _login_to_account(page)
    await expect(page.get_by_text("No MFA methods configured.")).to_be_visible()
    await page.get_by_role("button", name="Add TOTP Method").click()
    await expect(page.get_by_text("Register TOTP Authenticator")).to_be_visible(timeout=5_000)
    await expect(page.get_by_role("button", name="Verify & Save")).to_be_visible()


async def test_totp_verify_invalid_code(page: Page, test_user: UserModel):
    await _login_to_account(page)
    await page.get_by_role("button", name="Add TOTP Method").click()
    await expect(page.get_by_text("Register TOTP Authenticator")).to_be_visible(timeout=5_000)
    await page.locator("input[aria-label='6-digit verification code']").fill("000000")
    await page.get_by_role("button", name="Verify & Save").click()
    await expect(page.get_by_text("Invalid code")).to_be_visible(timeout=5_000)


async def test_delete_account(page: Page, test_user: UserModel):
    """Test account deletion flow with email confirmation."""
    async with async_session() as session:
        second_admin = UserModel(
            email="admin2@example.com",
            password_hash=hash_password("admin2pass"),
            role="admin",
        )
        session.add(second_admin)
        await session.commit()

    try:
        await _login_to_account(page)
        await page.get_by_role("button", name="Delete Your Account").click()
        await expect(page.get_by_text("Delete Your Account?")).to_be_visible(timeout=5_000)
        await page.locator(".q-dialog input").fill(TEST_EMAIL)
        await page.get_by_role("button", name="Delete My Account").click()
        await expect(page.get_by_role("button", name="Sign in", exact=True)).to_be_visible(timeout=10_000)
    finally:
        async with async_session() as session:
            a2 = (await session.execute(
                select(UserModel).where(UserModel.email == "admin2@example.com")
            )).scalar_one_or_none()
            if a2:
                await session.delete(a2)
                await session.commit()
