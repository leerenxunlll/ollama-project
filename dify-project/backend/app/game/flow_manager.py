"""Deterministic timing and action eligibility layered over the phase graph."""

from collections.abc import Sequence
from datetime import datetime, timezone

from app.game.state_machine import can_investigate, next_phase
from app.schemas.flow import GameFlowState, GameFlowVoteProgress

PHASE_MINIMUM_DURATIONS_SECONDS = {
    "intro": 10,
    "act_1": 10,
    "investigation_1": 10,
    "discussion_1": 10,
    "act_2": 10,
    "investigation_2": 10,
    "discussion_2": 10,
    "final_discussion": 10,
    "vote": 10,
    "ending": 0,
}
DISCUSSION_PHASES = frozenset({"discussion_1", "discussion_2", "final_discussion"})


def build_flow_state(
    *,
    game_id: int,
    status: str,
    current_phase: str,
    phase_started_at: datetime | None,
    votes_cast: int,
    total_voters: int,
    now: datetime | None = None,
) -> GameFlowState:
    """Calculate a safe, deterministic flow snapshot using the server clock."""
    server_now = _as_utc(now or datetime.now(timezone.utc))
    started_at = _as_utc(phase_started_at) if phase_started_at else None
    elapsed = 0
    if started_at is not None:
        elapsed = max(0, int((server_now - started_at).total_seconds()))

    minimum_duration = PHASE_MINIMUM_DURATIONS_SECONDS.get(current_phase, 0)
    remaining = max(0, minimum_duration - elapsed)
    minimum_time_satisfied = remaining == 0
    voting_complete = total_voters > 0 and votes_cast >= total_voters
    in_progress = status == "in_progress"
    is_vote_phase = current_phase == "vote"

    return GameFlowState(
        game_id=game_id,
        status=status,
        current_phase=current_phase,
        phase_started_at=started_at,
        elapsed_seconds=elapsed,
        minimum_duration_seconds=minimum_duration,
        remaining_seconds=remaining,
        minimum_time_satisfied=minimum_time_satisfied,
        can_investigate=can_investigate(status, current_phase),
        can_discuss=in_progress and current_phase in DISCUSSION_PHASES,
        can_vote=in_progress and is_vote_phase and not voting_complete,
        can_advance=(
            in_progress
            and next_phase(current_phase) is not None
            and minimum_time_satisfied
            and (not is_vote_phase or voting_complete)
        ),
        is_finished=status == "finished",
        vote_progress=GameFlowVoteProgress(
            votes_cast=votes_cast,
            total_voters=total_voters,
            voting_complete=voting_complete,
        ),
    )


def tally_votes(
    votes: Sequence[tuple[int, int]], game_character_ids: Sequence[int]
) -> tuple[dict[int, int], int | None, bool]:
    """Count votes in stable character order and detect positive-count ties."""
    counts = {character_id: 0 for character_id in game_character_ids}
    for _voter_id, target_id in votes:
        if target_id in counts:
            counts[target_id] += 1

    highest = max(counts.values(), default=0)
    if highest == 0:
        return counts, None, False

    leaders = [
        character_id for character_id, count in counts.items() if count == highest
    ]
    if len(leaders) > 1:
        return counts, None, True
    return counts, leaders[0], False


def _as_utc(value: datetime) -> datetime:
    """Treat SQLite's naive UTC timestamps as UTC for consistent arithmetic."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
