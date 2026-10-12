"""Strict contracts for script review, bounded revision, approval, and publish."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.writer import WriterChapterPack, WriterPhase

RoleKey = Literal["role_1", "role_2", "role_3", "role_4"]
IssueSeverity = Literal["critical", "high", "medium", "low"]
ReviewVerdict = Literal["pass", "needs_revision", "blocked"]
IssueScope = Literal[
    "blueprint",
    "case_truth",
    "timeline_event",
    "character",
    "clue",
    "shared_chapter",
    "character_chapter",
]


class StrictQualityModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ScriptIssueLocation(StrictQualityModel):
    """Typed location for one checker issue; unused references are null."""

    scope: IssueScope
    field_path: Annotated[str, Field(min_length=1, max_length=200)]
    phase: WriterPhase | None = None
    role_key: RoleKey | None = None
    event_key: Annotated[str, Field(pattern=r"^event_[1-9][0-9]*$")] | None = None
    clue_key: Annotated[str, Field(pattern=r"^clue_[1-9][0-9]*$")] | None = None

    @model_validator(mode="after")
    def validate_scope_references(self) -> "ScriptIssueLocation":
        expected = {
            "blueprint": set(),
            "case_truth": set(),
            "timeline_event": {"event_key"},
            "character": {"role_key"},
            "clue": {"clue_key"},
            "shared_chapter": {"phase"},
            "character_chapter": {"phase", "role_key"},
        }[self.scope]
        actual = {
            key
            for key in ("phase", "role_key", "event_key", "clue_key")
            if getattr(self, key) is not None
        }
        if actual != expected:
            raise ValueError(
                f"{self.scope} location requires references {sorted(expected)}"
            )
        return self


class ScriptReviewIssue(StrictQualityModel):
    issue_code: Annotated[str, Field(min_length=1, max_length=80)]
    category: Literal[
        "timeline_consistency",
        "character_knowledge",
        "canonical_truth",
        "clue_consistency",
        "causal_logic",
        "solvability",
        "character_motivation",
        "narrative_continuity",
        "mystery_pacing",
        "script_quality",
    ]
    severity: IssueSeverity
    description: Annotated[str, Field(min_length=1, max_length=3000)]
    location: ScriptIssueLocation
    evidence: Annotated[str, Field(min_length=1, max_length=3000)]
    suggested_fix: Annotated[str, Field(min_length=1, max_length=3000)]


class ScriptReviewReport(StrictQualityModel):
    verdict: ReviewVerdict
    summary: Annotated[str, Field(min_length=1, max_length=3000)]
    issues: list[ScriptReviewIssue] = Field(max_length=100)


class ScriptReviewRunRead(StrictQualityModel):
    id: int
    draft_id: int
    content_revision: int
    review_status: Literal["completed", "failed", "stale"]
    report: ScriptReviewReport | None
    error_type: str | None
    created_at: datetime
    completed_at: datetime | None


class ScriptRevisionRecordRead(StrictQualityModel):
    id: int
    draft_id: int
    from_revision: int
    to_revision: int
    phase: WriterPhase
    related_review_id: int
    issues_addressed: list[ScriptReviewIssue]
    previous_chapter_pack: WriterChapterPack
    new_chapter_pack: WriterChapterPack
    created_at: datetime


class ScriptApproveRequest(StrictQualityModel):
    review_run_id: int = Field(gt=0)
    accepted_medium_issue_indexes: list[int] = Field(default_factory=list)


class ScriptApprovalRead(StrictQualityModel):
    draft_id: int
    content_revision: int
    review_run_id: int
    accepted_medium_issue_indexes: list[int]
    approved_at: datetime


class ScriptPublicationRead(StrictQualityModel):
    draft_id: int
    publication_status: Literal["unpublished", "publishing", "published"]
    script_id: int | None
    content_revision: int
    title: str | None
    approved_revision: int | None = None
    approved_review_run_id: int | None = None
    approved_at: datetime | None = None


class DeterministicValidationIssue(StrictQualityModel):
    code: str
    field_path: str
    message: str


class ScriptReviewResponse(StrictQualityModel):
    review_run: ScriptReviewRunRead


class ScriptRevisionResponse(StrictQualityModel):
    revision: ScriptRevisionRecordRead
    content_revision: int
