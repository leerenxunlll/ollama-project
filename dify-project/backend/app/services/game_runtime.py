"""Persisted, event-driven runtime orchestration with one bounded action per tick."""

import math
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.agents.character_agent import (
    CharacterAgent,
    CharacterOutputValidationError,
)
from app.agents.dify_client import (
    DifyConfigurationError,
    DifyError,
    DifyTimeoutError,
)
from app.agents.director_agent import DirectorAgent, DirectorOutputValidationError
from app.agents.director_workflow_client import (
    DirectorWorkflowConfigurationError,
    DirectorWorkflowError,
    DirectorWorkflowTimeoutError,
)
from app.game.flow_manager import can_public_speak
from app.game.runtime_policy import (
    DISCUSSION_PHASES,
    INVESTIGATION_PHASES,
    READING_PHASES,
    RUNTIME_POLICY,
    RUNTIME_READY_PHASES,
    RuntimePolicy,
)
from app.game.state_machine import GameRuleError
from app.models import (
    DirectorRecommendationRecord,
    GameCharacter,
    GameClueDisclosure,
    GamePhaseAcknowledgement,
    GameRuntimeActionLog,
    GameRuntimeState,
    GameSession,
    Message,
)
from app.schemas.director import DirectorAction
from app.schemas.runtime import (
    GameRuntimeActionRead,
    GameRuntimeStatusRead,
    PhaseReadAcknowledgement,
    RuntimeReadyResponse,
    RuntimeStepResult,
)
from app.services.director import analyze_game_with_director
from app.services.director_actions import (
    DirectorApplyConflict,
    apply_director_recommendation,
)
from app.services.evidence import (
    next_ai_investigation,
    next_ai_investigation_location,
    search_for_ai,
)
from app.services.game_flow import get_game_flow_state
from app.services.gameplay import advance_game_phase
from app.services.runtime_guards import (
    RuntimeClaimLost,
    StaleRuntimeAction,
    assert_runtime_action_current,
)


def get_game_runtime_status(
    db: Session,
    game_id: int,
    *,
    now: datetime | None = None,
    policy: RuntimePolicy = RUNTIME_POLICY,
) -> GameRuntimeStatusRead:
    """Read the scheduler and audit state without creating or advancing anything."""
    game = _get_game(db, game_id)
    state = db.get(GameRuntimeState, game_id)
    current_time = _utc(now or datetime.now(timezone.utc))
    ai_speech_at = _latest_ai_public_speech_at(db, game_id)
    proactive_speech_at = _latest_proactive_speech_at(db, game_id)
    recent_actions = db.scalars(
        select(GameRuntimeActionLog)
        .where(GameRuntimeActionLog.game_session_id == game_id)
        .order_by(
            GameRuntimeActionLog.started_at.desc(), GameRuntimeActionLog.id.desc()
        )
        .limit(10)
    ).all()
    if state is None:
        runtime_status = "not_started"
        action_status = "idle"
    else:
        runtime_status = "enabled" if state.enabled else "paused"
        action_status = state.action_status

    return GameRuntimeStatusRead(
        game_id=game.id,
        game_status=game.status,
        current_phase=game.current_phase,
        runtime_status=runtime_status,
        phase_read_acknowledged=_phase_read_acknowledged(db, game),
        ready_for_phase=(
            state.ready_phase
            if state is not None and state.ready_phase == game.current_phase
            else None
        ),
        action_status=action_status,
        last_tick_at=state.last_tick_at if state is not None else None,
        last_director_analysis_at=(
            state.last_director_analysis_at if state is not None else None
        ),
        last_proactive_speech_at=proactive_speech_at,
        last_action_type=state.last_action_type if state is not None else None,
        last_error_code=state.last_error_code if state is not None else None,
        next_check_after_seconds=_next_check_seconds(
            db, game, state, current_time, ai_speech_at, policy
        ),
        recent_actions=[
            GameRuntimeActionRead.model_validate(row) for row in recent_actions
        ],
    )


def start_game_runtime(
    db: Session, game_id: int, now: datetime | None = None
) -> GameRuntimeStatusRead:
    """Enable client-ticked orchestration for an already started game."""
    game = _get_game(db, game_id)
    if game.status != "in_progress":
        raise GameRuleError("Runtime can only start for an in-progress game")
    current_time = _utc(now or datetime.now(timezone.utc))
    assert_runtime_action_current(
        db,
        game_id,
        expected_phase=game.current_phase,
        expected_phase_started_at=game.phase_started_at,
        now=current_time,
    )
    db.execute(
        sqlite_insert(GameRuntimeState)
        .values(
            game_session_id=game_id,
            enabled=True,
            action_status="idle",
        )
        .on_conflict_do_nothing(index_elements=[GameRuntimeState.game_session_id])
    )
    db.execute(
        update(GameRuntimeState)
        .where(GameRuntimeState.game_session_id == game_id)
        .values(enabled=True, last_error_code=None)
    )
    db.commit()
    return get_game_runtime_status(db, game_id, now=current_time)


def pause_game_runtime(
    db: Session, game_id: int, now: datetime | None = None
) -> GameRuntimeStatusRead:
    """Stop future claims while allowing an already claimed action to finish."""
    _get_game(db, game_id)
    db.execute(
        update(GameRuntimeState)
        .where(GameRuntimeState.game_session_id == game_id)
        .values(enabled=False)
    )
    db.commit()
    return get_game_runtime_status(db, game_id, now=now)


