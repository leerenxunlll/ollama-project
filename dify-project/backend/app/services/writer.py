"""Deterministic validation and persistence for unpublished Writer drafts."""

import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.agents.writer_workflow_client import (
    WriterWorkflowClient,
    WriterWorkflowError,
)
from app.core.config import settings
from app.models import ScriptDraft
from app.schemas.writer import (
    WriterBlueprint,
    WriterChapterPack,
    WriterCreateRequest,
    WriterDraftRead,
    WriterPhase,
)

WriterTask = Literal["blueprint", "chapter_pack"]
LEASE_SECONDS = 600
PHASE_ORDER: dict[str, tuple[str, str]] = {
    "intro": ("blueprint_ready", "intro_ready"),
    "act_1": ("intro_ready", "act_1_ready"),
    "act_2": ("act_1_ready", "draft_complete"),
}


class WriterDraftError(Exception):
    """Base service error with a safe HTTP-facing category."""

    status_code = 400
    error_type = "writer_draft_error"
    public_message = "Writer draft request failed"


class WriterDraftNotFoundError(WriterDraftError):
    status_code = 404
    error_type = "draft_not_found"
    public_message = "Writer draft was not found"


class WriterGenerationConflictError(WriterDraftError):
    status_code = 409
    error_type = "generation_conflict"
    public_message = "This Writer draft step is already running or complete"


class WriterGenerationOrderError(WriterDraftError):
    status_code = 409
    error_type = "invalid_generation_order"
    public_message = "Generate the preceding Writer step first"


class WriterNotConfiguredServiceError(WriterDraftError):
    status_code = 503
    error_type = "writer_not_configured"
    public_message = "Writer Dify is not configured"


class WriterGenerationError(WriterDraftError):
    status_code = 502
    error_type = "writer_generation_failed"
    public_message = "Writer generation failed validation or Dify execution"

    def __init__(
        self,
        error_type: str = "writer_generation_failed",
        public_message: str = "Writer generation failed validation or Dify execution",
        status_code: int = 502,
    ) -> None:
        super().__init__(public_message)
        self.error_type = error_type
        self.public_message = public_message
        self.status_code = status_code


