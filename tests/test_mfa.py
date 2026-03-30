"""Tests for TOTP MFA functionality."""

import pyotp

from wiregui.auth.mfa import (
    generate_totp_qr_svg,
    generate_totp_secret,
    get_totp_uri,
    verify_totp_code,
)
from wiregui.models.mfa_method import MFAMethod
from wiregui.models.user import User


# --- TOTP secret generation ---


def test_generate_secret():
    secret = generate_totp_secret()
    assert len(secret) == 32  # base32 encoded
    assert secret.isalpha() or any(c.isdigit() for c in secret)


def test_generate_secret_unique():
    s1 = generate_totp_secret()
    s2 = generate_totp_secret()
    assert s1 != s2


# --- TOTP URI ---


def test_get_totp_uri():
    uri = get_totp_uri("JBSWY3DPEHPK3PXP", "user@example.com")
    assert uri.startswith("otpauth://totp/")
    assert "user%40example.com" in uri or "user@example.com" in uri
    assert "secret=JBSWY3DPEHPK3PXP" in uri
    assert "issuer=WireGUI" in uri


def test_get_totp_uri_custom_issuer():
    uri = get_totp_uri("SECRET", "test@test.com", issuer="MyVPN")
    assert "issuer=MyVPN" in uri


# --- TOTP verification ---


def test_verify_valid_code():
    secret = generate_totp_secret()
    totp = pyotp.TOTP(secret)
    code = totp.now()
    assert verify_totp_code(secret, code) is True


def test_verify_invalid_code():
    secret = generate_totp_secret()
    assert verify_totp_code(secret, "000000") is False


def test_verify_wrong_secret():
    secret1 = generate_totp_secret()
    secret2 = generate_totp_secret()
    code = pyotp.TOTP(secret1).now()
    assert verify_totp_code(secret2, code) is False


def test_verify_empty_code():
    secret = generate_totp_secret()
    assert verify_totp_code(secret, "") is False


# --- QR code generation ---


def test_generate_qr_svg():
    uri = get_totp_uri("SECRET", "test@test.com")
    svg = generate_totp_qr_svg(uri)
    assert "<svg" in svg
    assert "</svg>" in svg


# --- MFA method model integration ---


async def test_create_totp_method(session):
    user = User(email="mfa-test@example.com")
    session.add(user)
    await session.flush()

    secret = generate_totp_secret()
    method = MFAMethod(
        name="My Phone",
        type="totp",
        payload={"secret": secret},
        user_id=user.id,
    )
    session.add(method)
    await session.flush()

    from sqlmodel import select
    fetched = (await session.execute(
        select(MFAMethod).where(MFAMethod.user_id == user.id)
    )).scalar_one()

    assert fetched.name == "My Phone"
    assert fetched.type == "totp"
    stored_secret = fetched.payload["secret"]
    code = pyotp.TOTP(stored_secret).now()
    assert verify_totp_code(stored_secret, code) is True


async def test_user_multiple_mfa_methods(session):
    user = User(email="multi-mfa@example.com")
    session.add(user)
    await session.flush()

    m1 = MFAMethod(name="Phone", type="totp", payload={"secret": generate_totp_secret()}, user_id=user.id)
    m2 = MFAMethod(name="Backup", type="totp", payload={"secret": generate_totp_secret()}, user_id=user.id)
    session.add_all([m1, m2])
    await session.flush()

    from sqlmodel import select, func
    count = (await session.execute(
        select(func.count()).select_from(MFAMethod).where(MFAMethod.user_id == user.id)
    )).scalar()
    assert count == 2