def acknowledge_current_phase(
    db: Session, game_id: int, now: datetime | None = None
) -> PhaseReadAcknowledgement:
    """Idempotently acknowledge only the currently active reading phase."""
    game = _get_game(db, game_id)
    if game.status != "in_progress" or game.current_phase not in READING_PHASES:
        raise GameRuleError(
            "Only the current intro, Act 1, or Act 2 can be acknowledged"
        )
    _require_human_character(db, game_id)
    current_time = _utc(now or datetime.now(timezone.utc))
    phase = game.current_phase
    started_at = game.phase_started_at
    assert_runtime_action_current(
        db,
        game_id,
        expected_phase=phase,
        expected_phase_started_at=started_at,
        now=current_time,
    )

    if phase == "intro":
        db.execute(
            update(GameSession)
            .where(
                GameSession.id == game_id,
                GameSession.status == "in_progress",
                GameSession.current_phase == "intro",
                GameSession.phase_started_at == started_at,
            )
            .values(
                human_intro_acknowledged_at=func.coalesce(
                    GameSession.human_intro_acknowledged_at, current_time
                )
            )
        )
        db.commit()
        db.refresh(game)
        acknowledged_at = game.human_intro_acknowledged_at
    else:
        db.execute(
            sqlite_insert(GamePhaseAcknowledgement)
            .values(
                game_session_id=game_id,
                phase=phase,
                acknowledged_at=current_time,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    GamePhaseAcknowledgement.game_session_id,
                    GamePhaseAcknowledgement.phase,
                ]
            )
        )
        db.commit()
        acknowledged_at = db.scalar(
            select(GamePhaseAcknowledgement.acknowledged_at).where(
                GamePhaseAcknowledgement.game_session_id == game_id,
                GamePhaseAcknowledgement.phase == phase,
            )
        )

    if acknowledged_at is None:
        raise GameRuleError("Phase acknowledgement could not be saved")
    return PhaseReadAcknowledgement(
        game_id=game_id,
        phase=phase,
        acknowledged=True,
        acknowledged_at=acknowledged_at,
    )


def mark_runtime_ready(
    db: Session, game_id: int, now: datetime | None = None
) -> RuntimeReadyResponse:
    """Record readiness for the current investigation or discussion only."""
    game = _get_game(db, game_id)
    state = db.get(GameRuntimeState, game_id)
    if state is None:
        raise GameRuleError("Start the runtime before marking the game ready")
    if game.status != "in_progress" or game.current_phase not in RUNTIME_READY_PHASES:
        raise GameRuleError("The current phase does not accept a readiness signal")

    current_time = _utc(now or datetime.now(timezone.utc))
    phase = game.current_phase
    assert_runtime_action_current(
        db,
        game_id,
        expected_phase=phase,
        expected_phase_started_at=game.phase_started_at,
        now=current_time,
    )
    if state.ready_phase != phase:
        state.ready_phase = phase
        state.ready_at = current_time
    db.commit()
    db.refresh(state)
    return RuntimeReadyResponse(
        game_id=game_id,
        phase=phase,
        ready=True,
        ready_at=state.ready_at or current_time,
    )


