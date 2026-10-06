"""Development-only Director Workflow debug and apply endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agents.character_agent import CharacterAgent, get_character_agent
from app.agents.director_agent import (
    DirectorAgent,
    DirectorOutputValidationError,
    get_director_agent,
)
from app.agents.director_workflow_client import (
    DirectorWorkflowConfigurationError,
    DirectorWorkflowError,
    DirectorWorkflowTimeoutError,
)
from app.core.config import settings
from app.db.session import get_db
from app.game.state_machine import GameRuleError
from app.schemas.director import (
    DirectorApplyResponse,
    DirectorConfiguredRead,
    DirectorRecommendationRead,
)
from app.services.director import analyze_game_with_director
from app.services.director_actions import apply_director_recommendation

router = APIRouter()


@router.get("/director/status", response_model=DirectorConfiguredRead)
def get_director_status() -> DirectorConfiguredRead:
    """Report whether the separate Director API key is configured."""
    _require_development()
    return DirectorConfiguredRead(configured=settings.dify_director_configured)


@router.post(
    "/games/{game_id}/director/analyze",
    response_model=DirectorRecommendationRead,
)
def analyze_game(
    game_id: int,
    db: Session = Depends(get_db),
    agent: DirectorAgent = Depends(get_director_agent),
) -> DirectorRecommendationRead:
    """Run one manual analysis and persist only its validated recommendation."""
    _require_development()
    if not settings.dify_director_configured:
        raise HTTPException(
            status_code=503,
            detail=(
                "Director Workflow is not configured; set DIFY_API_URL and "
                "DIFY_DIRECTOR_API_KEY"
            ),
        )
    try:
        return analyze_game_with_director(db, game_id, agent)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except GameRuleError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except DirectorOutputValidationError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except DirectorWorkflowConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except DirectorWorkflowTimeoutError as error:
        raise HTTPException(status_code=504, detail=str(error)) from error
    except DirectorWorkflowError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.post(
    "/games/{game_id}/director/recommendations/{recommendation_id}/apply",
    response_model=DirectorApplyResponse,
)
def apply_recommendation(
    game_id: int,
    recommendation_id: int,
    db: Session = Depends(get_db),
    character_agent: CharacterAgent = Depends(get_character_agent),
) -> DirectorApplyResponse:
    """Validate and apply one pending recommendation at most once."""
    _require_development()
    try:
        return apply_director_recommendation(
            db, game_id, recommendation_id, character_agent
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


def _require_development() -> None:
    if settings.app_env != "development":
        raise HTTPException(status_code=404, detail="Not found")
