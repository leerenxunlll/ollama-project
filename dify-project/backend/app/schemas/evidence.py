"""Safe request and response schemas for investigation and clue sharing."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

ClueVisibility = Literal["private", "public"]
ClueKnowledgeSource = Literal[
    "direct_acquisition", "private_disclosure", "public_disclosure"
]


class ClueEvidenceRead(BaseModel):
    """A clue the current player is allowed to see."""

    clue_id: int
    name: str
    description: str
    act: str
    location: str
    importance: int
    knowledge_source: ClueKnowledgeSource
    first_known_at: datetime
    source_game_character_id: int | None = None


class MyClueStateRead(BaseModel):
    """Separate direct discoveries, private shares, and public clues."""

    game_id: int
    human_game_character_id: int
    acquired_clues: list[ClueEvidenceRead]
    known_via_share_clues: list[ClueEvidenceRead]
    publicly_disclosed_clues: list[ClueEvidenceRead]


class PublicCluesRead(BaseModel):
    game_id: int
    clues: list[ClueEvidenceRead]


class ClueShareRequest(BaseModel):
    clue_id: int = Field(gt=0)
    visibility: ClueVisibility
    target_game_character_id: int | None = Field(default=None, gt=0)
    client_request_id: UUID

    @model_validator(mode="after")
    def validate_target(self) -> "ClueShareRequest":
        if self.visibility == "private" and self.target_game_character_id is None:
            raise ValueError("Private clue sharing requires a target")
        if self.visibility == "public" and self.target_game_character_id is not None:
            raise ValueError("Public clue sharing cannot have a target")
        return self


class ClueDisclosureRead(BaseModel):
    id: int
    game_id: int
    clue_id: int
    source_game_character_id: int
    visibility: ClueVisibility
    target_game_character_id: int | None
    related_message_id: int
    created_at: datetime
    replayed: bool = False


class ClueHistoryEventRead(BaseModel):
    event_id: str
    event_type: Literal[
        "clue_acquired", "clue_shared_privately", "clue_disclosed_publicly"
    ]
    clue_id: int
    clue_name: str
    actor_name: str
    target_name: str | None
    occurred_at: datetime
