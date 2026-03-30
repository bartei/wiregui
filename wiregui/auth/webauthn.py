"""WebAuthn (FIDO2) MFA via the webauthn library.

Registration and authentication ceremonies for platform (native) and
cross-platform (portable/security key) authenticators.
"""

import json
from uuid import UUID

from loguru import logger
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import bytes_to_base64url, base64url_to_bytes
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from wiregui.config import get_settings


def _rp_id() -> str:
    """Get the Relying Party ID from the external URL hostname."""
    from urllib.parse import urlparse
    return urlparse(get_settings().external_url).hostname


def _rp_name() -> str:
    return "WireGUI"


def _origin() -> str:
    return get_settings().external_url


def create_registration_options(user_id: UUID, user_email: str, existing_credentials: list[dict] = None) -> dict:
    """Generate WebAuthn registration options to send to the browser.

    Returns a dict with 'options' (serialized for JSON) and 'challenge' (to store in session).
    """
    exclude = []
    for cred in (existing_credentials or []):
        cred_id = cred.get("credential_id")
        if cred_id:
            exclude.append(PublicKeyCredentialDescriptor(id=base64url_to_bytes(cred_id)))

    options = generate_registration_options(
        rp_id=_rp_id(),
        rp_name=_rp_name(),
        user_id=str(user_id).encode(),
        user_name=user_email,
        user_display_name=user_email,
        exclude_credentials=exclude,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )

    # Serialize for JSON transport
    from webauthn.helpers import options_to_json
    return {
        "options_json": options_to_json(options),
        "challenge": bytes_to_base64url(options.challenge),
    }


def verify_registration(credential_json: str, challenge: str) -> dict:
    """Verify a WebAuthn registration response from the browser.

    Returns a dict with credential data to store in MFAMethod.payload.
    """
    verification = verify_registration_response(
        credential=credential_json,
        expected_challenge=base64url_to_bytes(challenge),
        expected_rp_id=_rp_id(),
        expected_origin=_origin(),
    )

    return {
        "credential_id": bytes_to_base64url(verification.credential_id),
        "public_key": bytes_to_base64url(verification.credential_public_key),
        "sign_count": verification.sign_count,
        "attestation_type": verification.fmt if hasattr(verification, 'fmt') else "none",
    }


def create_authentication_options(credentials: list[dict]) -> dict:
    """Generate WebAuthn authentication options for existing credentials.

    Returns a dict with 'options' (serialized) and 'challenge' (to store in session).
    """
    allow = []
    for cred in credentials:
        cred_id = cred.get("credential_id")
        if cred_id:
            allow.append(PublicKeyCredentialDescriptor(id=base64url_to_bytes(cred_id)))

    options = generate_authentication_options(
        rp_id=_rp_id(),
        allow_credentials=allow,
        user_verification=UserVerificationRequirement.PREFERRED,
    )

    from webauthn.helpers import options_to_json
    return {
        "options_json": options_to_json(options),
        "challenge": bytes_to_base64url(options.challenge),
    }


def verify_authentication(credential_json: str, challenge: str, stored_credential: dict) -> dict:
    """Verify a WebAuthn authentication response.

    Returns updated credential data (new sign_count).
    """
    verification = verify_authentication_response(
        credential=credential_json,
        expected_challenge=base64url_to_bytes(challenge),
        expected_rp_id=_rp_id(),
        expected_origin=_origin(),
        credential_public_key=base64url_to_bytes(stored_credential["public_key"]),
        credential_current_sign_count=stored_credential.get("sign_count", 0),
    )

    return {
        "new_sign_count": verification.new_sign_count,
    }
