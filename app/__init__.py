import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.middleware import logging_middleware
from app.api.v1.router import router as v1_router

logging.basicConfig(level=logging.INFO)


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        debug=settings.DEBUG,
        version="1.0.0",
        redoc_url="/redoc",
        swagger_ui_parameters={"persistAuthorization": True},
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(BaseHTTPMiddleware, dispatch=logging_middleware)

    app.include_router(v1_router, prefix="/api/v1")

    @app.on_event("startup")
    def create_tables():
        from app.db.base import Base
        from app.db.session import engine
        import app.models  # noqa: F401 — registers all models with Base
        Base.metadata.create_all(bind=engine)

    return app
