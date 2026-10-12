"""Focused Writer draft API, schema, workflow, and concurrency tests."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.agents import writer_workflow_client
from app.core.config import settings
from app.db.base import Base
from app.models import Character, GameSession, Script, ScriptDraft
from app.schemas.writer import (
    WriterBlueprint,
    WriterChapterPack,
)
from app.services import writer as writer_service


def valid_request() -> dict:
    return {
        "theme": "封闭空间悬疑",
        "era": "现代",
        "atmosphere": "压抑",
        "difficulty": "medium",
        "custom_requirements": "线索可公平推理",
    }


def valid_blueprint() -> dict:
    return {
        "script_metadata": {
            "title": "雾钟档案",
            "summary": "一场暴风雪中的旧案调查。",
            "theme": "封闭空间悬疑",
            "era": "现代",
            "atmosphere": "压抑",
            "difficulty": "medium",
        },
        "case_truth": {
            "culprit_role_key": "role_2",
            "victim": "顾闻舟，旧疗养院的管理人",
            "motive": "死者准备公开一份伪造档案",
            "method": "利用停电时预先布置的药物",
            "crime_time": "21:10 至 21:20",
            "crime_location": "疗养院档案室",
            "case_summary": "凶手借暴风雪掩护，利用旧档案室的断电间隙行凶。",
            "key_causal_facts": [
                "档案被调换",
                "备用电源被人为关闭",
                "凶手熟悉药物保管流程",
            ],
        },
        "canonical_timeline": [
            {
                "event_key": f"event_{index}",
                "time": f"20:{index * 5:02d}",
                "location": "疗养院",
                "description": f"真实事件 {index} 发生。",
                "involved_role_keys": [f"role_{index % 4 + 1}"],
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
                "public_background": f"公开经历{index}",
                "private_background": f"私人背景{index}",
                "personality": f"性格{index}",
                "speaking_style": f"说话方式{index}",
                "personal_goal": f"目标{index}",
                "personal_history": f"一次具体经历{index}",
                "relationship_to_victim": f"与死者关系{index}",
                "pre_case_experience": f"案发前经历{index}",
                "private_secrets": [f"秘密{index}"],
                "initial_knowledge": [f"初始认知{index}"],
            }
            for index in range(1, 5)
        ],
        "clues": [
            {
                "clue_key": f"clue_{index}",
                "name": f"线索{index}",
                "description": f"与真实事件 event_{index} 相关的物证。",
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
            "content": "暴风雪封住了疗养院的出口，众人开始回忆各自经历。",
            "chapter_order": order,
            "unlock_phase": phase,
        },
        "character_chapters": [
            {
                "role_key": f"role_{index}",
                "title": f"角色{index}的{phase}经历",
                "content": f"角色{index}回忆起一段与案件有关的具体往事。",
                "chapter_order": order,
                "unlock_phase": phase,
            }
            for index in range(1, 5)
        ],
    }


class MockWriterClient:
    def __init__(self, outputs: list[dict | Exception]) -> None:
        self.outputs = outputs
        self.calls: list[tuple[str, str, str]] = []

    def run(self, task_type: str, payload: str, user_id: str) -> dict:
        self.calls.append((task_type, payload, user_id))
        output = self.outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        return deepcopy(output)


@pytest.fixture
def writer_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "dify_api_url", "https://dify.test/v1")
    monkeypatch.setattr(settings, "dify_writer_api_key", "test-writer-key")


def test_create_draft_validates_request_and_does_not_create_script(client) -> None:
    response = client.post("/api/writer/drafts", json=valid_request())
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "created"
    assert body["blueprint"] is None
    assert body["chapter_packs"] == {}
    assert body["completed_steps"] == []
    assert client.get("/api/scripts").json() == []


@pytest.mark.parametrize(
    "changes",
    [
        {"difficulty": "impossible"},
        {"theme": "   "},
        {"custom_requirements": "   "},
        {"unexpected": "not allowed"},
    ],
)
def test_create_draft_rejects_invalid_request(client, changes: dict) -> None:
    response = client.post("/api/writer/drafts", json={**valid_request(), **changes})
    assert response.status_code == 422


def test_blueprint_rejects_non_four_roles_and_unknown_culprit() -> None:
    blueprint = valid_blueprint()
    with pytest.raises(ValidationError):
        WriterBlueprint.model_validate(
            {**blueprint, "characters": blueprint["characters"][:3]}
        )

    blueprint = valid_blueprint()
    blueprint["case_truth"]["culprit_role_key"] = "role_5"
    with pytest.raises(ValidationError):
        WriterBlueprint.model_validate(blueprint)


def test_blueprint_rejects_duplicate_role_and_invalid_timeline_reference() -> None:
    blueprint = valid_blueprint()
    blueprint["characters"][1]["role_key"] = "role_1"
    with pytest.raises(ValidationError):
        WriterBlueprint.model_validate(blueprint)

    blueprint = valid_blueprint()
    blueprint["canonical_timeline"][0]["involved_role_keys"] = ["role_4"]
    blueprint["canonical_timeline"][0]["involved_role_keys"] = ["role_9"]
    with pytest.raises(ValidationError):
        WriterBlueprint.model_validate(blueprint)


def test_blueprint_rejects_reused_personal_story_and_knowledge() -> None:
    blueprint = valid_blueprint()
    blueprint["characters"][1]["personal_goal"] = blueprint["characters"][0][
        "personal_goal"
    ]
    with pytest.raises(ValidationError):
        WriterBlueprint.model_validate(blueprint)

    blueprint = valid_blueprint()
    blueprint["characters"][1]["initial_knowledge"] = blueprint["characters"][0][
        "initial_knowledge"
    ]
    with pytest.raises(ValidationError):
        WriterBlueprint.model_validate(blueprint)


def test_blueprint_rejects_duplicate_events_and_unknown_clue_event() -> None:
    blueprint = valid_blueprint()
    blueprint["canonical_timeline"][1]["event_key"] = "event_1"
    with pytest.raises(ValidationError):
        WriterBlueprint.model_validate(blueprint)

    blueprint = valid_blueprint()
    blueprint["clues"][0]["related_event_keys"] = ["event_99"]
    with pytest.raises(ValidationError):
        WriterBlueprint.model_validate(blueprint)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda pack: pack.update(character_chapters=pack["character_chapters"][:3]),
        lambda pack: pack["character_chapters"][1].update(role_key="role_1"),
        lambda pack: pack["character_chapters"][0].update(unlock_phase="act_2"),
        lambda pack: pack["shared_chapter"].update(chapter_order=3),
    ],
)
def test_chapter_pack_rejects_invalid_count_roles_phase_and_order(mutate) -> None:
    pack = valid_pack("intro")
    mutate(pack)
    with pytest.raises(ValidationError):
        WriterChapterPack.model_validate(pack)


def test_writer_generation_requires_steps_and_keeps_successful_results(
    client, monkeypatch: pytest.MonkeyPatch, writer_config
) -> None:
    mock = MockWriterClient(
        [valid_blueprint(), valid_pack("intro"), RuntimeError("offline")]
    )
    monkeypatch.setattr(writer_service, "get_writer_client", lambda: mock)
    draft = client.post("/api/writer/drafts", json=valid_request()).json()

    out_of_order = client.post(
        f"/api/writer/drafts/{draft['id']}/generate-chapter-pack/intro"
    )
    assert out_of_order.status_code == 409

    blueprint_response = client.post(
        f"/api/writer/drafts/{draft['id']}/generate-blueprint"
    )
    assert blueprint_response.status_code == 200
    assert blueprint_response.json()["status"] == "blueprint_ready"
    assert blueprint_response.json()["completed_steps"] == ["blueprint"]

    duplicate_blueprint = client.post(
        f"/api/writer/drafts/{draft['id']}/generate-blueprint"
    )
    assert duplicate_blueprint.status_code == 409
    assert len(mock.calls) == 1

    intro_response = client.post(
        f"/api/writer/drafts/{draft['id']}/generate-chapter-pack/intro"
    )
    assert intro_response.status_code == 200
    assert intro_response.json()["status"] == "intro_ready"

    act_1_response = client.post(
        f"/api/writer/drafts/{draft['id']}/generate-chapter-pack/act_1"
    )
    assert act_1_response.status_code == 502
    current = client.get(f"/api/writer/drafts/{draft['id']}").json()
    assert current["status"] == "generation_failed"
    assert current["failed_step"] == "act_1"
    assert current["completed_steps"] == ["blueprint", "intro"]
    assert "act_1" not in current["chapter_packs"]
    assert [call[0] for call in mock.calls] == [
        "blueprint",
        "chapter_pack",
        "chapter_pack",
    ]


def test_chapter_generation_preserves_previous_packs_and_can_retry(
    client, monkeypatch: pytest.MonkeyPatch, writer_config
) -> None:
    mock = MockWriterClient(
        [
            valid_blueprint(),
            valid_pack("intro"),
            RuntimeError("offline"),
            valid_pack("act_1"),
        ]
    )
    monkeypatch.setattr(writer_service, "get_writer_client", lambda: mock)
    draft = client.post("/api/writer/drafts", json=valid_request()).json()
    draft_id = draft["id"]
    client.post(f"/api/writer/drafts/{draft_id}/generate-blueprint")
    client.post(f"/api/writer/drafts/{draft_id}/generate-chapter-pack/intro")
    failed = client.post(f"/api/writer/drafts/{draft_id}/generate-chapter-pack/act_1")
    assert failed.status_code == 502
    retried = client.post(f"/api/writer/drafts/{draft_id}/generate-chapter-pack/act_1")
    assert retried.status_code == 200
    assert retried.json()["status"] == "act_1_ready"
    assert retried.json()["completed_steps"] == ["blueprint", "intro", "act_1"]


def test_completed_draft_rejects_repeated_steps(
    client, monkeypatch, writer_config
) -> None:
    mock = MockWriterClient(
        [
            valid_blueprint(),
            valid_pack("intro"),
            valid_pack("act_1"),
            valid_pack("act_2"),
        ]
    )
    monkeypatch.setattr(writer_service, "get_writer_client", lambda: mock)
    draft_id = client.post("/api/writer/drafts", json=valid_request()).json()["id"]
    client.post(f"/api/writer/drafts/{draft_id}/generate-blueprint")
    for phase in ("intro", "act_1", "act_2"):
        response = client.post(
            f"/api/writer/drafts/{draft_id}/generate-chapter-pack/{phase}"
        )
        assert response.status_code == 200
    repeated = client.post(f"/api/writer/drafts/{draft_id}/generate-chapter-pack/act_2")
    assert repeated.status_code == 409
    assert len(mock.calls) == 4


def test_writer_config_status_and_development_only_draft_access(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "dify_api_url", "https://dify.test/v1")
    monkeypatch.setattr(settings, "dify_character_api_key", "character-test-key")
    monkeypatch.setattr(settings, "dify_director_api_key", "director-test-key")
    monkeypatch.setattr(settings, "dify_writer_api_key", "")
    assert settings.dify_writer_configured is False
    assert client.get("/api/writer/status").json() == {"configured": False}
    draft_id = client.post("/api/writer/drafts", json=valid_request()).json()["id"]
    monkeypatch.setattr(settings, "app_env", "production")
    assert client.get(f"/api/writer/drafts/{draft_id}").status_code == 404
    assert client.get("/api/writer/status").status_code == 404


def test_writer_draft_does_not_mutate_script_or_game(
    client, db_session, monkeypatch, writer_config
) -> None:
    script = Script(title="Untouched script", status="ready")
    db_session.add(script)
    db_session.flush()
    characters = [
        Character(
            script_id=script.id,
            name=f"Character {index}",
            identity="Investigator",
            public_background="Public",
            private_background="Private",
            personality="Careful",
            speaking_style="Measured",
            personal_goal="Find the truth",
        )
        for index in range(4)
    ]
    db_session.add_all(characters)
    db_session.flush()
    game = GameSession(
        script_id=script.id, random_seed=3, status="ready", current_phase="intro"
    )
    db_session.add(game)
    db_session.commit()
    script_id, game_id = script.id, game.id
    monkeypatch.setattr(
        writer_service,
        "get_writer_client",
        lambda: MockWriterClient([valid_blueprint()]),
    )
    draft_id = client.post("/api/writer/drafts", json=valid_request()).json()["id"]
    response = client.post(f"/api/writer/drafts/{draft_id}/generate-blueprint")
    assert response.status_code == 200
    db_session.expire_all()
    assert db_session.get(Script, script_id).status == "ready"
    assert (
        len(
            db_session.scalars(
                select(Character).where(Character.script_id == script_id)
            ).all()
        )
        == 4
    )
    assert db_session.get(GameSession, game_id).current_phase == "intro"


def test_stale_generation_claim_can_be_recovered(
    db_session, monkeypatch, writer_config
) -> None:
    draft = ScriptDraft(
        status="generating_blueprint",
        generation_request_json=valid_request(),
        chapter_packs_json={},
        step_durations_seconds_json={},
        updated_at=datetime.now(timezone.utc) - timedelta(minutes=11),
    )
    db_session.add(draft)
    db_session.commit()
    monkeypatch.setattr(
        writer_service,
        "get_writer_client",
        lambda: MockWriterClient([valid_blueprint()]),
    )
    result = writer_service.generate_blueprint(db_session, draft.id)
    assert result.status == "blueprint_ready"


def test_old_generation_token_cannot_save_after_lease_recovery(db_session) -> None:
    draft = ScriptDraft(
        generation_request_json=valid_request(),
        chapter_packs_json={},
        step_durations_seconds_json={},
    )
    db_session.add(draft)
    db_session.commit()

    _, _, _, old_token = writer_service._claim_step(db_session, draft.id, "blueprint")
    db_session.execute(
        update(ScriptDraft)
        .where(ScriptDraft.id == draft.id)
        .values(updated_at=datetime.now(timezone.utc) - timedelta(minutes=11))
    )
    db_session.commit()
    _, _, _, current_token = writer_service._claim_step(
        db_session, draft.id, "blueprint"
    )
    assert old_token != current_token

    with pytest.raises(writer_service.WriterGenerationConflictError):
        writer_service._save_step(
            db_session,
            draft.id,
            "blueprint",
            old_token,
            valid_blueprint(),
            1.0,
        )
    db_session.expire_all()
    current = db_session.get(ScriptDraft, draft.id)
    assert current.status == "generating_blueprint"
    assert current.blueprint_json is None
    assert current.generation_token == current_token


def test_file_sqlite_atomic_claim_allows_only_one_concurrent_request(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "writer-concurrency.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False, "timeout": 5},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with Session(engine) as db:
        draft = ScriptDraft(
            generation_request_json=valid_request(),
            chapter_packs_json={},
            step_durations_seconds_json={},
        )
        db.add(draft)
        db.commit()
        draft_id = draft.id

    def claim() -> str:
        with factory() as db:
            try:
                writer_service._claim_step(db, draft_id, "blueprint")
                return "claimed"
            except writer_service.WriterGenerationConflictError:
                return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _index: claim(), range(2)))
    assert outcomes.count("claimed") == 1
    assert outcomes.count("conflict") == 1
    with Session(engine) as db:
        assert db.get(ScriptDraft, draft_id).status == "generating_blueprint"
    engine.dispose()


class FakeResponse:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self.payload = payload

    def json(self) -> dict:
        return self.payload


def test_writer_client_parses_object_and_json_string(monkeypatch) -> None:
    client = writer_workflow_client.WriterWorkflowClient(
        "https://dify.test/v1", "secret"
    )
    captured_request: dict = {}

    def respond_with_json_string(url, **kwargs):
        captured_request.update(url=url, **kwargs)
        return FakeResponse(
            200,
            {"data": {"status": "succeeded", "outputs": {"result": '{"ok": true}'}}},
        )

    monkeypatch.setattr(writer_workflow_client.httpx, "post", respond_with_json_string)
    assert client.run("blueprint", "{}", "draft-1-writer") == {"ok": True}
    assert captured_request["url"] == "https://dify.test/v1/workflows/run"
    assert captured_request["headers"]["Authorization"] == "Bearer secret"
    assert captured_request["json"] == {
        "inputs": {"task_type": "blueprint", "payload": "{}"},
        "response_mode": "blocking",
        "user": "draft-1-writer",
    }

    monkeypatch.setattr(
        writer_workflow_client.httpx,
        "post",
        lambda *args, **kwargs: FakeResponse(
            200, {"data": {"status": "succeeded", "outputs": {"result": {"ok": True}}}}
        ),
    )
    assert client.run("blueprint", "{}", "draft-1-writer") == {"ok": True}


@pytest.mark.parametrize(
    "payload,expected",
    [
        (
            {"data": {"status": "failed", "outputs": {}}},
            writer_workflow_client.WriterWorkflowFailedError,
        ),
        (
            {"data": {"status": "succeeded", "outputs": {}}},
            writer_workflow_client.WriterMissingResultError,
        ),
        (
            {"data": {"status": "succeeded", "outputs": {"result": "not-json"}}},
            writer_workflow_client.WriterMalformedJSONError,
        ),
        (
            {"data": {"status": "succeeded", "outputs": {"result": [1]}}},
            writer_workflow_client.WriterOutputError,
        ),
    ],
)
def test_writer_client_rejects_missing_or_invalid_result(
    monkeypatch, payload, expected
) -> None:
    client = writer_workflow_client.WriterWorkflowClient(
        "https://dify.test/v1", "secret"
    )
    monkeypatch.setattr(
        writer_workflow_client.httpx,
        "post",
        lambda *args, **kwargs: FakeResponse(200, payload),
    )
    with pytest.raises(expected):
        client.run("blueprint", "{}", "draft-1-writer")


def test_writer_client_does_not_echo_http_body_or_api_key(monkeypatch) -> None:
    client = writer_workflow_client.WriterWorkflowClient(
        "https://dify.test/v1", "secret-key"
    )
    monkeypatch.setattr(
        writer_workflow_client.httpx,
        "post",
        lambda *args, **kwargs: FakeResponse(401, {"error": "secret-key"}),
    )
    with pytest.raises(writer_workflow_client.WriterHTTPError) as error:
        client.run("blueprint", "{}", "draft-1-writer")
    assert "secret-key" not in str(error.value)
