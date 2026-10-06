"""Character interaction data passed to the shared Character Agent."""

from typing import Literal

from pydantic import BaseModel, Field

InteractionMode = Literal["private_reply", "public_reply", "proactive_public"]
InteractionChannel = Literal["private", "public"]


class CharacterInteraction(BaseModel):
    """Describe what triggered one character reply without exposing ORM state."""

    mode: InteractionMode
    channel: InteractionChannel
    source_game_character_id: int | None = None
    source_character_name: str | None = None
    current_message: str = Field(min_length=1)
