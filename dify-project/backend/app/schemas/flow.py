"""Safe game flow and development voting API schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class GameFlowVoteProgress(BaseModel):
    """Vote completion counts without exposing the live vote tally."""

    votes_cast: int
    total_voters: int
    voting_complete: bool


class GameFlowState(BaseModel):
    """Non-sensitive process state computed by the backend game flow manager."""

    game_id: int
    status: str
    current_phase: str
    phase_started_at: datetime | None
    elapsed_seconds: int
    minimum_duration_seconds: int
    remaining_seconds: int
    minimum_time_satisfied: bool
    can_investigate: bool
    can_discuss: bool
    can_vote: bool
    can_advance: bool
    is_finished: bool
    vote_progress: GameFlowVoteProgress


class VoteCreate(BaseModel):
    """Development request to record one character's final vote."""

    voter_game_character_id: int = Field(gt=0)
    target_game_character_id: int = Field(gt=0)


class VoteRead(BaseModel):
    """Persisted vote fields for the current unauthenticated development API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    game_session_id: int
    voter_game_character_id: int
    target_game_character_id: int
    created_at: datetime


class VoteResultRead(BaseModel):
    """Deterministic development tally; never returned by player-safe flow state."""

    game_id: int
    vote_count_by_target: dict[int, int]
    winner_game_character_id: int | None
    is_tie: bool
    votes_cast: int
    total_voters: int
    voting_complete: bool
    submitted_voter_game_character_ids: list[int]
