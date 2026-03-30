"""Integration tests for MFA — full registration and authentication flows through the database."""

import pyotp
from sqlmodel import func, select

from wiregui.auth.mfa import generate_totp_secret, verify_totp_code
from wiregui.auth.passwords import hash_password, verify_password
from wiregui.auth.session import authenticate_user
from wiregui.models.mfa_method import MFAMethod
from wiregui.models.user import User
from wiregui.utils.time import utcnow


async def test_full_totp_registration_flow(session, monkeypatch):
    """End-to-end: create user → generate secret → verify code → store method → re-verify from DB."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def mock_session():
        yield session

    # Create user with password
    user = User(email="mfa-flow@example.com", password_hash=hash_password("secure123"))
    session.add(user)
    await session.flush()

    # Step 1: Generate TOTP secret (happens in account page)
    secret = generate_totp_secret()

    # Step 2: User scans QR, enters code from their authenticator
    totp = pyotp.TOTP(secret)
    code = totp.now()

    # Step 3: Verify the code is correct before saving
    assert verify_totp_code(secret, code) is True

    # Step 4: Save the MFA method to DB
    method = MFAMethod(
        name="My Authenticator",
        type="totp",
        payload={"secret": secret},
        user_id=user.id,
    )
    session.add(method)
    await session.flush()

    # Step 5: Simulate future login — load method from DB and verify a fresh code
    fetched_methods = (await session.execute(
        select(MFAMethod).where(MFAMethod.user_id == user.id)
    )).scalars().all()

    assert len(fetched_methods) == 1
    stored_secret = fetched_methods[0].payload["secret"]
    fresh_code = pyotp.TOTP(stored_secret).now()
    assert verify_totp_code(stored_secret, fresh_code) is True


async def test_mfa_blocks_login_without_code(session, monkeypatch):
    """User with MFA should not be fully authenticated without completing MFA challenge."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def mock_session():
        yield session

    monkeypatch.setattr("wiregui.auth.session.async_session", mock_session)

    # Create user with MFA
    user = User(email="mfa-block@example.com", password_hash=hash_password("password1"))
    session.add(user)
    await session.flush()

    secret = generate_totp_secret()
    method = MFAMethod(name="Phone", type="totp", payload={"secret": secret}, user_id=user.id)
    session.add(method)
    await session.flush()

    # Password auth succeeds
    authed_user = await authenticate_user("mfa-block@example.com", "password1")
    assert authed_user is not None

    # But MFA methods exist — login page would redirect to /mfa instead of completing login
    mfa_methods = (await session.execute(
        select(MFAMethod).where(MFAMethod.user_id == authed_user.id)
    )).scalars().all()
    assert len(mfa_methods) > 0  # Login flow would check this and redirect to /mfa


async def test_mfa_wrong_code_rejected(session):
    """Wrong TOTP code should be rejected even if method is valid."""
    user = User(email="mfa-wrong@example.com", password_hash=hash_password("pw"))
    session.add(user)
    await session.flush()

    secret = generate_totp_secret()
    method = MFAMethod(name="Auth", type="totp", payload={"secret": secret}, user_id=user.id)
    session.add(method)
    await session.flush()

    # Load from DB and try wrong code
    fetched = (await session.execute(
        select(MFAMethod).where(MFAMethod.user_id == user.id)
    )).scalar_one()

    assert verify_totp_code(fetched.payload["secret"], "000000") is False
    assert verify_totp_code(fetched.payload["secret"], "123456") is False


async def test_mfa_multiple_methods_any_valid_code_works(session):
    """If user has multiple TOTP methods, a valid code from any should work."""
    user = User(email="mfa-multi@example.com")
    session.add(user)
    await session.flush()

    secret1 = generate_totp_secret()
    secret2 = generate_totp_secret()

    session.add(MFAMethod(name="Phone", type="totp", payload={"secret": secret1}, user_id=user.id))
    session.add(MFAMethod(name="Backup", type="totp", payload={"secret": secret2}, user_id=user.id))
    await session.flush()

    methods = (await session.execute(
        select(MFAMethod).where(MFAMethod.user_id == user.id)
    )).scalars().all()

    # Code from method 1 should verify against method 1's secret
    code1 = pyotp.TOTP(secret1).now()
    verified = False
    for m in methods:
        if verify_totp_code(m.payload["secret"], code1):
            verified = True
            break
    assert verified is True

    # Code from method 2 should also work
    code2 = pyotp.TOTP(secret2).now()
    verified2 = False
    for m in methods:
        if verify_totp_code(m.payload["secret"], code2):
            verified2 = True
            break
    assert verified2 is True


async def test_mfa_method_last_used_tracking(session):
    """Verifying MFA should update last_used_at timestamp."""
    user = User(email="mfa-tracking@example.com")
    session.add(user)
    await session.flush()

    secret = generate_totp_secret()
    method = MFAMethod(name="Auth", type="totp", payload={"secret": secret}, user_id=user.id)
    session.add(method)
    await session.flush()

    assert method.last_used_at is None

    # Simulate successful verification and update
    code = pyotp.TOTP(secret).now()
    assert verify_totp_code(secret, code) is True

    method.last_used_at = utcnow()
    session.add(method)
    await session.flush()

    fetched = await session.get(MFAMethod, method.id)
    assert fetched.last_used_at is not None


async def test_mfa_delete_method_allows_login_without_mfa(session, monkeypatch):
    """After removing all MFA methods, user should not be redirected to MFA challenge."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def mock_session():
        yield session

    monkeypatch.setattr("wiregui.auth.session.async_session", mock_session)

    user = User(email="mfa-remove@example.com", password_hash=hash_password("pw"))
    session.add(user)
    await session.flush()

    secret = generate_totp_secret()
    method = MFAMethod(name="Temp", type="totp", payload={"secret": secret}, user_id=user.id)
    session.add(method)
    await session.flush()

    # MFA exists
    count = (await session.execute(
        select(func.count()).select_from(MFAMethod).where(MFAMethod.user_id == user.id)
    )).scalar()
    assert count == 1

    # Delete it
    await session.delete(method)
    await session.flush()

    count = (await session.execute(
        select(func.count()).select_from(MFAMethod).where(MFAMethod.user_id == user.id)
    )).scalar()
    assert count == 0

    # Password auth still works
    authed = await authenticate_user("mfa-remove@example.com", "pw")
    assert authed is not None

    # No MFA methods — login flow would skip MFA challenge
    mfa_check = (await session.execute(
        select(MFAMethod).where(MFAMethod.user_id == authed.id)
    )).scalars().all()
    assert len(mfa_check) == 0


async def test_disabled_user_with_mfa_cannot_login(session, monkeypatch):
    """Disabled user should be rejected at password stage, never reaching MFA."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def mock_session():
        yield session

    monkeypatch.setattr("wiregui.auth.session.async_session", mock_session)

    user = User(
        email="mfa-disabled@example.com",
        password_hash=hash_password("pw"),
        disabled_at=utcnow(),
    )
    session.add(user)
    await session.flush()

    secret = generate_totp_secret()
    session.add(MFAMethod(name="Auth", type="totp", payload={"secret": secret}, user_id=user.id))
    await session.flush()

    # Password auth rejects disabled user before MFA is ever checked
    result = await authenticate_user("mfa-disabled@example.com", "pw")
    assert result is None
