from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from wiregui.api.deps import get_db, require_admin
from wiregui.models.configuration import Configuration
from wiregui.models.user import User
from wiregui.schemas.configuration import ConfigurationRead, ConfigurationUpdate

router = APIRouter(prefix="/configuration", tags=["configuration"])


async def _get_config(session: AsyncSession) -> Configuration:
    result = await session.execute(select(Configuration).limit(1))
    config = result.scalar_one_or_none()
    if not config:
        config = Configuration()
        session.add(config)
        await session.commit()
        await session.refresh(config)
    return config


@router.get("/", response_model=ConfigurationRead)
async def get_configuration(
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    return await _get_config(session)


@router.put("/", response_model=ConfigurationRead)
async def update_configuration(
    body: ConfigurationUpdate,
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    config = await _get_config(session)

    for key, val in body.model_dump(exclude_unset=True).items():
        setattr(config, key, val)

    session.add(config)
    await session.commit()
    await session.refresh(config)
    return config
