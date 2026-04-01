"""E2E tests for SAML authentication — mock SimpleSAMLphp IdP.

Requires mock-saml service running (docker compose up -d mock-saml).
IdP metadata: http://localhost:8080/simplesaml/saml2/idp/metadata.php
Test users: user1/user1pass, user2/user2pass
"""

import os
import subprocess
import time

import httpx
import pytest
import pytest_asyncio
from playwright.async_api import Page, expect
from sqlmodel import select

from wiregui.db import async_session
from wiregui.models.configuration import Configuration
from wiregui.models.user import User
from tests.e2e.conftest import FAKE_SERVER_KEY, _cleanup_user_by_email

MOCK_SAML_HOST = os.environ.get("MOCK_SAML_HOST", "localhost")
MOCK_SAML_METADATA_URL = f"http://{MOCK_SAML_HOST}:8080/simplesaml/saml2/idp/metadata.php"

# Separate app port for SAML tests (like OIDC IdP tests)
SAML_APP_PORT = 13003
SAML_APP_BASE = f"http://localhost:{SAML_APP_PORT}"

SAML_TEST_EMAIL = "user1@example.com"


def _fetch_idp_metadata() -> str:
    """Fetch IdP metadata XML from the mock SAML server."""
    try:
        r = httpx.get(MOCK_SAML_METADATA_URL, timeout=5)
        r.raise_for_status()
        return r.text
    except Exception:
        pytest.skip(f"Mock SAML IdP not available at {MOCK_SAML_METADATA_URL}")


def _saml_provider_config(metadata: str) -> dict:
    return {
        "id": "test-saml",
        "label": "Sign in with Mock SAML",
        "metadata": metadata,
        "sign_requests": False,
        "sign_metadata": False,
        "signed_assertion_in_resp": False,
        "signed_envelopes_in_resp": False,
        "auto_create_users": True,
        "strict": False,  # Relaxed for test IdP with expired certs
    }


@pytest_asyncio.fixture(scope="module")
async def saml_metadata():
    return _fetch_idp_metadata()


@pytest.fixture(scope="module")
def app_with_saml(saml_metadata):
    """Start a WireGUI instance with a SAML provider seeded in the DB."""
    import asyncio

    # Seed the SAML provider config into the database
    async def _seed():
        async with async_session() as session:
            config = (await session.execute(select(Configuration).limit(1))).scalar_one_or_none()
            if config is None:
                config = Configuration(server_public_key=FAKE_SERVER_KEY)
                session.add(config)
                await session.flush()

            providers = list(config.saml_identity_providers or [])
            providers = [p for p in providers if p.get("id") != "test-saml"]
            providers.append(_saml_provider_config(saml_metadata))
            config.saml_identity_providers = providers
            session.add(config)
            await session.commit()

    asyncio.get_event_loop().run_until_complete(_seed())

    env = os.environ.copy()
    env["WG_LOG_TO_FILE"] = "false"
    env["WG_PORT"] = str(SAML_APP_PORT)
    env["WG_EXTERNAL_URL"] = SAML_APP_BASE
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
            r = httpx.get(f"{SAML_APP_BASE}/api/health", timeout=1)
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

    # Clean up seeded provider and test user
    async def _cleanup():
        await _cleanup_user_by_email(SAML_TEST_EMAIL)
        async with async_session() as session:
            config = (await session.execute(select(Configuration).limit(1))).scalar_one_or_none()
            if config:
                config.saml_identity_providers = [
                    p for p in (config.saml_identity_providers or []) if p.get("id") != "test-saml"
                ]
                session.add(config)
                await session.commit()

    asyncio.get_event_loop().run_until_complete(_cleanup())


async def test_saml_button_visible_on_login(app_with_saml, page: Page):
    """Login page shows SAML provider button."""
    await page.goto(f"{SAML_APP_BASE}/login")
    await page.wait_for_load_state("networkidle")
    await expect(page.get_by_text("Sign in with Mock SAML")).to_be_visible(timeout=10_000)


async def test_saml_redirect_to_idp(app_with_saml, page: Page):
    """Clicking SAML login redirects to the SimpleSAMLphp IdP login page."""
    await page.goto(f"{SAML_APP_BASE}/auth/saml/test-saml")
    # Should redirect to the SimpleSAMLphp SSO service
    await page.wait_for_url(f"**{MOCK_SAML_HOST}:8080/simplesaml/**", timeout=30_000)


async def test_saml_sp_metadata_endpoint(app_with_saml, page: Page):
    """SP metadata endpoint returns valid XML."""
    response = await page.request.get(f"{SAML_APP_BASE}/auth/saml/test-saml/metadata")
    assert response.status == 200
    body = await response.text()
    assert "EntityDescriptor" in body
    assert "AssertionConsumerService" in body


async def test_full_saml_login_flow(app_with_saml, page: Page):
    """Full SAML SSO flow: app → IdP login → callback → authenticated."""
    await page.goto(f"{SAML_APP_BASE}/auth/saml/test-saml")
    await page.wait_for_url(f"**{MOCK_SAML_HOST}:8080/simplesaml/**", timeout=30_000)

    # SimpleSAMLphp login form
    await page.locator("input[name='username']").fill("user1")
    await page.locator("input[name='password']").fill("password")
    await page.locator("button[type='submit'], input[type='submit']").first.click()

    # Should redirect back to the app after SAML response
    await page.wait_for_url(f"{SAML_APP_BASE}/**", timeout=15_000)
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(3000)

    assert "/login" not in page.url, f"SAML login failed — still on login page: {page.url}"

    # Verify user was auto-created in DB
    async with async_session() as session:
        result = await session.execute(select(User).where(User.email == SAML_TEST_EMAIL))
        user = result.scalar_one_or_none()
        assert user is not None, f"Expected user {SAML_TEST_EMAIL} to be auto-created"
        assert user.last_signed_in_method == "saml:test-saml"