def create_draft(db: Session, request: WriterCreateRequest) -> WriterDraftRead:
    """Persist only the user request; no Dify call occurs at creation time."""
    draft = ScriptDraft(
        generation_request_json=request.model_dump(mode="json"),
        chapter_packs_json={},
        step_durations_seconds_json={},
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return _read_draft(draft)


def get_draft(db: Session, draft_id: int) -> WriterDraftRead:
    draft = db.get(ScriptDraft, draft_id)
    if draft is None:
        raise WriterDraftNotFoundError
    return _read_draft(draft)


def get_writer_client() -> WriterWorkflowClient:
    return WriterWorkflowClient(
        api_url=settings.dify_api_url,
        api_key=settings.dify_writer_api_key,
    )


def generate_blueprint(db: Session, draft_id: int) -> WriterDraftRead:
    return _generate_step(db, draft_id, "blueprint")


def generate_chapter_pack(
    db: Session, draft_id: int, phase: WriterPhase
) -> WriterDraftRead:
    return _generate_step(db, draft_id, phase)


def build_blueprint_request(request: dict[str, Any]) -> dict[str, Any]:
    """Build a bounded creation context; never reads runtime game state."""
    return {
        "generation_request": request,
        "constraints": {
            "character_count": 4,
            "role_keys": ["role_1", "role_2", "role_3", "role_4"],
            "player_assignment": "one human player and three AI characters",
            "difficulty_must_match_request": True,
            "timeline_is_canonical_truth": True,
            "character_secrets_are_role_specific": True,
            "output_contract": "WriterBlueprint",
        },
    }


def build_chapter_pack_request(
    phase: WriterPhase,
    blueprint: dict[str, Any],
    previous_packs: dict[str, Any],
) -> dict[str, Any]:
    """Give Writer only the blueprint and previously completed story packs."""
    return {
        "phase": phase,
        "blueprint": blueprint,
        "previous_chapter_packs": previous_packs,
        "constraints": {
            "shared_chapter_count": 1,
            "private_chapter_count": 4,
            "role_keys": ["role_1", "role_2", "role_3", "role_4"],
            "chapter_order": {"intro": 1, "act_1": 2, "act_2": 3}[phase],
            "unlock_phase_must_match_phase": True,
            "respect_private_knowledge": True,
            "do_not_add_or_change_case_truth": True,
            "output_contract": "WriterChapterPack",
            "length_targets_characters": {
                "shared": "200-500 Chinese characters",
                "private": "350-800 Chinese characters",
            },
        },
    }


def _generate_step(
    db: Session, draft_id: int, step: WriterTask | WriterPhase
) -> WriterDraftRead:
    if not settings.dify_writer_configured:
        raise WriterNotConfiguredServiceError
    request, blueprint, packs, claim_token = _claim_step(db, draft_id, step)
    started = time.monotonic()
    task_type = "blueprint" if step == "blueprint" else "chapter_pack"
    if step == "blueprint":
        payload = build_blueprint_request(request)
    else:
        if blueprint is None:
            _mark_failed(db, draft_id, step, claim_token, "invalid_generation_order")
            raise WriterGenerationOrderError
        payload = build_chapter_pack_request(step, blueprint, packs)

    try:
        result = get_writer_client().run(
            task_type=task_type,
            payload=json.dumps(payload, ensure_ascii=False),
            user_id=f"draft-{draft_id}-writer",
        )
        if step == "blueprint":
            validated: WriterBlueprint | WriterChapterPack = (
                WriterBlueprint.model_validate(result)
            )
            if validated.script_metadata.difficulty != request["difficulty"]:
                raise ValueError("script difficulty must match the creation request")
            if (
                validated.script_metadata.theme != request["theme"]
                or validated.script_metadata.era != request["era"]
                or validated.script_metadata.atmosphere != request["atmosphere"]
            ):
                raise ValueError("script metadata must preserve the creation request")
        else:
            validated = WriterChapterPack.model_validate(result)
            if validated.phase != step:
                raise ValueError("chapter pack phase does not match requested phase")
        elapsed = round(time.monotonic() - started, 2)
        _save_step(
            db,
            draft_id,
            step,
            claim_token,
            validated.model_dump(mode="json"),
            elapsed,
        )
    except Exception as error:
        error_type = _safe_error_type(error)
        _mark_failed(db, draft_id, step, claim_token, error_type)
        if isinstance(error, WriterDraftError):
            raise
        if isinstance(error, WriterWorkflowError):
            status_code = 504 if error.error_type == "dify_timeout" else 502
            raise WriterGenerationError(
                error_type=error.error_type,
                public_message=error.public_message,
                status_code=status_code,
            ) from error
        if error_type == "schema_validation_failed":
            raise WriterGenerationError(
                error_type,
                "Writer output failed Pydantic validation",
            ) from error
        raise WriterGenerationError(
            error_type,
            "Writer output failed deterministic validation",
        ) from error
    db.expire_all()
    return get_draft(db, draft_id)


def _claim_step(
    db: Session, draft_id: int, step: WriterTask | WriterPhase
) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any], str]:
    draft = db.get(ScriptDraft, draft_id)
    if draft is None:
        raise WriterDraftNotFoundError

    now = datetime.now(timezone.utc)
    stale_before = now - timedelta(seconds=LEASE_SECONDS)
    target_status = f"generating_{step}"
    if step == "blueprint":
        if draft.blueprint_json is not None:
            raise WriterGenerationConflictError
        ready_status = "blueprint_ready"
        expected_statuses = {"created"}
    else:
        if step in (draft.chapter_packs_json or {}):
            raise WriterGenerationConflictError
        ready_status, completed_status = PHASE_ORDER[step]
        expected_statuses = {ready_status}
        if draft.status == completed_status:
            raise WriterGenerationConflictError

    if draft.status == "generation_failed" and draft.failed_step == step:
        expected_statuses.add("generation_failed")
    updated_at = draft.updated_at
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    stale_claim = draft.status == target_status and updated_at < stale_before
    if stale_claim:
        expected_statuses.add(target_status)
    if draft.status.startswith("generating_") and not stale_claim:
        raise WriterGenerationConflictError
    if draft.status not in expected_statuses:
        raise WriterGenerationOrderError

    conditions = [ScriptDraft.id == draft_id, ScriptDraft.status == draft.status]
    if draft.status == "generation_failed":
        conditions.append(ScriptDraft.failed_step == step)
    if stale_claim:
        conditions.append(ScriptDraft.updated_at < stale_before)
    claim_token = str(uuid4())
    result = db.execute(
        update(ScriptDraft)
        .where(*conditions)
        .values(
            status=target_status,
            failed_step=None,
            last_error_type=None,
            generation_token=claim_token,
            updated_at=now,
        )
    )
    if result.rowcount != 1:
        db.rollback()
        raise WriterGenerationConflictError
    request = dict(draft.generation_request_json)
    blueprint = dict(draft.blueprint_json) if draft.blueprint_json else None
    packs = dict(draft.chapter_packs_json or {})
    db.commit()
    return request, blueprint, packs, claim_token


