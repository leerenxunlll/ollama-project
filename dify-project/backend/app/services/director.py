"""Persist validated Director recommendations without giving AI state authority."""

from sqlalchemy.orm import Session

from app.agents.director_agent import DirectorAgent
from app.models import DirectorRecommendationRecord
from app.schemas.director import DirectorRecommendationRead
from app.services.director_actions import validate_director_references
from app.services.director_context import build_director_context


def analyze_game_with_director(
    db: Session, game_id: int, agent: DirectorAgent
) -> DirectorRecommendationRead:
    """Build a filtered context, validate the workflow result, then save it."""
    context = build_director_context(db, game_id)
    recommendation = agent.analyze(context)
    validate_director_references(db, game_id, recommendation)
    record = DirectorRecommendationRecord(
        game_session_id=game_id,
        pace=recommendation.pace.value,
        narrative_risk=recommendation.narrative_risk.value,
        recommended_action=recommendation.recommended_action.value,
        target_game_character_id=recommendation.target_game_character_id,
        clue_id=recommendation.clue_id,
        public_message_id=recommendation.public_message_id,
        reason=recommendation.reason,
        status="pending",
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return DirectorRecommendationRead.model_validate(record)
