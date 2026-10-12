"""Persistence for unpublished Writer-generated script drafts."""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ScriptDraft(Base):
    """A development-only generated draft, separate from published scripts."""

    __tablename__ = "script_drafts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('created', 'generating_blueprint', 'blueprint_ready', "
            "'generating_intro', 'intro_ready', 'generating_act_1', "
            "'act_1_ready', 'generating_act_2', 'draft_complete', "
            "'generation_failed')",
            name="ck_script_drafts_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(32), default="created", nullable=False)
    generation_request_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False
    )
    blueprint_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    chapter_packs_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    step_durations_seconds_json: Mapped[dict[str, float]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    failed_step: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_error_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    generation_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    content_revision: Mapped[int] = mapped_column(
        Integer, default=1, server_default=text("1"), nullable=False
    )
    approved_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    approved_review_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    accepted_medium_issue_indexes_json: Mapped[list[int]] = mapped_column(
        JSON, default=list, server_default=text("'[]'"), nullable=False
    )
    publication_status: Mapped[str] = mapped_column(
        String(20),
        default="unpublished",
        server_default=text("'unpublished'"),
        nullable=False,
    )
    published_script_id: Mapped[int | None] = mapped_column(
        ForeignKey("scripts.id"), unique=True, nullable=True
    )
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


class ScriptReviewRun(Base):
    """One review report bound to an exact draft content revision."""

    __tablename__ = "script_review_runs"
    __table_args__ = (
        CheckConstraint(
            "review_status IN ('completed', 'failed', 'stale')",
            name="ck_script_review_runs_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    draft_id: Mapped[int] = mapped_column(
        ForeignKey("script_drafts.id"), nullable=False, index=True
    )
    content_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    review_status: Mapped[str] = mapped_column(String(20), nullable=False)
    report_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ScriptRevisionRecord(Base):
    """Recoverable before/after content for a bounded chapter-pack revision."""

    __tablename__ = "script_revision_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    draft_id: Mapped[int] = mapped_column(
        ForeignKey("script_drafts.id"), nullable=False, index=True
    )
    from_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    to_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    phase: Mapped[str] = mapped_column(String(20), nullable=False)
    related_review_id: Mapped[int] = mapped_column(
        ForeignKey("script_review_runs.id"), nullable=False
    )
    issues_addressed_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False
    )
    previous_chapter_pack_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False
    )
    new_chapter_pack_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
