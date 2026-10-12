"""Safe response schemas for reader-visible script chapters."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ScriptChapterRead(BaseModel):
    """One chapter the caller is currently allowed to read."""

    chapter_id: int
    title: str
    chapter_order: int
    unlock_phase: Literal["intro", "act_1", "act_2"]
    content: str


class IntroAcknowledgementRead(BaseModel):
    """Persisted confirmation that the selected player read the intro."""

    game_id: int
    acknowledged: bool
    acknowledged_at: datetime
