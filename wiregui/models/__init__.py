"""All SQLModel table models — imported here so Alembic autogenerate can discover them."""

from wiregui.models.api_token import ApiToken
from wiregui.models.configuration import Configuration
from wiregui.models.connectivity_check import ConnectivityCheck
from wiregui.models.device import Device
from wiregui.models.mfa_method import MFAMethod
from wiregui.models.oidc_connection import OIDCConnection
from wiregui.models.rule import Rule
from wiregui.models.user import User

__all__ = [
    "ApiToken",
    "Configuration",
    "ConnectivityCheck",
    "Device",
    "MFAMethod",
    "OIDCConnection",
    "Rule",
    "User",
]
