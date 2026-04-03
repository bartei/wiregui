"""E2E tests for admin settings page — client defaults, security, OIDC/SAML providers."""

import pytest_asyncio
from playwright.async_api import Page, expect
from sqlmodel import select

from wiregui.db import async_session
from wiregui.models.configuration import Configuration
from wiregui.models.user import User
from tests.e2e.conftest import TEST_APP_BASE, login


@pytest_asyncio.fixture(autouse=True)
async def reset_config(app_server):
    """Snapshot config before test, restore after."""
    async with async_session() as session:
        c = (await session.execute(select(Configuration).limit(1))).scalar_one_or_none()
        if not c:
            yield
            return
        snap = {
            "default_client_endpoint": c.default_client_endpoint,
            "default_client_dns": list(c.default_client_dns),
            "default_client_mtu": c.default_client_mtu,
            "default_client_persistent_keepalive": c.default_client_persistent_keepalive,
            "default_client_allowed_ips": list(c.default_client_allowed_ips),
            "vpn_session_duration": c.vpn_session_duration,
            "local_auth_enabled": c.local_auth_enabled,
            "allow_unprivileged_device_management": c.allow_unprivileged_device_management,
            "allow_unprivileged_device_configuration": c.allow_unprivileged_device_configuration,
            "openid_connect_providers": list(c.openid_connect_providers or []),
            "saml_identity_providers": list(c.saml_identity_providers or []),
        }
        cid = c.id

    yield

    async with async_session() as session:
        c = await session.get(Configuration, cid)
        if c:
            for k, v in snap.items():
                setattr(c, k, v)
            session.add(c)
            await session.commit()


async def _go_to_settings(page: Page):
    await login(page)
    await expect(page.get_by_text("My Devices")).to_be_visible(timeout=10_000)
    await page.goto(f"{TEST_APP_BASE}/admin/settings")
    await expect(page.get_by_text("Default Client Configuration")).to_be_visible(timeout=10_000)


# --- Client Defaults ---


async def test_save_client_defaults(page: Page, test_user: User):
    """Save endpoint, DNS, MTU, keepalive, allowed IPs — verify persists in DB."""
    await _go_to_settings(page)

    endpoint = page.locator("input[aria-label='Endpoint']")
    await endpoint.clear()
    await endpoint.fill("vpn.test.local")

    dns = page.locator("input[aria-label='DNS Servers']")
    await dns.clear()
    await dns.fill("9.9.9.9, 149.112.112.112")

    mtu = page.locator("input[aria-label='MTU']")
    await mtu.clear()
    await mtu.fill("1420")

    keepalive = page.locator("input[aria-label='Persistent Keepalive']")
    await keepalive.clear()
    await keepalive.fill("30")

    allowed = page.locator("input[aria-label='Allowed IPs']")
    await allowed.clear()
    await allowed.fill("10.0.0.0/8, 192.168.0.0/16")

    await page.get_by_role("button", name="Save Defaults").click()
    await expect(page.get_by_text("Client defaults saved")).to_be_visible(timeout=5_000)

    # Verify in DB
    async with async_session() as session:
        c = (await session.execute(select(Configuration).limit(1))).scalar_one()
        assert c.default_client_endpoint == "vpn.test.local"
        assert c.default_client_dns == ["9.9.9.9", "149.112.112.112"]
        assert c.default_client_mtu == 1420
        assert c.default_client_persistent_keepalive == 30
        assert c.default_client_allowed_ips == ["10.0.0.0/8", "192.168.0.0/16"]


