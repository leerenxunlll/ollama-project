"""Deterministic review, bounded chapter revision, approval, and publication."""

import json
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.agents.script_quality_workflow_client import (
    ScriptQualityWorkflowClient,
    ScriptQualityWorkflowError,
)
from app.core.config import settings
from app.models import (
    Character,
    CharacterScriptChapter,
    Clue,
    Script,
    ScriptCanonicalData,
    ScriptDraft,
    ScriptReviewRun,
    ScriptRevisionRecord,
    SharedScriptChapter,
)
from app.schemas.quality import (
    DeterministicValidationIssue,
    ScriptApprovalRead,
    ScriptApproveRequest,
    ScriptPublicationRead,
    ScriptReviewIssue,
    ScriptReviewReport,
    ScriptReviewRunRead,
    ScriptRevisionRecordRead,
    ScriptRevisionResponse,
)
from app.schemas.writer import (
    WriterBlueprint,
    WriterChapterPack,
    WriterCreateRequest,
    WriterPhase,
)

MAX_QUALITY_PAYLOAD_CHARACTERS = 180_000
MAX_REVISIONS_PER_PHASE = 2
WRITER_PHASES: tuple[WriterPhase, ...] = ("intro", "act_1", "act_2")
CHAPTER_ORDER = {"intro": 1, "act_1": 2, "act_2": 3}


class ScriptQualityError(Exception):
    """Safe, typed service error returned to the Development API."""

    def __init__(
        self,
        error_type: str,
        message: str,
        status_code: int = 409,
        issues: list[DeterministicValidationIssue] | None = None,
    ) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.public_message = message
        self.status_code = status_code
        self.issues = issues or []


def get_quality_client() -> ScriptQualityWorkflowClient:
    """Build the independent client without falling back to another Dify key."""
    return ScriptQualityWorkflowClient(
        api_url=settings.dify_api_url,
        api_key=settings.dify_script_quality_api_key,
    )


def validate_complete_draft(
    draft: ScriptDraft,
) -> tuple[WriterCreateRequest, WriterBlueprint, dict[WriterPhase, WriterChapterPack]]:
    """Validate the full persisted draft using the existing Writer contracts."""
    issues: list[DeterministicValidationIssue] = []
    if draft.status != "draft_complete":
        issues.append(
            DeterministicValidationIssue(
                code="draft_incomplete",
                field_path="status",
                message="Draft must finish all four Writer generation steps.",
            )
        )
    try:
        request = WriterCreateRequest.model_validate(draft.generation_request_json)
    except ValidationError as error:
        issues.extend(_validation_issues("generation_request", error))
        request = None
    try:
        blueprint = WriterBlueprint.model_validate(draft.blueprint_json)
    except ValidationError as error:
        issues.extend(_validation_issues("blueprint", error))
        blueprint = None
    raw_packs = draft.chapter_packs_json or {}
    if set(raw_packs) != set(WRITER_PHASES):
        issues.append(
            DeterministicValidationIssue(
                code="chapter_pack_coverage",
                field_path="chapter_packs",
                message="Draft must contain intro, act_1, and act_2 chapter packs.",
            )
        )
    packs: dict[WriterPhase, WriterChapterPack] = {}
    for phase in WRITER_PHASES:
        raw_pack = raw_packs.get(phase)
        if raw_pack is None:
            continue
        try:
            pack = WriterChapterPack.model_validate(raw_pack)
            if pack.phase != phase:
                raise ValueError("chapter pack phase does not match its stored key")
            packs[phase] = pack
        except (ValidationError, ValueError) as error:
            if isinstance(error, ValidationError):
                issues.extend(_validation_issues(f"chapter_packs.{phase}", error))
            else:
                issues.append(
                    DeterministicValidationIssue(
                        code="chapter_phase_mismatch",
                        field_path=f"chapter_packs.{phase}.phase",
                        message="Chapter pack phase must match its storage key.",
                    )
                )
    if blueprint is not None and request is not None:
        metadata = blueprint.script_metadata
        if (
            metadata.difficulty != request.difficulty
            or metadata.theme != request.theme
            or metadata.era != request.era
            or metadata.atmosphere != request.atmosphere
        ):
            issues.append(
                DeterministicValidationIssue(
                    code="metadata_request_mismatch",
                    field_path="blueprint.script_metadata",
                    message="Script metadata must preserve the original request.",
                )
            )
        if len(blueprint.characters) != 4:
            issues.append(
                DeterministicValidationIssue(
                    code="character_count",
                    field_path="blueprint.characters",
                    message="A publishable Script requires exactly four characters.",
                )
            )
        if (
            sum(
                character.role_key == blueprint.case_truth.culprit_role_key
                for character in blueprint.characters
            )
            != 1
        ):
            issues.append(
                DeterministicValidationIssue(
                    code="culprit_reference",
                    field_path="blueprint.case_truth.culprit_role_key",
                    message="The culprit role must resolve to exactly one character.",
                )
            )
        if not 1 <= len(blueprint.clues) <= 12:
            issues.append(
                DeterministicValidationIssue(
                    code="clue_count",
                    field_path="blueprint.clues",
                    message="The Script requires between three and twelve clues.",
                )
            )
        for clue in blueprint.clues:
            if not clue.related_event_keys:
                issues.append(
                    DeterministicValidationIssue(
                        code="clue_event_reference",
                        field_path=f"blueprint.clues.{clue.clue_key}.related_event_keys",
                        message=(
                            "Each clue must reference at least one canonical event."
                        ),
                    )
                )
    if issues:
        raise ScriptQualityError(
            "deterministic_validation_failed",
            "Draft failed deterministic validation.",
            status_code=422,
            issues=issues,
        )
    assert request is not None and blueprint is not None
    return request, blueprint, packs


