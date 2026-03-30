from datetime import datetime

from wiregui.utils.time import utcnow
from uuid import UUID, uuid4

from sqlmodel import Field, JSON, Column, Relationship, SQLModel


class OIDCConnection(SQLModel, table=True):
    __tablename__ = "oidc_connections"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    provider: str
    refresh_token: str | None = None  # encrypted at application level
    refresh_response: dict | None = Field(default=None, sa_column=Column(JSON))
    refreshed_at: datetime | None = None

    user_id: UUID = Field(foreign_key="users.id", index=True)

    inserted_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    # Relationships
    user: "User" = Relationship(back_populates="oidc_connections")


from wiregui.models.user import User  # noqa: E402, F401
