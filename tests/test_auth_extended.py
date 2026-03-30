"""Extended auth tests — OIDC registration, WebAuthn options, session edge cases."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from wiregui.auth.passwords import hash_password
from wiregui.auth.session import authenticate_user
from wiregui.models.user import User
from wiregui.utils.time import utcnow


# ========== Session / authenticate_user edge cases ==========


async def test_authenticate_user_no_password_hash(session, monkeypatch):
    """Users without a password (OIDC-only) should not authenticate via password."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def mock_session():
        yield session

    monkeypatch.setattr("wiregui.auth.session.async_session", mock_session)

    user = User(email="no-pw@test.com", password_hash=None)
    session.add(user)
    await session.flush()

    result = await authenticate_user("no-pw@test.com", "anything")
    assert result is None


async def test_authenticate_user_disabled(session, monkeypatch):
    """Disabled users should not authenticate."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def mock_session():
        yield session

    monkeypatch.setattr("wiregui.auth.session.async_session", mock_session)

    user = User(email="disabled-auth@test.com", password_hash=hash_password("pw"), disabled_at=utcnow())
    session.add(user)
    await session.flush()

    result = await authenticate_user("disabled-auth@test.com", "pw")
    assert result is None


async def test_authenticate_user_nonexistent(session, monkeypatch):
    """Nonexistent email should return None."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def mock_session():
        yield session

    monkeypatch.setattr("wiregui.auth.session.async_session", mock_session)

    result = await authenticate_user("ghost@nowhere.com", "pw")
    assert result is None


# ========== OIDC provider registration ==========


async def test_register_providers_from_config(session, monkeypatch):
    """register_providers should register configured OIDC providers with authlib."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def mock_session():
        yield session

    monkeypatch.setattr("wiregui.auth.oidc.async_session", mock_session)

    from wiregui.models.configuration import Configuration
    config = Configuration(openid_connect_providers=[
        {
            "id": "test-reg",
            "label": "Test",
            "scope": "openid email",
            "client_id": "cid",
            "client_secret": "cs",
            "discovery_document_uri": "https://idp.test/.well-known/openid-configuration",
        }
    ])
    session.add(config)
    await session.flush()

    with patch("wiregui.auth.oidc.oauth") as mock_oauth:
        from wiregui.auth.oidc import register_providers
        await register_providers()
        mock_oauth.register.assert_called_once()
        call_kwargs = mock_oauth.register.call_args[1]
        assert call_kwargs["name"] == "test-reg"
        assert call_kwargs["client_id"] == "cid"


async def test_get_client_unknown_provider():
    """get_client should raise for unregistered providers."""
    import pytest
    from wiregui.auth.oidc import get_client
    with pytest.raises(ValueError, match="not registered"):
        get_client("nonexistent-provider-xyz")


# ========== WebAuthn options ==========


def test_webauthn_registration_options(monkeypatch):
    """create_registration_options should return valid options and challenge."""
    monkeypatch.setattr("wiregui.auth.webauthn.get_settings", lambda: type("S", (), {
        "external_url": "https://vpn.example.com",
    })())

    from wiregui.auth.webauthn import create_registration_options
    user_id = uuid4()
    result = create_registration_options(user_id, "user@example.com")

    assert "options_json" in result
    assert "challenge" in result
    assert len(result["challenge"]) > 10
    assert "user@example.com" in result["options_json"]


def test_webauthn_registration_options_with_excludes(monkeypatch):
    """Existing credentials should be excluded from registration options."""
    monkeypatch.setattr("wiregui.auth.webauthn.get_settings", lambda: type("S", (), {
        "external_url": "https://vpn.example.com",
    })())

    from wiregui.auth.webauthn import create_registration_options
    existing = [{"credential_id": "AQIDBA"}]  # base64url of bytes [1,2,3,4]
    result = create_registration_options(uuid4(), "user@example.com", existing)
    assert "options_json" in result


def test_webauthn_authentication_options(monkeypatch):
    """create_authentication_options should accept credential descriptors."""
    monkeypatch.setattr("wiregui.auth.webauthn.get_settings", lambda: type("S", (), {
        "external_url": "https://vpn.example.com",
    })())

    from wiregui.auth.webauthn import create_authentication_options
    credentials = [{"credential_id": "AQIDBA"}]
    result = create_authentication_options(credentials)
    assert "options_json" in result
    assert "challenge" in result


# ========== Events — rule update/delete with rebuild ==========


@patch("wiregui.services.events.get_settings")
@patch("wiregui.services.events.firewall")
async def test_on_rule_updated_triggers_rebuild(mock_fw, mock_settings):
    """on_rule_updated should rebuild the user's firewall chain."""
    mock_settings.return_value.wg_enabled = True
    mock_fw.rebuild_all_rules = AsyncMock()

    from wiregui.models.rule import Rule
    from wiregui.services.events import on_rule_updated

    # Need to mock the DB call inside _rebuild_user_chain
    with patch("wiregui.services.events.async_session") as mock_session_factory:
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        # Mock the select results
        mock_rules_result = MagicMock()
        mock_rules_result.scalars.return_value.all.return_value = []
        mock_devices_result = MagicMock()
        mock_devices_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(side_effect=[mock_rules_result, mock_devices_result])

        mock_session_factory.return_value = mock_session

        rule = Rule(action="accept", destination="10.0.0.0/8", user_id="a1b2c3d4-0000-0000-0000-000000000000")
        await on_rule_updated(rule)

        mock_fw.rebuild_all_rules.assert_awaited_once()


@patch("wiregui.services.events.get_settings")
@patch("wiregui.services.events.firewall")
async def test_on_rule_deleted_triggers_rebuild(mock_fw, mock_settings):
    """on_rule_deleted should rebuild the user's firewall chain."""
    mock_settings.return_value.wg_enabled = True
    mock_fw.rebuild_all_rules = AsyncMock()

    from wiregui.models.rule import Rule
    from wiregui.services.events import on_rule_deleted

    with patch("wiregui.services.events.async_session") as mock_session_factory:
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_rules_result = MagicMock()
        mock_rules_result.scalars.return_value.all.return_value = []
        mock_devices_result = MagicMock()
        mock_devices_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(side_effect=[mock_rules_result, mock_devices_result])

        mock_session_factory.return_value = mock_session

        rule = Rule(action="drop", destination="0.0.0.0/0", user_id="a1b2c3d4-0000-0000-0000-000000000000")
        await on_rule_deleted(rule)

        mock_fw.rebuild_all_rules.assert_awaited_once()


@patch("wiregui.services.events.get_settings")
async def test_on_rule_deleted_skips_when_disabled(mock_settings):
    """Rule events should be no-ops when WG is disabled."""
    mock_settings.return_value.wg_enabled = False

    from wiregui.models.rule import Rule
    from wiregui.services.events import on_rule_deleted, on_rule_updated

    rule = Rule(action="drop", destination="0.0.0.0/0", user_id="a1b2c3d4-0000-0000-0000-000000000000")
    await on_rule_updated(rule)  # Should not raise
    await on_rule_deleted(rule)  # Should not raise