def run_runtime_tick(
    db: Session,
    game_id: int,
    director_agent: DirectorAgent,
    character_agent: CharacterAgent,
    *,
    now: datetime | None = None,
    policy: RuntimePolicy = RUNTIME_POLICY,
) -> RuntimeStepResult:
    """Claim one tick and run at most one public speech or one phase advance."""
    current_time = _utc(now or datetime.now(timezone.utc))
    game = _get_game(db, game_id)
    state = db.get(GameRuntimeState, game_id)
    phase_before = game.current_phase
    if state is None:
        return _idle_result(game, "not_started", "runtime_not_started", policy)
    if not state.enabled:
        return _idle_result(game, "paused", "runtime_paused", policy)
    if game.status != "in_progress":
        reason = (
            "game_finished"
            if game.status in {"finished", "completed"}
            else "game_not_started"
        )
        return _idle_result(game, "enabled", reason, policy)

    token = secrets.token_urlsafe(32)
    old_token = state.claim_token
    lease_is_expired = old_token is not None and (
        state.lease_expires_at is None or _utc(state.lease_expires_at) <= current_time
    )
    phase_condition = (
        GameSession.phase_started_at.is_(None)
        if game.phase_started_at is None
        else GameSession.phase_started_at == game.phase_started_at
    )
    active_game = (
        select(GameSession.id)
        .where(
            GameSession.id == game_id,
            GameSession.status == "in_progress",
            GameSession.current_phase == game.current_phase,
            phase_condition,
        )
        .exists()
    )
    claim = db.execute(
        update(GameRuntimeState)
        .where(
            GameRuntimeState.game_session_id == game_id,
            GameRuntimeState.enabled.is_(True),
            or_(
                GameRuntimeState.claim_token.is_(None),
                GameRuntimeState.lease_expires_at.is_(None),
                GameRuntimeState.lease_expires_at <= current_time,
            ),
            active_game,
        )
        .execution_options(synchronize_session=False)
        .values(
            claim_token=token,
            lease_expires_at=current_time
            + timedelta(seconds=policy.action_lease_seconds),
            claimed_phase=game.current_phase,
            claimed_phase_started_at=game.phase_started_at,
            action_status="processing",
            last_tick_at=current_time,
        )
    )
    if claim.rowcount != 1:
        db.rollback()
        return _idle_result(
            _get_game(db, game_id),
            "enabled",
            "concurrent_tick_conflict",
            policy,
            execution_status="conflict",
        )

    if lease_is_expired and old_token is not None:
        _expire_claim_logs(db, game_id, old_token, current_time)
    db.commit()
    db.expire_all()
    game = _get_game(db, game_id)
    state = db.get(GameRuntimeState, game_id)
    if (
        state is None
        or state.claim_token != token
        or game.status != "in_progress"
        or game.current_phase != state.claimed_phase
        or game.phase_started_at != state.claimed_phase_started_at
    ):
        return _finish_tick(
            db,
            game_id,
            token,
            phase_before,
            current_time,
            reason_code="stale_phase",
            execution_status="idle",
            policy=policy,
        )

    flow = get_game_flow_state(db, game_id, now=current_time)
    ready_phase = state.ready_phase if state.ready_phase == game.current_phase else None

    if game.current_phase in READING_PHASES:
        if not _phase_read_acknowledged(db, game):
            _mark_phase_entry_processed(state, game)
            return _finish_tick(
                db,
                game_id,
                token,
                phase_before,
                current_time,
                reason_code="reading_not_acknowledged",
                execution_status="idle",
                policy=policy,
            )
        if not flow.minimum_time_satisfied:
            return _finish_tick(
                db,
                game_id,
                token,
                phase_before,
                current_time,
                reason_code="minimum_duration_not_elapsed",
                execution_status="idle",
                policy=policy,
            )
        return _advance_for_runtime(
            db,
            game,
            state,
            token,
            phase_before,
            current_time,
            "reading_completed",
            policy,
        )

    if game.current_phase in INVESTIGATION_PHASES:
        if ready_phase == game.current_phase and not flow.minimum_time_satisfied:
            return _finish_tick(
                db,
                game_id,
                token,
                phase_before,
                current_time,
                reason_code="minimum_duration_not_elapsed",
                execution_status="idle",
                policy=policy,
            )
        if ready_phase == game.current_phase:
            return _advance_for_runtime(
                db,
                game,
                state,
                token,
                phase_before,
                current_time,
                "investigation_ready",
                policy,
            )
        scheduled_investigation = next_ai_investigation(
            db,
            game,
            policy.ai_investigations_per_character_per_phase,
        )
        if scheduled_investigation is not None:
            character, _attempt, event_key = scheduled_investigation
            return _run_ai_investigation(
                db,
                game,
                character,
                event_key,
                token,
                phase_before,
                current_time,
                policy,
            )

    if game.current_phase in DISCUSSION_PHASES | {"final_discussion"}:
        if ready_phase == game.current_phase:
            if not flow.minimum_time_satisfied:
                return _finish_tick(
                    db,
                    game_id,
                    token,
                    phase_before,
                    current_time,
                    reason_code="minimum_duration_not_elapsed",
                    execution_status="idle",
                    policy=policy,
                )
            if game.current_phase == "final_discussion":
                event_type = "final_vote_ready"
            else:
                event_type = "discussion_ready"
            return _advance_for_runtime(
                db,
                game,
                state,
                token,
                phase_before,
                current_time,
                event_type,
                policy,
            )

    if game.current_phase == "vote":
        if not flow.vote_progress.voting_complete:
            return _finish_tick(
                db,
                game_id,
                token,
                phase_before,
                current_time,
                reason_code="vote_incomplete",
                execution_status="idle",
                policy=policy,
            )
        if not flow.minimum_time_satisfied:
            return _finish_tick(
                db,
                game_id,
                token,
                phase_before,
                current_time,
                reason_code="minimum_duration_not_elapsed",
                execution_status="idle",
                policy=policy,
            )
        return _advance_for_runtime(
            db,
            game,
            state,
            token,
            phase_before,
            current_time,
            "all_votes_cast",
            policy,
        )

    pending = _latest_pending_recommendation(db, game_id)
    if pending is not None:
        ready, wait_reason = _pending_action_eligible(
            db, game, pending, current_time, flow, policy
        )
        if ready:
            return _apply_runtime_recommendation(
                db,
                game,
                pending,
                character_agent,
                token,
                phase_before,
                current_time,
                policy,
            )
        if wait_reason:
            return _finish_tick(
                db,
                game_id,
                token,
                phase_before,
                current_time,
                reason_code=wait_reason,
                execution_status="idle",
                policy=policy,
                recommendation_id=pending.id,
            )

    if not can_public_speak(game.status, game.current_phase):
        return _finish_tick(
            db,
            game_id,
            token,
            phase_before,
            current_time,
            reason_code="no_eligible_action",
            execution_status="idle",
            policy=policy,
        )

    event = _director_event(db, game, state, current_time, policy)
    if event is None:
        return _finish_tick(
            db,
            game_id,
            token,
            phase_before,
            current_time,
            reason_code="no_new_event",
            execution_status="idle",
            policy=policy,
        )
    event_key, event_type, watermark_updates = event
    cooldown = _remaining_cooldown(
        state.last_director_analysis_at,
        current_time,
        policy.director_analysis_cooldown_seconds,
    )
    if cooldown > 0:
        return _finish_tick(
            db,
            game_id,
            token,
            phase_before,
            current_time,
            reason_code="cooldown_active",
            execution_status="idle",
            policy=policy,
            next_check_after_seconds=cooldown,
        )

    action_log = _new_action_log(
        db,
        game_id,
        token,
        event_key,
        event_type,
        "director_analysis",
        current_time,
    )
    if action_log is None:
        return _finish_tick(
            db,
            game_id,
            token,
            phase_before,
            current_time,
            reason_code="no_new_event",
            execution_status="idle",
            policy=policy,
        )
    for field, value in watermark_updates.items():
        setattr(state, field, value)
    state.last_director_analysis_at = current_time
    db.commit()

    try:
        recommendation = analyze_game_with_director(
            db,
            game_id,
            director_agent,
            commit=False,
            expected_phase=phase_before,
            expected_phase_started_at=game.phase_started_at,
            runtime_claim_token=token,
            now=current_time,
        )
        action_log = db.get(GameRuntimeActionLog, action_log.id)
        action_log.related_recommendation_id = recommendation.id
        record = db.get(DirectorRecommendationRecord, recommendation.id)
        if record is None:
            raise StaleRuntimeAction("Director recommendation was not persisted")
        can_apply, wait_reason = _pending_action_eligible(
            db, game, record, current_time, flow, policy
        )
        if can_apply:
            apply_result = apply_director_recommendation(
                db,
                game_id,
                recommendation.id,
                character_agent,
                current_time,
                commit_final=False,
                expected_phase=phase_before,
                expected_phase_started_at=game.phase_started_at,
                runtime_claim_token=token,
                allow_phase_advance=game.current_phase in DISCUSSION_PHASES,
                allow_public_speech=(
                    can_public_speak(game.status, game.current_phase)
                    and game.current_phase not in READING_PHASES
                ),
            )
            return _finish_after_recommendation(
                db,
                game_id,
                token,
                phase_before,
                current_time,
                recommendation.id,
                apply_result,
                action_log,
                policy,
            )

        action_log.execution_status = "completed"
        action_log.reason_code = wait_reason or "recommendation_pending"
        action_log.related_recommendation_id = recommendation.id
        action_log.completed_at = current_time
        return _finish_tick(
            db,
            game_id,
            token,
            phase_before,
            current_time,
            reason_code=action_log.reason_code,
            execution_status="completed",
            action_type="director_analysis",
            policy=policy,
            recommendation_id=recommendation.id,
            action_log=action_log,
        )
    except Exception as error:
        db.rollback()
        reason_code = _safe_runtime_error_code(error, director=True)
        failed_log = db.scalar(
            select(GameRuntimeActionLog).where(
                GameRuntimeActionLog.game_session_id == game_id,
                GameRuntimeActionLog.event_key == event_key,
                GameRuntimeActionLog.claim_token == token,
            )
        )
        return _finish_tick(
            db,
            game_id,
            token,
            phase_before,
            current_time,
            reason_code=reason_code,
            execution_status="failed",
            policy=policy,
            action_log=failed_log,
        )


