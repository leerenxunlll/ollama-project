"""Read-only AI configuration status endpoint."""

from fastapi import APIRouter

from app.core.config import settings
from app.schemas.ai import AIStatusRead

router = APIRouter()


@router.get("/ai/status", response_model=AIStatusRead)
def get_ai_status() -> AIStatusRead:
    """Report whether Dify character chat is configured without exposing secrets."""
    return AIStatusRead(configured=settings.dify_character_configured)
