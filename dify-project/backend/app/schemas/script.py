"""Request and response schemas for script endpoints."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ScriptCreate(BaseModel):
    """Fields accepted when creating a draft script."""

    title: str = Field(min_length=1, max_length=200)
    summary: str | None = None
    theme: str | None = Field(default=None, max_length=120)
    era: str | None = Field(default=None, max_length=120)
    atmosphere: str | None = Field(default=None, max_length=120)
    difficulty: str | None = Field(default=None, max_length=40)


class ScriptRead(BaseModel):
    """Public metadata returned for one script."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    summary: str | None
    theme: str | None
    era: str | None
    atmosphere: str | None
    difficulty: str | None
    status: str
    created_at: datetime
    updated_at: datetime