def _run_ai_investigation(
    db: Session,
    game: GameSession,
    character: GameCharacter,
    event_key: str,
    token: str,
    phase_before: str,
    now: datetime,
    policy: RuntimePolicy,
) -> RuntimeStepResult:
    """Perform one deterministic AI search under the current Runtime claim."""
    action_log = _new_action_log(
        db,
        game.id,
        token,
        event_key,
        "ai_investigation",
        "ai_investigation",
        now,
    )
    if action_log is None:
        return _finish_tick(
            db,
            game.id,
            token,
            phase_before,
            now,
            reason_code="no_new_event",
            execution_status="idle",
            policy=policy,
        )

    location = next_ai_investigation_location(db, game, character.id)
    if location is None:
        action_log.execution_status = "skipped"
        action_log.reason_code = "no_investigation_locations"
        action_log.completed_at = now
        return _finish_tick(
            db,
            game.id,
            token,
            phase_before,
            now,
            reason_code="no_investigation_locations",
            execution_status="completed",
            action_type="ai_investigation",
            policy=policy,
            action_log=action_log,
        )

    try:
        result = search_for_ai(
            db,
            game.id,
            character.id,
            location,
            expected_phase=phase_before,
            expected_phase_started_at=game.phase_started_at,
            runtime_claim_token=token,
            now=now,
            commit=False,
        )
    except Exception as error:
        db.rollback()
        reason_code = _safe_runtime_error_code(error)
        failed_log = _new_action_log(
            db,
            game.id,
            token,
            event_key,
            "ai_investigation",
            "ai_investigation",
            now,
        )
        return _finish_tick(
            db,
            game.id,
            token,
            phase_before,
            now,
            reason_code=reason_code,
            execution_status="failed",
            action_type="ai_investigation",
            policy=policy,
            action_log=failed_log,
        )

    action_log.execution_status = "completed"
    action_log.reason_code = "clue_acquired" if result.found else "no_new_clue"
    action_log.completed_at = now
    return _finish_tick(
        db,
        game.id,
        token,
        phase_before,
        now,
        reason_code=action_log.reason_code,
        execution_status="completed",
        action_type="ai_investigation",
        policy=policy,
        action_log=action_log,
    )


