from datetime import datetime

from wiregui.utils.time import utcnow
from uuid import UUID, uuid4

from sqlmodel import Field, Relationship, SQLModel


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    email: str = Field(unique=True, index=True)
    password_hash: str | None = None
    role: str = Field(default="unprivileged")  # "admin" | "unprivileged"

    last_signed_in_at: datetime | None = None
    last_signed_in_method: str | None = None

    sign_in_token_hash: str | None = None
    sign_in_token_created_at: datetime | None = None

    disabled_at: datetime | None = None
    theme_preference: str = Field(default="auto")  # "light" | "dark" | "auto"

    inserted_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    # Relationships
    devices: list["Device"] = Relationship(back_populates="user")
    oidc_connections: list["OIDCConnection"] = Relationship(back_populates="user")
    api_tokens: list["ApiToken"] = Relationship(back_populates="user")
    mfa_methods: list["MFAMethod"] = Relationship(back_populates="user")
    rules: list["Rule"] = Relationship(back_populates="user")


# Avoid circular imports — these are resolved at runtime by SQLModel
from wiregui.models.api_token import ApiToken  # noqa: E402, F401
from wiregui.models.device import Device  # noqa: E402, F401
from wiregui.models.mfa_method import MFAMethod  # noqa: E402, F401
from wiregui.models.oidc_connection import OIDCConnection  # noqa: E402, F401
from wiregui.models.rule import Rule  # noqa: E402, F401
