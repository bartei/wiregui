"""v0 API router — aggregates all sub-routers."""

from fastapi import APIRouter

from wiregui.api.v0 import configuration, devices, rules, users

router = APIRouter(prefix="/v0")
router.include_router(users.router)
router.include_router(devices.router)
router.include_router(rules.router)
router.include_router(configuration.router)
