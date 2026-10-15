"""Safe ending and post-game God-View replay projections."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.schemas.voting import VoteReveal


class EndingTruth(BaseModel):
    """Canonical facts published with the script, revealed after resolution."""

    model_config = ConfigDict(extra="forbid")

    culprit_role_key: str
    victim: str
    motive: str
    method: str
    crime_time: str
    crime_location: str
    case_summary: str
    key_causal_facts: list[str]


class CanonicalTimelineEvent(BaseModel):
    """One published timeline entry; this does not assert it occurred in-game."""

    model_config = ConfigDict(extra="forbid")

    event_key: str
    time: str
    location: str
    description: str
    involved_role_keys: list[str]
    is_public_knowledge: bool


class EndingClue(BaseModel):
    """A formal clue marked core in the published script."""

    clue_id: int
    name: str
    description: str
    act: str
    location: str


class GameEndingRead(BaseModel):
    """Final deterministic result plus authoritative script truth."""

    game_id: int
    script_id: int
    culprit_game_character_id: int
    culprit_name: str
    vote_result: Literal["culprit_identified", "wrong_accusation", "tie"]
    accused_game_character_id: int | None
    is_tie: bool
    human_vote_target_id: int
    human_identified_culprit: bool
    case_outcome: Literal["culprit_identified", "wrong_accusation", "tie"]
    ending_narrative: str
    resolved_at: datetime
    truth: EndingTruth
    canonical_timeline: list[CanonicalTimelineEvent]
    key_clues: list[EndingClue]
    votes: list[VoteReveal]


ReplayEventType = Literal[
    "game_started",
    "message",
    "character_thought",
    "character_memory",
    "clue_acquired",
    "clue_disclosure",
    "vote",
    "game_ended",
]
ReplayVisibility = Literal["public", "private", "god"]


class GameReplayEvent(BaseModel):
    """One persisted event projected for the post-game God-View."""

    event_id: str
    event_type: ReplayEventType
    timestamp: datetime
    phase: str | None
    actor_game_character_id: int | None
    actor_name: str | None
    target_game_character_id: int | None = None
    target_name: str | None = None
    visibility: ReplayVisibility
    content: str | None = None
    inner_os: str | None = None
    emotion: str | None = None
    intent: str | None = None
    memory_importance: int | None = None
    subjective: bool = False
    related_message_id: int | None = None
    related_clue_id: int | None = None
    related_vote_id: int | None = None


class GameReplayRead(BaseModel):
    """Stable, read-only chronological projection after valid resolution."""

    game_id: int
    started_at: datetime | None
    ended_at: datetime
    events: list[GameReplayEvent]
