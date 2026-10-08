"""Runtime game sessions, character instances, and conversation messages."""

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.script import Character, Clue, Script


class GameSession(Base):
    """One playthrough of a reusable script."""

    __tablename__ = "game_sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ("
            "'waiting_for_character_selection', 'ready', 'in_progress', "
            "'finished', 'completed', 'abandoned')",
            name="ck_game_sessions_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    script_id: Mapped[int] = mapped_column(ForeignKey("scripts.id"), nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), default="waiting_for_character_selection", nullable=False
    )
    current_phase: Mapped[str] = mapped_column(
        String(80), default="intro", nullable=False
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
    phase_started_at: Mapped[datetime | None] = mapped_column(
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
    character_thoughts: Mapped[list["CharacterThought"]] = relationship(
        back_populates="game_session"
    )
    character_memories: Mapped[list["CharacterMemory"]] = relationship(
        back_populates="game_session"
    )
    votes: Mapped[list["Vote"]] = relationship(back_populates="game_session")
    director_recommendations: Mapped[list["DirectorRecommendationRecord"]] = (
        relationship(back_populates="game_session")
    )


class GameCharacter(Base):
    """The runtime state of one character within one game session."""

    __tablename__ = "game_characters"
    __table_args__ = (
        UniqueConstraint(
            "game_session_id", "character_id", name="uq_game_character_per_session"
        ),
        Index(
            "uq_game_characters_session_id_id",
            "game_session_id",
            "id",
            unique=True,
        ),
        CheckConstraint(
            "controller_type IS NULL OR controller_type IN ('human', 'ai')",
            name="ck_game_characters_controller",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    game_session_id: Mapped[int] = mapped_column(
        ForeignKey("game_sessions.id"), nullable=False
    )
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id"), nullable=False
    )
    controller_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
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
    clue_discoveries: Mapped[list["GameCharacterClue"]] = relationship(
        back_populates="game_character"
    )
    thoughts: Mapped[list["CharacterThought"]] = relationship(
        back_populates="game_character",
        foreign_keys="CharacterThought.game_character_id",
    )
    memories: Mapped[list["CharacterMemory"]] = relationship(
        back_populates="game_character",
        foreign_keys="CharacterMemory.game_character_id",
    )
    votes_cast: Mapped[list["Vote"]] = relationship(
        back_populates="voter_game_character",
        foreign_keys="Vote.voter_game_character_id",
    )
    votes_received: Mapped[list["Vote"]] = relationship(
        back_populates="target_game_character",
        foreign_keys="Vote.target_game_character_id",
    )


class GameCharacterClue(Base):
    """A clue explicitly known by one character during one game."""

    __tablename__ = "game_character_clues"
    __table_args__ = (
        UniqueConstraint("game_character_id", "clue_id", name="uq_game_character_clue"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    game_character_id: Mapped[int] = mapped_column(
        ForeignKey("game_characters.id"), nullable=False
    )
    clue_id: Mapped[int] = mapped_column(ForeignKey("clues.id"), nullable=False)
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    source: Mapped[str | None] = mapped_column(String(80), nullable=True)

    game_character: Mapped["GameCharacter"] = relationship(
        back_populates="clue_discoveries"
    )
    clue: Mapped["Clue"] = relationship(back_populates="game_character_clues")


class Vote(Base):
    """One final vote cast by a runtime character in a game session."""

    __tablename__ = "votes"
    __table_args__ = (
        CheckConstraint(
            "voter_game_character_id != target_game_character_id",
            name="ck_vote_not_self",
        ),
        UniqueConstraint(
            "game_session_id",
            "voter_game_character_id",
            name="uq_vote_per_game_character",
        ),
        ForeignKeyConstraint(
            ["game_session_id", "voter_game_character_id"],
            ["game_characters.game_session_id", "game_characters.id"],
            name="fk_votes_voter_game_character_session",
        ),
        ForeignKeyConstraint(
            ["game_session_id", "target_game_character_id"],
            ["game_characters.game_session_id", "game_characters.id"],
            name="fk_votes_target_game_character_session",
        ),
        Index("ix_votes_game_session_id", "game_session_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    game_session_id: Mapped[int] = mapped_column(
        ForeignKey("game_sessions.id", name="fk_votes_game_session_id"), nullable=False
    )
    voter_game_character_id: Mapped[int] = mapped_column(nullable=False)
    target_game_character_id: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    game_session: Mapped["GameSession"] = relationship(back_populates="votes")
    voter_game_character: Mapped["GameCharacter"] = relationship(
        back_populates="votes_cast",
        foreign_keys=[game_session_id, voter_game_character_id],
        overlaps="game_session,votes",
    )
    target_game_character: Mapped["GameCharacter"] = relationship(
        back_populates="votes_received",
        foreign_keys=[game_session_id, target_game_character_id],
        overlaps="game_session,votes,voter_game_character",
    )


class DirectorRecommendationRecord(Base):
    """A validated Director suggestion and its deterministic handling status."""

    __tablename__ = "director_recommendations"
    __table_args__ = (
        CheckConstraint(
            "pace IN ('on_track', 'stalled', 'rushed', 'off_track')",
            name="ck_director_recommendations_pace",
        ),
        CheckConstraint(
            "narrative_risk IN ('low', 'medium', 'high')",
            name="ck_director_recommendations_narrative_risk",
        ),
        CheckConstraint(
            "recommended_action IN ('no_action', 'request_ai_speaker', "
            "'recommend_phase_advance', 'suggest_clue_hint', 'highlight_public_fact')",
            name="ck_director_recommendations_action",
        ),
        CheckConstraint(
            "status IN ('pending', 'applying', 'applied', 'rejected', 'advisory')",
            name="ck_director_recommendations_status",
        ),
        ForeignKeyConstraint(
            ["game_session_id", "target_game_character_id"],
            ["game_characters.game_session_id", "game_characters.id"],
            name="fk_director_recommendations_target_session",
        ),
        Index(
            "ix_director_recommendations_game_created",
            "game_session_id",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    game_session_id: Mapped[int] = mapped_column(
        ForeignKey(
            "game_sessions.id",
            name="fk_director_recommendations_game_session_id",
        ),
        nullable=False,
    )
    pace: Mapped[str] = mapped_column(String(20), nullable=False)
    narrative_risk: Mapped[str] = mapped_column(String(20), nullable=False)
    recommended_action: Mapped[str] = mapped_column(String(40), nullable=False)
    target_game_character_id: Mapped[int | None] = mapped_column(nullable=True)
    clue_id: Mapped[int | None] = mapped_column(
        ForeignKey("clues.id", name="fk_director_recommendations_clue_id"),
        nullable=True,
    )
    public_message_id: Mapped[int | None] = mapped_column(
        ForeignKey("messages.id", name="fk_director_recommendations_public_message_id"),
        nullable=True,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    applied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    game_session: Mapped["GameSession"] = relationship(
        back_populates="director_recommendations"
    )
    target_game_character: Mapped["GameCharacter | None"] = relationship(
        foreign_keys=[game_session_id, target_game_character_id],
        overlaps="game_session,director_recommendations",
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
        Index(
            "uq_messages_session_id_id",
            "game_session_id",
            "id",
            unique=True,
        ),
        Index(
            "uq_messages_session_id_id_sender",
            "game_session_id",
            "id",
            "sender_game_character_id",
            unique=True,
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
    character_thought: Mapped["CharacterThought | None"] = relationship(
        back_populates="ai_message",
        foreign_keys="CharacterThought.ai_message_id",
        uselist=False,
    )
    memory_updates: Mapped[list["CharacterMemory"]] = relationship(
        back_populates="source_message",
        foreign_keys="CharacterMemory.source_message_id",
    )


class CharacterThought(Base):
    """Private roleplay state produced alongside one AI message."""

    __tablename__ = "character_thoughts"
    __table_args__ = (
        CheckConstraint(
            "emotion IN ('calm', 'nervous', 'angry', 'afraid', 'sad', "
            "'confident', 'suspicious', 'confused')",
            name="ck_character_thoughts_emotion",
        ),
        CheckConstraint(
            "intent IN ('cooperate', 'hide_information', 'seek_information', "
            "'accuse', 'deflect', 'persuade', 'observe', 'other')",
            name="ck_character_thoughts_intent",
        ),
        ForeignKeyConstraint(
            ["game_session_id", "game_character_id"],
            ["game_characters.game_session_id", "game_characters.id"],
            name="fk_character_thoughts_game_character_session",
        ),
        ForeignKeyConstraint(
            ["game_session_id", "ai_message_id", "game_character_id"],
            [
                "messages.game_session_id",
                "messages.id",
                "messages.sender_game_character_id",
            ],
            name="fk_character_thoughts_ai_message_sender",
        ),
        UniqueConstraint("ai_message_id", name="uq_character_thought_ai_message"),
        Index(
            "ix_character_thoughts_character_created",
            "game_character_id",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    game_session_id: Mapped[int] = mapped_column(
        ForeignKey(
            "game_sessions.id",
            name="fk_character_thoughts_game_session_id_game_sessions",
        ),
        nullable=False,
    )
    game_character_id: Mapped[int] = mapped_column(
        ForeignKey(
            "game_characters.id",
            name="fk_character_thoughts_game_character_id_game_characters",
        ),
        nullable=False,
    )
    ai_message_id: Mapped[int] = mapped_column(
        ForeignKey("messages.id", name="fk_character_thoughts_ai_message_id_messages"),
        nullable=False,
    )
    inner_os: Mapped[str] = mapped_column(Text, nullable=False)
    emotion: Mapped[str] = mapped_column(String(20), nullable=False)
    intent: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    game_session: Mapped["GameSession"] = relationship(
        back_populates="character_thoughts"
    )
    game_character: Mapped["GameCharacter"] = relationship(
        back_populates="thoughts", foreign_keys=[game_character_id]
    )
    ai_message: Mapped["Message"] = relationship(
        back_populates="character_thought", foreign_keys=[ai_message_id]
    )


class CharacterMemory(Base):
    """A subjective fact retained by one runtime character in one game."""

    __tablename__ = "character_memories"
    __table_args__ = (
        CheckConstraint(
            "importance BETWEEN 1 AND 5",
            name="ck_character_memories_importance",
        ),
        ForeignKeyConstraint(
            ["game_session_id", "game_character_id"],
            ["game_characters.game_session_id", "game_characters.id"],
            name="fk_character_memories_game_character_session",
        ),
        ForeignKeyConstraint(
            ["game_session_id", "source_message_id"],
            ["messages.game_session_id", "messages.id"],
            name="fk_character_memories_source_message_session",
        ),
        Index(
            "ix_character_memories_character_importance_created",
            "game_character_id",
            "importance",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    game_session_id: Mapped[int] = mapped_column(
        ForeignKey(
            "game_sessions.id",
            name="fk_character_memories_game_session_id_game_sessions",
        ),
        nullable=False,
    )
    game_character_id: Mapped[int] = mapped_column(
        ForeignKey(
            "game_characters.id",
            name="fk_character_memories_game_character_id_game_characters",
        ),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    importance: Mapped[int] = mapped_column(nullable=False)
    source_message_id: Mapped[int] = mapped_column(
        ForeignKey(
            "messages.id", name="fk_character_memories_source_message_id_messages"
        ),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    game_session: Mapped["GameSession"] = relationship(
        back_populates="character_memories"
    )
    game_character: Mapped["GameCharacter"] = relationship(
        back_populates="memories", foreign_keys=[game_character_id]
    )
    source_message: Mapped["Message"] = relationship(
        back_populates="memory_updates", foreign_keys=[source_message_id]
    )
