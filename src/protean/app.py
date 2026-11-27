"""Application factory and CLI entry point (`protean`)."""

import logging
import sys
import threading
import webbrowser
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import APIRouter, FastAPI
from fastapi.staticfiles import StaticFiles

from protean import config
from protean.core import network, ports
from protean.core.errors import install_error_handlers
from protean.core.logger import setup_logging
from protean.core.security import install_local_guard
from protean.core.storage import ensure_workspace
from protean.modules.auth import login
from protean.modules.auth.router import router as auth_router
from protean.modules.drafts.router import router as drafts_router
from protean.modules.families.router import router as families_router
from protean.modules.marketplace.router import imports_router
from protean.modules.marketplace.router import router as marketplace_router
from protean.modules.profile.router import router as profile_router
from protean.modules.publish.router import router as publish_router
from protean.modules.reveal.router import router as reveal_router

log = logging.getLogger(__name__)

WEB_DIST = Path(__file__).parent / "web_dist"


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
    ensure_workspace()
    if config.OPEN_BROWSER:
        threading.Timer(
            0.5, webbrowser.open, args=[f"http://localhost:{config.PORT}"]
        ).start()
    yield
    await login.cancel()  # stop a login that is still polling GitHub
    await network.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Protean",
        description=config.DESCRIPTION,
        version=config.VERSION,
        lifespan=lifespan,
        docs_url=None,  # Swagger/ReDoc load scripts from a CDN; keep openapi.json only
        redoc_url=None,
    )
    install_error_handlers(app)
    install_local_guard(app)

    @app.get(config.PING_URL)
    def ping() -> dict[str, str]:
        """Lets a second launch recognise a running Protean (see core/ports.py)."""
        return config.PING_RESPONSE

    api = APIRouter(prefix="/api")
    api.include_router(profile_router)
    api.include_router(auth_router)
    api.include_router(marketplace_router)
    api.include_router(imports_router)
    api.include_router(drafts_router)
    api.include_router(families_router)
    api.include_router(publish_router)
    api.include_router(reveal_router)
    app.include_router(api)

    if (WEB_DIST / "index.html").exists():  # built UI shipped inside the package
        app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="ui")
    return app


def main() -> None:
    setup_logging()
    running = ports.find_running()
    if running:
        log.info("Protean is already running at http://localhost:%s", running)
        if config.OPEN_BROWSER:
            webbrowser.open(f"http://localhost:{running}")
        return

    sock = ports.bind_free()
    if sock is None:
        last = config.PORT + config.PORT_TRIES - 1
        log.error(
            "Ports %s-%s are all in use. Free one, or set PROTEAN_PORT.",
            config.PORT,
            last,
        )
        sys.exit(1)
    config.PORT = sock.getsockname()[1]  # may differ from the default
    log.info("Protean is running at http://localhost:%s", config.PORT)
    server = uvicorn.Server(
        uvicorn.Config(create_app(), log_level="warning", log_config=None)
    )
    try:
        server.run(sockets=[sock])
    except KeyboardInterrupt:
        log.info("Protean stopped")
