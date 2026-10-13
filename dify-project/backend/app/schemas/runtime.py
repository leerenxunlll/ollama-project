"""Safe request and response schemas for the bounded game runtime."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

RuntimeStatus = Literal["not_started", "enabled", "paused"]
RuntimeActionType = Literal[
    "none",
    "director_analysis",
    "proactive_speech",
    "phase_advance",
    "advisory",
]
RuntimeExecutionStatus = Literal["idle", "completed", "failed", "conflict"]


class GameRuntimeActionRead(BaseModel):
    """A runtime audit row without event keys, tokens, or model context."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: str
    action_type: str | None
    execution_status: Literal["processing", "completed", "failed", "skipped"]
    reason_code: str | None
    started_at: datetime
    completed_at: datetime | None
    related_message_id: int | None
    related_recommendation_id: int | None


class GameRuntimeStatusRead(BaseModel):
    """Current safe scheduler state and recent action summaries."""

    game_id: int
    game_status: str
    current_phase: str
    runtime_status: RuntimeStatus
    phase_read_acknowledged: bool
    ready_for_phase: str | None
    action_status: Literal["idle", "processing", "failed"]
    last_tick_at: datetime | None
    last_director_analysis_at: datetime | None
    last_proactive_speech_at: datetime | None
    last_action_type: str | None
    last_error_code: str | None
    next_check_after_seconds: int
    recent_actions: list[GameRuntimeActionRead]


class RuntimeStepResult(BaseModel):
    """The outcome of one bounded tick without exposing Director reasoning."""

    game_id: int
    runtime_status: RuntimeStatus
    action_type: RuntimeActionType
    execution_status: RuntimeExecutionStatus
    phase_before: str
    phase_after: str
    public_message_id: int | None = None
    recommendation_id: int | None = None
    reason_code: str
    next_check_after_seconds: int


class PhaseReadAcknowledgement(BaseModel):
    """Confirmation for the current intro, Act 1, or Act 2 only."""

    game_id: int
    phase: Literal["intro", "act_1", "act_2"]
    acknowledged: bool
    acknowledged_at: datetime


class RuntimeReadyResponse(BaseModel):
    """Explicit readiness for the current investigation or discussion phase."""

    game_id: int
    phase: Literal[
        "investigation_1",
        "discussion_1",
        "investigation_2",
        "discussion_2",
        "final_discussion",
    ]
    ready: bool
    ready_at: datetime
