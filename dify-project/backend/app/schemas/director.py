"""Director-only context, structured recommendations, and API responses."""

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.flow import GameFlowState
from app.schemas.game import MessageRead


class DirectorPace(str, Enum):
    """Narrative pacing observations allowed from the Director workflow."""

    on_track = "on_track"
    stalled = "stalled"
    rushed = "rushed"
    off_track = "off_track"


class DirectorNarrativeRisk(str, Enum):
    """Bounded risk level for the currently observed public narrative."""

    low = "low"
    medium = "medium"
    high = "high"


class DirectorAction(str, Enum):
    """Only the small, explicitly validated action set the Director may suggest."""

    no_action = "no_action"
    request_ai_speaker = "request_ai_speaker"
    recommend_phase_advance = "recommend_phase_advance"
    suggest_clue_hint = "suggest_clue_hint"
    highlight_public_fact = "highlight_public_fact"


class DirectorRecommendation(BaseModel):
    """Strict workflow output; it contains recommendations, never commands."""

    model_config = ConfigDict(extra="forbid")

    pace: DirectorPace
    narrative_risk: DirectorNarrativeRisk
    recommended_action: DirectorAction
    reason: str = Field(min_length=1, max_length=1000)
    target_game_character_id: int | None = Field(default=None, gt=0)
    clue_id: int | None = Field(default=None, gt=0)
    public_message_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_action_reference(self) -> "DirectorRecommendation":
        """Require exactly the reference appropriate to the selected action."""
        required_reference = {
            DirectorAction.request_ai_speaker: "target_game_character_id",
            DirectorAction.suggest_clue_hint: "clue_id",
            DirectorAction.highlight_public_fact: "public_message_id",
        }.get(self.recommended_action)
        references = {
            "target_game_character_id": self.target_game_character_id,
            "clue_id": self.clue_id,
            "public_message_id": self.public_message_id,
        }
        if required_reference and references[required_reference] is None:
            raise ValueError(
                f"{self.recommended_action.value} requires {required_reference}"
            )
        if any(
            value is not None
            for key, value in references.items()
            if key != required_reference
        ):
            raise ValueError("Recommendation contains an unrelated reference")
        if not self.reason.strip():
            raise ValueError("Recommendation reason cannot be blank")
        return self


class DirectorCharacterFact(BaseModel):
    """Authoritative script character data available to the Director only."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    age: int | None
    identity: str
    public_background: str
    private_background: str
    personality: str
    speaking_style: str
    personal_goal: str
    is_killer: bool


class DirectorClueFact(BaseModel):
    """Authoritative predefined clue data available to the Director."""

    id: int
    name: str
    description: str
    act: str
    location: str
    is_core: bool
    importance: int


class DirectorScriptContext(BaseModel):
    """Current Script facts without a speculative canonical truth document."""

    id: int
    title: str
    summary: str | None
    theme: str | None
    era: str | None
    atmosphere: str | None
    difficulty: str | None
    status: str
    culprit_character_id: int | None
    characters: list[DirectorCharacterFact]
    clues: list[DirectorClueFact]


class DirectorPublicMessage(BaseModel):
    """One public or system message; private channels have no schema path here."""

    id: int
    sender_game_character_id: int | None
    sender_name: str | None
    channel_type: Literal["public", "system"]
    content: str
    created_at: datetime


class DirectorPublicState(BaseModel):
    """A bounded recent public transcript used for narrative observation."""

    recent_messages: list[DirectorPublicMessage]


class DirectorClueProgress(BaseModel):
    """Objective clue acquisition state, not a character's subjective memory."""

    clue_id: int
    name: str
    act: str
    location: str
    is_core: bool
    importance: int
    available_in_current_phase: bool
    acquired_by_game_character_ids: list[int]


class DirectorParticipation(BaseModel):
    """Deterministic public participation counts for one runtime character."""

    game_character_id: int
    character_name: str
    controller_type: str | None
    public_message_count: int
    last_public_speech_at: datetime | None
    inactive_long_enough: bool


class DirectorVotingState(BaseModel):
    """Aggregate vote state without the voter-to-target mapping."""

    vote_count_by_target: dict[int, int]
    winner_game_character_id: int | None
    is_tie: bool
    votes_cast: int
    total_voters: int
    voting_complete: bool


class DirectorContext(BaseModel):
    """Dedicated Director input, intentionally separate from CharacterContext."""

    game_id: int
    script: DirectorScriptContext
    game_flow: GameFlowState
    voting_state: DirectorVotingState
    public_state: DirectorPublicState
    clue_progress: list[DirectorClueProgress]
    participation: list[DirectorParticipation]


class DirectorRecommendationRead(BaseModel):
    """Persisted recommendation shown only in Development / Debug UI."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    game_session_id: int
    pace: DirectorPace
    narrative_risk: DirectorNarrativeRisk
    recommended_action: DirectorAction
    target_game_character_id: int | None
    clue_id: int | None
    public_message_id: int | None
    reason: str
    status: Literal["pending", "applied", "rejected", "advisory"]
    created_at: datetime
    applied_at: datetime | None


class DirectorConfiguredRead(BaseModel):
    """Only exposes whether the independent Director workflow is configured."""

    configured: bool


class DirectorApplyResponse(BaseModel):
    """Outcome of validating and handling one recommendation exactly once."""

    recommendation_id: int
    status: Literal["applied", "rejected", "advisory"]
    reason: str
    public_message: MessageRead | None = None
    flow_state: GameFlowState | None = None
