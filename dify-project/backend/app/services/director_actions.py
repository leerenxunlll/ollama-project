"""Validate Director references and apply only the bounded supported actions."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.agents.character_agent import CharacterAgent
from app.game.state_machine import GameRuleError
from app.models import (
    Clue,
    DirectorRecommendationRecord,
    GameCharacter,
    GameSession,
    Message,
)
from app.schemas.director import (
    DirectorAction,
    DirectorApplyResponse,
    DirectorRecommendation,
)
from app.schemas.game import MessageRead
from app.services.game_flow import get_game_flow_state
from app.services.gameplay import advance_game_phase
from app.services.public_turn import run_proactive_speaker_step


def validate_director_references(
    db: Session, game_id: int, recommendation: DirectorRecommendation
) -> GameSession:
    """Confirm every recommendation reference belongs to the current game/script."""
    game = db.get(GameSession, game_id)
    if game is None:
        raise LookupError("Game not found")

    if recommendation.target_game_character_id is not None:
        character = db.get(GameCharacter, recommendation.target_game_character_id)
        if (
            character is None
            or character.game_session_id != game.id
            or character.controller_type != "ai"
        ):
            raise GameRuleError("Director target must be an AI character in this game")

    if recommendation.clue_id is not None:
        clue = db.get(Clue, recommendation.clue_id)
        if clue is None or clue.script_id != game.script_id:
            raise GameRuleError("Director clue must belong to this game's script")

    if recommendation.public_message_id is not None:
        message = db.get(Message, recommendation.public_message_id)
        if (
            message is None
            or message.game_session_id != game.id
            or message.channel_type != "public"
        ):
            raise GameRuleError("Director fact must reference a public game message")

    return game


def apply_director_recommendation(
    db: Session,
    game_id: int,
    recommendation_id: int,
    character_agent: CharacterAgent,
    now: datetime | None = None,
) -> DirectorApplyResponse:
    """Resolve one persisted recommendation through deterministic backend checks."""
    record = db.get(DirectorRecommendationRecord, recommendation_id)
    if record is None or record.game_session_id != game_id:
        raise LookupError("Director recommendation not found")

    if record.status != "pending":
        return DirectorApplyResponse(
            recommendation_id=record.id,
            status=record.status,
            reason="Recommendation was already handled",
        )

    action = DirectorAction(record.recommended_action)
    current_time = now or datetime.now(timezone.utc)
    recommendation = DirectorRecommendation(
        pace=record.pace,
        narrative_risk=record.narrative_risk,
        recommended_action=action,
        reason=record.reason,
        target_game_character_id=record.target_game_character_id,
        clue_id=record.clue_id,
        public_message_id=record.public_message_id,
    )

    response_message: MessageRead | None = None
    flow_state = None
    try:
        game = validate_director_references(db, game_id, recommendation)
        if action == DirectorAction.no_action:
            outcome = "applied"
            reason = "No action was needed"
        elif action == DirectorAction.request_ai_speaker:
            flow = get_game_flow_state(db, game.id, now=current_time)
            if game.status != "in_progress" or not flow.can_discuss:
                raise GameRuleError(
                    "An AI speaker can only be requested during active discussion"
                )
            proactive_result = run_proactive_speaker_step(
                db,
                game.id,
                recommendation.target_game_character_id,
                character_agent,
                commit=False,
            )
            response_message = proactive_result.ai_message
            outcome = "applied"
            reason = "One AI public speech was generated"
        elif action == DirectorAction.recommend_phase_advance:
            advance_game_phase(db, game.id, current_time, commit=False)
            outcome = "applied"
            reason = "The next phase passed deterministic flow checks"
        else:
            outcome = "advisory"
            reason = "Advisory only; no clue or public history was changed"

        record.status = outcome
        record.applied_at = current_time
        db.commit()
        if action == DirectorAction.recommend_phase_advance:
            flow_state = get_game_flow_state(db, game.id, now=current_time)
    except Exception as error:
        db.rollback()
        record = db.get(DirectorRecommendationRecord, recommendation_id)
        if record is None:
            raise LookupError("Director recommendation not found") from error
        record.status = "rejected"
        record.applied_at = current_time
        reason = _safe_rejection_reason(error)
        db.commit()
        outcome = "rejected"

    return DirectorApplyResponse(
        recommendation_id=record.id,
        status=outcome,
        reason=reason,
        public_message=response_message,
        flow_state=flow_state,
    )


def _safe_rejection_reason(error: Exception) -> str:
    """Return deterministic rules or a non-sensitive failure category."""
    if isinstance(error, (GameRuleError, LookupError)):
        return str(error)
    return f"Director action failed ({type(error).__name__})"