def _advance_for_runtime(
    db: Session,
    game: GameSession,
    state: GameRuntimeState,
    token: str,
    phase_before: str,
    now: datetime,
    event_type: str,
    policy: RuntimePolicy,
) -> RuntimeStepResult:
    event_key = f"advance:{phase_before}:{_time_key(game.phase_started_at)}"
    action_log = _new_action_log(
        db,
        game.id,
        token,
        event_key,
        event_type,
        "phase_advance",
        now,
    )
    if action_log is None:
        return _finish_tick(
            db,
            game.id,
            token,
            phase_before,
            now,
            reason_code="no_new_event",
            execution_status="idle",
            policy=policy,
        )
    try:
        advance_game_phase(
            db,
            game.id,
            now,
            commit=False,
            expected_phase=phase_before,
            expected_phase_started_at=game.phase_started_at,
            runtime_claim_token=token,
        )
        state.ready_phase = None
        state.ready_at = None
        action_log.execution_status = "completed"
        action_log.reason_code = "phase_advanced"
        action_log.completed_at = now
        return _finish_tick(
            db,
            game.id,
            token,
            phase_before,
            now,
            reason_code="phase_advanced",
            execution_status="completed",
            action_type="phase_advance",
            policy=policy,
            action_log=action_log,
        )
    except Exception as error:
        db.rollback()
        return _finish_tick(
            db,
            game.id,
            token,
            phase_before,
            now,
            reason_code=_safe_runtime_error_code(error),
            execution_status="failed",
            action_type="phase_advance",
            policy=policy,
        )


def _latest_pending_recommendation(
    db: Session, game_id: int
) -> DirectorRecommendationRecord | None:
    return db.scalar(
        select(DirectorRecommendationRecord)
        .where(
            DirectorRecommendationRecord.game_session_id == game_id,
            DirectorRecommendationRecord.status == "pending",
        )
        .order_by(
            DirectorRecommendationRecord.created_at.desc(),
            DirectorRecommendationRecord.id.desc(),
        )
        .limit(1)
    )


def _pending_action_eligible(
    db: Session,
    game: GameSession,
    record: DirectorRecommendationRecord,
    now: datetime,
    flow,
    policy: RuntimePolicy,
) -> tuple[bool, str | None]:
    if record.source_phase is None:
        return False, None
    if (
        game.current_phase != record.source_phase
        or game.phase_started_at != record.source_phase_started_at
    ):
        return True, None
    latest_public_id = db.scalar(
        select(func.max(Message.id)).where(
            Message.game_session_id == game.id,
            Message.channel_type == "public",
        )
    )
    if (
        record.source_last_public_message_id is not None
        and latest_public_id is not None
        and latest_public_id > record.source_last_public_message_id
    ):
        return True, None

    action = DirectorAction(record.recommended_action)
    if action in {
        DirectorAction.no_action,
        DirectorAction.suggest_clue_hint,
        DirectorAction.highlight_public_fact,
    }:
        return True, None
    if action == DirectorAction.request_ai_speaker:
        if not can_public_speak(game.status, game.current_phase):
            return True, None
        idle_seconds = _human_idle_seconds(db, game, now)
        if idle_seconds < policy.human_inactivity_threshold_seconds:
            return False, "human_active"
        proactive_cooldown = _remaining_cooldown(
            _latest_ai_public_speech_at(db, game.id),
            now,
            policy.proactive_speech_cooldown_seconds,
        )
        if proactive_cooldown:
            return False, "cooldown_active"
        return True, None
    if action == DirectorAction.recommend_phase_advance:
        if game.current_phase not in DISCUSSION_PHASES:
            return True, None
        if not flow.can_advance:
            return False, "minimum_duration_not_elapsed"
        if (
            _human_idle_seconds(db, game, now)
            < policy.human_inactivity_threshold_seconds
        ):
            return False, "human_active"
        return True, None
    return False, "no_eligible_action"


def _apply_runtime_recommendation(
    db: Session,
    game: GameSession,
    record: DirectorRecommendationRecord,
    character_agent: CharacterAgent,
    token: str,
    phase_before: str,
    now: datetime,
    policy: RuntimePolicy,
) -> RuntimeStepResult:
    event_key = f"recommendation:{record.id}"
    action_log = _new_action_log(
        db,
        game.id,
        token,
        event_key,
        "director_recommendation",
        record.recommended_action,
        now,
        recommendation_id=record.id,
    )
    if action_log is None:
        return _finish_tick(
            db,
            game.id,
            token,
            phase_before,
            now,
            reason_code="no_new_event",
            execution_status="idle",
            policy=policy,
            recommendation_id=record.id,
        )
    db.commit()
    try:
        outcome = apply_director_recommendation(
            db,
            game.id,
            record.id,
            character_agent,
            now,
            commit_final=False,
            expected_phase=record.source_phase,
            expected_phase_started_at=record.source_phase_started_at,
            runtime_claim_token=token,
            allow_phase_advance=game.current_phase in DISCUSSION_PHASES,
            allow_public_speech=(
                can_public_speak(game.status, game.current_phase)
                and game.current_phase not in READING_PHASES
            ),
        )
    except (DirectorApplyConflict, LookupError) as error:
        db.rollback()
        reason_code = (
            "stale_phase"
            if isinstance(error, LookupError)
            else "concurrent_tick_conflict"
        )
        failed_log = db.get(GameRuntimeActionLog, action_log.id)
        return _finish_tick(
            db,
            game.id,
            token,
            phase_before,
            now,
            reason_code=reason_code,
            execution_status="failed",
            action_type=_runtime_action_type(record.recommended_action),
            policy=policy,
            recommendation_id=record.id,
            action_log=failed_log,
        )
    return _finish_after_recommendation(
        db,
        game.id,
        token,
        phase_before,
        now,
        record.id,
        outcome,
        action_log,
        policy,
    )


