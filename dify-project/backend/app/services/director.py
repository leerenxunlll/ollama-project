"""Persist validated Director recommendations without giving AI state authority."""

from datetime import datetime

from sqlalchemy.orm import Session

from app.agents.director_agent import DirectorAgent
from app.models import DirectorRecommendationRecord, GameSession
from app.schemas.director import DirectorRecommendationRead
from app.services.director_actions import validate_director_references
from app.services.director_context import build_director_context
from app.services.runtime_guards import (
    StaleRuntimeAction,
    assert_runtime_action_current,
)


def analyze_game_with_director(
    db: Session,
    game_id: int,
    agent: DirectorAgent,
    *,
    commit: bool = True,
    expected_phase: str | None = None,
    expected_phase_started_at: datetime | None = None,
    runtime_claim_token: str | None = None,
    now: datetime | None = None,
) -> DirectorRecommendationRead:
    """Build a filtered context, validate the workflow result, then save it."""
    game = db.get(GameSession, game_id)
    if game is None:
        raise LookupError("Game not found")
    source_phase = game.current_phase
    source_phase_started_at = game.phase_started_at
    context = build_director_context(db, game_id)
    source_public_message_id = max(
        (
            message.id
            for message in context.public_state.recent_messages
            if message.channel_type == "public"
        ),
        default=None,
    )
    db.commit()
    recommendation = agent.analyze(context)
    validate_director_references(db, game_id, recommendation)
    db.commit()
    if expected_phase is not None and (
        source_phase != expected_phase
        or source_phase_started_at != expected_phase_started_at
    ):
        raise StaleRuntimeAction("Game phase changed before Director analysis")
    if expected_phase is not None or runtime_claim_token is not None:
        assert_runtime_action_current(
            db,
            game_id,
            claim_token=runtime_claim_token,
            expected_phase=expected_phase,
            expected_phase_started_at=expected_phase_started_at,
            now=now,
        )
    record = DirectorRecommendationRecord(
        game_session_id=game_id,
        pace=recommendation.pace.value,
        narrative_risk=recommendation.narrative_risk.value,
        recommended_action=recommendation.recommended_action.value,
        target_game_character_id=recommendation.target_game_character_id,
        clue_id=recommendation.clue_id,
        public_message_id=recommendation.public_message_id,
        reason=recommendation.reason,
        source_phase=source_phase,
        source_phase_started_at=source_phase_started_at,
        source_last_public_message_id=source_public_message_id,
        status="pending",
    )
    db.add(record)
    db.flush()
    if commit:
        db.commit()
    db.refresh(record)
    return DirectorRecommendationRead.model_validate(record)
