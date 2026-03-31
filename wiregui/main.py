from loguru import logger
from nicegui import app, ui

from wiregui.api.v0 import router as api_router
from wiregui.auth.seed import ensure_server_keypair, seed_admin
from wiregui.config import get_settings
from wiregui.db import init_db
from wiregui.log_config import setup_logging

# Mount REST API
app.include_router(api_router, prefix="/api")


@app.get("/api/health")
async def health():
    return {"status": "ok"}

# Import pages so their @ui.page decorators register routes
import wiregui.pages.account  # noqa: F401
import wiregui.pages.admin.devices  # noqa: F401
import wiregui.pages.admin.diagnostics  # noqa: F401
import wiregui.pages.admin.rules  # noqa: F401
import wiregui.pages.admin.settings  # noqa: F401
import wiregui.pages.admin.users  # noqa: F401
import wiregui.pages.auth_magic  # noqa: F401
import wiregui.pages.auth_oidc  # noqa: F401
import wiregui.pages.auth_saml  # noqa: F401
import wiregui.pages.devices  # noqa: F401
import wiregui.pages.home  # noqa: F401
import wiregui.pages.login  # noqa: F401
import wiregui.pages.mfa_challenge  # noqa: F401


async def startup() -> None:
    settings = get_settings()
    setup_logging(log_to_file=settings.log_to_file)
    await init_db()
    await seed_admin()
    await ensure_server_keypair()

    # Seed IdP providers from YAML config file (if configured), then register with authlib
    from wiregui.auth.seed import seed_idp_providers
    await seed_idp_providers()

    from wiregui.auth.oidc import register_providers
    await register_providers()

    from wiregui.tasks import register_task
    from wiregui.tasks.oidc_refresh import oidc_refresh_loop

    from wiregui.tasks.connectivity import connectivity_loop
    from wiregui.tasks.vpn_session import vpn_session_loop

    # Always run these tasks (even without WG for OIDC refresh and connectivity)
    register_task(oidc_refresh_loop(), name="oidc-refresh")
    register_task(connectivity_loop(), name="connectivity-check")

    if settings.wg_enabled:
        from wiregui.services.firewall import setup_base_tables, setup_masquerade
        from wiregui.services.wireguard import configure_interface, ensure_interface
        from wiregui.tasks.reconcile import reconcile
        from wiregui.tasks.stats import stats_loop

        await ensure_interface()
        await configure_interface()
        await setup_base_tables()
        await setup_masquerade()
        await reconcile()
        register_task(stats_loop(), name="wg-stats")
        register_task(vpn_session_loop(), name="vpn-session-expiry")
    else:
        logger.info("WireGuard disabled (WG_WG_ENABLED=false) — running in UI-only mode")

    logger.info("WireGUI ready")


async def shutdown() -> None:
    from wiregui.tasks import cancel_all
    await cancel_all()


app.on_startup(startup)
app.on_shutdown(shutdown)


def main() -> None:
    settings = get_settings()
    ui.run(
        host=settings.host,
        port=settings.port,
        title="WireGUI",
        storage_secret=settings.secret_key,
        reload=True,
    )


if __name__ in {"__main__", "__mp_main__"}:
    main()