def run_review(
    db: Session,
    draft_id: int,
    client: ScriptQualityWorkflowClient | None = None,
) -> ScriptReviewRunRead:
    """Validate the complete draft, call Dify, validate references, then persist."""
    draft = _get_draft(db, draft_id)
    request, blueprint, packs = validate_complete_draft(draft)
    revision = draft.content_revision
    payload = {
        "content_revision": revision,
        "generation_request": request.model_dump(mode="json"),
        "blueprint": blueprint.model_dump(mode="json"),
        "chapter_packs": {
            phase: pack.model_dump(mode="json") for phase, pack in packs.items()
        },
        "coverage": "complete_script_global_review",
    }
    payload_text = _bounded_payload(payload)
    try:
        result = (client or get_quality_client()).run(
            "review", payload_text, user_id=f"draft-{draft_id}-quality"
        )
        report = ScriptReviewReport.model_validate(result)
        _validate_issue_references(report, blueprint, packs)
        report = _apply_review_policy(report)
    except ScriptQualityWorkflowError as error:
        return _save_failed_review(db, draft, revision, error.error_type, error)
    except (ValidationError, ValueError):
        failure = ScriptQualityError(
            "invalid_review_report",
            "Quality Workflow returned an invalid review report.",
            status_code=502,
        )
        return _save_failed_review(db, draft, revision, failure.error_type, failure)

    db.refresh(draft)
    if draft.content_revision != revision:
        return _save_stale_review(db, draft_id, revision, report)
    run = ScriptReviewRun(
        draft_id=draft_id,
        content_revision=revision,
        review_status="completed",
        report_json=report.model_dump(mode="json"),
        created_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return _read_review_run(run)


def list_reviews(db: Session, draft_id: int) -> list[ScriptReviewRunRead]:
    _get_draft(db, draft_id)
    rows = db.scalars(
        select(ScriptReviewRun)
        .where(ScriptReviewRun.draft_id == draft_id)
        .order_by(ScriptReviewRun.id.desc())
    ).all()
    return [_read_review_run(row) for row in rows]


def list_revisions(db: Session, draft_id: int) -> list[ScriptRevisionRecordRead]:
    _get_draft(db, draft_id)
    rows = db.scalars(
        select(ScriptRevisionRecord)
        .where(ScriptRevisionRecord.draft_id == draft_id)
        .order_by(ScriptRevisionRecord.id.desc())
    ).all()
    return [_read_revision(row) for row in rows]


def revise_chapter_pack(
    db: Session,
    draft_id: int,
    phase: WriterPhase,
    client: ScriptQualityWorkflowClient | None = None,
) -> ScriptRevisionResponse:
    """Revise one chapter pack and commit only if its source revision is unchanged."""
    draft = _get_draft(db, draft_id)
    request, blueprint, packs = validate_complete_draft(draft)
    revision = draft.content_revision
    review = _latest_current_review(db, draft_id, revision)
    report = ScriptReviewReport.model_validate(review.report_json)
    if report.verdict != "needs_revision":
        raise ScriptQualityError(
            "revision_not_required",
            "The current review does not request a chapter revision.",
        )
    issues = [issue for issue in report.issues if issue.location.phase == phase]
    if not issues:
        raise ScriptQualityError(
            "no_issues_for_phase",
            "The current review has no issues assigned to this chapter phase.",
        )
    if any(
        issue.severity in ("critical", "high")
        and issue.location.scope
        in ("blueprint", "case_truth", "timeline_event", "character", "clue")
        for issue in report.issues
    ):
        raise ScriptQualityError(
            "blueprint_revision_forbidden",
            (
                "Blueprint and canonical truth issues require a new draft; "
                "they cannot be auto-revised."
            ),
        )
    used_count = (
        db.scalar(
            select(func.count(ScriptRevisionRecord.id)).where(
                ScriptRevisionRecord.draft_id == draft_id,
                ScriptRevisionRecord.phase == phase,
            )
        )
        or 0
    )
    if used_count >= MAX_REVISIONS_PER_PHASE:
        raise ScriptQualityError(
            "revision_limit_reached",
            "This phase has reached its limit of two automatic revisions.",
        )
    payload = {
        "content_revision": revision,
        "generation_request": request.model_dump(mode="json"),
        "blueprint": blueprint.model_dump(mode="json"),
        "target_phase": phase,
        "current_chapter_pack": packs[phase].model_dump(mode="json"),
        "other_chapter_packs": {
            key: value.model_dump(mode="json")
            for key, value in packs.items()
            if key != phase
        },
        "review_issues": [issue.model_dump(mode="json") for issue in issues],
        "constraints": {
            "preserve_blueprint": True,
            "preserve_roles_order_and_unlock_phase": True,
            "output_contract": "WriterChapterPack",
        },
    }
    try:
        result = (client or get_quality_client()).run(
            "revise_chapter_pack",
            _bounded_payload(payload),
            user_id=f"draft-{draft_id}-quality",
        )
        revised_pack = WriterChapterPack.model_validate(result)
        _validate_revision_pack(phase, packs[phase], revised_pack)
        replacement = {
            key: value.model_dump(mode="json") for key, value in packs.items()
        }
        replacement[phase] = revised_pack.model_dump(mode="json")
        _validate_components(
            draft.status,
            draft.generation_request_json,
            draft.blueprint_json,
            replacement,
        )
    except ScriptQualityWorkflowError as error:
        raise _workflow_service_error(error) from error
    except (ValidationError, ValueError) as error:
        raise ScriptQualityError(
            "invalid_revision_output",
            "Quality Workflow returned a chapter pack that failed validation.",
            status_code=502,
        ) from error

    now = datetime.now(timezone.utc)
    new_revision = revision + 1
    previous_pack = packs[phase].model_dump(mode="json")
    review_id = review.id
    # Release the read transaction before SQLite's conditional write. This
    # avoids two concurrent readers failing while upgrading to write locks.
    db.rollback()
    update_result = db.execute(
        update(ScriptDraft)
        .where(
            ScriptDraft.id == draft_id,
            ScriptDraft.status == "draft_complete",
            ScriptDraft.content_revision == revision,
            ScriptDraft.publication_status == "unpublished",
        )
        .values(
            chapter_packs_json=replacement,
            content_revision=new_revision,
            approved_revision=None,
            approved_review_run_id=None,
            approved_at=None,
            accepted_medium_issue_indexes_json=[],
            updated_at=now,
        )
    )
    if update_result.rowcount != 1:
        db.rollback()
        raise ScriptQualityError(
            "draft_changed_during_revision",
            "Draft changed while revision was running; no revision was saved.",
        )
    record = ScriptRevisionRecord(
        draft_id=draft_id,
        from_revision=revision,
        to_revision=new_revision,
        phase=phase,
        related_review_id=review_id,
        issues_addressed_json=[issue.model_dump(mode="json") for issue in issues],
        previous_chapter_pack_json=previous_pack,
        new_chapter_pack_json=revised_pack.model_dump(mode="json"),
        created_at=now,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return ScriptRevisionResponse(
        revision=_read_revision(record), content_revision=new_revision
    )


def approve_draft(
    db: Session, draft_id: int, payload: ScriptApproveRequest
) -> ScriptApprovalRead:
    draft = _get_draft(db, draft_id)
    validate_complete_draft(draft)
    review = db.get(ScriptReviewRun, payload.review_run_id)
    if (
        review is None
        or review.draft_id != draft_id
        or review.content_revision != draft.content_revision
        or review.review_status != "completed"
        or review.report_json is None
    ):
        raise ScriptQualityError(
            "current_review_required",
            "Approval requires a completed review for the current Draft revision.",
        )
    report = ScriptReviewReport.model_validate(review.report_json)
    if report.verdict != "pass" or any(
        issue.severity in ("critical", "high") for issue in report.issues
    ):
        raise ScriptQualityError(
            "review_not_approvable",
            "Only a passing report with no critical/high issues can be approved.",
        )
    expected_medium = {
        index
        for index, issue in enumerate(report.issues, start=1)
        if issue.severity == "medium"
    }
    accepted = set(payload.accepted_medium_issue_indexes)
    if (
        len(accepted) != len(payload.accepted_medium_issue_indexes)
        or accepted != expected_medium
    ):
        raise ScriptQualityError(
            "medium_issue_acceptance_required",
            (
                "Explicitly accept every medium issue by its displayed "
                "one-based issue number."
            ),
        )
    now = datetime.now(timezone.utc)
    result = db.execute(
        update(ScriptDraft)
        .where(
            ScriptDraft.id == draft_id,
            ScriptDraft.status == "draft_complete",
            ScriptDraft.content_revision == draft.content_revision,
            ScriptDraft.publication_status == "unpublished",
        )
        .values(
            approved_revision=draft.content_revision,
            approved_review_run_id=review.id,
            approved_at=now,
            accepted_medium_issue_indexes_json=sorted(accepted),
            updated_at=now,
        )
    )
    if result.rowcount != 1:
        db.rollback()
        raise ScriptQualityError("approval_conflict", "Draft changed before approval.")
    db.commit()
    return ScriptApprovalRead(
        draft_id=draft_id,
        content_revision=draft.content_revision,
        review_run_id=review.id,
        accepted_medium_issue_indexes=sorted(accepted),
        approved_at=now,
    )


def publish_draft(db: Session, draft_id: int) -> ScriptPublicationRead:
    """Publish all Script rows atomically and make the operation idempotent."""
    draft = _get_draft(db, draft_id)
    if draft.publication_status == "published" and draft.published_script_id:
        script = db.get(Script, draft.published_script_id)
        return ScriptPublicationRead(
            draft_id=draft_id,
            publication_status="published",
            script_id=draft.published_script_id,
            content_revision=draft.content_revision,
            title=script.title if script else None,
            approved_revision=draft.approved_revision,
            approved_review_run_id=draft.approved_review_run_id,
            approved_at=draft.approved_at,
        )
    if draft.publication_status != "unpublished":
        raise ScriptQualityError(
            "publication_conflict",
            "Draft is already being published or has an invalid publication state.",
        )
    request, blueprint, packs = validate_complete_draft(draft)
    revision = draft.content_revision
    if (
        draft.approved_revision != revision
        or draft.approved_review_run_id is None
        or draft.approved_at is None
    ):
        raise ScriptQualityError(
            "approval_required",
            "Publish requires explicit approval for the current Draft revision.",
        )
    review = db.get(ScriptReviewRun, draft.approved_review_run_id)
    if (
        review is None
        or review.review_status != "completed"
        or review.content_revision != revision
        or review.report_json is None
    ):
        raise ScriptQualityError(
            "current_review_required",
            "The approved review does not match the current Draft revision.",
        )
    report = ScriptReviewReport.model_validate(review.report_json)
    if report.verdict != "pass" or any(
        issue.severity in ("critical", "high") for issue in report.issues
    ):
        raise ScriptQualityError(
            "review_not_publishable",
            "Current review is not eligible for publication.",
        )
    current_medium = {
        index
        for index, issue in enumerate(report.issues, start=1)
        if issue.severity == "medium"
    }
    if set(draft.accepted_medium_issue_indexes_json or []) != current_medium:
        raise ScriptQualityError(
            "medium_issue_acceptance_required",
            "Every medium issue must be explicitly accepted for this review.",
        )
    _bounded_payload(
        {
            "generation_request": request.model_dump(mode="json"),
            "blueprint": blueprint.model_dump(mode="json"),
            "chapter_packs": {
                phase: pack.model_dump(mode="json") for phase, pack in packs.items()
            },
        }
    )
    approval_time = draft.approved_at
    # The claim is the first write in a fresh transaction. Its predicates
    # arbitrate concurrent publishers using the revision and approval IDs.
    db.rollback()

    claim = db.execute(
        update(ScriptDraft)
        .where(
            ScriptDraft.id == draft_id,
            ScriptDraft.status == "draft_complete",
            ScriptDraft.content_revision == revision,
            ScriptDraft.publication_status == "unpublished",
            ScriptDraft.approved_revision == revision,
            ScriptDraft.approved_review_run_id == review.id,
        )
        .values(publication_status="publishing")
    )
    if claim.rowcount != 1:
        db.rollback()
        raise ScriptQualityError(
            "publication_conflict",
            "Another request changed or claimed this Draft for publication.",
        )

    try:
        metadata = blueprint.script_metadata
        script = Script(
            title=metadata.title,
            summary=metadata.summary,
            theme=metadata.theme,
            era=metadata.era,
            atmosphere=metadata.atmosphere,
            difficulty=metadata.difficulty,
            status="draft",
        )
        db.add(script)
        db.flush()

        character_ids: dict[str, int] = {}
        characters: dict[str, Character] = {}
        for character_data in blueprint.characters:
            character = Character(
                script_id=script.id,
                name=character_data.name,
                age=character_data.age,
                identity=character_data.identity,
                public_background=character_data.public_background,
                private_background=character_data.private_background,
                personality=character_data.personality,
                speaking_style=character_data.speaking_style,
                personal_goal=character_data.personal_goal,
                personal_history=character_data.personal_history,
                relationship_to_victim=character_data.relationship_to_victim,
                pre_case_experience=character_data.pre_case_experience,
                private_secrets_json=character_data.private_secrets,
                initial_knowledge_json=character_data.initial_knowledge,
                is_killer=(
                    character_data.role_key == blueprint.case_truth.culprit_role_key
                ),
            )
            characters[character_data.role_key] = character
            db.add(character)
        db.flush()
        character_ids = {
            role_key: character.id for role_key, character in characters.items()
        }
        if sum(character.is_killer for character in characters.values()) != 1:
            raise ScriptQualityError(
                "culprit_mapping_failed",
                "Publication must map exactly one culprit character.",
                status_code=422,
            )

        clue_rows: dict[str, Clue] = {}
        for clue_data in blueprint.clues:
            clue = Clue(
                script_id=script.id,
                name=clue_data.name,
                description=clue_data.description,
                act=clue_data.act,
                location=clue_data.location,
                is_core=clue_data.is_core,
                importance=clue_data.importance,
            )
            clue_rows[clue_data.clue_key] = clue
            db.add(clue)
        db.flush()
        clue_ids = {key: clue.id for key, clue in clue_rows.items()}

        for phase in WRITER_PHASES:
            pack = packs[phase]
            shared = pack.shared_chapter
            db.add(
                SharedScriptChapter(
                    script_id=script.id,
                    chapter_order=shared.chapter_order,
                    unlock_phase=shared.unlock_phase,
                    title=shared.title,
                    content=shared.content,
                )
            )
            for chapter in pack.character_chapters:
                db.add(
                    CharacterScriptChapter(
                        character_id=character_ids[chapter.role_key],
                        chapter_order=chapter.chapter_order,
                        unlock_phase=chapter.unlock_phase,
                        title=chapter.title,
                        content=chapter.content,
                    )
                )
        canonical = ScriptCanonicalData(
            script_id=script.id,
            case_truth_json=blueprint.case_truth.model_dump(mode="json"),
            timeline_json=[
                event.model_dump(mode="json") for event in blueprint.canonical_timeline
            ],
            role_character_ids_json=character_ids,
            clue_ids_json=clue_ids,
            clue_event_keys_json={
                clue.clue_key: clue.related_event_keys for clue in blueprint.clues
            },
        )
        db.add(canonical)
        db.flush()
        script.status = "ready"
        db.execute(
            update(ScriptDraft)
            .where(
                ScriptDraft.id == draft_id,
                ScriptDraft.publication_status == "publishing",
                ScriptDraft.content_revision == revision,
            )
            .values(
                publication_status="published",
                published_script_id=script.id,
                updated_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
        return ScriptPublicationRead(
            draft_id=draft_id,
            publication_status="published",
            script_id=script.id,
            content_revision=revision,
            title=metadata.title,
            approved_revision=revision,
            approved_review_run_id=review.id,
            approved_at=approval_time,
        )
    except Exception:
        db.rollback()
        raise


def get_publication(db: Session, draft_id: int) -> ScriptPublicationRead:
    draft = _get_draft(db, draft_id)
    script = (
        db.get(Script, draft.published_script_id)
        if draft.published_script_id is not None
        else None
    )
    return ScriptPublicationRead(
        draft_id=draft_id,
        publication_status=draft.publication_status,
        script_id=draft.published_script_id,
        content_revision=draft.content_revision,
        title=script.title if script else None,
        approved_revision=draft.approved_revision,
        approved_review_run_id=draft.approved_review_run_id,
        approved_at=draft.approved_at,
    )


def _validate_components(
    status: str,
    request_json: dict[str, Any],
    blueprint_json: dict[str, Any] | None,
    chapter_packs_json: dict[str, Any],
) -> None:
    candidate = ScriptDraft(
        status=status,
        generation_request_json=request_json,
        blueprint_json=blueprint_json,
        chapter_packs_json=chapter_packs_json,
    )
    validate_complete_draft(candidate)


def _validate_issue_references(
    report: ScriptReviewReport,
    blueprint: WriterBlueprint,
    packs: dict[WriterPhase, WriterChapterPack],
) -> None:
    role_keys = {character.role_key for character in blueprint.characters}
    event_keys = {event.event_key for event in blueprint.canonical_timeline}
    clue_keys = {clue.clue_key for clue in blueprint.clues}
    for issue in report.issues:
        location = issue.location
        if location.role_key is not None and location.role_key not in role_keys:
            raise ValueError("review issue references an unknown role_key")
        if location.event_key is not None and location.event_key not in event_keys:
            raise ValueError("review issue references an unknown event_key")
        if location.clue_key is not None and location.clue_key not in clue_keys:
            raise ValueError("review issue references an unknown clue_key")
        if location.phase is not None:
            pack = packs.get(location.phase)
            if pack is None:
                raise ValueError("review issue references a missing phase")
            if location.scope == "character_chapter" and location.role_key not in {
                chapter.role_key for chapter in pack.character_chapters
            }:
                raise ValueError("review issue references an unknown character chapter")


def _apply_review_policy(report: ScriptReviewReport) -> ScriptReviewReport:
    """Use the stricter issue list when it conflicts with the model verdict."""
    if report.verdict != "pass":
        return report
    severe = [
        issue for issue in report.issues if issue.severity in ("critical", "high")
    ]
    if not severe:
        return report
    blueprint_issue = any(
        issue.location.scope in ("blueprint", "case_truth") for issue in severe
    )
    return report.model_copy(
        update={"verdict": "blocked" if blueprint_issue else "needs_revision"}
    )


def _validate_revision_pack(
    phase: WriterPhase,
    previous: WriterChapterPack,
    revised: WriterChapterPack,
) -> None:
    if revised.phase != phase or previous.phase != phase:
        raise ValueError("revision must preserve the requested phase")
    if revised.shared_chapter.chapter_order != previous.shared_chapter.chapter_order:
        raise ValueError("revision must preserve chapter_order")
    if revised.shared_chapter.unlock_phase != previous.shared_chapter.unlock_phase:
        raise ValueError("revision must preserve unlock_phase")
    old_by_role = {item.role_key: item for item in previous.character_chapters}
    new_by_role = {item.role_key: item for item in revised.character_chapters}
    if set(old_by_role) != set(new_by_role):
        raise ValueError("revision must preserve the role_key set")
    for role_key, old in old_by_role.items():
        new = new_by_role[role_key]
        if (
            new.chapter_order != old.chapter_order
            or new.unlock_phase != old.unlock_phase
        ):
            raise ValueError("revision must preserve private chapter ordering/unlocks")


def _latest_current_review(
    db: Session, draft_id: int, revision: int
) -> ScriptReviewRun:
    review = db.scalar(
        select(ScriptReviewRun)
        .where(
            ScriptReviewRun.draft_id == draft_id,
            ScriptReviewRun.content_revision == revision,
            ScriptReviewRun.review_status == "completed",
        )
        .order_by(ScriptReviewRun.id.desc())
        .limit(1)
    )
    if review is None or review.report_json is None:
        raise ScriptQualityError(
            "current_review_required",
            "A completed review for the current Draft revision is required.",
        )
    return review


def _save_failed_review(
    db: Session,
    draft: ScriptDraft,
    revision: int,
    error_type: str,
    error: Exception,
) -> ScriptReviewRunRead:
    status_code = getattr(error, "status_code", 502)
    if isinstance(error, ScriptQualityWorkflowError):
        status_code = {
            "quality_not_configured": 503,
            "dify_timeout": 504,
        }.get(error.error_type, 502)
    run = ScriptReviewRun(
        draft_id=draft.id,
        content_revision=revision,
        review_status="failed",
        report_json=None,
        error_type=error_type,
        created_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    raise ScriptQualityError(
        error_type,
        getattr(error, "public_message", "Quality review failed."),
        status_code=status_code,
    ) from error


def _save_stale_review(
    db: Session,
    draft_id: int,
    revision: int,
    report: ScriptReviewReport,
) -> ScriptReviewRunRead:
    now = datetime.now(timezone.utc)
    run = ScriptReviewRun(
        draft_id=draft_id,
        content_revision=revision,
        review_status="stale",
        report_json=report.model_dump(mode="json"),
        error_type="draft_changed_during_review",
        created_at=now,
        completed_at=now,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    raise ScriptQualityError(
        "draft_changed_during_review",
        "Draft changed while review was running; the report is stale.",
    )


def _read_review_run(row: ScriptReviewRun) -> ScriptReviewRunRead:
    return ScriptReviewRunRead(
        id=row.id,
        draft_id=row.draft_id,
        content_revision=row.content_revision,
        review_status=row.review_status,
        report=(
            ScriptReviewReport.model_validate(row.report_json)
            if row.report_json is not None
            else None
        ),
        error_type=row.error_type,
        created_at=row.created_at,
        completed_at=row.completed_at,
    )


def _read_revision(row: ScriptRevisionRecord) -> ScriptRevisionRecordRead:
    return ScriptRevisionRecordRead(
        id=row.id,
        draft_id=row.draft_id,
        from_revision=row.from_revision,
        to_revision=row.to_revision,
        phase=row.phase,
        related_review_id=row.related_review_id,
        issues_addressed=[
            ScriptReviewIssue.model_validate(issue)
            for issue in row.issues_addressed_json
        ],
        previous_chapter_pack=WriterChapterPack.model_validate(
            row.previous_chapter_pack_json
        ),
        new_chapter_pack=WriterChapterPack.model_validate(row.new_chapter_pack_json),
        created_at=row.created_at,
    )


def _get_draft(db: Session, draft_id: int) -> ScriptDraft:
    draft = db.get(ScriptDraft, draft_id)
    if draft is None:
        raise ScriptQualityError("draft_not_found", "Writer draft was not found.", 404)
    return draft


def _bounded_payload(payload: dict[str, Any]) -> str:
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(text) > MAX_QUALITY_PAYLOAD_CHARACTERS:
        raise ScriptQualityError(
            "quality_payload_too_large",
            (
                f"Complete review payload has {len(text)} characters; "
                f"the safe limit is {MAX_QUALITY_PAYLOAD_CHARACTERS}. "
                "No content was truncated."
            ),
            status_code=413,
        )
    return text


def _validation_issues(
    prefix: str, error: ValidationError
) -> list[DeterministicValidationIssue]:
    return [
        DeterministicValidationIssue(
            code="schema_invalid",
            field_path=".".join(str(part) for part in (prefix, *item["loc"])),
            message="Stored draft content does not match its strict Writer schema.",
        )
        for item in error.errors()
    ]


def _workflow_service_error(error: ScriptQualityWorkflowError) -> ScriptQualityError:
    status_code = 502
    if error.error_type == "quality_not_configured":
        status_code = 503
    elif error.error_type == "dify_timeout":
        status_code = 504
    return ScriptQualityError(error.error_type, error.public_message, status_code)
