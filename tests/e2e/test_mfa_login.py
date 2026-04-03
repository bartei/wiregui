"""E2E tests for MFA login flow — login with TOTP redirects to /mfa challenge page."""

import pyotp
import pytest_asyncio
from playwright.async_api import Page, expect

from wiregui.auth.mfa import generate_totp_secret
from wiregui.auth.passwords import hash_password
from wiregui.db import async_session
from wiregui.models.mfa_method import MFAMethod
from wiregui.models.user import User
from tests.e2e.conftest import (
    FAKE_SERVER_KEY,
    TEST_APP_BASE,
    TEST_PASSWORD,
    _cleanup_user_by_email,
)

MFA_EMAIL = "e2e-mfa@example.com"
MFA_PASSWORD = "mfapass123"
TOTP_SECRET = generate_totp_secret()


@pytest_asyncio.fixture
async def mfa_user(app_server):
    """Create a user with a TOTP MFA method, clean up after."""
    await _cleanup_user_by_email(MFA_EMAIL)

    async with async_session() as session:
        from sqlmodel import select
        from wiregui.models.configuration import Configuration

        config = (await session.execute(select(Configuration).limit(1))).scalar_one_or_none()
        if config:
            if not config.server_public_key:
                config.server_public_key = FAKE_SERVER_KEY
                session.add(config)
        else:
            config = Configuration(server_public_key=FAKE_SERVER_KEY)
            session.add(config)

        user = User(
            email=MFA_EMAIL,
            password_hash=hash_password(MFA_PASSWORD),
            role="admin",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        mfa = MFAMethod(
            name="Test TOTP",
            type="totp",
            payload={"secret": TOTP_SECRET},
            user_id=user.id,
        )
        session.add(mfa)
        await session.commit()

    yield user

    await _cleanup_user_by_email(MFA_EMAIL)


async def _login_mfa_user(page: Page):
    """Fill login form for the MFA user and submit."""
    await page.goto(f"{TEST_APP_BASE}/login")
    await page.wait_for_load_state("networkidle")
    await page.locator("input[aria-label='Email']").fill(MFA_EMAIL)
    await page.locator("input[aria-label='Password']").fill(MFA_PASSWORD)
    await page.get_by_role("button", name="Sign in", exact=True).click()


async def test_mfa_login_redirects_to_challenge(page: Page, mfa_user: User):
    """Login with MFA-enabled user redirects to /mfa challenge page."""
    await _login_mfa_user(page)
    await expect(page.get_by_text("Two-Factor Authentication")).to_be_visible(timeout=10_000)
    await expect(page.locator("input[aria-label='Authentication Code']")).to_be_visible()


async def test_mfa_valid_totp_completes_login(page: Page, mfa_user: User):
    """Entering a valid TOTP code on /mfa completes login."""
    await _login_mfa_user(page)
    await expect(page.get_by_text("Two-Factor Authentication")).to_be_visible(timeout=10_000)

    code = pyotp.TOTP(TOTP_SECRET).now()
    await page.locator("input[aria-label='Authentication Code']").fill(code)
    await page.get_by_role("button", name="Verify").click()

    await expect(page.get_by_text("My Devices")).to_be_visible(timeout=10_000)


async def test_mfa_invalid_code_shows_error(page: Page, mfa_user: User):
    """Entering an invalid TOTP code shows error and stays on /mfa."""
    await _login_mfa_user(page)
    await expect(page.get_by_text("Two-Factor Authentication")).to_be_visible(timeout=10_000)

    await page.locator("input[aria-label='Authentication Code']").fill("000000")
    await page.get_by_role("button", name="Verify").click()

    await expect(page.get_by_text("Invalid code")).to_be_visible(timeout=5_000)
    await expect(page.get_by_text("Two-Factor Authentication")).to_be_visible()


async def test_mfa_cancel_returns_to_login(page: Page, mfa_user: User):
    """Clicking Cancel on /mfa clears session and returns to login."""
    await _login_mfa_user(page)
    await expect(page.get_by_text("Two-Factor Authentication")).to_be_visible(timeout=10_000)

    await page.get_by_role("button", name="Cancel").click()
    await expect(page.get_by_role("button", name="Sign in", exact=True)).to_be_visible(timeout=10_000)