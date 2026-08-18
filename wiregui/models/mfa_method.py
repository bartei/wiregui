from datetime import datetime

from wiregui.utils.time import utcnow
from uuid import UUID, uuid4

from sqlmodel import Field, JSON, Column, Relationship, SQLModel


class MFAMethod(SQLModel, table=True):
    __tablename__ = "mfa_methods"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str
    type: str  # "totp" | "native" | "portable"
    payload: dict = Field(default_factory=dict, sa_column=Column(JSON))  # encrypted at app level
    last_used_at: datetime | None = None

    user_id: UUID = Field(foreign_key="users.id", index=True, ondelete="CASCADE")

    inserted_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    # Relationships
    user: "User" = Relationship(back_populates="mfa_methods")


from wiregui.models.user import User  # noqa: E402, F401
