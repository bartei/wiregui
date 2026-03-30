"""TOTP Multi-Factor Authentication using pyotp."""

import io
from urllib.parse import quote

import pyotp
import qrcode
import qrcode.image.svg


def generate_totp_secret() -> str:
    """Generate a new random TOTP secret."""
    return pyotp.random_base32()


def get_totp_uri(secret: str, email: str, issuer: str = "WireGUI") -> str:
    """Build an otpauth:// URI for QR code scanning."""
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=issuer)


def verify_totp_code(secret: str, code: str) -> bool:
    """Verify a TOTP code against a secret. Allows 1 window of clock drift."""
    return pyotp.TOTP(secret).verify(code, valid_window=1)


def generate_totp_qr_svg(uri: str) -> str:
    """Generate an SVG QR code for a TOTP provisioning URI."""
    qr = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage)
    buf = io.BytesIO()
    qr.save(buf)
    return buf.getvalue().decode()
