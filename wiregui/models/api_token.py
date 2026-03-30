from datetime import datetime

from wiregui.utils.time import utcnow
from uuid import UUID, uuid4

from sqlmodel import Field, Relationship, SQLModel


class ApiToken(SQLModel, table=True):
    __tablename__ = "api_tokens"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    token_hash: str = Field(unique=True, index=True)
    expires_at: datetime | None = None

    user_id: UUID = Field(foreign_key="users.id", index=True)

    inserted_at: datetime = Field(default_factory=utcnow)

    # Relationships
    user: "User" = Relationship(back_populates="api_tokens")


from wiregui.models.user import User  # noqa: E402, F401
