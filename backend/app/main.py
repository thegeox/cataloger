from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import UnidentifiedImageError

from .config import Settings
from .connectors import ConnectorError
from .db import make_engine
from .routers import fields, images, sources, templates
from .services.metadata import MetadataValidationError

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="Cataloger", version="0.1.0")
    app.state.settings = settings
    app.state.engine = make_engine(settings.database_url)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(ConnectorError)
    async def _connector_error(_: Request, exc: ConnectorError):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(MetadataValidationError)
    async def _metadata_error(_: Request, exc: MetadataValidationError):
        return JSONResponse({"detail": "Metadata no válida", "errors": exc.errors}, status_code=422)

    @app.exception_handler(UnidentifiedImageError)
    async def _bad_image(_: Request, exc: UnidentifiedImageError):
        return JSONResponse({"detail": f"No se pudo leer la imagen: {exc}"}, status_code=422)

    for r in (sources.router, fields.router, images.router, templates.router):
        app.include_router(r)

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    # Serve the built frontend (npm run build) from the same origin, with SPA fallback.
    if FRONTEND_DIST.is_dir():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            target = (FRONTEND_DIST / path).resolve()
            if path and target.is_file() and target.is_relative_to(FRONTEND_DIST):
                return FileResponse(target)
            return FileResponse(FRONTEND_DIST / "index.html")

    return app

