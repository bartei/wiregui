"""SAML SP-initiated SSO via python3-saml."""

from loguru import logger
from onelogin.saml2.auth import OneLogin_Saml2_Auth
from onelogin.saml2.idp_metadata_parser import OneLogin_Saml2_IdPMetadataParser

from wiregui.config import get_settings


def _build_saml_settings(provider_config: dict) -> dict:
    """Build python3-saml settings dict from our provider config."""
    settings = get_settings()
    base_url = settings.external_url

    # Parse IdP metadata XML to extract endpoints and certs
    idp_data = OneLogin_Saml2_IdPMetadataParser.parse(provider_config.get("metadata", ""))
    idp_settings = idp_data.get("idp", {})

    return {
        "strict": provider_config.get("strict", True),
        "debug": False,
        "sp": {
            "entityId": f"{base_url}/auth/saml/{provider_config['id']}/metadata",
            "assertionConsumerService": {
                "url": f"{base_url}/auth/saml/{provider_config['id']}/callback",
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
            },
            "NameIDFormat": "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress",
        },
        "idp": idp_settings,
        "security": {
            "authnRequestsSigned": provider_config.get("sign_requests", True),
            "wantAssertionsSigned": provider_config.get("signed_assertion_in_resp", True),
            "signMetadata": provider_config.get("sign_metadata", True),
        },
    }


def prepare_saml_request(request_data: dict) -> dict:
    """Prepare a dict that python3-saml expects from an HTTP request.

    Args:
        request_data: dict with keys: http_host, script_name, server_port,
                      get_data (dict), post_data (dict), https (str "on"/"off")
    """
    return {
        "http_host": request_data.get("http_host", "localhost"),
        "script_name": request_data.get("script_name", ""),
        "server_port": request_data.get("server_port", 443),
        "get_data": request_data.get("get_data", {}),
        "post_data": request_data.get("post_data", {}),
        "https": request_data.get("https", "on"),
    }


def create_saml_auth(provider_config: dict, request_data: dict) -> OneLogin_Saml2_Auth:
    """Create a python3-saml Auth instance for a provider."""
    saml_settings = _build_saml_settings(provider_config)
    req = prepare_saml_request(request_data)
    return OneLogin_Saml2_Auth(req, saml_settings)


def get_login_url(auth: OneLogin_Saml2_Auth) -> str:
    """Get the SSO redirect URL."""
    return auth.login()


def process_response(auth: OneLogin_Saml2_Auth) -> dict | None:
    """Process the SAML response and return user attributes.

    Returns dict with 'email' key, or None on failure.
    """
    auth.process_response()
    errors = auth.get_errors()
    if errors:
        logger.error("SAML response errors: {}", errors)
        return None

    if not auth.is_authenticated():
        logger.warning("SAML: user not authenticated")
        return None

    attrs = auth.get_attributes()
    name_id = auth.get_nameid()

    # Try to extract email from various attribute names
    email = (
        attrs.get("email", [None])[0]
        or attrs.get("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress", [None])[0]
        or attrs.get("urn:oid:0.9.2342.19200300.100.1.3", [None])[0]
        or name_id
    )

    if not email:
        logger.error("SAML: no email found in attributes or NameID")
        return None

    return {
        "email": email,
        "name_id": name_id,
        "attributes": {k: v for k, v in attrs.items()},
    }


def get_metadata(provider_config: dict) -> str:
    """Generate SP metadata XML."""
    settings = _build_saml_settings(provider_config)
    from onelogin.saml2.settings import OneLogin_Saml2_Settings
    saml_settings = OneLogin_Saml2_Settings(settings, sp_validation_only=True)
    metadata = saml_settings.get_sp_metadata()
    errors = saml_settings.validate_metadata(metadata)
    if errors:
        logger.error("SP metadata validation errors: {}", errors)
    return metadata.decode() if isinstance(metadata, bytes) else metadata
