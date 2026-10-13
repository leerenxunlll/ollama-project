"""Development-only HTTP controls for the bounded game runtime."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agents.character_agent import CharacterAgent, get_character_agent
from app.agents.director_agent import DirectorAgent, get_director_agent
from app.core.config import settings
from app.db.session import get_db
from app.game.state_machine import GameRuleError
from app.schemas.runtime import (
    GameRuntimeStatusRead,
    PhaseReadAcknowledgement,
    RuntimeReadyResponse,
    RuntimeStepResult,
)
from app.services.game_runtime import (
    acknowledge_current_phase,
    get_game_runtime_status,
    mark_runtime_ready,
    pause_game_runtime,
    run_runtime_tick,
    start_game_runtime,
)

router = APIRouter()


@router.get("/games/{game_id}/runtime", response_model=GameRuntimeStatusRead)
def read_runtime_status(
    game_id: int, db: Session = Depends(get_db)
) -> GameRuntimeStatusRead:
    """Return safe scheduler status without creating or advancing anything."""
    _require_development()
    try:
        return get_game_runtime_status(db, game_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/games/{game_id}/runtime/start", response_model=GameRuntimeStatusRead)
def enable_runtime(
    game_id: int, db: Session = Depends(get_db)
) -> GameRuntimeStatusRead:
    _require_development()
    try:
        return start_game_runtime(db, game_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except GameRuleError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/games/{game_id}/runtime/pause", response_model=GameRuntimeStatusRead)
def disable_runtime(
    game_id: int, db: Session = Depends(get_db)
) -> GameRuntimeStatusRead:
    _require_development()
    try:
        return pause_game_runtime(db, game_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post(
    "/games/{game_id}/runtime/acknowledge-phase",
    response_model=PhaseReadAcknowledgement,
)
def acknowledge_phase(
    game_id: int, db: Session = Depends(get_db)
) -> PhaseReadAcknowledgement:
    _require_development()
    try:
        return acknowledge_current_phase(db, game_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except GameRuleError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/games/{game_id}/runtime/ready", response_model=RuntimeReadyResponse)
def mark_ready(game_id: int, db: Session = Depends(get_db)) -> RuntimeReadyResponse:
    _require_development()
    try:
        return mark_runtime_ready(db, game_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except GameRuleError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/games/{game_id}/runtime/tick", response_model=RuntimeStepResult)
def tick_runtime(
    game_id: int,
    db: Session = Depends(get_db),
    director_agent: DirectorAgent = Depends(get_director_agent),
    character_agent: CharacterAgent = Depends(get_character_agent),
) -> RuntimeStepResult:
    _require_development()
    try:
        return run_runtime_tick(db, game_id, director_agent, character_agent)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


def _require_development() -> None:
    if settings.app_env != "development":
        raise HTTPException(status_code=404, detail="Not found")