def _save_step(
    db: Session,
    draft_id: int,
    step: WriterTask | WriterPhase,
    claim_token: str,
    content: dict[str, Any],
    elapsed_seconds: float,
) -> None:
    target_status = f"generating_{step}"
    now = datetime.now(timezone.utc)
    draft = db.get(ScriptDraft, draft_id)
    if draft is None or draft.status != target_status:
        db.rollback()
        raise WriterGenerationConflictError

    durations = dict(draft.step_durations_seconds_json or {})
    durations[str(step)] = elapsed_seconds
    values: dict[str, Any] = {
        "status": _success_status(step),
        "failed_step": None,
        "last_error_type": None,
        "generation_token": None,
        "step_durations_seconds_json": durations,
        "updated_at": now,
    }
    if step == "blueprint":
        values["blueprint_json"] = content
    else:
        packs = dict(draft.chapter_packs_json or {})
        packs[str(step)] = content
        values["chapter_packs_json"] = packs
    result = db.execute(
        update(ScriptDraft)
        .where(
            ScriptDraft.id == draft_id,
            ScriptDraft.status == target_status,
            ScriptDraft.generation_token == claim_token,
        )
        .values(**values)
    )
    if result.rowcount != 1:
        db.rollback()
        raise WriterGenerationConflictError
    db.commit()


def _mark_failed(
    db: Session,
    draft_id: int,
    step: WriterTask | WriterPhase,
    claim_token: str,
    error_type: str,
) -> None:
    db.execute(
        update(ScriptDraft)
        .where(
            ScriptDraft.id == draft_id,
            ScriptDraft.status == f"generating_{step}",
            ScriptDraft.generation_token == claim_token,
        )
        .values(
            status="generation_failed",
            failed_step=str(step),
            last_error_type=error_type,
            generation_token=None,
            updated_at=datetime.now(timezone.utc),
        )
    )
    db.commit()


def _success_status(step: WriterTask | WriterPhase) -> str:
    if step == "blueprint":
        return "blueprint_ready"
    return {"intro": "intro_ready", "act_1": "act_1_ready", "act_2": "draft_complete"}[
        step
    ]


def _safe_error_type(error: Exception) -> str:
    if isinstance(error, WriterWorkflowError):
        return error.error_type
    if error.__class__.__name__ == "ValidationError":
        return "schema_validation_failed"
    return "deterministic_validation_failed"


def _read_draft(draft: ScriptDraft) -> WriterDraftRead:
    blueprint = (
        WriterBlueprint.model_validate(draft.blueprint_json)
        if draft.blueprint_json
        else None
    )
    packs = {
        phase: WriterChapterPack.model_validate(pack)
        for phase, pack in (draft.chapter_packs_json or {}).items()
    }
    complete = []
    if blueprint is not None:
        complete.append("blueprint")
    complete.extend(phase for phase in ("intro", "act_1", "act_2") if phase in packs)
    return WriterDraftRead(
        id=draft.id,
        status=draft.status,
        content_revision=draft.content_revision,
        publication_status=draft.publication_status,
        published_script_id=draft.published_script_id,
        generation_request=WriterCreateRequest.model_validate(
            draft.generation_request_json
        ),
        blueprint=blueprint,
        chapter_packs=packs,
        step_durations_seconds=dict(draft.step_durations_seconds_json or {}),
        failed_step=draft.failed_step,
        last_error_type=draft.last_error_type,
        completed_steps=complete,
    )
