"""Development-only endpoints for creating and inspecting Writer drafts."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.schemas.quality import (
    ScriptApprovalRead,
    ScriptApproveRequest,
    ScriptPublicationRead,
    ScriptReviewRunRead,
    ScriptRevisionRecordRead,
    ScriptRevisionResponse,
)
from app.schemas.writer import WriterCreateRequest, WriterDraftRead, WriterPhase
from app.services import script_quality
from app.services import writer as writer_service

router = APIRouter(prefix="/writer", tags=["writer-development"])


def _require_development() -> None:
    if settings.app_env != "development":
        raise HTTPException(status_code=404, detail="Not found")


def _raise_writer_http_error(error: writer_service.WriterDraftError) -> None:
    raise HTTPException(
        status_code=error.status_code,
        detail={"code": error.error_type, "message": error.public_message},
    ) from error


def _raise_quality_http_error(error: script_quality.ScriptQualityError) -> None:
    detail: dict[str, object] = {
        "code": error.error_type,
        "message": error.public_message,
    }
    if error.issues:
        detail["issues"] = [issue.model_dump(mode="json") for issue in error.issues]
    raise HTTPException(status_code=error.status_code, detail=detail) from error


@router.get("/status")
def get_writer_status() -> dict[str, bool]:
    _require_development()
    return {"configured": settings.dify_writer_configured}


@router.get("/quality/status")
def get_script_quality_status() -> dict[str, bool]:
    _require_development()
    return {"configured": settings.dify_script_quality_configured}


@router.post("/drafts", response_model=WriterDraftRead, status_code=201)
def create_writer_draft(
    request: WriterCreateRequest,
    db: Session = Depends(get_db),
) -> WriterDraftRead:
    _require_development()
    return writer_service.create_draft(db, request)


@router.get("/drafts/{draft_id}", response_model=WriterDraftRead)
def read_writer_draft(
    draft_id: int,
    db: Session = Depends(get_db),
) -> WriterDraftRead:
    _require_development()
    try:
        return writer_service.get_draft(db, draft_id)
    except writer_service.WriterDraftError as error:
        _raise_writer_http_error(error)


@router.post("/drafts/{draft_id}/generate-blueprint", response_model=WriterDraftRead)
def generate_writer_blueprint(
    draft_id: int,
    db: Session = Depends(get_db),
) -> WriterDraftRead:
    _require_development()
    try:
        return writer_service.generate_blueprint(db, draft_id)
    except writer_service.WriterDraftError as error:
        _raise_writer_http_error(error)


@router.post(
    "/drafts/{draft_id}/generate-chapter-pack/{phase}",
    response_model=WriterDraftRead,
)
def generate_writer_chapter_pack(
    draft_id: int,
    phase: WriterPhase,
    db: Session = Depends(get_db),
) -> WriterDraftRead:
    _require_development()
    try:
        return writer_service.generate_chapter_pack(db, draft_id, phase)
    except writer_service.WriterDraftError as error:
        _raise_writer_http_error(error)


@router.post(
    "/drafts/{draft_id}/review",
    response_model=ScriptReviewRunRead,
    status_code=201,
)
def review_writer_draft(
    draft_id: int,
    db: Session = Depends(get_db),
) -> ScriptReviewRunRead:
    _require_development()
    try:
        return script_quality.run_review(db, draft_id)
    except script_quality.ScriptQualityError as error:
        _raise_quality_http_error(error)


@router.get(
    "/drafts/{draft_id}/reviews",
    response_model=list[ScriptReviewRunRead],
)
def list_writer_draft_reviews(
    draft_id: int,
    db: Session = Depends(get_db),
) -> list[ScriptReviewRunRead]:
    _require_development()
    try:
        return script_quality.list_reviews(db, draft_id)
    except script_quality.ScriptQualityError as error:
        _raise_quality_http_error(error)


@router.post(
    "/drafts/{draft_id}/revise/{phase}",
    response_model=ScriptRevisionResponse,
)
def revise_writer_draft(
    draft_id: int,
    phase: WriterPhase,
    db: Session = Depends(get_db),
) -> ScriptRevisionResponse:
    _require_development()
    try:
        return script_quality.revise_chapter_pack(db, draft_id, phase)
    except script_quality.ScriptQualityError as error:
        _raise_quality_http_error(error)


@router.get(
    "/drafts/{draft_id}/revisions",
    response_model=list[ScriptRevisionRecordRead],
)
def list_writer_draft_revisions(
    draft_id: int,
    db: Session = Depends(get_db),
) -> list[ScriptRevisionRecordRead]:
    _require_development()
    try:
        return script_quality.list_revisions(db, draft_id)
    except script_quality.ScriptQualityError as error:
        _raise_quality_http_error(error)


@router.post(
    "/drafts/{draft_id}/approve",
    response_model=ScriptApprovalRead,
)
def approve_writer_draft(
    draft_id: int,
    payload: ScriptApproveRequest,
    db: Session = Depends(get_db),
) -> ScriptApprovalRead:
    _require_development()
    try:
        return script_quality.approve_draft(db, draft_id, payload)
    except script_quality.ScriptQualityError as error:
        _raise_quality_http_error(error)


@router.post(
    "/drafts/{draft_id}/publish",
    response_model=ScriptPublicationRead,
)
def publish_writer_draft(
    draft_id: int,
    db: Session = Depends(get_db),
) -> ScriptPublicationRead:
    _require_development()
    try:
        return script_quality.publish_draft(db, draft_id)
    except script_quality.ScriptQualityError as error:
        _raise_quality_http_error(error)


@router.get(
    "/drafts/{draft_id}/publication",
    response_model=ScriptPublicationRead,
)
def read_writer_draft_publication(
    draft_id: int,
    db: Session = Depends(get_db),
) -> ScriptPublicationRead:
    _require_development()
    try:
        return script_quality.get_publication(db, draft_id)
    except script_quality.ScriptQualityError as error:
        _raise_quality_http_error(error)
