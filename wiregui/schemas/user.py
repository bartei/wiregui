from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr


class UserRead(BaseModel):
    id: UUID
    email: str
    role: str
    disabled_at: datetime | None
    last_signed_in_at: datetime | None
    last_signed_in_method: str | None
    inserted_at: datetime
    updated_at: datetime


class UserCreate(BaseModel):
    email: str
    password: str
    role: str = "unprivileged"


class UserUpdate(BaseModel):
    email: str | None = None
    password: str | None = None
    role: str | None = None
    disabled_at: datetime | None = None
