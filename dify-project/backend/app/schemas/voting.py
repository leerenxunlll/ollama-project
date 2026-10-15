"""Strict schemas for private AI voting and safe vote progress."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.context import CharacterContext


class StrictVoteModel(BaseModel):
    """Reject unexpected fields in generated voting data."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CharacterVoteCandidate(StrictVoteModel):
    """One public, eligible target in the current game."""

    game_character_id: int = Field(gt=0)
    character_name: Annotated[str, Field(min_length=1, max_length=120)]
    public_identity: Annotated[str, Field(min_length=1, max_length=160)]


class CharacterVoteContext(StrictVoteModel):
    """Permission-filtered information for one AI vote decision."""

    game_id: int = Field(gt=0)
    voter_game_character_id: int = Field(gt=0)
    current_phase: Literal["vote"]
    character_context: CharacterContext
    eligible_candidates: list[CharacterVoteCandidate] = Field(
        min_length=3, max_length=3
    )


class CharacterVoteDecision(StrictVoteModel):
    """One structured target and concise fictional decision rationale."""

    target_game_character_id: int = Field(gt=0, strict=True)
    reason: Annotated[str, Field(min_length=1, max_length=500, strict=True)]
    confidence: float = Field(ge=0, le=1, strict=True)


class VoteCharacterStatus(StrictVoteModel):
    """A safe completion flag without revealing the target."""

    game_character_id: int
    character_name: str
    has_voted: bool


class GameVoteStatus(StrictVoteModel):
    """Publicly safe vote progress for the one-human/three-AI game."""

    game_id: int
    current_phase: str
    votes_cast: int
    total_voters: int
    human_has_voted: bool
    ai_characters: list[VoteCharacterStatus]
    voting_complete: bool


class AIVoteWorkflowStatus(StrictVoteModel):
    """Credential presence only; never contains a key value."""

    configured: bool


class VoteReveal(StrictVoteModel):
    """One final vote, revealed only after a valid resolution exists."""

    vote_id: int
    voter_game_character_id: int
    voter_name: str
    target_game_character_id: int
    target_name: str
    reason: str | None
    created_at: datetime


class VoteTally(StrictVoteModel):
    """Deterministic tally reused by resolution and ending projections."""

    vote_count_by_target: dict[int, int]
    winner_game_character_id: int | None
    is_tie: bool
