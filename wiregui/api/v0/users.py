from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from wiregui.api.deps import get_db, require_admin
from wiregui.auth.passwords import hash_password
from wiregui.models.user import User
from wiregui.schemas.user import UserCreate, UserRead, UserUpdate
from wiregui.services.users import delete_user_and_cleanup

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/", response_model=list[UserRead])
async def list_users(
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    result = await session.execute(select(User).order_by(User.email))
    return result.scalars().all()


@router.get("/{user_id}", response_model=UserRead)
async def get_user(
    user_id: UUID,
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    return user


@router.post("/", response_model=UserRead, status_code=201)
async def create_user(
    body: UserCreate,
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        role=body.role,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@router.put("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: UUID,
    body: UserUpdate,
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")

    updates = body.model_dump(exclude_unset=True)
    if "password" in updates:
        updates["password_hash"] = hash_password(updates.pop("password"))
    for key, val in updates.items():
        setattr(user, key, val)

    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@router.delete("/{user_id}", status_code=204)
async def delete_user(
    user_id: UUID,
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    await delete_user_and_cleanup(session, user)
