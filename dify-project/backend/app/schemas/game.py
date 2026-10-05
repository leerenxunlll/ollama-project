"""Request and response schemas for game session endpoints."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    controller_type: str | None
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


class GameStateRead(BaseModel):
    """Safe lifecycle and narrative state for the development interface."""

    game_id: int
    status: str
    current_phase: str
    started_at: datetime | None
    ended_at: datetime | None
    next_phase: str | None
    can_investigate: bool


class InvestigationLocationsRead(BaseModel):
    """Locations with undiscovered clues for the current investigation act."""

    game_id: int
    current_phase: str
    locations: list[str]


class InvestigationSearch(BaseModel):
    """Search one location on behalf of a runtime character."""

    game_character_id: int
    location: str = Field(min_length=1)


class InvestigationClueRead(BaseModel):
    """A clue explicitly granted by one search action."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    act: str
    location: str
    is_core: bool
    importance: int


class InvestigationResultRead(BaseModel):
    """Result of a deterministic search; an empty result is still successful."""

    game_id: int
    game_character_id: int
    location: str
    found: bool
    clue: InvestigationClueRead | None


class PlayerMessageCreate(BaseModel):
    """A public or private message submitted by a game character."""

    sender_game_character_id: int
    channel_type: str = Field(pattern="^(public|private)$")
    receiver_game_character_id: int | None = None
    content: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_receiver(self) -> "PlayerMessageCreate":
        """Match receiver presence to the selected conversation channel."""
        if (
            self.channel_type == "public"
            and self.receiver_game_character_id is not None
        ):
            raise ValueError("Public messages cannot have a receiver")
        if self.channel_type == "private" and self.receiver_game_character_id is None:
            raise ValueError("Private messages require a receiver")
        return self


class MessageRead(BaseModel):
    """Persisted player message; system messages are not accepted by this API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    game_session_id: int
    sender_game_character_id: int
    channel_type: str
    receiver_game_character_id: int | None
    content: str
    created_at: datetime


class SelectableCharacterRead(BaseModel):
    """Public-only details available during human character selection."""

    game_character_id: int
    character_id: int
    name: str
    age: int | None
    identity: str
    public_background: str
    personality: str
    speaking_style: str


class CharacterSelection(BaseModel):
    """Request to assign the human player to one runtime character."""

    game_character_id: int


class MyCharacterRead(BaseModel):
    """The selected human character card and only its own private fields."""

    game_character_id: int
    character_id: int
    name: str
    age: int | None
    identity: str
    public_background: str
    private_background: str
    personality: str
    speaking_style: str
    personal_goal: str
    current_emotion: str | None
    current_goal: str | None
