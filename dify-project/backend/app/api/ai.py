"""Read-only AI configuration status endpoint."""

from fastapi import APIRouter

from app.core.config import settings
from app.schemas.ai import AIStatusRead
from app.schemas.voting import AIVoteWorkflowStatus

router = APIRouter()


@router.get("/ai/status", response_model=AIStatusRead)
def get_ai_status() -> AIStatusRead:
    """Report whether Dify character chat is configured without exposing secrets."""
    return AIStatusRead(configured=settings.dify_character_configured)


@router.get("/ai/vote/status", response_model=AIVoteWorkflowStatus)
def get_vote_workflow_status() -> AIVoteWorkflowStatus:
    """Report Vote Workflow credential presence without exposing its value."""
    return AIVoteWorkflowStatus(configured=settings.dify_vote_configured)
