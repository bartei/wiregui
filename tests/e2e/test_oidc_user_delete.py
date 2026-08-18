"""E2E acceptance tests for issue #7 — deleting OIDC-created users from /admin/users.

Before the cascade fix, the Delete button silently did nothing for any user with
child rows (an OIDC auto-created user always has an oidc_connections row).

The full repro test needs the mock-oidc container: docker compose up -d mock-oidc
"""

import os
import subprocess
import time

import pytest
import pytest_asyncio
from playwright.async_api import Browser, Page, expect
from sqlmodel import func, select

from wiregui.auth.passwords import hash_password
from wiregui.db import async_session
from wiregui.models.api_token import ApiToken
from wiregui.models.device import Device
from wiregui.models.mfa_method import MFAMethod
from wiregui.models.oidc_connection import OIDCConnection
from wiregui.models.rule import Rule
from wiregui.models.user import User
from tests.e2e.conftest import TEST_APP_BASE, _cleanup_user_by_email, login
from tests.e2e.test_idp_seed import _mock_oidc_yaml, _write_yaml

CHILD_MODELS = (Device, Rule, MFAMethod, ApiToken, OIDCConnection)

VICTIM_EMAIL = "e2e-oidc-victim@example.com"

# Dedicated port for the IdP-enabled app instance (13002 is used by test_idp_seed)
DELETE_APP_PORT = 13003
DELETE_APP_BASE = f"http://localhost:{DELETE_APP_PORT}"

ADMIN_EMAIL = "e2e-idp-admin@example.com"
ADMIN_PASSWORD = "adminpass123"
# The mock IdP passes the login username through as `sub`, and the app falls back
# to sub-as-email, so the username must be a full email address.
OIDC_USERNAME = "oidc-delete-me@test.local"
OIDC_EMAIL = OIDC_USERNAME


async def _seed_full_user(email: str) -> User:
    """Create a user with one of every child row type, as an OIDC login would (and more)."""
    async with async_session() as session:
        user = User(email=email, password_hash=None, role="unprivileged",
                    last_signed_in_method="oidc:test-idp")
        session.add(user)
        await session.flush()
        session.add(OIDCConnection(provider="test-idp", refresh_token="tok", user_id=user.id))
        session.add(Device(name="victim-dev", public_key="pk-e2e-victim", user_id=user.id))
        session.add(MFAMethod(name="Authenticator", type="totp", payload={"secret": "s"}, user_id=user.id))
        session.add(ApiToken(token_hash="hash-e2e-victim", user_id=user.id))
        session.add(Rule(action="accept", destination="10.99.0.0/16", user_id=user.id))
        await session.commit()
        await session.refresh(user)
        return user


async def _assert_user_fully_deleted(email: str, user_id) -> None:
    async with async_session() as session:
        remaining = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
        assert remaining is None, f"user {email} still exists"
        for model in CHILD_MODELS:
            cnt = (await session.execute(
                select(func.count()).select_from(model).where(model.user_id == user_id)
            )).scalar()
            assert cnt == 0, f"{model.__tablename__} still has rows for deleted user"


def _delete_button(page: Page, email: str):
    """The delete (second) action button in the users-table row for the given email."""
    return page.locator("tr").filter(has_text=email).locator("button").nth(1)


# ---------------------------------------------------------------------------
# Admin UI delete of a user with every child row type (standard app instance)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(autouse=True)
async def cleanup_victims():
    yield
    for email in (VICTIM_EMAIL, OIDC_EMAIL, ADMIN_EMAIL):
        await _cleanup_user_by_email(email)


async def test_admin_delete_button_removes_user_with_all_child_rows(page: Page, test_user: User):
    victim = await _seed_full_user(VICTIM_EMAIL)

    await login(page)
    await expect(page.get_by_text("My Devices")).to_be_visible(timeout=10_000)
    await page.goto(f"{TEST_APP_BASE}/admin/users")
    await expect(page.get_by_role("main").get_by_text("Users")).to_be_visible(timeout=10_000)

    await _delete_button(page, VICTIM_EMAIL).click()

    await expect(page.get_by_text(f"User {VICTIM_EMAIL} deleted")).to_be_visible(timeout=10_000)
    await expect(page.locator("tr").filter(has_text=VICTIM_EMAIL)).to_have_count(0)

    await _assert_user_fully_deleted(VICTIM_EMAIL, victim.id)


