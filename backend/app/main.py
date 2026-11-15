"""Aplicación FastAPI de EduMap."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import Settings
from .database import Database
from .routers import documents, projects
from .services.pdf_extractor import ocr_available, ocr_languages_available

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings.upload_dir.mkdir(parents=True, exist_ok=True)
        app.state.db.init()
        yield

    app = FastAPI(title="EduMap API", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.db = Database(settings.db_path)

    app.add_middleware(
        CORSMiddleware, allow_origins=list(settings.cors_origins),
        allow_methods=["*"], allow_headers=["*"],
    )
    app.include_router(documents.router)
    app.include_router(projects.router)

    @app.get("/api/health", tags=["sistema"])
    def health() -> dict:
        return {
            "status": "ok",
            "maxUploadMb": settings.max_upload_mb,
            "ocr": ocr_available(settings),
            "ocrLanguages": ocr_languages_available(settings),
        }

    # Si el frontend ya fue compilado (npm run build) se sirve desde el mismo puerto.
    if settings.frontend_dist:
        app.mount("/", StaticFiles(directory=settings.frontend_dist, html=True), name="frontend")
    return app


app = create_app()
