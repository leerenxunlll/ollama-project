"""Script Quality review, controlled revision, approval, and publish tests."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from threading import Barrier

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker

from app.agents.script_quality_workflow_client import ScriptQualityConnectionError
from app.core.config import settings
from app.db.base import Base
from app.models import (
    Character,
    CharacterScriptChapter,
    Clue,
    GameSession,
    Script,
    ScriptCanonicalData,
    ScriptDraft,
    ScriptReviewRun,
    ScriptRevisionRecord,
    SharedScriptChapter,
)
from app.services import script_quality
from app.services.character_context import build_character_context
from app.services.director_context import build_director_context


def valid_request() -> dict:
    return {
        "theme": "封闭空间悬疑",
        "era": "现代",
        "atmosphere": "压抑",
        "difficulty": "medium",
        "custom_requirements": None,
    }


def valid_blueprint() -> dict:
    return {
        "script_metadata": {
            "title": "雾钟档案",
            "summary": "暴风雪夜的一场旧案调查。",
            "theme": "封闭空间悬疑",
            "era": "现代",
            "atmosphere": "压抑",
            "difficulty": "medium",
        },
        "case_truth": {
            "culprit_role_key": "role_2",
            "victim": "顾闻舟",
            "motive": "阻止档案被公开",
            "method": "利用停电布置药物",
            "crime_time": "21:10 至 21:20",
            "crime_location": "档案室",
            "case_summary": "凶手借停电掩盖作案。",
            "key_causal_facts": ["档案被调换", "备用电源被关闭", "凶手熟悉药柜"],
        },
        "canonical_timeline": [
            {
                "event_key": f"event_{index}",
                "time": f"20:{index * 5:02d}",
                "location": "疗养院",
                "description": f"真实事件 {index} 发生。",
                "involved_role_keys": [f"role_{index}"],
                "is_public_knowledge": index == 1,
            }
            for index in range(1, 5)
        ],
        "characters": [
            {
                "role_key": f"role_{index}",
                "name": f"角色{index}",
                "age": 30 + index,
                "identity": f"身份{index}",
                "public_background": f"公开背景{index}",
                "private_background": f"私人背景{index}",
                "personality": f"性格{index}",
                "speaking_style": f"说话风格{index}",
                "personal_goal": f"目标{index}",
                "personal_history": f"个人经历{index}",
                "relationship_to_victim": f"与死者关系{index}",
                "pre_case_experience": f"案发前经历{index}",
                "private_secrets": [f"私密秘密_SENTINEL_{index}"],
                "initial_knowledge": [f"初始认知{index}"],
            }
            for index in range(1, 5)
        ],
        "clues": [
            {
                "clue_key": f"clue_{index}",
                "name": f"线索{index}",
                "description": f"关联 event_{index} 的线索。",
                "act": "act_1" if index < 3 else "act_2",
                "location": "档案室",
                "is_core": index == 1,
                "importance": 3,
                "related_event_keys": [f"event_{index}"],
            }
            for index in range(1, 4)
        ],
    }


def valid_pack(phase: str) -> dict:
    order = {"intro": 1, "act_1": 2, "act_2": 3}[phase]
    return {
        "phase": phase,
        "shared_chapter": {
            "title": f"{phase} 公共章节",
            "content": f"{phase} 的公共剧情内容。",
            "chapter_order": order,
            "unlock_phase": phase,
        },
        "character_chapters": [
            {
                "role_key": f"role_{index}",
                "title": f"角色{index}的{phase}章节",
                "content": f"角色{index}的{phase}私有内容。",
                "chapter_order": order,
                "unlock_phase": phase,
            }
            for index in range(1, 5)
        ],
    }


def complete_draft(db_session, *, status: str = "draft_complete") -> ScriptDraft:
    draft = ScriptDraft(
        status=status,
        generation_request_json=valid_request(),
        blueprint_json=valid_blueprint(),
        chapter_packs_json={
            phase: valid_pack(phase) for phase in ("intro", "act_1", "act_2")
        },
        step_durations_seconds_json={},
    )
    db_session.add(draft)
    db_session.commit()
    return draft


def issue(
    *,
    severity: str = "high",
    scope: str = "shared_chapter",
    phase: str | None = "act_1",
    role_key: str | None = None,
    event_key: str | None = None,
    clue_key: str | None = None,
) -> dict:
    return {
        "issue_code": "continuity_gap",
        "category": "narrative_continuity",
        "severity": severity,
        "description": "第一幕没有解释角色如何到达档案室。",
        "location": {
            "scope": scope,
            "field_path": "chapter.content",
            "phase": phase,
            "role_key": role_key,
            "event_key": event_key,
            "clue_key": clue_key,
        },
        "evidence": "公开章节没有交代转场。",
        "suggested_fix": "增加一句说明。",
    }


def report(verdict: str = "pass", issues: list[dict] | None = None) -> dict:
    return {
        "verdict": verdict,
        "summary": "检查了真相、时间线、角色认知、线索和三阶段章节。",
        "issues": issues or [],
    }


class MockQualityClient:
    def __init__(self, results: list[dict | Exception]) -> None:
        self.results = results
        self.calls: list[tuple[str, str, str]] = []

    def run(self, task_type: str, payload: str, user_id: str) -> dict:
        self.calls.append((task_type, payload, user_id))
        output = self.results.pop(0)
        if isinstance(output, Exception):
            raise output
        return deepcopy(output)


def install_quality_client(monkeypatch, mock: MockQualityClient) -> None:
    monkeypatch.setattr(script_quality, "get_quality_client", lambda: mock)


def file_quality_database(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'script-quality-concurrency.db'}",
        connect_args={"timeout": 10},
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        draft = ScriptDraft(
            status="draft_complete",
            generation_request_json=valid_request(),
            blueprint_json=valid_blueprint(),
            chapter_packs_json={
                phase: valid_pack(phase) for phase in ("intro", "act_1", "act_2")
            },
            step_durations_seconds_json={},
        )
        db.add(draft)
        db.commit()
        draft_id = draft.id
    return engine, factory, draft_id


def test_incomplete_draft_cannot_be_reviewed(client, db_session, monkeypatch) -> None:
    draft = complete_draft(db_session, status="act_1_ready")
    mock = MockQualityClient([report()])
    install_quality_client(monkeypatch, mock)

    response = client.post(f"/api/writer/drafts/{draft.id}/review")

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "deterministic_validation_failed"
    assert mock.calls == []
    assert db_session.scalar(select(func.count(ScriptReviewRun.id))) == 0


def test_review_report_is_schema_and_reference_checked(
    client, db_session, monkeypatch
) -> None:
    draft = complete_draft(db_session)
    invalid = report(
        "pass",
        [
            issue(
                scope="timeline_event",
                phase=None,
                event_key="event_99",
            )
        ],
    )
    mock = MockQualityClient([invalid])
    install_quality_client(monkeypatch, mock)

    response = client.post(f"/api/writer/drafts/{draft.id}/review")

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "invalid_review_report"
    run = db_session.scalar(select(ScriptReviewRun))
    assert run is not None
    assert run.review_status == "failed"
    assert run.report_json is None
    assert db_session.get(ScriptDraft, draft.id).content_revision == 1


@pytest.mark.parametrize(
    "invalid_report",
    [
        "missing_field",
        "unknown_field",
        "invalid_severity",
        "unknown_role",
        "unknown_clue",
    ],
)
def test_review_rejects_invalid_schema_fields_and_references(
    client, db_session, monkeypatch, invalid_report: str
) -> None:
    draft = complete_draft(db_session)
    invalid = report()
    if invalid_report == "missing_field":
        invalid.pop("summary")
    elif invalid_report == "unknown_field":
        invalid["execute"] = "do not run"
    elif invalid_report == "invalid_severity":
        invalid["issues"] = [issue(severity="urgent")]
    elif invalid_report == "unknown_role":
        invalid["issues"] = [issue(scope="character", phase=None, role_key="role_9")]
    else:
        invalid["issues"] = [issue(scope="clue", phase=None, clue_key="clue_99")]
    install_quality_client(monkeypatch, MockQualityClient([invalid]))

    response = client.post(f"/api/writer/drafts/{draft.id}/review")

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "invalid_review_report"
    run = db_session.scalar(select(ScriptReviewRun))
    assert run.review_status == "failed"
    assert run.report_json is None


def test_passing_verdict_with_critical_issue_is_downgraded(
    client, db_session, monkeypatch
) -> None:
    draft = complete_draft(db_session)
    mock = MockQualityClient([report("pass", [issue(severity="critical")])])
    install_quality_client(monkeypatch, mock)

    response = client.post(f"/api/writer/drafts/{draft.id}/review")

    assert response.status_code == 201
    body = response.json()
    assert body["review_status"] == "completed"
    assert body["content_revision"] == 1
    assert body["report"]["verdict"] == "needs_revision"
    assert mock.calls[0][0] == "review"
    assert "case_truth" in mock.calls[0][1]
    assert db_session.get(ScriptDraft, draft.id).blueprint_json == valid_blueprint()


def test_failed_quality_call_is_recorded_without_changing_draft(
    client, db_session, monkeypatch
) -> None:
    draft = complete_draft(db_session)
    before = deepcopy(draft.chapter_packs_json)
    mock = MockQualityClient([ScriptQualityConnectionError("Could not connect")])
    install_quality_client(monkeypatch, mock)

    response = client.post(f"/api/writer/drafts/{draft.id}/review")

    assert response.status_code == 502
    db_session.expire_all()
    current = db_session.get(ScriptDraft, draft.id)
    assert current.chapter_packs_json == before
    assert current.content_revision == 1
    assert db_session.scalar(select(func.count(ScriptReviewRun.id))) == 1


def test_revision_replaces_only_one_pack_and_invalidates_old_review(
    client, db_session, monkeypatch
) -> None:
    draft = complete_draft(db_session)
    revised_pack = valid_pack("act_1")
    revised_pack["shared_chapter"]["content"] = "经核对补全了第一幕转场。"
    mock = MockQualityClient([report("needs_revision", [issue()]), revised_pack])
    install_quality_client(monkeypatch, mock)
    review_response = client.post(f"/api/writer/drafts/{draft.id}/review")
    assert review_response.status_code == 201
    before_intro = deepcopy(draft.chapter_packs_json["intro"])
    before_act_2 = deepcopy(draft.chapter_packs_json["act_2"])

    response = client.post(f"/api/writer/drafts/{draft.id}/revise/act_1")

    assert response.status_code == 200
    assert response.json()["content_revision"] == 2
    db_session.expire_all()
    current = db_session.get(ScriptDraft, draft.id)
    assert current.content_revision == 2
    assert current.chapter_packs_json["intro"] == before_intro
    assert current.chapter_packs_json["act_2"] == before_act_2
    assert (
        current.chapter_packs_json["act_1"]["shared_chapter"]["content"]
        == "经核对补全了第一幕转场。"
    )
    assert current.approved_revision is None
    assert current.approved_review_run_id is None
    assert db_session.scalar(select(func.count(ScriptRevisionRecord.id))) == 1
    assert mock.calls[1][0] == "revise_chapter_pack"
    stale_approval = client.post(
        f"/api/writer/drafts/{draft.id}/approve",
        json={"review_run_id": review_response.json()["id"]},
    )
    assert stale_approval.status_code == 409


def test_invalid_revision_preserves_original_content(
    client, db_session, monkeypatch
) -> None:
    draft = complete_draft(db_session)
    mock = MockQualityClient([report("needs_revision", [issue()]), {"bad": "shape"}])
    install_quality_client(monkeypatch, mock)
    client.post(f"/api/writer/drafts/{draft.id}/review")
    original = deepcopy(draft.chapter_packs_json)

    response = client.post(f"/api/writer/drafts/{draft.id}/revise/act_1")

    assert response.status_code == 502
    db_session.expire_all()
    current = db_session.get(ScriptDraft, draft.id)
    assert current.chapter_packs_json == original
    assert current.content_revision == 1
    assert db_session.scalar(select(func.count(ScriptRevisionRecord.id))) == 0


def test_revision_requires_current_review_and_only_accepts_valid_phase(
    client, db_session
) -> None:
    draft = complete_draft(db_session)
    response = client.post(f"/api/writer/drafts/{draft.id}/revise/act_1")
    assert response.status_code == 409
    invalid_phase = client.post(f"/api/writer/drafts/{draft.id}/revise/vote")
    assert invalid_phase.status_code == 422


def test_medium_issues_require_explicit_acceptance_and_publish_atomically(
    client, db_session, monkeypatch
) -> None:
    draft = complete_draft(db_session)
    mock = MockQualityClient([report("pass", [issue(severity="medium")])])
    install_quality_client(monkeypatch, mock)
    review_response = client.post(f"/api/writer/drafts/{draft.id}/review")
    assert review_response.status_code == 201
    review_id = review_response.json()["id"]

    rejected = client.post(
        f"/api/writer/drafts/{draft.id}/approve",
        json={
            "review_run_id": review_id,
            "accepted_medium_issue_indexes": [],
        },
    )
    assert rejected.status_code == 409
    approved = client.post(
        f"/api/writer/drafts/{draft.id}/approve",
        json={
            "review_run_id": review_id,
            "accepted_medium_issue_indexes": [1],
        },
    )
    assert approved.status_code == 200
    published = client.post(f"/api/writer/drafts/{draft.id}/publish")
    assert published.status_code == 200
    result = published.json()
    assert result["publication_status"] == "published"
    assert result["script_id"] is not None
    assert "case_truth" not in result
    assert "role_2" not in str(result)

    script = db_session.get(Script, result["script_id"])
    assert script.status == "ready"
    characters = db_session.scalars(
        select(Character).where(Character.script_id == script.id)
    ).all()
    clues = db_session.scalars(select(Clue).where(Clue.script_id == script.id)).all()
    shared = db_session.scalars(
        select(SharedScriptChapter).where(SharedScriptChapter.script_id == script.id)
    ).all()
    private = db_session.scalars(
        select(CharacterScriptChapter).where(
            CharacterScriptChapter.character_id.in_(
                [character.id for character in characters]
            )
        )
    ).all()
    canonical = db_session.get(ScriptCanonicalData, script.id)
    assert len(characters) == 4
    assert sum(character.is_killer for character in characters) == 1
    assert len(clues) == 3
    assert len(shared) == 3
    assert len(private) == 12
    assert canonical.case_truth_json["culprit_role_key"] == "role_2"
    assert canonical.role_character_ids_json["role_2"] == next(
        character.id for character in characters if character.is_killer
    )
    assert canonical.clue_ids_json.keys() == {"clue_1", "clue_2", "clue_3"}
    assert canonical.clue_event_keys_json["clue_1"] == ["event_1"]
    assert characters[0].private_secrets_json

    repeated = client.post(f"/api/writer/drafts/{draft.id}/publish")
    assert repeated.status_code == 200
    assert repeated.json()["script_id"] == result["script_id"]
    assert db_session.scalar(select(func.count(Script.id))) == 1
    game_response = client.post("/api/games", json={"script_id": script.id})
    assert game_response.status_code == 201
    game = game_response.json()
    game_id = game["id"]
    role_ids = [item["id"] for item in game["game_characters"]]
    selected = client.post(
        f"/api/games/{game_id}/select-character",
        json={"game_character_id": role_ids[0]},
    )
    assert selected.status_code == 200
    intro = client.get(f"/api/games/{game_id}/me/story").json()
    assert len(intro) == 1
    assert intro[0]["content"] == "角色1的intro私有内容。"
    assert client.post(f"/api/games/{game_id}/me/acknowledge-intro").status_code == 200
    assert client.post(f"/api/games/{game_id}/start").status_code == 200

    game_session = db_session.get(GameSession, game_id)
    game_session.phase_started_at = datetime.now(timezone.utc) - timedelta(seconds=120)
    db_session.commit()
    advanced = client.post(f"/api/games/{game_id}/advance-phase")
    assert advanced.status_code == 200
    public_act_1 = client.get(f"/api/games/{game_id}/story/public").json()
    assert [chapter["unlock_phase"] for chapter in public_act_1] == [
        "intro",
        "act_1",
    ]
    character_context = client.get(
        f"/api/games/{game_id}/characters/{role_ids[1]}/context"
    ).json()
    private_chapters = character_context["character_script_chapters"]
    assert [chapter["unlock_phase"] for chapter in private_chapters] == [
        "intro",
        "act_1",
    ]
    assert "角色2的act_1私有内容。" in str(private_chapters)
    assert "角色1的act_1私有内容。" not in str(private_chapters)


def test_publish_requires_approval_and_transaction_rolls_back_on_failure(
    client, db_session, monkeypatch
) -> None:
    draft = complete_draft(db_session)
    mock = MockQualityClient([report()])
    install_quality_client(monkeypatch, mock)
    review = client.post(f"/api/writer/drafts/{draft.id}/review").json()
    response = client.post(f"/api/writer/drafts/{draft.id}/publish")
    assert response.status_code == 409

    client.post(
        f"/api/writer/drafts/{draft.id}/approve",
        json={"review_run_id": review["id"]},
    )

    def fail_canonical_insert(_mapper, _connection, _target) -> None:
        raise RuntimeError("injected failure")

    event.listen(ScriptCanonicalData, "before_insert", fail_canonical_insert)
    try:
        with pytest.raises(RuntimeError, match="injected failure"):
            script_quality.publish_draft(db_session, draft.id)
    finally:
        event.remove(ScriptCanonicalData, "before_insert", fail_canonical_insert)
    db_session.expire_all()
    current = db_session.get(ScriptDraft, draft.id)
    assert current.publication_status == "unpublished"
    assert current.published_script_id is None
    assert db_session.scalar(select(func.count(Script.id))) == 0
    assert db_session.scalar(select(func.count(Character.id))) == 0


def test_concurrent_revisions_only_save_one_version(tmp_path, monkeypatch) -> None:
    engine, factory, draft_id = file_quality_database(tmp_path)
    with factory() as db:
        db.add(
            ScriptReviewRun(
                draft_id=draft_id,
                content_revision=1,
                review_status="completed",
                report_json=report("needs_revision", [issue()]),
            )
        )
        db.commit()

    barrier = Barrier(2)
    mock = MockQualityClient([valid_pack("act_1"), valid_pack("act_1")])
    original_bounded_payload = script_quality._bounded_payload

    def synchronize_before_revision(payload: dict) -> str:
        result = original_bounded_payload(payload)
        barrier.wait(timeout=5)
        return result

    monkeypatch.setattr(script_quality, "_bounded_payload", synchronize_before_revision)

    def revise() -> str:
        with factory() as db:
            try:
                script_quality.revise_chapter_pack(db, draft_id, "act_1", client=mock)
                return "revised"
            except script_quality.ScriptQualityError as error:
                return error.error_type

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda _index: revise(), range(2)))
        assert outcomes.count("revised") == 1
        assert outcomes.count("draft_changed_during_revision") == 1
        with factory() as db:
            assert db.get(ScriptDraft, draft_id).content_revision == 2
            assert db.scalar(select(func.count(ScriptRevisionRecord.id))) == 1
    finally:
        engine.dispose()


def test_concurrent_publication_creates_exactly_one_script(
    tmp_path, monkeypatch
) -> None:
    engine, factory, draft_id = file_quality_database(tmp_path)
    with factory() as db:
        review = ScriptReviewRun(
            draft_id=draft_id,
            content_revision=1,
            review_status="completed",
            report_json=report(),
        )
        db.add(review)
        db.flush()
        draft = db.get(ScriptDraft, draft_id)
        draft.approved_revision = 1
        draft.approved_review_run_id = review.id
        draft.approved_at = datetime.now(timezone.utc)
        db.commit()

    barrier = Barrier(2)
    original_bounded_payload = script_quality._bounded_payload

    def synchronize_before_claim(payload: dict) -> str:
        result = original_bounded_payload(payload)
        barrier.wait(timeout=5)
        return result

    monkeypatch.setattr(script_quality, "_bounded_payload", synchronize_before_claim)

    def publish() -> str:
        with factory() as db:
            try:
                script_quality.publish_draft(db, draft_id)
                return "published"
            except script_quality.ScriptQualityError as error:
                return error.error_type

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda _index: publish(), range(2)))
        assert outcomes.count("published") == 1
        assert outcomes.count("publication_conflict") == 1
        with factory() as db:
            draft = db.get(ScriptDraft, draft_id)
            assert draft.publication_status == "published"
            assert draft.published_script_id is not None
            assert db.scalar(select(func.count(Script.id))) == 1
            assert db.scalar(select(func.count(Character.id))) == 4
    finally:
        engine.dispose()


def test_published_truth_is_director_only_and_character_private_data_is_scoped(
    client, db_session, monkeypatch
) -> None:
    draft = complete_draft(db_session)
    mock = MockQualityClient([report()])
    install_quality_client(monkeypatch, mock)
    review = client.post(f"/api/writer/drafts/{draft.id}/review").json()
    client.post(
        f"/api/writer/drafts/{draft.id}/approve",
        json={"review_run_id": review["id"]},
    )
    published = client.post(f"/api/writer/drafts/{draft.id}/publish").json()
    game = client.post("/api/games", json={"script_id": published["script_id"]}).json()
    game_id = game["id"]
    runtime_ids = [item["id"] for item in game["game_characters"]]

    own_context = build_character_context(db_session, game_id, runtime_ids[0])
    director_context = build_director_context(db_session, game_id)

    assert own_context.character.initial_knowledge == ["初始认知1"]
    assert own_context.character.private_secrets == ["私密秘密_SENTINEL_1"]
    assert "私密秘密_SENTINEL_2" not in str(own_context.model_dump())
    assert "case_truth" not in own_context.model_dump()["character"]
    assert director_context.script.case_truth["culprit_role_key"] == "role_2"
    assert len(director_context.script.canonical_timeline) == 4
    assert "private Message" not in str(director_context.model_dump())
    assert "inner_os" not in str(director_context.model_dump())
    assert "私密秘密_SENTINEL_2" in str(director_context.model_dump())
    assert "case_truth" not in client.get("/api/scripts").text


def test_review_payload_is_never_truncated_and_quality_key_is_independent(
    client, db_session, monkeypatch
) -> None:
    draft = complete_draft(db_session)
    oversized = deepcopy(draft.chapter_packs_json)
    for phase, pack in oversized.items():
        pack["shared_chapter"]["content"] = "长文本" * 3997 + f"公共{phase}"
        for index, chapter in enumerate(pack["character_chapters"]):
            chapter["content"] = "长文本" * 3997 + f"角色{phase}{index}"
    draft.chapter_packs_json = oversized
    db_session.commit()
    monkeypatch.setattr(settings, "dify_api_url", "https://dify.example/v1")
    monkeypatch.setattr(settings, "dify_writer_api_key", "writer-key")
    monkeypatch.setattr(settings, "dify_script_quality_api_key", "")
    assert not settings.dify_script_quality_configured
    assert client.get("/api/writer/quality/status").json() == {"configured": False}
    response = client.post(f"/api/writer/drafts/{draft.id}/review")
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "quality_payload_too_large"
