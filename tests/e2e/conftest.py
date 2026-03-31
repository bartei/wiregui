"""E2E test configuration — async Playwright browser tests against a running app."""

import os
import subprocess
import time

import pytest
import pytest_asyncio
from playwright.async_api import Browser, Page, async_playwright
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import select

from wiregui.auth.passwords import hash_password
from wiregui.config import get_settings
from wiregui.db import async_session
from wiregui.models.configuration import Configuration
from wiregui.models.user import User

FAKE_SERVER_KEY = "SFake0ServerPubKey0000000000000000000000000w="
TEST_EMAIL = "e2e-test@example.com"
TEST_PASSWORD = "testpass123"

# Dedicated port so we don't conflict with a dev instance on 13000
TEST_APP_PORT = 13001
TEST_APP_BASE = f"http://localhost:{TEST_APP_PORT}"

_CHILD_TABLES = ("devices", "rules", "mfa_methods", "api_tokens", "oidc_connections")


def pytest_addoption(parser):
    parser.addoption("--headed", action="store_true", default=False, help="Run browser in headed mode")
    parser.addoption("--slowmo", type=int, default=0, help="Slow down Playwright actions by ms")


async def _cleanup_user_by_email(email: str):
    """Delete a user and all related objects by email."""
    engine = create_async_engine(get_settings().database_url)
    async with engine.begin() as conn:
        row = (await conn.execute(
            text("SELECT id FROM users WHERE email = :email"), {"email": email}
        )).first()
        if row:
            uid = row[0]
            for table in _CHILD_TABLES:
                await conn.execute(text(f"DELETE FROM {table} WHERE user_id = :uid"), {"uid": uid})  # noqa: S608
            await conn.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": uid})
    await engine.dispose()


async def _cleanup_test_user():
    await _cleanup_user_by_email(TEST_EMAIL)


# ---------------------------------------------------------------------------
# App subprocess — shared across all e2e tests in the session
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def app_server():
    """Start WireGUI on TEST_APP_PORT for the entire test session."""
    import httpx

    env = os.environ.copy()
    env["WG_LOG_TO_FILE"] = "false"
    env["WG_PORT"] = str(TEST_APP_PORT)
    env["WG_EXTERNAL_URL"] = TEST_APP_BASE
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
            r = httpx.get(f"{TEST_APP_BASE}/api/health", timeout=1)
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


# ---------------------------------------------------------------------------
# Playwright browser — session-scoped, one browser for all tests
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="session")
async def browser(request):
    """Launch a Playwright Chromium browser for the session."""
    headed = request.config.getoption("--headed")
    slowmo = request.config.getoption("--slowmo")
    pw = await async_playwright().start()
    br = await pw.chromium.launch(headless=not headed, slow_mo=slowmo)
    yield br
    await br.close()
    await pw.stop()


@pytest_asyncio.fixture
async def page(browser: Browser):
    """Create a fresh browser context + page per test (isolated cookies/storage)."""
    context = await browser.new_context()
    pg = await context.new_page()
    yield pg
    await context.close()


# ---------------------------------------------------------------------------
# Test user fixture
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def test_user(app_server):
    """Create a test admin user, yield it, clean up after."""
    await _cleanup_test_user()

    async with async_session() as session:
        config = (await session.execute(select(Configuration).limit(1))).scalar_one_or_none()
        if config:
            if not config.server_public_key:
                config.server_public_key = FAKE_SERVER_KEY
                session.add(config)
        else:
            config = Configuration(server_public_key=FAKE_SERVER_KEY)
            session.add(config)

        user = User(
            email=TEST_EMAIL,
            password_hash=hash_password(TEST_PASSWORD),
            role="admin",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    yield user

    await _cleanup_test_user()


# ---------------------------------------------------------------------------
# Playwright helpers
# ---------------------------------------------------------------------------


async def login(page: Page, email: str = TEST_EMAIL, password: str = TEST_PASSWORD):
    """Fill the login form and submit."""
    await page.goto(f"{TEST_APP_BASE}/login")
    await page.wait_for_load_state("networkidle")
    await page.locator("input[aria-label='Email']").fill(email)
    await page.locator("input[aria-label='Password']").fill(password)
    await page.get_by_role("button", name="Sign in", exact=True).click()
