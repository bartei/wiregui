from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from wiregui.api.deps import get_current_api_user, get_db
from wiregui.config import get_settings
from wiregui.models.device import Device
from wiregui.models.user import User
from wiregui.schemas.device import DeviceCreate, DeviceRead, DeviceUpdate
from wiregui.services.events import on_device_created, on_device_deleted, on_device_updated
from wiregui.utils.crypto import generate_keypair, generate_preshared_key
from wiregui.utils.network import allocate_ipv4, allocate_ipv6

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("/", response_model=list[DeviceRead])
async def list_devices(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_api_user),
):
    if current_user.role == "admin":
        result = await session.execute(select(Device).order_by(Device.inserted_at.desc()))
    else:
        result = await session.execute(
            select(Device).where(Device.user_id == current_user.id).order_by(Device.inserted_at.desc())
        )
    return result.scalars().all()


@router.get("/{device_id}", response_model=DeviceRead)
async def get_device(
    device_id: UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_api_user),
):
    device = await session.get(Device, device_id)
    if not device:
        raise HTTPException(404, "Device not found")
    if current_user.role != "admin" and device.user_id != current_user.id:
        raise HTTPException(403, "Access denied")
    return device


@router.post("/", response_model=DeviceRead, status_code=201)
async def create_device(
    body: DeviceCreate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_api_user),
):
    settings = get_settings()
    owner_id = body.user_id if (body.user_id and current_user.role == "admin") else current_user.id

    _private_key, public_key = generate_keypair()
    psk = generate_preshared_key()
    ipv4 = await allocate_ipv4(session, settings.wg_ipv4_network)
    ipv6 = await allocate_ipv6(session, settings.wg_ipv6_network)

    device = Device(
        name=body.name,
        description=body.description,
        public_key=public_key,
        preshared_key=psk,
        ipv4=ipv4,
        ipv6=ipv6,
        user_id=owner_id,
    )
    session.add(device)
    await session.commit()
    await session.refresh(device)

    logger.info("API: device created {} ({})", device.name, device.ipv4)
    await on_device_created(device)
    return device


@router.put("/{device_id}", response_model=DeviceRead)
async def update_device(
    device_id: UUID,
    body: DeviceUpdate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_api_user),
):
    device = await session.get(Device, device_id)
    if not device:
        raise HTTPException(404, "Device not found")
    if current_user.role != "admin" and device.user_id != current_user.id:
        raise HTTPException(403, "Access denied")

    for key, val in body.model_dump(exclude_unset=True).items():
        setattr(device, key, val)

    session.add(device)
    await session.commit()
    await session.refresh(device)

    await on_device_updated(device)
    return device


@router.delete("/{device_id}", status_code=204)
async def delete_device(
    device_id: UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_api_user),
):
    device = await session.get(Device, device_id)
    if not device:
        raise HTTPException(404, "Device not found")
    if current_user.role != "admin" and device.user_id != current_user.id:
        raise HTTPException(403, "Access denied")

    await session.delete(device)
    await session.commit()
    logger.info("API: device deleted {}", device.name)
    await on_device_deleted(device)
