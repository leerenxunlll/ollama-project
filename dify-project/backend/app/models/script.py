"""Reusable script templates and their predefined characters and clues."""

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.game import GameCharacter, GameCharacterClue, GameSession


class Script(Base):
    """A reusable murder-mystery script definition."""

    __tablename__ = "scripts"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'ready')", name="ck_scripts_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    theme: Mapped[str | None] = mapped_column(String(120), nullable=True)
    era: Mapped[str | None] = mapped_column(String(120), nullable=True)
    atmosphere: Mapped[str | None] = mapped_column(String(120), nullable=True)
    difficulty: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    characters: Mapped[list["Character"]] = relationship(back_populates="script")
    clues: Mapped[list["Clue"]] = relationship(back_populates="script")
    shared_script_chapters: Mapped[list["SharedScriptChapter"]] = relationship(
        back_populates="script"
    )
    game_sessions: Mapped[list["GameSession"]] = relationship(back_populates="script")


class Character(Base):
    """A character template; private details stay separate from public bio."""

    __tablename__ = "characters"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    script_id: Mapped[int] = mapped_column(ForeignKey("scripts.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    identity: Mapped[str] = mapped_column(String(160), nullable=False)
    public_background: Mapped[str] = mapped_column(Text, nullable=False)
    private_background: Mapped[str] = mapped_column(Text, nullable=False)
    personality: Mapped[str] = mapped_column(Text, nullable=False)
    speaking_style: Mapped[str] = mapped_column(Text, nullable=False)
    personal_goal: Mapped[str] = mapped_column(Text, nullable=False)
    personal_history: Mapped[str | None] = mapped_column(Text, nullable=True)
    relationship_to_victim: Mapped[str | None] = mapped_column(Text, nullable=True)
    pre_case_experience: Mapped[str | None] = mapped_column(Text, nullable=True)
    private_secrets_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    initial_knowledge_json: Mapped[list[str] | None] = mapped_column(
        JSON, nullable=True
    )
    is_killer: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    script: Mapped["Script"] = relationship(back_populates="characters")
    game_characters: Mapped[list["GameCharacter"]] = relationship(
        back_populates="character"
    )
    script_chapters: Mapped[list["CharacterScriptChapter"]] = relationship(
        back_populates="character"
    )


class ScriptCanonicalData(Base):
    """God/Director-only facts and stable draft-key mappings for one Script."""

    __tablename__ = "script_canonical_data"

    script_id: Mapped[int] = mapped_column(ForeignKey("scripts.id"), primary_key=True)
    case_truth_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    timeline_json: Mapped[list[dict]] = mapped_column(JSON, nullable=False)
    role_character_ids_json: Mapped[dict[str, int]] = mapped_column(
        JSON, nullable=False
    )
    clue_ids_json: Mapped[dict[str, int]] = mapped_column(JSON, nullable=False)
    clue_event_keys_json: Mapped[dict[str, list[str]]] = mapped_column(
        JSON, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class Clue(Base):
    """A clue predefined as part of a script."""

    __tablename__ = "clues"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    script_id: Mapped[int] = mapped_column(ForeignKey("scripts.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    act: Mapped[str] = mapped_column(String(80), nullable=False)
    location: Mapped[str] = mapped_column(String(160), nullable=False)
    is_core: Mapped[bool] = mapped_column(default=False, nullable=False)
    importance: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    script: Mapped["Script"] = relationship(back_populates="clues")
    game_character_clues: Mapped[list["GameCharacterClue"]] = relationship(
        back_populates="clue"
    )


class SharedScriptChapter(Base):
    """A story chapter shared by every character in a script."""

    __tablename__ = "shared_script_chapters"
    __table_args__ = (
        CheckConstraint(
            "unlock_phase IN ('intro', 'act_1', 'act_2')",
            name="ck_shared_script_chapters_unlock_phase",
        ),
        CheckConstraint(
            "chapter_order > 0",
            name="ck_shared_script_chapters_order_positive",
        ),
        UniqueConstraint(
            "script_id", "chapter_order", name="uq_shared_script_chapters_script_order"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    script_id: Mapped[int] = mapped_column(ForeignKey("scripts.id"), nullable=False)
    chapter_order: Mapped[int] = mapped_column(Integer, nullable=False)
    unlock_phase: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    script: Mapped["Script"] = relationship(back_populates="shared_script_chapters")


class CharacterScriptChapter(Base):
    """A private story chapter belonging to one script character template."""

    __tablename__ = "character_script_chapters"
    __table_args__ = (
        CheckConstraint(
            "unlock_phase IN ('intro', 'act_1', 'act_2')",
            name="ck_character_script_chapters_unlock_phase",
        ),
        CheckConstraint(
            "chapter_order > 0",
            name="ck_character_script_chapters_order_positive",
        ),
        UniqueConstraint(
            "character_id",
            "chapter_order",
            name="uq_character_script_chapters_character_order",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id"), nullable=False
    )
    chapter_order: Mapped[int] = mapped_column(Integer, nullable=False)
    unlock_phase: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    character: Mapped["Character"] = relationship(back_populates="script_chapters")
