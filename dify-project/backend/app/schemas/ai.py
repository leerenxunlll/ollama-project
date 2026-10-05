"""Request and response schemas for AI status and character chat."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.game import MessageRead


class AIStatusRead(BaseModel):
    """Expose whether character chat is configured without revealing secrets."""

    configured: bool


class AIChatRequest(BaseModel):
    """A human player's message addressed to one AI-controlled character."""

    target_game_character_id: int
    content: str = Field(min_length=1)

    @field_validator("content")
    @classmethod
    def validate_content(cls, content: str) -> str:
        """Reject whitespace-only player messages while preserving their text."""
        if not content.strip():
            raise ValueError("Message content cannot be empty")
        return content


class AIChatResponse(BaseModel):
    """The two persisted messages produced by one successful AI chat turn."""

    human_message: MessageRead
    ai_message: MessageRead


class CharacterEmotion(str, Enum):
    """Finite set of emotions accepted from a Character Agent."""

    CALM = "calm"
    NERVOUS = "nervous"
    ANGRY = "angry"
    AFRAID = "afraid"
    SAD = "sad"
    CONFIDENT = "confident"
    SUSPICIOUS = "suspicious"
    CONFUSED = "confused"


class CharacterIntent(str, Enum):
    """A descriptive intent that never triggers a game action by itself."""

    COOPERATE = "cooperate"
    HIDE_INFORMATION = "hide_information"
    SEEK_INFORMATION = "seek_information"
    ACCUSE = "accuse"
    DEFLECT = "deflect"
    PERSUADE = "persuade"
    OBSERVE = "observe"
    OTHER = "other"


class MemoryUpdate(BaseModel):
    """One proposed subjective memory from a validated character turn."""

    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1)
    importance: int = Field(ge=1, le=5)

    @field_validator("content")
    @classmethod
    def validate_content(cls, content: str) -> str:
        """Reject blank memory text while keeping meaningful whitespace intact."""
        if not content.strip():
            raise ValueError("Memory content cannot be empty")
        return content.strip()


class CharacterModelOutput(BaseModel):
    """Strict JSON contract returned by the Dify Character Chatflow."""

    model_config = ConfigDict(extra="forbid")

    speech: str = Field(min_length=1)
    inner_os: str = Field(max_length=500)
    emotion: CharacterEmotion
    intent: CharacterIntent
    memory_updates: list[MemoryUpdate] = Field(max_length=2)

    @field_validator("speech")
    @classmethod
    def validate_speech(cls, speech: str) -> str:
        """Reject blank speech before the backend persists a turn."""
        if not speech.strip():
            raise ValueError("Speech cannot be empty")
        return speech.strip()

    @field_validator("inner_os")
    @classmethod
    def validate_inner_os(cls, inner_os: str) -> str:
        """Reject blank thoughts and keep this private field concise."""
        if not inner_os.strip():
            raise ValueError("Inner OS cannot be empty")
        return inner_os.strip()


class CharacterThoughtRead(BaseModel):
    """Private thought fields returned only by a development endpoint."""

    model_config = ConfigDict(from_attributes=True)

    inner_os: str
    emotion: CharacterEmotion
    intent: CharacterIntent
    created_at: datetime


class CharacterMemoryRead(BaseModel):
    """A stored subjective memory shown in the development inspector."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    content: str
    importance: int
    source_message_id: int
    created_at: datetime


class CharacterDebugStateRead(BaseModel):
    """Development-only cognitive state for one AI-controlled character."""

    game_id: int
    game_character_id: int
    current_emotion: CharacterEmotion | None
    latest_thought: CharacterThoughtRead | None
    memories: list[CharacterMemoryRead]
