"""Protect the local API from other websites in the user's browser.

Protean listens on localhost only, but any page the user visits could still try to call it.
 - Host check blocks DNS-rebinding attacks.
 - Origin check blocks cross-site state-changing requests (browsers always send Origin on those).
"""

from fastapi import FastAPI, Request
from starlette.middleware.trustedhost import TrustedHostMiddleware

from protean import config
from protean.core.errors import FORBIDDEN_ORIGIN, error_response


def install_local_guard(app: FastAPI) -> None:
    @app.middleware("http")
    async def _origin_check(request: Request, call_next):
        origin = request.headers.get("origin")
        allowed = {f"http://{h}:{config.PORT}" for h in config.ALLOWED_HOSTS}
        if (
            request.method not in config.SAFE_METHODS
            and origin is not None
            and origin not in allowed
        ):
            return error_response(
                403, FORBIDDEN_ORIGIN, "Cross-site requests are not allowed."
            )
        return await call_next(request)

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(config.ALLOWED_HOSTS))
