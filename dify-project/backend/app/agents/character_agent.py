"""Character roleplay orchestration using only a validated safe context."""

from pydantic import BaseModel, Field, field_validator

from app.agents.dify_client import DifyClient
from app.core.config import settings
from app.schemas.context import CharacterContext


class CharacterReply(BaseModel):
    """A character's spoken reply returned by its Chatflow."""

    speech: str = Field(min_length=1)

    @field_validator("speech")
    @classmethod
    def validate_speech(cls, speech: str) -> str:
        """Reject blank replies before they can be persisted as messages."""
        if not speech.strip():
            raise ValueError("Character reply cannot be empty")
        return speech


class CharacterAgent:
    """Convert an authorized CharacterContext into one Dify Chatflow request."""

    def __init__(self, dify_client: DifyClient) -> None:
        self.dify_client = dify_client

    def respond(
        self,
        context: CharacterContext,
        query: str,
        user_id: str,
    ) -> CharacterReply:
        """Ask Dify to roleplay the character represented by this context."""
        answer = self.dify_client.chat(
            character_context=context.model_dump_json(),
            query=query,
            user_id=user_id,
        )
        return CharacterReply(speech=answer)


def get_character_agent() -> CharacterAgent:
    """Create a request-scoped agent; missing configuration fails only on use."""
    return CharacterAgent(
        DifyClient(
            api_url=settings.dify_api_url,
            api_key=settings.dify_character_api_key,
        )
    )
