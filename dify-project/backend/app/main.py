"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.ai import router as ai_router
from app.api.games import router as games_router
from app.api.health import router as health_router
from app.api.scripts import router as scripts_router
from app.core.config import settings
from app.db.init_db import create_tables
from app.db.session import engine


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Create missing database tables before serving requests."""
    create_tables(engine)
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(ai_router, prefix="/api")
app.include_router(health_router, prefix="/api")
app.include_router(scripts_router, prefix="/api")
app.include_router(games_router, prefix="/api")
