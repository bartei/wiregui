"""E2E tests for IdP seeding from YAML config file (WG_IDP_CONFIG_FILE).

Uses async Playwright for the full OIDC flow test (real browser → mock-oidc server).
The seed function tests run without a browser.
"""

import os
import subprocess
import tempfile
import time
from pathlib import Path

import pytest
import pytest_asyncio
import yaml
from playwright.async_api import Page, expect
from sqlmodel import select

from wiregui.auth.seed import seed_idp_providers
from wiregui.db import async_session
from wiregui.models.configuration import Configuration
from tests.e2e.conftest import FAKE_SERVER_KEY


MOCK_OIDC_HOST = os.environ.get("MOCK_OIDC_HOST", "localhost")
MOCK_OIDC_DISCOVERY = f"http://{MOCK_OIDC_HOST}:9000/test-idp/.well-known/openid-configuration"

# Separate port for the IdP-seeded app instance
IDP_APP_PORT = 13002
IDP_APP_BASE = f"http://localhost:{IDP_APP_PORT}"


def _write_yaml(data: dict) -> Path:
    f = tempfile.NamedTemporaryFile(suffix=".yaml", delete=False, mode="w")
    yaml.safe_dump(data, f)
    f.close()
    return Path(f.name)


def _mock_oidc_yaml() -> dict:
    return {
        "openid_connect_providers": [
            {
                "id": "test-idp",
                "label": "Sign in with Mock IdP",
                "scope": "openid email profile",
                "client_id": "wiregui-test",
                "client_secret": "wiregui-test-secret",
                "discovery_document_uri": MOCK_OIDC_DISCOVERY,
                "auto_create_users": True,
            }
        ]
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def clean_config():
    """Ensure a Configuration row exists with no IdP providers, and restore after."""
    async with async_session() as session:
        config = (await session.execute(select(Configuration).limit(1))).scalar_one_or_none()
        orig_oidc = list(config.openid_connect_providers or []) if config else []
        orig_saml = list(config.saml_identity_providers or []) if config else []

        if config is None:
            config = Configuration(server_public_key=FAKE_SERVER_KEY)
            session.add(config)

        config.openid_connect_providers = []
        config.saml_identity_providers = []
        session.add(config)
        await session.commit()

    yield

    async with async_session() as session:
        config = (await session.execute(select(Configuration).limit(1))).scalar_one()
        config.openid_connect_providers = orig_oidc
        config.saml_identity_providers = orig_saml
        session.add(config)
        await session.commit()


# ---------------------------------------------------------------------------
# Seed function tests (no browser needed)
# ---------------------------------------------------------------------------


async def test_seed_noop_when_no_config_file(clean_config, monkeypatch):
    monkeypatch.setattr("wiregui.auth.seed.get_settings", lambda: type("S", (), {"idp_config_file": None})())
    await seed_idp_providers()
    async with async_session() as session:
        config = (await session.execute(select(Configuration).limit(1))).scalar_one()
        assert config.openid_connect_providers == []


async def test_seed_noop_when_file_missing(clean_config, monkeypatch):
    monkeypatch.setattr("wiregui.auth.seed.get_settings", lambda: type("S", (), {"idp_config_file": "/nonexistent/idps.yaml"})())
    await seed_idp_providers()
    async with async_session() as session:
        config = (await session.execute(select(Configuration).limit(1))).scalar_one()
        assert config.openid_connect_providers == []


async def test_seed_adds_oidc_provider(clean_config, monkeypatch):
    path = _write_yaml(_mock_oidc_yaml())
    monkeypatch.setattr("wiregui.auth.seed.get_settings", lambda: type("S", (), {"idp_config_file": str(path)})())
    await seed_idp_providers()
    async with async_session() as session:
        config = (await session.execute(select(Configuration).limit(1))).scalar_one()
        assert len(config.openid_connect_providers) == 1
        assert config.openid_connect_providers[0]["id"] == "test-idp"
    path.unlink()


async def test_seed_adds_saml_provider(clean_config, monkeypatch):
    yaml_data = {"saml_identity_providers": [{"id": "test-saml", "label": "Test SAML IdP", "metadata": "<EntityDescriptor/>", "sign_requests": True, "sign_metadata": False, "signed_assertion_in_resp": True, "signed_envelopes_in_resp": True, "auto_create_users": False}]}
    path = _write_yaml(yaml_data)
    monkeypatch.setattr("wiregui.auth.seed.get_settings", lambda: type("S", (), {"idp_config_file": str(path)})())
    await seed_idp_providers()
    async with async_session() as session:
        config = (await session.execute(select(Configuration).limit(1))).scalar_one()
        assert len(config.saml_identity_providers) == 1
        assert config.saml_identity_providers[0]["id"] == "test-saml"
    path.unlink()


async def test_seed_upserts_existing_provider(clean_config, monkeypatch):
    async with async_session() as session:
        config = (await session.execute(select(Configuration).limit(1))).scalar_one()
        config.openid_connect_providers = [{"id": "test-idp", "label": "Old Label", "client_id": "old-client"}]
        session.add(config)
        await session.commit()

    yaml_data = {"openid_connect_providers": [{"id": "test-idp", "label": "Updated Label", "client_id": "new-client", "client_secret": "new-secret", "discovery_document_uri": MOCK_OIDC_DISCOVERY}]}
    path = _write_yaml(yaml_data)
    monkeypatch.setattr("wiregui.auth.seed.get_settings", lambda: type("S", (), {"idp_config_file": str(path)})())
    await seed_idp_providers()
    async with async_session() as session:
        config = (await session.execute(select(Configuration).limit(1))).scalar_one()
        assert config.openid_connect_providers[0]["label"] == "Updated Label"
        assert config.openid_connect_providers[0]["client_id"] == "new-client"
    path.unlink()


async def test_seed_preserves_providers_not_in_yaml(clean_config, monkeypatch):
    async with async_session() as session:
        config = (await session.execute(select(Configuration).limit(1))).scalar_one()
        config.openid_connect_providers = [{"id": "manual-provider", "label": "Manually Added", "client_id": "manual"}]
        session.add(config)
        await session.commit()

    yaml_data = {"openid_connect_providers": [{"id": "yaml-provider", "label": "From YAML", "client_id": "yaml-client", "client_secret": "yaml-secret", "discovery_document_uri": MOCK_OIDC_DISCOVERY}]}
    path = _write_yaml(yaml_data)
    monkeypatch.setattr("wiregui.auth.seed.get_settings", lambda: type("S", (), {"idp_config_file": str(path)})())
    await seed_idp_providers()
    async with async_session() as session:
        config = (await session.execute(select(Configuration).limit(1))).scalar_one()
        ids = {p["id"] for p in config.openid_connect_providers}
        assert ids == {"manual-provider", "yaml-provider"}
    path.unlink()


async def test_seed_invalid_yaml(clean_config, monkeypatch):
    f = tempfile.NamedTemporaryFile(suffix=".yaml", delete=False, mode="w")
    f.write(": : : invalid yaml [[[")
    f.close()
    path = Path(f.name)
    monkeypatch.setattr("wiregui.auth.seed.get_settings", lambda: type("S", (), {"idp_config_file": str(path)})())
    await seed_idp_providers()
    async with async_session() as session:
        config = (await session.execute(select(Configuration).limit(1))).scalar_one()
        assert config.openid_connect_providers == []
    path.unlink()


# ---------------------------------------------------------------------------
# Playwright browser tests — full OIDC login flow via mock-oidc
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def idp_yaml_file():
    path = _write_yaml(_mock_oidc_yaml())
    yield path
    path.unlink()


@pytest.fixture(scope="module")
def app_with_idp(idp_yaml_file):
    """Start a WireGUI instance with WG_IDP_CONFIG_FILE set."""
    import httpx

    env = os.environ.copy()
    env["WG_IDP_CONFIG_FILE"] = str(idp_yaml_file)
    env["WG_LOG_TO_FILE"] = "false"
    env["WG_PORT"] = str(IDP_APP_PORT)
    env["WG_EXTERNAL_URL"] = IDP_APP_BASE
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
            r = httpx.get(f"{IDP_APP_BASE}/api/health", timeout=1)
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


async def test_oidc_button_visible_on_login(app_with_idp, page: Page):
    await page.goto(f"{IDP_APP_BASE}/login")
    await page.wait_for_load_state("networkidle")
    await expect(page.get_by_text("Sign in with Mock IdP")).to_be_visible(timeout=10_000)


async def test_full_oidc_login_flow(app_with_idp, page: Page):
    """Click the OIDC button → mock-oidc login → redirected back → authenticated."""
    await page.goto(f"{IDP_APP_BASE}/auth/oidc/test-idp")
    await page.wait_for_url("**/test-idp/authorize**", timeout=10_000)

    await page.locator("input[name='username']").fill("oidc-e2e-user@test.local")
    await page.locator("input[type='submit']").click()

    await page.wait_for_url(f"{IDP_APP_BASE}/**", timeout=15_000)
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(3000)

    assert "/login" not in page.url, f"OIDC login failed — still on login page: {page.url}"
    await expect(page.get_by_text("My Devices")).to_be_visible(timeout=10_000)
