"""Health endpoint for checking backend connectivity."""

from fastapi import APIRouter

from app.core.config import settings

router = APIRouter()


@router.get("/health")
def get_health() -> dict[str, str]:
    """Return the application health status."""
    return {"status": "ok", "app": settings.app_name}