async def test_client_defaults_persist_on_reload(page: Page, test_user: User):
    """Saved defaults are reflected after page reload."""
    # Set values via DB
    async with async_session() as session:
        c = (await session.execute(select(Configuration).limit(1))).scalar_one()
        c.default_client_endpoint = "reload-test.vpn"
        c.default_client_dns = ["8.8.8.8"]
        c.default_client_mtu = 1500
        c.default_client_persistent_keepalive = 15
        c.default_client_allowed_ips = ["172.16.0.0/12"]
        session.add(c)
        await session.commit()

    await _go_to_settings(page)

    await expect(page.locator("input[aria-label='Endpoint']")).to_have_value("reload-test.vpn")
    await expect(page.locator("input[aria-label='DNS Servers']")).to_have_value("8.8.8.8")
    await expect(page.locator("input[aria-label='MTU']")).to_have_value("1500")
    await expect(page.locator("input[aria-label='Persistent Keepalive']")).to_have_value("15")
    await expect(page.locator("input[aria-label='Allowed IPs']")).to_have_value("172.16.0.0/12")


# --- Security ---


async def test_save_security_local_auth_toggle(page: Page, test_user: User):
    """Toggle local auth off — verify in DB."""
    await _go_to_settings(page)

    # Find the local auth switch and toggle it off
    switch = page.locator(".q-toggle", has_text="Local Authentication")
    await switch.click()

    await page.get_by_role("button", name="Save Security Settings").click()
    await expect(page.get_by_text("Security settings saved")).to_be_visible(timeout=5_000)

    async with async_session() as session:
        c = (await session.execute(select(Configuration).limit(1))).scalar_one()
        assert c.local_auth_enabled is False


async def test_save_vpn_session_duration(page: Page, test_user: User):
    """Change VPN session duration — verify in DB."""
    await _go_to_settings(page)

    await page.locator("label:has-text('VPN Session Duration')").click()
    await page.get_by_role("option", name="Every Day").click()

    await page.get_by_role("button", name="Save Security Settings").click()
    await expect(page.get_by_text("Security settings saved")).to_be_visible(timeout=5_000)

    async with async_session() as session:
        c = (await session.execute(select(Configuration).limit(1))).scalar_one()
        assert c.vpn_session_duration == 86400


async def test_save_unprivileged_toggles(page: Page, test_user: User):
    """Toggle unprivileged device management/configuration — verify in DB."""
    await _go_to_settings(page)

    await page.locator(".q-toggle", has_text="Allow Unprivileged Device Management").click()
    await page.locator(".q-toggle", has_text="Allow Unprivileged Device Configuration").click()

    await page.get_by_role("button", name="Save Security Settings").click()
    await expect(page.get_by_text("Security settings saved")).to_be_visible(timeout=5_000)

    async with async_session() as session:
        c = (await session.execute(select(Configuration).limit(1))).scalar_one()
        # Toggled from default (True) to False
        assert c.allow_unprivileged_device_management is False
        assert c.allow_unprivileged_device_configuration is False


# --- OIDC Providers ---


async def test_add_oidc_provider(page: Page, test_user: User):
    """Add an OIDC provider — appears in table and DB."""
    await _go_to_settings(page)

    await page.get_by_role("button", name="Add OIDC Provider").click()
    await expect(page.get_by_text("OIDC Provider", exact=True)).to_be_visible(timeout=5_000)

    await page.locator(".q-dialog input[aria-label='Config ID']").fill("e2e-test-oidc")
    await page.locator(".q-dialog input[aria-label='Label']").fill("E2E Test IdP")
    await page.locator(".q-dialog input[aria-label='Client ID']").fill("test-client-id")
    await page.locator(".q-dialog input[aria-label='Client Secret']").fill("test-client-secret")
    await page.locator(".q-dialog input[aria-label='Discovery Document URI']").fill("https://idp.test/.well-known/openid-configuration")

    await page.locator(".q-dialog").get_by_role("button", name="Save").click()
    await expect(page.get_by_text("OIDC provider 'E2E Test IdP' saved")).to_be_visible(timeout=5_000)

    await expect(page.get_by_role("cell", name="e2e-test-oidc")).to_be_visible(timeout=5_000)

    # Verify in DB
    async with async_session() as session:
        c = (await session.execute(select(Configuration).limit(1))).scalar_one()
        provider = next((p for p in c.openid_connect_providers if p["id"] == "e2e-test-oidc"), None)
        assert provider is not None
        assert provider["label"] == "E2E Test IdP"
        assert provider["client_id"] == "test-client-id"


