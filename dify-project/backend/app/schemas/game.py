"""Request and response schemas for game session endpoints."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class GameCreate(BaseModel):
    """Request to start a game from an existing ready script."""

    script_id: int


class CharacterSummary(BaseModel):
    """Character fields safe for the basic game status response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class GameCharacterRead(BaseModel):
    """The visible identity and controller for a runtime character."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    character_id: int
    controller_type: str
    character: CharacterSummary


class GameRead(BaseModel):
    """Basic game state without private character state or random seed."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    script_id: int
    status: str
    current_phase: str
    created_at: datetime
    started_at: datetime | None
    ended_at: datetime | None
    game_characters: list[GameCharacterRead]
