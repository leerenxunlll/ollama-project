"""Character roleplay orchestration using only a validated safe context."""

from pydantic import BaseModel, ValidationError

from app.agents.dify_client import DifyClient
from app.core.config import settings
from app.schemas.ai import (
    CharacterEmotion,
    CharacterIntent,
    CharacterModelOutput,
    MemoryUpdate,
)
from app.schemas.context import CharacterContext


class CharacterOutputValidationError(Exception):
    """Raised when a Dify answer does not match the structured reply contract."""


class CharacterReply(BaseModel):
    """Validated internal reply consumed by the game chat service."""

    speech: str
    inner_os: str
    emotion: CharacterEmotion
    intent: CharacterIntent
    memory_updates: list[MemoryUpdate]


def parse_character_reply(answer: str) -> CharacterReply:
    """Parse Dify's raw JSON answer and reject any invalid character state."""
    try:
        model_output = CharacterModelOutput.model_validate_json(answer)
    except ValidationError as error:
        raise CharacterOutputValidationError(
            "Dify returned invalid structured character output"
        ) from error
    return CharacterReply.model_validate(model_output.model_dump())


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
        return parse_character_reply(answer)


def get_character_agent() -> CharacterAgent:
    """Create a request-scoped agent; missing configuration fails only on use."""
    return CharacterAgent(
        DifyClient(
            api_url=settings.dify_api_url,
            api_key=settings.dify_character_api_key,
        )
    )
