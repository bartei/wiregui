"""Background tasks — registered on app startup."""

import asyncio

from loguru import logger

from wiregui.config import get_settings

_tasks: list[asyncio.Task] = []


def register_task(coro, name: str) -> None:
    """Schedule a coroutine as a background task."""
    task = asyncio.create_task(coro, name=name)
    _tasks.append(task)
    logger.info("Background task registered: {}", name)


async def cancel_all() -> None:
    """Cancel all registered background tasks (called on shutdown)."""
    for task in _tasks:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    _tasks.clear()
    logger.info("All background tasks cancelled")
