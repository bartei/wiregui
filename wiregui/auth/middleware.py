"""NiceGUI auth middleware — redirects unauthenticated requests to /login."""

from fastapi import Request
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

# Paths that don't require authentication
PUBLIC_PREFIXES = ("/login", "/_nicegui", "/api")


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if any(request.url.path.startswith(p) for p in PUBLIC_PREFIXES):
            return await call_next(request)

        # NiceGUI stores auth state in the Starlette session (cookie-backed)
        if not request.session.get("authenticated"):
            return RedirectResponse(url="/login")

        return await call_next(request)
