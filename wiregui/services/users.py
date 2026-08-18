"""User lifecycle operations shared by the admin UI, REST API and account page."""

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from wiregui.models.device import Device
from wiregui.models.user import User
from wiregui.services.events import on_device_deleted


async def delete_user_and_cleanup(session: AsyncSession, user: User) -> None:
    """Delete a user and all their data, then remove their WireGuard peers.

    The database cascades devices, rules, MFA methods, API tokens and OIDC
    connections (ON DELETE CASCADE on the user_id FKs). Devices are snapshotted
    first so their WG peers/routes can be torn down after the delete is committed.
    """
    devices = (
        await session.execute(select(Device).where(Device.user_id == user.id))
    ).scalars().all()

    await session.delete(user)
    await session.commit()
    logger.info("Deleted user {} and cascaded {} device(s)", user.email, len(devices))

    for device in devices:
        await on_device_deleted(device)