def _finish_after_recommendation(
    db: Session,
    game_id: int,
    token: str,
    phase_before: str,
    now: datetime,
    recommendation_id: int,
    outcome,
    action_log: GameRuntimeActionLog,
    policy: RuntimePolicy,
) -> RuntimeStepResult:
    action = DirectorAction(
        db.get(DirectorRecommendationRecord, recommendation_id).recommended_action
    )
    if outcome.status == "rejected":
        reason_code = _apply_rejection_code(outcome.reason)
        execution_status = "failed"
        action_type = _runtime_action_type(action.value)
        action_log.execution_status = "failed"
    else:
        reason_code = (
            "advisory_only" if outcome.status == "advisory" else "action_applied"
        )
        execution_status = "completed"
        action_type = _runtime_action_type(action.value)
        action_log.execution_status = "completed"
    action_log.action_type = action_type
    action_log.reason_code = reason_code
    action_log.completed_at = now
    action_log.related_message_id = (
        outcome.public_message.id if outcome.public_message is not None else None
    )
    action_log.related_recommendation_id = recommendation_id
    return _finish_tick(
        db,
        game_id,
        token,
        phase_before,
        now,
        reason_code=reason_code,
        execution_status=execution_status,
        action_type=action_type,
        policy=policy,
        public_message_id=(
            outcome.public_message.id if outcome.public_message is not None else None
        ),
        recommendation_id=recommendation_id,
        action_log=action_log,
    )


def _director_event(
    db: Session,
    game: GameSession,
    state: GameRuntimeState,
    now: datetime,
    policy: RuntimePolicy,
) -> tuple[str, str, dict[str, object]] | None:
    analysis_phases = INVESTIGATION_PHASES | DISCUSSION_PHASES | {"final_discussion"}
    phase_started_at = game.phase_started_at
    phase_is_new = phase_started_at is not None and _time_key(
        state.last_processed_phase_started_at
    ) != _time_key(phase_started_at)
    human_message = _latest_human_public_message(db, game.id)
    latest_human_id = human_message[0] if human_message is not None else None
    latest_public_disclosure_id = db.scalar(
        select(func.max(GameClueDisclosure.id)).where(
            GameClueDisclosure.game_session_id == game.id,
            GameClueDisclosure.visibility == "public",
        )
    )
    has_new_public_disclosure = latest_public_disclosure_id is not None and (
        state.last_processed_public_clue_disclosure_id is None
        or latest_public_disclosure_id > state.last_processed_public_clue_disclosure_id
    )
    has_new_human_message = latest_human_id is not None and (
        state.last_processed_public_message_id is None
        or latest_human_id > state.last_processed_public_message_id
    )

    if phase_is_new and game.current_phase in analysis_phases:
        watermark_updates = {
            "last_processed_phase_started_at": phase_started_at,
            "last_processed_public_clue_disclosure_id": latest_public_disclosure_id,
            **(
                {"last_processed_public_message_id": latest_human_id}
                if latest_human_id is not None
                else {}
            ),
        }
        if (
            phase_started_at is not None
            and _human_idle_seconds(db, game, now)
            >= policy.human_inactivity_threshold_seconds
        ):
            watermark_updates["last_inactivity_phase_started_at"] = phase_started_at
        return (
            f"phase:{game.current_phase}:{_time_key(phase_started_at)}",
            "phase_entry",
            watermark_updates,
        )
    if has_new_public_disclosure and game.current_phase in analysis_phases:
        return (
            f"public-clue-disclosure:{latest_public_disclosure_id}",
            "public_clue_disclosure",
            {
                "last_processed_public_clue_disclosure_id": latest_public_disclosure_id,
                **(
                    {"last_processed_public_message_id": latest_human_id}
                    if latest_human_id is not None
                    else {}
                ),
                "last_inactivity_phase_started_at": None,
            },
        )
    if has_new_human_message and game.current_phase in analysis_phases:
        return (
            f"human-message:{latest_human_id}",
            "human_public_message",
            {
                "last_processed_public_message_id": latest_human_id,
                "last_processed_public_clue_disclosure_id": latest_public_disclosure_id,
                "last_inactivity_phase_started_at": None,
            },
        )
    if game.current_phase in DISCUSSION_PHASES | {"final_discussion"}:
        idle_seconds = _human_idle_seconds(db, game, now)
        inactivity_not_processed = _time_key(
            state.last_inactivity_phase_started_at
        ) != _time_key(phase_started_at)
        if (
            phase_started_at is not None
            and inactivity_not_processed
            and idle_seconds >= policy.human_inactivity_threshold_seconds
        ):
            return (
                f"inactive:{game.current_phase}:{_time_key(phase_started_at)}",
                "human_inactive",
                {
                    "last_processed_phase_started_at": phase_started_at,
                    "last_inactivity_phase_started_at": phase_started_at,
                    "last_processed_public_clue_disclosure_id": (
                        latest_public_disclosure_id
                    ),
                    **(
                        {"last_processed_public_message_id": latest_human_id}
                        if latest_human_id is not None
                        else {}
                    ),
                },
            )
    return None


def _new_action_log(
    db: Session,
    game_id: int,
    token: str,
    event_key: str,
    event_type: str,
    action_type: str | None,
    now: datetime,
    recommendation_id: int | None = None,
) -> GameRuntimeActionLog | None:
    existing = db.scalar(
        select(GameRuntimeActionLog.id).where(
            GameRuntimeActionLog.game_session_id == game_id,
            GameRuntimeActionLog.event_key == event_key,
        )
    )
    if existing is not None:
        return None
    action_log = GameRuntimeActionLog(
        game_session_id=game_id,
        event_key=event_key,
        event_type=event_type,
        action_type=action_type,
        execution_status="processing",
        claim_token=token,
        started_at=now,
        related_recommendation_id=recommendation_id,
    )
    db.add(action_log)
    db.flush()
    return action_log


