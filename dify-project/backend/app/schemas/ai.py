"""Request and response schemas for AI status and character chat."""

from pydantic import BaseModel, Field, field_validator

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
