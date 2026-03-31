"""End-to-end tests for device management UI using NiceGUI's User fixture."""

import pytest
from nicegui.testing import User

from wiregui.models.user import User as UserModel
from tests.e2e.conftest import TEST_EMAIL, TEST_PASSWORD


async def _login(user: User):
    """Helper to log in via the UI."""
    await user.open("/login")
    user.find("Email").type(TEST_EMAIL)
    user.find("Password").type(TEST_PASSWORD)
    user.find("Sign in").click()
    await user.should_see("My Devices")


@pytest.mark.parametrize("user", [{"storage": {}}], indirect=True)
async def test_add_device_via_ui(user: User, test_user: UserModel):
    """Test the full flow: login → devices → add device → see it in table."""
    await _login(user)

    # Open create dialog
    user.find("Add Device").click()
    await user.should_see("New Device")

    # Fill device name and submit
    user.find("Device Name").type("Test Laptop")
    user.find("Create").click()

    # Should see config dialog with the device config
    await user.should_see("Test Laptop")


@pytest.mark.parametrize("user", [{"storage": {}}], indirect=True)
async def test_add_device_requires_name(user: User, test_user: UserModel):
    """Test that creating a device without a name shows an error."""
    await _login(user)

    # Open create dialog and submit without name
    user.find("Add Device").click()
    await user.should_see("New Device")
    user.find("Create").click()
    await user.should_see("Device name is required")