def _finish_tick(
    db: Session,
    game_id: int,
    token: str,
    phase_before: str,
    now: datetime,
    *,
    reason_code: str,
    execution_status: str,
    policy: RuntimePolicy,
    action_type: str = "none",
    public_message_id: int | None = None,
    recommendation_id: int | None = None,
    action_log: GameRuntimeActionLog | None = None,
    next_check_after_seconds: int | None = None,
) -> RuntimeStepResult:
    if action_log is not None:
        if action_log.execution_status == "processing":
            action_log.execution_status = (
                "failed" if execution_status == "failed" else "completed"
            )
        if action_log.reason_code is None:
            action_log.reason_code = reason_code
        action_log.completed_at = now

    state_update = db.execute(
        update(GameRuntimeState)
        .where(
            GameRuntimeState.game_session_id == game_id,
            GameRuntimeState.claim_token == token,
            GameRuntimeState.lease_expires_at > now,
        )
        .execution_options(synchronize_session=False)
        .values(
            claim_token=None,
            lease_expires_at=None,
            claimed_phase=None,
            claimed_phase_started_at=None,
            action_status=("failed" if execution_status == "failed" else "idle"),
            last_action_type=(None if action_type == "none" else action_type),
            last_error_code=(reason_code if execution_status == "failed" else None),
        )
    )
    if state_update.rowcount != 1:
        db.rollback()
        game = _get_game(db, game_id)
        return _idle_result(
            game,
            "enabled",
            "concurrent_tick_conflict",
            policy,
            execution_status="conflict",
        )

    db.commit()
    db.expire_all()
    game = _get_game(db, game_id)
    state = db.get(GameRuntimeState, game_id)
    runtime_status = "enabled" if state and state.enabled else "paused"
    return RuntimeStepResult(
        game_id=game_id,
        runtime_status=runtime_status,
        action_type=action_type,
        execution_status=execution_status,
        phase_before=phase_before,
        phase_after=game.current_phase,
        public_message_id=public_message_id,
        recommendation_id=recommendation_id,
        reason_code=reason_code,
        next_check_after_seconds=(
            next_check_after_seconds
            if next_check_after_seconds is not None
            else policy.runtime_tick_interval_seconds
        ),
    )


def _idle_result(
    game: GameSession,
    runtime_status: str,
    reason_code: str,
    policy: RuntimePolicy,
    *,
    execution_status: str = "idle",
    next_check_after_seconds: int | None = None,
) -> RuntimeStepResult:
    return RuntimeStepResult(
        game_id=game.id,
        runtime_status=runtime_status,
        action_type="none",
        execution_status=execution_status,
        phase_before=game.current_phase,
        phase_after=game.current_phase,
        reason_code=reason_code,
        next_check_after_seconds=(
            next_check_after_seconds or policy.runtime_tick_interval_seconds
        ),
    )


def _expire_claim_logs(
    db: Session, game_id: int, old_token: str, now: datetime
) -> None:
    expired_logs = db.scalars(
        select(GameRuntimeActionLog).where(
            GameRuntimeActionLog.game_session_id == game_id,
            GameRuntimeActionLog.claim_token == old_token,
            GameRuntimeActionLog.execution_status == "processing",
        )
    ).all()
    for action_log in expired_logs:
        action_log.execution_status = "failed"
        action_log.reason_code = "lease_expired"
        action_log.completed_at = now
        if action_log.related_recommendation_id is not None:
            recommendation = db.get(
                DirectorRecommendationRecord,
                action_log.related_recommendation_id,
            )
            if recommendation is not None and recommendation.status == "applying":
                recommendation.status = "rejected"
                recommendation.applied_at = now


def _mark_phase_entry_processed(state: GameRuntimeState, game: GameSession) -> None:
    if game.phase_started_at is not None:
        state.last_processed_phase_started_at = game.phase_started_at


def _latest_human_public_message(
    db: Session, game_id: int
) -> tuple[int, datetime] | None:
    return db.execute(
        select(Message.id, Message.created_at)
        .join(GameCharacter, GameCharacter.id == Message.sender_game_character_id)
        .where(
            Message.game_session_id == game_id,
            Message.channel_type == "public",
            GameCharacter.game_session_id == game_id,
            GameCharacter.controller_type == "human",
        )
        .order_by(Message.id.desc())
        .limit(1)
    ).first()


def _latest_ai_public_speech_at(db: Session, game_id: int) -> datetime | None:
    return db.scalar(
        select(func.max(Message.created_at))
        .join(GameCharacter, GameCharacter.id == Message.sender_game_character_id)
        .where(
            Message.game_session_id == game_id,
            Message.channel_type == "public",
            GameCharacter.game_session_id == game_id,
            GameCharacter.controller_type == "ai",
        )
    )


def _latest_proactive_speech_at(db: Session, game_id: int) -> datetime | None:
    return db.scalar(
        select(func.max(GameRuntimeActionLog.completed_at)).where(
            GameRuntimeActionLog.game_session_id == game_id,
            GameRuntimeActionLog.action_type == "proactive_speech",
            GameRuntimeActionLog.related_message_id.is_not(None),
            GameRuntimeActionLog.execution_status == "completed",
        )
    )