async def test_delete_oidc_provider(page: Page, test_user: User):
    """Delete an OIDC provider — removed from table and DB."""
    # Seed a provider
    async with async_session() as session:
        c = (await session.execute(select(Configuration).limit(1))).scalar_one()
        providers = list(c.openid_connect_providers or [])
        providers.append({
            "id": "delete-me-oidc", "label": "Delete Me", "scope": "openid",
            "client_id": "x", "client_secret": "x",
            "discovery_document_uri": "https://x/.well-known/openid-configuration",
        })
        c.openid_connect_providers = providers
        session.add(c)
        await session.commit()

    await _go_to_settings(page)
    await expect(page.get_by_role("cell", name="delete-me-oidc")).to_be_visible(timeout=5_000)

    row = page.locator("tr", has_text="delete-me-oidc")
    await row.locator(".q-btn").first.click()

    await expect(page.get_by_text("OIDC provider deleted")).to_be_visible(timeout=5_000)
    await page.wait_for_timeout(500)
    await expect(page.get_by_role("cell", name="delete-me-oidc")).not_to_be_visible()

    # Verify in DB
    async with async_session() as session:
        c = (await session.execute(select(Configuration).limit(1))).scalar_one()
        assert not any(p["id"] == "delete-me-oidc" for p in c.openid_connect_providers)


# --- SAML Providers ---


async def test_add_saml_provider(page: Page, test_user: User):
    """Add a SAML provider — appears in table and DB."""
    await _go_to_settings(page)

    await page.get_by_role("button", name="Add SAML Provider").click()
    await expect(page.get_by_text("SAML Identity Provider", exact=True)).to_be_visible(timeout=5_000)

    await page.locator(".q-dialog input[aria-label='Config ID']").fill("e2e-test-saml")
    await page.locator(".q-dialog input[aria-label='Label']").fill("E2E SAML IdP")
    await page.locator(".q-dialog textarea").fill("<EntityDescriptor>test</EntityDescriptor>")

    await page.locator(".q-dialog").get_by_role("button", name="Save").click()
    await expect(page.get_by_text("SAML provider 'E2E SAML IdP' saved")).to_be_visible(timeout=5_000)

    await expect(page.get_by_role("cell", name="e2e-test-saml")).to_be_visible(timeout=5_000)

    # Verify in DB
    async with async_session() as session:
        c = (await session.execute(select(Configuration).limit(1))).scalar_one()
        provider = next((p for p in c.saml_identity_providers if p["id"] == "e2e-test-saml"), None)
        assert provider is not None
        assert provider["label"] == "E2E SAML IdP"


async def test_delete_saml_provider(page: Page, test_user: User):
    """Delete a SAML provider — removed from table and DB."""
    async with async_session() as session:
        c = (await session.execute(select(Configuration).limit(1))).scalar_one()
        providers = list(c.saml_identity_providers or [])
        providers.append({
            "id": "delete-me-saml", "label": "Delete Me SAML",
            "metadata": "<EntityDescriptor/>",
        })
        c.saml_identity_providers = providers
        session.add(c)
        await session.commit()

    await _go_to_settings(page)
    await expect(page.get_by_role("cell", name="delete-me-saml")).to_be_visible(timeout=5_000)

    row = page.locator("tr", has_text="delete-me-saml")
    await row.locator(".q-btn").first.click()

    await expect(page.get_by_text("SAML provider deleted")).to_be_visible(timeout=5_000)
    await page.wait_for_timeout(500)
    await expect(page.get_by_role("cell", name="delete-me-saml")).not_to_be_visible()

    # Verify in DB
    async with async_session() as session:
        c = (await session.execute(select(Configuration).limit(1))).scalar_one()
        assert not any(p["id"] == "delete-me-saml" for p in c.saml_identity_providers)