# ---------------------------------------------------------------------------
# Full issue #7 repro: OIDC auto-create login, then admin deletes via UI
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def idp_yaml_file():
    path = _write_yaml(_mock_oidc_yaml())
    yield path
    path.unlink()


@pytest.fixture(scope="module")
def app_with_idp(idp_yaml_file):
    """Start a WireGUI instance with WG_IDP_CONFIG_FILE set, on its own port."""
    import httpx

    env = os.environ.copy()
    env["WG_IDP_CONFIG_FILE"] = str(idp_yaml_file)
    env["WG_LOG_TO_FILE"] = "false"
    env["WG_PORT"] = str(DELETE_APP_PORT)
    env["WG_EXTERNAL_URL"] = DELETE_APP_BASE
    env.pop("PYTEST_CURRENT_TEST", None)
    env.pop("NICEGUI_SCREEN_TEST_PORT", None)

    proc = subprocess.Popen(
        ["uv", "run", "python", "-m", "wiregui.main"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    for _ in range(30):
        try:
            r = httpx.get(f"{DELETE_APP_BASE}/api/health", timeout=1)
            if r.status_code == 200:
                break
        except Exception:
            pass
        time.sleep(1)
    else:
        proc.kill()
        out = proc.stdout.read().decode() if proc.stdout else ""
        pytest.fail(f"App did not start in time. Output:\n{out}")

    yield proc

    proc.terminate()
    proc.wait(timeout=10)


@pytest_asyncio.fixture
async def idp_admin(app_with_idp):
    """An admin account on the IdP-enabled instance."""
    await _cleanup_user_by_email(ADMIN_EMAIL)
    async with async_session() as session:
        admin = User(email=ADMIN_EMAIL, password_hash=hash_password(ADMIN_PASSWORD), role="admin")
        session.add(admin)
        await session.commit()
        await session.refresh(admin)
    yield admin
    await _cleanup_user_by_email(ADMIN_EMAIL)


async def test_admin_deletes_oidc_autocreated_user(app_with_idp, browser: Browser, idp_admin: User):
    await _cleanup_user_by_email(OIDC_EMAIL)

    # 1) Log in via the mock IdP — auto-creates the user with an OIDC connection
    ctx = await browser.new_context()
    pg = await ctx.new_page()
    await pg.goto(f"{DELETE_APP_BASE}/auth/oidc/test-idp")
    await pg.wait_for_url("**/test-idp/authorize**", timeout=10_000)
    await pg.locator("input[name='username']").fill(OIDC_USERNAME)
    await pg.locator("input[type='submit']").click()
    await pg.wait_for_url(f"{DELETE_APP_BASE}/**", timeout=15_000)
    await pg.wait_for_load_state("networkidle")
    await expect(pg.get_by_text("My Devices")).to_be_visible(timeout=10_000)
    await ctx.close()

    async with async_session() as session:
        user = (await session.execute(select(User).where(User.email == OIDC_EMAIL))).scalar_one()
        conns = (await session.execute(
            select(OIDCConnection).where(OIDCConnection.user_id == user.id)
        )).scalars().all()
        assert len(conns) == 1, "OIDC login should have created a connection row"
        user_id = user.id

    # 2) Admin deletes the user through /admin/users — the flow issue #7 reported broken
    ctx = await browser.new_context()
    pg = await ctx.new_page()
    await pg.goto(f"{DELETE_APP_BASE}/login")
    await pg.wait_for_load_state("networkidle")
    await pg.locator("input[aria-label='Email']").fill(ADMIN_EMAIL)
    await pg.locator("input[aria-label='Password']").fill(ADMIN_PASSWORD)
    await pg.get_by_role("button", name="Sign in", exact=True).click()
    await expect(pg.get_by_text("My Devices")).to_be_visible(timeout=10_000)

    await pg.goto(f"{DELETE_APP_BASE}/admin/users")
    await expect(pg.get_by_role("main").get_by_text("Users")).to_be_visible(timeout=10_000)
    await expect(pg.locator("tr").filter(has_text=OIDC_EMAIL)).to_be_visible(timeout=10_000)

    await _delete_button(pg, OIDC_EMAIL).click()

    await expect(pg.get_by_text(f"User {OIDC_EMAIL} deleted")).to_be_visible(timeout=10_000)
    await expect(pg.locator("tr").filter(has_text=OIDC_EMAIL)).to_have_count(0)
    await ctx.close()

    # 3) Nothing left behind in the database
    await _assert_user_fully_deleted(OIDC_EMAIL, user_id)
