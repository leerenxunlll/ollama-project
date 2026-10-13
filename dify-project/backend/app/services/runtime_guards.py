"""Database compare-and-set checks for in-flight runtime actions."""

from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import GameRuntimeState, GameSession


class RuntimeClaimLost(RuntimeError):
    """The caller's runtime lease expired or was replaced by another tick."""


class StaleRuntimeAction(RuntimeError):
    """The game phase changed while an external model call was running."""


def assert_runtime_action_current(
    db: Session,
    game_id: int,
    *,
    claim_token: str | None = None,
    expected_phase: str | None = None,
    expected_phase_started_at: datetime | None = None,
    now: datetime | None = None,
) -> None:
    """Acquire SQLite's write lock and verify lease and phase in this transaction."""
    if claim_token is not None:
        claim = db.execute(
            update(GameRuntimeState)
            .where(
                GameRuntimeState.game_session_id == game_id,
                GameRuntimeState.claim_token == claim_token,
                GameRuntimeState.lease_expires_at > (now or datetime.now(timezone.utc)),
            )
            .execution_options(synchronize_session=False)
            .values(action_status=GameRuntimeState.action_status)
        )
        if claim.rowcount != 1:
            raise RuntimeClaimLost("Runtime action lease is no longer current")

    if expected_phase is not None:
        phase_condition = (
            GameSession.phase_started_at.is_(None)
            if expected_phase_started_at is None
            else GameSession.phase_started_at == expected_phase_started_at
        )
        phase = db.execute(
            update(GameSession)
            .where(
                GameSession.id == game_id,
                GameSession.status == "in_progress",
                GameSession.current_phase == expected_phase,
                phase_condition,
            )
            .execution_options(synchronize_session=False)
            .values(current_phase=GameSession.current_phase)
        )
        if phase.rowcount != 1:
            raise StaleRuntimeAction("Game phase changed during runtime action")
