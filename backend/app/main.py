import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api import audit_log, auth, conversations, dashboard, imports, integrations, leads, setup_api, users
from app.core.config import PROJECT_ROOT, get_settings
from app.core.db import SessionLocal, engine
from app.core.errors import install_error_handling
from app.services.setup import ensure_default_flows
from app.services.workers import Workers

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    with SessionLocal() as db:
        ensure_default_flows(db)
    workers = Workers()
    if settings.workers_enabled:
        workers.start()
    yield
    if settings.workers_enabled:
        workers.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.2.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Correlation-ID"],
    )
    install_error_handling(app)

    for module in (auth, users, audit_log, leads, conversations, imports, setup_api, dashboard, integrations):
        app.include_router(module.router)

    @app.get("/health", tags=["health"])
    def health():
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception:
            return JSONResponse(status_code=503, content={"status": "degraded", "database": "down"})
        return {"status": "ok", "database": "ok", "business": settings.business_name}

    # Serve the built CRM (frontend/dist) from the same address, with SPA fallback.
    if FRONTEND_DIST.is_dir():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith(("api/", "webhooks/")):
                return JSONResponse(status_code=404, content={"code": "not_found", "message": "Not found."})
            f = FRONTEND_DIST / path
            if path and f.is_file() and FRONTEND_DIST in f.resolve().parents:
                return FileResponse(f)
            return FileResponse(FRONTEND_DIST / "index.html")

    return app


app = create_app()
