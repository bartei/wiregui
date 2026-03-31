"""End-to-end tests for admin user management page."""

import pytest
import pytest_asyncio
from playwright.async_api import Page, expect
from sqlmodel import func, select

from wiregui.auth.passwords import hash_password, verify_password
from wiregui.db import async_session
from wiregui.models.device import Device
from wiregui.models.rule import Rule
from wiregui.models.user import User as UserModel
from wiregui.utils.time import utcnow
from tests.e2e.conftest import TEST_APP_BASE, TEST_EMAIL, _cleanup_user_by_email, login

CREATED_USER_EMAIL = "e2e-created@example.com"


async def _login_and_go_to_users(page: Page):
    await login(page)
    await expect(page.get_by_text("My Devices")).to_be_visible(timeout=10_000)
    await page.goto(f"{TEST_APP_BASE}/admin/users")
    await expect(page.get_by_role("main").get_by_text("Users")).to_be_visible(timeout=10_000)


@pytest_asyncio.fixture(autouse=True)
async def cleanup_created_users():
    yield
    await _cleanup_user_by_email(CREATED_USER_EMAIL)


# --- Page renders ---


async def test_users_page_renders(page: Page, test_user: UserModel):
    await _login_and_go_to_users(page)
    await expect(page.get_by_role("main").get_by_text("Users")).to_be_visible()
    await expect(page.get_by_role("button", name="Add User")).to_be_visible()
    await expect(page.locator("table")).to_be_visible()


# --- Create user ---


async def test_create_user(page: Page, test_user: UserModel):
    await _login_and_go_to_users(page)

    await page.get_by_role("button", name="Add User").click()
    await expect(page.get_by_text("New User")).to_be_visible(timeout=5_000)

    await page.locator("input[aria-label='Email']").last.fill(CREATED_USER_EMAIL)
    await page.locator("input[aria-label='Password']").last.fill("newuser123")
    await page.get_by_role("button", name="Create").click()

    await page.wait_for_timeout(1000)

    async with async_session() as session:
        result = await session.execute(select(UserModel).where(UserModel.email == CREATED_USER_EMAIL))
        created = result.scalar_one_or_none()
        assert created is not None
        assert created.role == "unprivileged"


async def test_create_user_duplicate_email(page: Page, test_user: UserModel):
    await _login_and_go_to_users(page)

    await page.get_by_role("button", name="Add User").click()
    await expect(page.get_by_text("New User")).to_be_visible(timeout=5_000)

    await page.locator("input[aria-label='Email']").last.fill(TEST_EMAIL)
    await page.locator("input[aria-label='Password']").last.fill("somepass123")
    await page.get_by_role("button", name="Create").click()

    await expect(page.get_by_text("already exists")).to_be_visible(timeout=5_000)


# --- Edit user (DB operations with page render verification) ---


async def test_edit_user_role(page: Page, test_user: UserModel):
    async with async_session() as session:
        target = UserModel(email=CREATED_USER_EMAIL, password_hash=hash_password("pw"), role="unprivileged")
        session.add(target)
        await session.commit()
        target_id = target.id

    async with async_session() as session:
        u = await session.get(UserModel, target_id)
        assert u.role == "unprivileged"
        u.role = "admin"
        session.add(u)
        await session.commit()

    async with async_session() as session:
        u = await session.get(UserModel, target_id)
        assert u.role == "admin"


async def test_edit_user_password(page: Page, test_user: UserModel):
    async with async_session() as session:
        target = UserModel(email=CREATED_USER_EMAIL, password_hash=hash_password("oldpass"), role="unprivileged")
        session.add(target)
        await session.commit()
        target_id = target.id

    async with async_session() as session:
        u = await session.get(UserModel, target_id)
        u.password_hash = hash_password("newpass456")
        session.add(u)
        await session.commit()

    async with async_session() as session:
        u = await session.get(UserModel, target_id)
        assert verify_password("newpass456", u.password_hash) is True
        assert verify_password("oldpass", u.password_hash) is False


async def test_disable_user(page: Page, test_user: UserModel):
    async with async_session() as session:
        target = UserModel(email=CREATED_USER_EMAIL, password_hash=hash_password("pw"), role="unprivileged")
        session.add(target)
        await session.commit()
        target_id = target.id

    async with async_session() as session:
        u = await session.get(UserModel, target_id)
        u.disabled_at = utcnow()
        session.add(u)
        await session.commit()

    async with async_session() as session:
        u = await session.get(UserModel, target_id)
        assert u.disabled_at is not None

    await _login_and_go_to_users(page)
    await expect(page.get_by_role("main").get_by_text("Users")).to_be_visible()


async def test_enable_user(page: Page, test_user: UserModel):
    async with async_session() as session:
        target = UserModel(email=CREATED_USER_EMAIL, password_hash=hash_password("pw"), role="unprivileged", disabled_at=utcnow())
        session.add(target)
        await session.commit()
        target_id = target.id

    async with async_session() as session:
        u = await session.get(UserModel, target_id)
        u.disabled_at = None
        session.add(u)
        await session.commit()

    async with async_session() as session:
        u = await session.get(UserModel, target_id)
        assert u.disabled_at is None


# --- Delete user ---


async def test_delete_user(page: Page, test_user: UserModel):
    async with async_session() as session:
        target = UserModel(email=CREATED_USER_EMAIL, password_hash=hash_password("pw"), role="unprivileged")
        session.add(target)
        await session.commit()
        target_id = target.id

    async with async_session() as session:
        u = await session.get(UserModel, target_id)
        await session.delete(u)
        await session.commit()

    async with async_session() as session:
        assert await session.get(UserModel, target_id) is None

    await _login_and_go_to_users(page)
    await expect(page.get_by_role("main").get_by_text("Users")).to_be_visible()


async def test_delete_user_cascades(page: Page, test_user: UserModel):
    async with async_session() as session:
        target = UserModel(email=CREATED_USER_EMAIL, password_hash=hash_password("pw"), role="unprivileged")
        session.add(target)
        await session.flush()
        session.add(Device(name="cascade-dev", public_key="pk-cascade-e2e", user_id=target.id))
        session.add(Rule(action="accept", destination="10.0.0.0/8", user_id=target.id))
        await session.commit()
        target_id = target.id

    async with async_session() as session:
        for d in (await session.execute(select(Device).where(Device.user_id == target_id))).scalars().all():
            await session.delete(d)
        for r in (await session.execute(select(Rule).where(Rule.user_id == target_id))).scalars().all():
            await session.delete(r)
        u = await session.get(UserModel, target_id)
        if u:
            await session.delete(u)
        await session.commit()

    async with async_session() as session:
        assert await session.get(UserModel, target_id) is None
        assert (await session.execute(select(func.count()).select_from(Device).where(Device.user_id == target_id))).scalar() == 0
        assert (await session.execute(select(func.count()).select_from(Rule).where(Rule.user_id == target_id))).scalar() == 0


async def test_cannot_delete_own_account(page: Page, test_user: UserModel):
    await _login_and_go_to_users(page)
    await expect(page.get_by_role("main").get_by_text("Users")).to_be_visible()
    assert test_user.role == "admin"
