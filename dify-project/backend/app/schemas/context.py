"""Permission-filtered contexts intended for future AI orchestration."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.ai import CharacterEmotion


class ContextMemory(BaseModel):
    """One memory known only by the character receiving this context."""

    content: str
    importance: int
    created_at: datetime


class ContextGame(BaseModel):
    """Non-sensitive game fields visible in an agent context."""

    id: int
    status: str
    current_phase: str


class ContextCharacter(BaseModel):
    """The current character's own private role and runtime state."""

    game_character_id: int
    character_id: int
    name: str
    identity: str
    public_background: str
    private_background: str
    personality: str
    speaking_style: str
    personal_goal: str
    personal_history: str | None = None
    relationship_to_victim: str | None = None
    pre_case_experience: str | None = None
    private_secrets: list[str] = Field(default_factory=list)
    initial_knowledge: list[str] = Field(default_factory=list)
    current_emotion: CharacterEmotion | None
    current_goal: str | None


class ContextOtherCharacter(BaseModel):
    """Public details about another character in the same game."""

    game_character_id: int
    name: str
    identity: str
    public_background: str


class ContextMessage(BaseModel):
    """One message visible to the context recipient."""

    id: int
    sender_game_character_id: int | None
    channel_type: Literal["public", "private", "system"]
    receiver_game_character_id: int | None
    content: str
    created_at: datetime


class ContextClue(BaseModel):
    """A clue explicitly granted to the context recipient."""

    clue_id: int
    name: str
    description: str
    act: str
    location: str
    is_core: bool
    importance: int
    discovered_at: datetime
    source: str | None


class ContextScriptChapter(BaseModel):
    """One prewritten chapter currently unlocked for this character."""

    chapter_id: int
    chapter_order: int
    unlock_phase: Literal["intro", "act_1", "act_2"]
    title: str
    content: str


class CharacterContext(BaseModel):
    """Complete, permission-filtered input for one future Character Agent."""

    game: ContextGame
    character: ContextCharacter
    other_characters: list[ContextOtherCharacter]
    public_messages: list[ContextMessage]
    private_messages: list[ContextMessage]
    known_clues: list[ContextClue]
    memories: list[ContextMemory]
    shared_script_chapters: list[ContextScriptChapter]
    character_script_chapters: list[ContextScriptChapter]


class DirectorCharacterContext(BaseModel):
    """Character data a future Director may inspect, including secrets."""

    game_character_id: int
    character_id: int
    name: str
    identity: str
    public_background: str
    private_background: str
    personality: str
    speaking_style: str
    personal_goal: str
    is_killer: bool
    controller_type: str | None
    current_emotion: str | None
    current_goal: str | None


class DirectorClueContext(BaseModel):
    """A script clue and the runtime characters who have discovered it."""

    clue_id: int
    name: str
    description: str
    act: str
    location: str
    is_core: bool
    importance: int
    known_by_game_character_ids: list[int]


class DirectorContext(BaseModel):
    """Schema for a future privileged Director context; no builder or API yet."""

    game: ContextGame
    characters: list[DirectorCharacterContext]
    messages: list[ContextMessage]
    clues: list[DirectorClueContext]
