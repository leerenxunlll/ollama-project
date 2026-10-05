"""Runtime game sessions, character instances, and conversation messages."""

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.script import Character, Script


class GameSession(Base):
    """One playthrough of a reusable script."""

    __tablename__ = "game_sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('in_progress', 'completed', 'abandoned')",
            name="ck_game_sessions_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    script_id: Mapped[int] = mapped_column(ForeignKey("scripts.id"), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="in_progress", nullable=False
    )
    current_phase: Mapped[str] = mapped_column(
        String(80), default="introduction", nullable=False
    )
    random_seed: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    script: Mapped["Script"] = relationship(back_populates="game_sessions")
    game_characters: Mapped[list["GameCharacter"]] = relationship(
        back_populates="game_session"
    )
    messages: Mapped[list["Message"]] = relationship(back_populates="game_session")


class GameCharacter(Base):
    """The runtime state of one character within one game session."""

    __tablename__ = "game_characters"
    __table_args__ = (
        UniqueConstraint(
            "game_session_id", "character_id", name="uq_game_character_per_session"
        ),
        CheckConstraint(
            "controller_type IN ('human', 'ai')", name="ck_game_characters_controller"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    game_session_id: Mapped[int] = mapped_column(
        ForeignKey("game_sessions.id"), nullable=False
    )
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id"), nullable=False
    )
    controller_type: Mapped[str] = mapped_column(String(20), nullable=False)
    current_emotion: Mapped[str | None] = mapped_column(String(120), nullable=True)
    current_goal: Mapped[str | None] = mapped_column(Text, nullable=True)

    game_session: Mapped["GameSession"] = relationship(back_populates="game_characters")
    character: Mapped["Character"] = relationship(back_populates="game_characters")
    sent_messages: Mapped[list["Message"]] = relationship(
        back_populates="sender_game_character",
        foreign_keys="Message.sender_game_character_id",
    )
    received_messages: Mapped[list["Message"]] = relationship(
        back_populates="receiver_game_character",
        foreign_keys="Message.receiver_game_character_id",
    )


class Message(Base):
    """A public, private, or system message from a game session."""

    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint(
            "channel_type IN ('public', 'private', 'system')",
            name="ck_messages_channel_type",
        ),
        CheckConstraint(
            "(channel_type = 'private' AND receiver_game_character_id IS NOT NULL) "
            "OR (channel_type IN ('public', 'system') "
            "AND receiver_game_character_id IS NULL)",
            name="ck_messages_receiver_by_channel",
        ),
        CheckConstraint(
            "channel_type = 'system' OR sender_game_character_id IS NOT NULL",
            name="ck_messages_sender_by_channel",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    game_session_id: Mapped[int] = mapped_column(
        ForeignKey("game_sessions.id"), nullable=False
    )
    sender_game_character_id: Mapped[int | None] = mapped_column(
        ForeignKey("game_characters.id"), nullable=True
    )
    channel_type: Mapped[str] = mapped_column(String(20), nullable=False)
    receiver_game_character_id: Mapped[int | None] = mapped_column(
        ForeignKey("game_characters.id"), nullable=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    game_session: Mapped["GameSession"] = relationship(back_populates="messages")
    sender_game_character: Mapped["GameCharacter | None"] = relationship(
        back_populates="sent_messages",
        foreign_keys=[sender_game_character_id],
    )
    receiver_game_character: Mapped["GameCharacter | None"] = relationship(
        back_populates="received_messages",
        foreign_keys=[receiver_game_character_id],
    )
