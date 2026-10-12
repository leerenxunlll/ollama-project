"""Strict request and generated-content schemas for Writer drafts."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Difficulty = Literal["easy", "medium", "hard"]
WriterPhase = Literal["intro", "act_1", "act_2"]
RoleKey = Literal["role_1", "role_2", "role_3", "role_4"]
WriterDraftStatus = Literal[
    "created",
    "generating_blueprint",
    "blueprint_ready",
    "generating_intro",
    "intro_ready",
    "generating_act_1",
    "act_1_ready",
    "generating_act_2",
    "draft_complete",
    "generation_failed",
]
NonEmptyText = Annotated[str, Field(min_length=1, max_length=12000)]


class StrictWriterModel(BaseModel):
    """Base class that rejects unrecognized Writer fields."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class WriterCreateRequest(StrictWriterModel):
    """User-provided creative constraints; game size remains fixed at four."""

    theme: Annotated[str, Field(min_length=1, max_length=120)]
    era: Annotated[str, Field(min_length=1, max_length=120)]
    atmosphere: Annotated[str, Field(min_length=1, max_length=120)]
    difficulty: Difficulty
    custom_requirements: str | None = Field(default=None, max_length=3000)

    @field_validator("custom_requirements")
    @classmethod
    def reject_blank_custom_requirements(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("custom_requirements cannot be blank")
        return value


class WriterScriptMetadata(StrictWriterModel):
    title: Annotated[str, Field(min_length=1, max_length=200)]
    summary: NonEmptyText
    theme: Annotated[str, Field(min_length=1, max_length=120)]
    era: Annotated[str, Field(min_length=1, max_length=120)]
    atmosphere: Annotated[str, Field(min_length=1, max_length=120)]
    difficulty: Difficulty


class WriterCaseTruth(StrictWriterModel):
    culprit_role_key: RoleKey
    victim: NonEmptyText
    motive: NonEmptyText
    method: NonEmptyText
    crime_time: NonEmptyText
    crime_location: NonEmptyText
    case_summary: NonEmptyText
    key_causal_facts: list[NonEmptyText] = Field(min_length=3, max_length=12)


class WriterTimelineEvent(StrictWriterModel):
    event_key: Annotated[str, Field(pattern=r"^event_[1-9][0-9]*$")]
    time: NonEmptyText
    location: NonEmptyText
    description: NonEmptyText
    involved_role_keys: list[RoleKey] = Field(min_length=1, max_length=4)
    is_public_knowledge: bool

    @field_validator("involved_role_keys")
    @classmethod
    def unique_involved_roles(cls, value: list[RoleKey]) -> list[RoleKey]:
        if len(value) != len(set(value)):
            raise ValueError("involved_role_keys must be unique")
        return value


class WriterCharacter(StrictWriterModel):
    role_key: RoleKey
    name: Annotated[str, Field(min_length=1, max_length=120)]
    age: int | None = Field(default=None, ge=1, le=120)
    identity: Annotated[str, Field(min_length=1, max_length=160)]
    public_background: NonEmptyText
    private_background: NonEmptyText
    personality: NonEmptyText
    speaking_style: NonEmptyText
    personal_goal: NonEmptyText
    personal_history: NonEmptyText
    relationship_to_victim: NonEmptyText
    pre_case_experience: NonEmptyText
    private_secrets: list[NonEmptyText] = Field(min_length=1, max_length=8)
    initial_knowledge: list[NonEmptyText] = Field(min_length=1, max_length=12)


class WriterClue(StrictWriterModel):
    clue_key: Annotated[str, Field(pattern=r"^clue_[1-9][0-9]*$")]
    name: Annotated[str, Field(min_length=1, max_length=160)]
    description: NonEmptyText
    act: Literal["act_1", "act_2"]
    location: Annotated[str, Field(min_length=1, max_length=160)]
    is_core: bool
    importance: int = Field(ge=1, le=5)
    related_event_keys: list[Annotated[str, Field(pattern=r"^event_[1-9][0-9]*$")]] = (
        Field(min_length=1, max_length=8)
    )


class WriterBlueprint(StrictWriterModel):
    """Canonical case facts and all reusable script templates."""

    script_metadata: WriterScriptMetadata
    case_truth: WriterCaseTruth
    canonical_timeline: list[WriterTimelineEvent] = Field(min_length=4, max_length=20)
    characters: list[WriterCharacter] = Field(min_length=4, max_length=4)
    clues: list[WriterClue] = Field(min_length=3, max_length=12)

    @model_validator(mode="after")
    def validate_references(self) -> "WriterBlueprint":
        role_keys = [character.role_key for character in self.characters]
        expected_roles = {"role_1", "role_2", "role_3", "role_4"}
        if set(role_keys) != expected_roles:
            raise ValueError(
                "characters must contain role_1 through role_4 exactly once"
            )
        if len(role_keys) != len(set(role_keys)):
            raise ValueError("character role_key values must be unique")
        if self.case_truth.culprit_role_key not in role_keys:
            raise ValueError("culprit_role_key must reference a blueprint character")
        names = [character.name.casefold() for character in self.characters]
        if len(names) != len(set(names)):
            raise ValueError("character names must be unique")
        for field_name in (
            "personal_goal",
            "personal_history",
            "relationship_to_victim",
        ):
            values = [
                getattr(character, field_name).casefold()
                for character in self.characters
            ]
            if len(values) != len(set(values)):
                raise ValueError(f"character {field_name} values must be distinct")
        knowledge_sets = [
            tuple(sorted(item.casefold() for item in character.initial_knowledge))
            for character in self.characters
        ]
        if len(knowledge_sets) != len(set(knowledge_sets)):
            raise ValueError(
                "each role must have a distinct initial knowledge boundary"
            )

        event_keys = [event.event_key for event in self.canonical_timeline]
        if len(event_keys) != len(set(event_keys)):
            raise ValueError("timeline event_key values must be unique")
        for event in self.canonical_timeline:
            if not set(event.involved_role_keys).issubset(role_keys):
                raise ValueError("timeline contains an unknown role_key")

        clue_keys = [clue.clue_key for clue in self.clues]
        if len(clue_keys) != len(set(clue_keys)):
            raise ValueError("clue_key values must be unique")
        for clue in self.clues:
            if not set(clue.related_event_keys).issubset(event_keys):
                raise ValueError("clue references an unknown event_key")
        return self


class WriterChapter(StrictWriterModel):
    title: Annotated[str, Field(min_length=1, max_length=200)]
    content: NonEmptyText
    chapter_order: int = Field(ge=1, le=3)
    unlock_phase: WriterPhase


class WriterCharacterChapter(WriterChapter):
    role_key: RoleKey


class WriterChapterPack(StrictWriterModel):
    phase: WriterPhase
    shared_chapter: WriterChapter
    character_chapters: list[WriterCharacterChapter] = Field(min_length=4, max_length=4)

    @model_validator(mode="after")
    def validate_phase_and_roles(self) -> "WriterChapterPack":
        expected_order = {"intro": 1, "act_1": 2, "act_2": 3}[self.phase]
        if self.shared_chapter.unlock_phase != self.phase:
            raise ValueError("shared chapter unlock_phase must match pack phase")
        if self.shared_chapter.chapter_order != expected_order:
            raise ValueError("shared chapter_order must match Phase 8A ordering")
        role_keys = [chapter.role_key for chapter in self.character_chapters]
        expected_roles = {"role_1", "role_2", "role_3", "role_4"}
        if set(role_keys) != expected_roles:
            raise ValueError("character chapters must cover role_1 through role_4")
        if len(role_keys) != len(set(role_keys)):
            raise ValueError("character chapter role_key values must be unique")
        if any(
            chapter.unlock_phase != self.phase for chapter in self.character_chapters
        ):
            raise ValueError("character chapter unlock_phase must match pack phase")
        if any(
            chapter.chapter_order != expected_order
            for chapter in self.character_chapters
        ):
            raise ValueError("character chapter_order must match Phase 8A ordering")
        private_titles = [
            chapter.title.casefold() for chapter in self.character_chapters
        ]
        private_contents = [
            chapter.content.casefold() for chapter in self.character_chapters
        ]
        if len(private_titles) != len(set(private_titles)):
            raise ValueError("private chapter titles must be distinct")
        if len(private_contents) != len(set(private_contents)):
            raise ValueError("each private chapter must have distinct content")
        if self.shared_chapter.content.casefold() in private_contents:
            raise ValueError("shared chapter cannot duplicate a private chapter")
        return self


class WriterDraftRead(StrictWriterModel):
    """Development-only view containing spoilers and generated story content."""

    id: int
    status: WriterDraftStatus
    content_revision: int = 1
    publication_status: Literal["unpublished", "publishing", "published"] = (
        "unpublished"
    )
    published_script_id: int | None = None
    generation_request: WriterCreateRequest
    blueprint: WriterBlueprint | None
    chapter_packs: dict[str, WriterChapterPack]
    step_durations_seconds: dict[str, float]
    failed_step: str | None
    last_error_type: str | None
    completed_steps: list[str]