def _human_idle_seconds(db: Session, game: GameSession, now: datetime) -> int:
    latest_human = _latest_human_public_message(db, game.id)
    last_activity = (
        _utc(latest_human[1])
        if latest_human is not None
        else _utc(game.phase_started_at or game.started_at or game.created_at)
    )
    return max(0, int((_utc(now) - last_activity).total_seconds()))


def _phase_read_acknowledged(db: Session, game: GameSession) -> bool:
    if game.current_phase == "intro":
        return game.human_intro_acknowledged_at is not None
    if game.current_phase not in {"act_1", "act_2"}:
        return False
    return (
        db.scalar(
            select(GamePhaseAcknowledgement.id).where(
                GamePhaseAcknowledgement.game_session_id == game.id,
                GamePhaseAcknowledgement.phase == game.current_phase,
            )
        )
        is not None
    )


def _require_human_character(db: Session, game_id: int) -> GameCharacter:
    characters = list(
        db.scalars(
            select(GameCharacter).where(
                GameCharacter.game_session_id == game_id,
                GameCharacter.controller_type == "human",
            )
        ).all()
    )
    if len(characters) != 1:
        raise GameRuleError("The human character is not selected")
    return characters[0]


def _remaining_cooldown(
    last_at: datetime | None, now: datetime, cooldown_seconds: int
) -> int:
    if last_at is None:
        return 0
    elapsed = (_utc(now) - _utc(last_at)).total_seconds()
    return max(0, math.ceil(cooldown_seconds - elapsed))


def _next_check_seconds(
    db: Session,
    game: GameSession,
    state: GameRuntimeState | None,
    now: datetime,
    last_ai_speech_at: datetime | None,
    policy: RuntimePolicy,
) -> int:
    if state is None or not state.enabled:
        return policy.runtime_tick_interval_seconds
    if state.claim_token and state.lease_expires_at:
        lease_wait = math.ceil((_utc(state.lease_expires_at) - now).total_seconds())
        if lease_wait > 0:
            return lease_wait
    if game.status != "in_progress":
        return policy.runtime_tick_interval_seconds
    if game.current_phase in READING_PHASES and not _phase_read_acknowledged(db, game):
        return policy.runtime_tick_interval_seconds
    flow = get_game_flow_state(db, game.id, now=now)
    if not flow.minimum_time_satisfied:
        return max(1, flow.remaining_seconds)
    if (
        game.current_phase in INVESTIGATION_PHASES
        and state.ready_phase != game.current_phase
    ):
        return policy.runtime_tick_interval_seconds
    if game.current_phase in DISCUSSION_PHASES | {"final_discussion"}:
        idle_wait = max(
            0,
            policy.human_inactivity_threshold_seconds
            - _human_idle_seconds(db, game, now),
        )
        director_wait = _remaining_cooldown(
            state.last_director_analysis_at,
            now,
            policy.director_analysis_cooldown_seconds,
        )
        speech_wait = _remaining_cooldown(
            last_ai_speech_at,
            now,
            policy.proactive_speech_cooldown_seconds,
        )
        waits = [value for value in (idle_wait, director_wait, speech_wait) if value]
        if waits and state.ready_phase != game.current_phase:
            return min(waits)
    return policy.runtime_tick_interval_seconds


def _get_game(db: Session, game_id: int) -> GameSession:
    game = db.get(GameSession, game_id)
    if game is None:
        raise LookupError("Game not found")
    return game


def _time_key(value: datetime | None) -> str:
    return _utc(value).isoformat() if value is not None else "none"


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _runtime_action_type(action: str) -> str:
    if action == DirectorAction.request_ai_speaker.value:
        return "proactive_speech"
    if action == DirectorAction.recommend_phase_advance.value:
        return "phase_advance"
    if action in {
        DirectorAction.suggest_clue_hint.value,
        DirectorAction.highlight_public_fact.value,
    }:
        return "advisory"
    return "director_analysis"


def _apply_rejection_code(reason: str) -> str:
    if "DifyTimeoutError" in reason:
        return "character_timeout"
    if "DifyConfigurationError" in reason:
        return "character_not_configured"
    if "CharacterOutputValidationError" in reason:
        return "character_output_invalid"
    if "phase" in reason.lower() or "public message" in reason.lower():
        return "stale_phase"
    return "recommendation_rejected"


def _safe_runtime_error_code(error: Exception, *, director: bool = False) -> str:
    if isinstance(error, (RuntimeClaimLost, StaleRuntimeAction)):
        return "stale_phase"
    if director:
        if isinstance(error, DirectorWorkflowConfigurationError):
            return "director_not_configured"
        if isinstance(error, DirectorWorkflowTimeoutError):
            return "director_timeout"
        if isinstance(error, DirectorOutputValidationError):
            return "director_output_invalid"
        if isinstance(error, DirectorWorkflowError):
            return "director_unavailable"
        return "runtime_action_failed"
    if isinstance(error, DifyConfigurationError):
        return "character_not_configured"
    if isinstance(error, DifyTimeoutError):
        return "character_timeout"
    if isinstance(error, DifyError):
        return "character_unavailable"
    if isinstance(error, CharacterOutputValidationError):
        return "character_output_invalid"
    if isinstance(error, GameRuleError):
        return "stale_phase"
    return "runtime_action_failed"
