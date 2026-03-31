"""End-to-end tests for account page — password, TOTP, API tokens, deletion."""

from unittest.mock import patch

import pytest
from nicegui import ui
from nicegui.testing import User

from wiregui.models.user import User as UserModel
from tests.e2e.conftest import TEST_EMAIL, TEST_PASSWORD


async def _login(user: User):
    """Log in and navigate to account page."""
    await user.open("/login")
    user.find("Email").type(TEST_EMAIL)
    user.find("Password").type(TEST_PASSWORD)
    user.find("Sign in").click()
    await user.should_see("My Devices")
    await user.open("/account")
    await user.should_see("Account Settings")


@pytest.mark.parametrize("user", [{"storage": {}}], indirect=True)
async def test_change_password(user: User, test_user: UserModel):
    """Test changing password: fill form, submit, verify success."""
    await _login(user)

    user.find("Current Password").type(TEST_PASSWORD)
    user.find("New Password").type("newpass12345")
    user.find("Confirm Password").type("newpass12345")
    user.find("Update Password").click()
    await user.should_see("Password changed")


@pytest.mark.parametrize("user", [{"storage": {}}], indirect=True)
async def test_change_password_wrong_current(user: User, test_user: UserModel):
    """Test that wrong current password is rejected."""
    await _login(user)

    user.find("Current Password").type("wrongpassword")
    user.find("New Password").type("newpass12345")
    user.find("Confirm Password").type("newpass12345")
    user.find("Update Password").click()
    await user.should_see("Wrong current password")


@pytest.mark.parametrize("user", [{"storage": {}}], indirect=True)
async def test_change_password_mismatch(user: User, test_user: UserModel):
    """Test that mismatched passwords are rejected."""
    await _login(user)

    user.find("Current Password").type(TEST_PASSWORD)
    user.find("New Password").type("newpass12345")
    user.find("Confirm Password").type("differentpass")
    user.find("Update Password").click()
    await user.should_see("Passwords don't match")


@pytest.mark.parametrize("user", [{"storage": {}}], indirect=True)
async def test_change_password_too_short(user: User, test_user: UserModel):
    """Test that short passwords are rejected."""
    await _login(user)

    user.find("Current Password").type(TEST_PASSWORD)
    user.find("New Password").type("short")
    user.find("Confirm Password").type("short")
    user.find("Update Password").click()
    await user.should_see("Min 8 characters")


@pytest.mark.parametrize("user", [{"storage": {}}], indirect=True)
async def test_create_api_token(user: User, test_user: UserModel):
    """Test creating an API token and seeing the copy banner."""
    await _login(user)

    await user.should_see("No API tokens.")
    user.find("Add API Token").click()
    await user.should_see("Copy now")


@pytest.mark.parametrize("user", [{"storage": {}}], indirect=True)
async def test_totp_registration_flow(user: User, test_user: UserModel):
    """Test starting TOTP registration shows QR and verify form."""
    with patch("wiregui.pages.account.generate_totp_secret", return_value="JBSWY3DPEHPK3PXP"), \
         patch("wiregui.pages.account.generate_totp_qr_svg", return_value='<svg></svg>'), \
         patch("wiregui.pages.account.get_totp_uri", return_value="otpauth://totp/WireGUI:test?secret=JBSWY3DPEHPK3PXP"):

        await _login(user)

        await user.should_see("No MFA methods configured.")
        user.find("Add TOTP Method").click()
        await user.should_see("Register TOTP Authenticator")
        await user.should_see("JBSWY3DPEHPK3PXP")
        await user.should_see("Verify & Save")


@pytest.mark.parametrize("user", [{"storage": {}}], indirect=True)
async def test_totp_verify_invalid_code(user: User, test_user: UserModel):
    """Test that an invalid TOTP code is rejected."""
    with patch("wiregui.pages.account.generate_totp_secret", return_value="JBSWY3DPEHPK3PXP"), \
         patch("wiregui.pages.account.generate_totp_qr_svg", return_value='<svg></svg>'), \
         patch("wiregui.pages.account.get_totp_uri", return_value="otpauth://totp/WireGUI:test?secret=JBSWY3DPEHPK3PXP"):

        await _login(user)

        user.find("Add TOTP Method").click()
        await user.should_see("Register TOTP Authenticator")

        user.find("6-digit verification code").type("000000")
        user.find("Verify & Save").click()
        await user.should_see("Invalid code")


@pytest.mark.parametrize("user", [{"storage": {}}], indirect=True)
async def test_delete_account(user: User, test_user: UserModel):
    """Test account deletion flow with email confirmation."""
    # Create a second admin first so deletion is allowed
    from wiregui.db import async_session
    from wiregui.auth.passwords import hash_password

    async with async_session() as session:
        second_admin = UserModel(
            email="admin2@example.com",
            password_hash=hash_password("admin2pass"),
            role="admin",
        )
        session.add(second_admin)
        await session.commit()

    try:
        await _login(user)

        user.find("Delete Your Account").click()
        await user.should_see("Delete Your Account?")

        user.find(ui.input).type(TEST_EMAIL)
        user.find("Delete My Account").click()

        # Should redirect to login
        await user.should_see("Sign in")
    finally:
        # Clean up second admin
        async with async_session() as session:
            from sqlmodel import select
            a2 = (await session.execute(select(UserModel).where(UserModel.email == "admin2@example.com"))).scalar_one_or_none()
            if a2:
                await session.delete(a2)
                await session.commit()
