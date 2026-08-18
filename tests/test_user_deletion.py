"""User deletion cascade tests (issue #7).

An OIDC auto-created user always has an oidc_connections row; before the
user_id FKs gained ON DELETE CASCADE, deleting such a user failed with a FK
violation and the admin Delete button silently did nothing.
"""

import pytest_asyncio
from sqlmodel import func, select

from wiregui.models.api_token import ApiToken
from wiregui.models.device import Device
from wiregui.models.mfa_method import MFAMethod
from wiregui.models.oidc_connection import OIDCConnection
from wiregui.models.rule import Rule
from wiregui.models.user import User
from wiregui.services.users import delete_user_and_cleanup

CHILD_MODELS = (Device, Rule, MFAMethod, ApiToken, OIDCConnection)


async def _child_counts(session, user_id) -> dict[str, int]:
    counts = {}
    for model in CHILD_MODELS:
        counts[model.__tablename__] = (
            await session.execute(
                select(func.count()).select_from(model).where(model.user_id == user_id)
            )
        ).scalar()
    return counts


@pytest_asyncio.fixture
async def oidc_user(session) -> User:
    """A user as created by an OIDC auto-create login, with one of every child row."""
    user = User(
        email="oidc-user@test.local",
        password_hash=None,
        role="unprivileged",
        last_signed_in_method="oidc:test-idp",
    )
    session.add(user)
    await session.flush()

    session.add(OIDCConnection(provider="test-idp", refresh_token="tok", user_id=user.id))
    session.add(Device(name="laptop", public_key="pk-oidc-user", user_id=user.id))
    session.add(MFAMethod(name="Authenticator", type="totp", payload={"secret": "s"}, user_id=user.id))
    session.add(ApiToken(token_hash="hash-oidc-user", user_id=user.id))
    session.add(Rule(action="accept", destination="10.0.0.0/8", user_id=user.id))
    await session.commit()
    await session.refresh(user)
    return user


async def test_oidc_user_fixture_has_all_child_rows(session, oidc_user):
    counts = await _child_counts(session, oidc_user.id)
    assert all(c == 1 for c in counts.values()), counts


async def test_delete_user_cascades_all_children(session, oidc_user):
    user_id = oidc_user.id
    await session.delete(oidc_user)
    await session.commit()

    assert await session.get(User, user_id) is None
    counts = await _child_counts(session, user_id)
    assert all(c == 0 for c in counts.values()), counts


async def test_delete_user_spares_global_rules_and_other_users(session, oidc_user):
    session.add(Rule(action="drop", destination="192.168.0.0/16", user_id=None))
    other = User(email="other@test.local", role="unprivileged")
    session.add(other)
    await session.flush()
    session.add(Device(name="other-dev", public_key="pk-other", user_id=other.id))
    session.add(OIDCConnection(provider="test-idp", user_id=other.id))
    await session.commit()
    other_id = other.id

    await session.delete(oidc_user)
    await session.commit()

    global_rules = (
        await session.execute(select(func.count()).select_from(Rule).where(Rule.user_id.is_(None)))
    ).scalar()
    assert global_rules == 1
    assert await session.get(User, other_id) is not None
    other_counts = await _child_counts(session, other_id)
    assert other_counts["devices"] == 1
    assert other_counts["oidc_connections"] == 1


async def test_delete_user_and_cleanup_removes_wg_peers(session, oidc_user, monkeypatch):
    deleted_devices = []

    async def fake_on_device_deleted(device):
        deleted_devices.append(device.public_key)

    monkeypatch.setattr("wiregui.services.users.on_device_deleted", fake_on_device_deleted)

    user_id = oidc_user.id
    await delete_user_and_cleanup(session, oidc_user)

    assert await session.get(User, user_id) is None
    counts = await _child_counts(session, user_id)
    assert all(c == 0 for c in counts.values()), counts
    assert deleted_devices == ["pk-oidc-user"]
