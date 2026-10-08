"""Phase 7 flow, voting, information-boundary, and Director API checks."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.character_agent import (
    CharacterReply,
)
from app.agents.director_agent import DirectorAgent, DirectorOutputValidationError
from app.agents.director_workflow_client import (
    DirectorWorkflowError,
    DirectorWorkflowResponseError,
)
from app.game.flow_manager import build_flow_state
from app.models import (
    CharacterMemory,
    CharacterThought,
    Clue,
    DirectorRecommendationRecord,
    GameCharacter,
    GameCharacterClue,
    GameSession,
    Message,
    Script,
    Vote,
)
from app.schemas.ai import CharacterEmotion, CharacterIntent
from app.schemas.director import (
    DirectorAction,
    DirectorNarrativeRisk,
    DirectorPace,
    DirectorRecommendation,
)
from app.schemas.flow import VoteCreate
from app.services.director_context import build_director_context
from app.services.game_flow import create_vote, get_vote_result
from app.services.seed import seed_development_data


class FakeDirectorAgent:
    """Return a fixed Director recommendation and retain the supplied context."""

    def __init__(self, recommendation=None, error: Exception | None = None) -> None:
        self.recommendation = recommendation
        self.error = error
        self.context = None

    def analyze(self, context):
        self.context = context
        if self.error is not None:
            raise self.error
        return self.recommendation


class FakeCharacterAgent:
    """Return a safe deterministic response for Director speaker-action tests."""

    def __init__(self) -> None:
        self.calls = []

    def respond(self, character_context, interaction_context, user_id):
        self.calls.append((character_context, interaction_context, user_id))
        return CharacterReply(
            speech="我可以补充一件公开线索。",
            inner_os="测试用的角色内心状态。",
            emotion=CharacterEmotion.CALM,
            intent=CharacterIntent.OBSERVE,
            memory_updates=[],
        )


def _start_game(client, db_session: Session) -> dict:
    script = seed_development_data(db_session)
    created = client.post("/api/games", json={"script_id": script.id})
    assert created.status_code == 201
    game = created.json()
    selected = client.post(
        f"/api/games/{game['id']}/select-character",
        json={"game_character_id": game["game_characters"][0]["id"]},
    )
    assert selected.status_code == 200
    started = client.post(f"/api/games/{game['id']}/start")
    assert started.status_code == 200
    return game


def _game_characters(db_session: Session, game_id: int) -> list[GameCharacter]:
    return list(
        db_session.scalars(
            select(GameCharacter)
            .where(GameCharacter.game_session_id == game_id)
            .order_by(GameCharacter.id)
        ).all()
    )


def _set_phase(
    db_session: Session,
    game_id: int,
    phase: str,
    started_at: datetime | None = None,
) -> GameSession:
    game = db_session.get(GameSession, game_id)
    game.current_phase = phase
    game.phase_started_at = started_at or datetime.now(timezone.utc)
    db_session.commit()
    return game


def _cast_complete_vote_set(
    db_session: Session, game_id: int, target_indices: tuple[int, ...] | None = None
) -> None:
    characters = _game_characters(db_session, game_id)
    targets = target_indices or tuple(
        (index + 1) % len(characters) for index in range(4)
    )
    for voter_index, target_index in enumerate(targets):
        create_vote(
            db_session,
            game_id,
            VoteCreate(
                voter_game_character_id=characters[voter_index].id,
                target_game_character_id=characters[target_index].id,
            ),
        )


def _recommendation(action: DirectorAction, **references) -> DirectorRecommendation:
    return DirectorRecommendation(
        pace=DirectorPace.on_track,
        narrative_risk=DirectorNarrativeRisk.low,
        recommended_action=action,
        reason="测试推荐。",
        **references,
    )


def _save_recommendation(
    db_session: Session,
    game_id: int,
    action: DirectorAction,
    **references,
) -> DirectorRecommendationRecord:
    recommendation = _recommendation(action, **references)
    record = DirectorRecommendationRecord(
        game_session_id=game_id,
        pace=recommendation.pace.value,
        narrative_risk=recommendation.narrative_risk.value,
        recommended_action=recommendation.recommended_action.value,
        target_game_character_id=recommendation.target_game_character_id,
        clue_id=recommendation.clue_id,
        public_message_id=recommendation.public_message_id,
        reason=recommendation.reason,
    )
    db_session.add(record)
    db_session.commit()
    db_session.refresh(record)
    return record


def test_flow_state_uses_server_clock_and_has_no_private_fields(
    client, db_session: Session
) -> None:
    game = _start_game(client, db_session)
    stored_game = db_session.get(GameSession, game["id"])
    assert stored_game.phase_started_at == stored_game.started_at

    now = datetime.now(timezone.utc)
    stored_game.phase_started_at = now - timedelta(seconds=4)
    db_session.commit()
    response = client.get(f"/api/games/{game['id']}/flow")
    assert response.status_code == 200
    state = response.json()
    assert state["elapsed_seconds"] >= 3
    assert state["minimum_duration_seconds"] == 10
    assert state["remaining_seconds"] <= 7
    assert state["minimum_time_satisfied"] is False
    assert state["can_advance"] is False
    assert state["vote_progress"] == {
        "votes_cast": 0,
        "total_voters": 4,
        "voting_complete": False,
    }
    assert "is_killer" not in response.text
    assert "private_background" not in response.text


def test_flow_manager_clock_injection_and_vote_gate() -> None:
    now = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
    state = build_flow_state(
        game_id=4,
        status="in_progress",
        current_phase="vote",
        phase_started_at=now - timedelta(seconds=11),
        votes_cast=3,
        total_voters=4,
        now=now,
    )
    assert state.elapsed_seconds == 11
    assert state.minimum_duration_seconds == 10
    assert state.remaining_seconds == 0
    assert state.minimum_time_satisfied is True
    assert state.can_vote is True
    assert state.can_advance is False

    complete = build_flow_state(
        game_id=4,
        status="in_progress",
        current_phase="vote",
        phase_started_at=now - timedelta(seconds=11),
        votes_cast=4,
        total_voters=4,
        now=now,
    )
    assert complete.can_vote is False
    assert complete.can_advance is True


@pytest.mark.parametrize(
    ("phase", "expected"),
    [
        ("intro", True),
        ("act_1", True),
        ("investigation_1", True),
        ("discussion_1", True),
        ("act_2", True),
        ("investigation_2", True),
        ("discussion_2", True),
        ("final_discussion", True),
        ("vote", False),
        ("ending", False),
    ],
)
def test_flow_state_has_explicit_public_speech_policy(
    phase: str, expected: bool
) -> None:
    state = build_flow_state(
        game_id=4,
        status="in_progress",
        current_phase=phase,
        phase_started_at=None,
        votes_cast=0,
        total_voters=4,
    )
    assert state.can_public_speak is expected


def test_public_speech_requires_an_in_progress_game() -> None:
    state = build_flow_state(
        game_id=4,
        status="finished",
        current_phase="intro",
        phase_started_at=None,
        votes_cast=0,
        total_voters=4,
    )
    assert state.can_public_speak is False


def test_phase_advance_enforces_time_votes_and_single_step(
    client, db_session: Session
) -> None:
    game = _start_game(client, db_session)
    blocked = client.post(f"/api/games/{game['id']}/advance-phase")
    assert blocked.status_code == 409
    assert db_session.get(GameSession, game["id"]).current_phase == "intro"

    past = datetime.now(timezone.utc) - timedelta(seconds=11)
    _set_phase(db_session, game["id"], "vote", past)
    no_votes = client.post(f"/api/games/{game['id']}/advance-phase")
    assert no_votes.status_code == 409
    assert db_session.get(GameSession, game["id"]).current_phase == "vote"

    _cast_complete_vote_set(db_session, game["id"])
    advanced = client.post(f"/api/games/{game['id']}/advance-phase")
    assert advanced.status_code == 200
    assert advanced.json()["current_phase"] == "ending"
    assert advanced.json()["status"] == "finished"


def test_invalid_phase_cannot_advance_and_flow_manager_has_no_agent_dependency(
    client, db_session: Session
) -> None:
    from app.game import flow_manager

    game = _start_game(client, db_session)
    _set_phase(
        db_session,
        game["id"],
        "unknown_phase",
        datetime.now(timezone.utc) - timedelta(seconds=30),
    )
    response = client.post(f"/api/games/{game['id']}/advance-phase")
    assert response.status_code == 409
    assert not hasattr(flow_manager, "CharacterAgent")


def test_votes_validate_phase_membership_self_vote_and_duplicate(
    client, db_session: Session
) -> None:
    game = _start_game(client, db_session)
    characters = _game_characters(db_session, game["id"])
    before_vote = client.post(
        f"/api/games/{game['id']}/votes",
        json={
            "voter_game_character_id": characters[0].id,
            "target_game_character_id": characters[1].id,
        },
    )
    assert before_vote.status_code == 409

    _set_phase(db_session, game["id"], "vote")
    self_vote = client.post(
        f"/api/games/{game['id']}/votes",
        json={
            "voter_game_character_id": characters[0].id,
            "target_game_character_id": characters[0].id,
        },
    )
    assert self_vote.status_code == 409

    foreign_game = client.post(
        "/api/games", json={"script_id": game["script_id"]}
    ).json()
    foreign_character_id = foreign_game["game_characters"][0]["id"]
    foreign_vote = client.post(
        f"/api/games/{game['id']}/votes",
        json={
            "voter_game_character_id": foreign_character_id,
            "target_game_character_id": characters[1].id,
        },
    )
    assert foreign_vote.status_code == 404

    payload = {
        "voter_game_character_id": characters[0].id,
        "target_game_character_id": characters[1].id,
    }
    accepted = client.post(f"/api/games/{game['id']}/votes", json=payload)
    duplicate = client.post(f"/api/games/{game['id']}/votes", json=payload)
    assert accepted.status_code == 201
    assert duplicate.status_code == 409
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(Vote)
            .where(Vote.game_session_id == game["id"])
        )
        == 1
    )


@pytest.mark.parametrize(
    ("target_indices", "winner_index", "is_tie"),
    [
        ((1, 0, 0, 0), 0, False),
        ((1, 0, 1, 0), None, True),
    ],
)
def test_vote_tally_is_deterministic_for_winner_and_tie(
    client,
    db_session: Session,
    target_indices: tuple[int, ...],
    winner_index: int | None,
    is_tie: bool,
) -> None:
    game = _start_game(client, db_session)
    _set_phase(db_session, game["id"], "vote")
    characters = _game_characters(db_session, game["id"])
    _cast_complete_vote_set(db_session, game["id"], target_indices)

    result = get_vote_result(db_session, game["id"])
    repeated = get_vote_result(db_session, game["id"])
    expected_winner = characters[winner_index].id if winner_index is not None else None
    assert result.winner_game_character_id == expected_winner
    assert result.is_tie is is_tie
    assert result.voting_complete is True
    assert result.votes_cast == result.total_voters == 4
    assert result.model_dump() == repeated.model_dump()


def test_vote_tally_empty_and_flow_vote_progress_do_not_reveal_choices(
    client, db_session: Session
) -> None:
    game = _start_game(client, db_session)
    _set_phase(db_session, game["id"], "vote")
    result = client.get(f"/api/games/{game['id']}/votes/result")
    assert result.status_code == 200
    assert result.json()["vote_count_by_target"]
    assert result.json()["winner_game_character_id"] is None
    assert result.json()["is_tie"] is False

    flow = client.get(f"/api/games/{game['id']}/flow")
    assert flow.status_code == 200
    assert "vote_count_by_target" not in flow.text
    assert flow.json()["vote_progress"]["votes_cast"] == 0


def test_vote_debug_endpoints_are_development_only(
    client, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.api import games as games_api

    game = _start_game(client, db_session)
    monkeypatch.setattr(games_api.settings, "app_env", "production")
    result = client.get(f"/api/games/{game['id']}/votes/result")
    character_ids = [character["id"] for character in game["game_characters"]]
    cast = client.post(
        f"/api/games/{game['id']}/votes",
        json={
            "voter_game_character_id": character_ids[0],
            "target_game_character_id": character_ids[1],
        },
    )
    assert result.status_code == 404
    assert cast.status_code == 404


def test_director_context_includes_script_truth_and_excludes_runtime_private_data(
    client, db_session: Session
) -> None:
    game = _start_game(client, db_session)
    characters = _game_characters(db_session, game["id"])
    script = db_session.get(Script, game["script_id"])
    clue = db_session.scalars(
        select(Clue).where(Clue.script_id == script.id).order_by(Clue.id)
    ).first()
    human, ai_character = characters[0], characters[1]
    ai_public = Message(
        game_session_id=game["id"],
        sender_game_character_id=ai_character.id,
        channel_type="public",
        content="PUBLIC_SENTINEL: 旧钟停在十一点。",
    )
    private_message = Message(
        game_session_id=game["id"],
        sender_game_character_id=human.id,
        channel_type="private",
        receiver_game_character_id=ai_character.id,
        content="PRIVATE_SENTINEL: 我在私聊里告诉你一件事。",
    )
    system_message = Message(
        game_session_id=game["id"],
        sender_game_character_id=None,
        channel_type="system",
        content="SYSTEM_SENTINEL: 进入开发测试阶段。",
    )
    db_session.add_all([ai_public, private_message, system_message])
    db_session.flush()
    db_session.add_all(
        [
            CharacterThought(
                game_session_id=game["id"],
                game_character_id=ai_character.id,
                ai_message_id=ai_public.id,
                inner_os="THOUGHT_SENTINEL: 我怀疑另一个角色。",
                emotion="nervous",
                intent="observe",
            ),
            CharacterMemory(
                game_session_id=game["id"],
                game_character_id=ai_character.id,
                content="MEMORY_SENTINEL: 私人记忆。",
                importance=3,
                source_message_id=ai_public.id,
            ),
            GameCharacterClue(
                game_character_id=ai_character.id,
                clue_id=clue.id,
                source="test",
            ),
        ]
    )
    db_session.commit()

    context = build_director_context(db_session, game["id"])
    payload = context.model_dump_json()
    assert context.script.culprit_character_id is not None
    assert any(
        character.private_background in payload for character in script.characters
    )
    assert any(item.id == clue.id for item in context.script.clues)
    acquired = next(item for item in context.clue_progress if item.clue_id == clue.id)
    assert acquired.acquired_by_game_character_ids == [ai_character.id]
    assert context.game_flow.current_phase == "intro"
    assert any(
        message.content.startswith("PUBLIC_SENTINEL")
        for message in context.public_state.recent_messages
    )
    assert any(
        message.content.startswith("SYSTEM_SENTINEL")
        for message in context.public_state.recent_messages
    )
    assert "PRIVATE_SENTINEL" not in payload
    assert "THOUGHT_SENTINEL" not in payload
    assert "MEMORY_SENTINEL" not in payload
    assert "current_emotion" not in payload
    assert "intent" not in payload


def test_director_context_limits_public_history_to_recent_50(
    client, db_session: Session
) -> None:
    game = _start_game(client, db_session)
    character = _game_characters(db_session, game["id"])[0]
    db_session.add_all(
        [
            Message(
                game_session_id=game["id"],
                sender_game_character_id=character.id,
                channel_type="public",
                content=f"bounded-message-{index}",
            )
            for index in range(51)
        ]
    )
    db_session.commit()

    context = build_director_context(db_session, game["id"])
    messages = context.public_state.recent_messages
    assert len(messages) == 50
    assert all(message.content != "bounded-message-0" for message in messages)
    assert messages[-1].content == "bounded-message-50"


def test_director_recommendation_schema_rejects_unknown_commands_and_bad_refs() -> None:
    base = {
        "pace": "on_track",
        "narrative_risk": "low",
        "recommended_action": "no_action",
        "reason": "保持观察。",
    }
    assert DirectorRecommendation.model_validate(base).recommended_action == (
        DirectorAction.no_action
    )
    with pytest.raises(ValidationError):
        DirectorRecommendation.model_validate({**base, "command": "delete_game"})
    with pytest.raises(ValidationError):
        DirectorRecommendation.model_validate(
            {**base, "recommended_action": "request_ai_speaker"}
        )
    with pytest.raises(ValidationError):
        DirectorRecommendation.model_validate(
            {
                **base,
                "recommended_action": "request_ai_speaker",
                "target_game_character_id": 1,
                "clue_id": 2,
            }
        )


def test_director_workflow_client_sends_blocking_context_and_parses_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.agents.director_workflow_client import DirectorWorkflowClient

    request_data = {}

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {
                "data": {
                    "status": "succeeded",
                    "outputs": {
                        "recommendation": {
                            "pace": "on_track",
                            "narrative_risk": "low",
                            "recommended_action": "no_action",
                            "reason": "当前节奏正常。",
                        }
                    },
                }
            }

    def fake_post(url, **kwargs):
        request_data["url"] = url
        request_data.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr("app.agents.director_workflow_client.httpx.post", fake_post)
    client = DirectorWorkflowClient("https://dify.example/v1", "director-secret")
    result = client.run('{"game_id":9}', "game-9-director")

    assert result["recommended_action"] == "no_action"
    assert request_data["url"] == "https://dify.example/v1/workflows/run"
    assert request_data["json"] == {
        "inputs": {"director_context": '{"game_id":9}'},
        "response_mode": "blocking",
        "user": "game-9-director",
    }
    assert request_data["headers"]["Authorization"] == "Bearer director-secret"


def test_director_workflow_client_rejects_malformed_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.agents.director_workflow_client import DirectorWorkflowClient

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"data": {"status": "succeeded", "outputs": {"answer": "{}"}}}

    monkeypatch.setattr(
        "app.agents.director_workflow_client.httpx.post",
        lambda *_args, **_kwargs: FakeResponse(),
    )
    client = DirectorWorkflowClient("https://dify.example/v1", "key")
    with pytest.raises(DirectorWorkflowResponseError):
        client.run("{}", "game-1-director")


def test_director_agent_rejects_unstructured_or_extra_fields() -> None:
    class FakeWorkflowClient:
        @staticmethod
        def run(_context, user_id):
            assert user_id == "game-1-director"
            return {
                "pace": "on_track",
                "narrative_risk": "low",
                "recommended_action": "no_action",
                "reason": "no-op",
                "command": "delete_game",
            }

    with pytest.raises(DirectorOutputValidationError):
        DirectorAgent(FakeWorkflowClient()).analyze(
            SimpleNamespace(game_id=1, model_dump_json=lambda: "{}")
        )


def _configure_director(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "dify_api_url", "https://dify.example/v1")
    monkeypatch.setattr(settings, "dify_director_api_key", "test-director-key")


def test_director_analyze_persists_validated_output_without_returning_context(
    client, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.agents.director_agent import get_director_agent

    game = _start_game(client, db_session)
    fake_agent = FakeDirectorAgent(_recommendation(DirectorAction.no_action))
    _configure_director(monkeypatch)
    client.app.dependency_overrides[get_director_agent] = lambda: fake_agent

    response = client.post(f"/api/games/{game['id']}/director/analyze")
    assert response.status_code == 200
    assert response.json()["status"] == "pending"
    assert response.json()["recommended_action"] == "no_action"
    assert "culprit_character_id" not in response.text
    assert "private_background" not in response.text
    assert fake_agent.context.script.culprit_character_id is not None
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(DirectorRecommendationRecord)
            .where(DirectorRecommendationRecord.game_session_id == game["id"])
        )
        == 1
    )


def test_director_analyze_rejects_invalid_reference_without_saving(
    client, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.agents.director_agent import get_director_agent

    game = _start_game(client, db_session)
    other_script = Script(title="Other script", status="ready")
    db_session.add(other_script)
    db_session.flush()
    foreign_clue = Clue(
        script_id=other_script.id,
        name="Foreign clue",
        description="Not part of this game.",
        act="act_1",
        location="Other place",
    )
    db_session.add(foreign_clue)
    db_session.commit()
    fake_agent = FakeDirectorAgent(
        _recommendation(DirectorAction.suggest_clue_hint, clue_id=foreign_clue.id)
    )
    _configure_director(monkeypatch)
    client.app.dependency_overrides[get_director_agent] = lambda: fake_agent

    response = client.post(f"/api/games/{game['id']}/director/analyze")
    assert response.status_code == 502
    assert "clue must belong" in response.json()["detail"]
    assert (
        db_session.scalar(
            select(func.count()).select_from(DirectorRecommendationRecord)
        )
        == 0
    )


def test_director_failure_does_not_change_game_state_or_persist_output(
    client, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.agents.director_agent import get_director_agent

    game = _start_game(client, db_session)
    fake_agent = FakeDirectorAgent(error=DirectorWorkflowError("upstream failed"))
    _configure_director(monkeypatch)
    client.app.dependency_overrides[get_director_agent] = lambda: fake_agent

    response = client.post(f"/api/games/{game['id']}/director/analyze")
    assert response.status_code == 502
    assert db_session.get(GameSession, game["id"]).current_phase == "intro"
    assert (
        db_session.scalar(
            select(func.count()).select_from(DirectorRecommendationRecord)
        )
        == 0
    )


def test_malformed_dify_recommendation_is_not_persisted(
    client, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.agents.director_agent import get_director_agent

    class MalformedWorkflowClient:
        @staticmethod
        def run(_context, user_id):
            assert user_id.startswith("game-")
            return {
                "pace": "on_track",
                "narrative_risk": "low",
                "recommended_action": "no_action",
                "reason": "正常。",
                "command": "change_killer",
            }

    game = _start_game(client, db_session)
    _configure_director(monkeypatch)
    client.app.dependency_overrides[get_director_agent] = lambda: DirectorAgent(
        MalformedWorkflowClient()
    )
    response = client.post(f"/api/games/{game['id']}/director/analyze")

    assert response.status_code == 502
    assert (
        db_session.scalar(
            select(func.count()).select_from(DirectorRecommendationRecord)
        )
        == 0
    )


def test_analysis_requires_director_key_without_calling_character_workflow(
    client, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import settings

    game = _start_game(client, db_session)
    monkeypatch.setattr(settings, "dify_api_url", "https://dify.example/v1")
    monkeypatch.setattr(settings, "dify_director_api_key", "")
    response = client.post(f"/api/games/{game['id']}/director/analyze")
    assert response.status_code == 503
    assert "DIFY_DIRECTOR_API_KEY" in response.json()["detail"]
    assert (
        db_session.scalar(
            select(func.count()).select_from(DirectorRecommendationRecord)
        )
        == 0
    )


def test_director_status_never_exposes_key_and_is_development_only(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.api import director as director_api

    _configure_director(monkeypatch)
    status = client.get("/api/director/status")
    assert status.status_code == 200
    assert status.json() == {"configured": True}
    assert "test-director-key" not in status.text

    monkeypatch.setattr(director_api.settings, "app_env", "production")
    hidden = client.get("/api/director/status")
    assert hidden.status_code == 404


def test_apply_no_action_and_advisories_never_change_public_history_or_vote(
    client, db_session: Session
) -> None:
    from app.agents.character_agent import get_character_agent

    game = _start_game(client, db_session)
    clue = db_session.scalars(
        select(Clue).where(Clue.script_id == game["script_id"])
    ).first()
    before_messages = db_session.scalar(
        select(func.count())
        .select_from(Message)
        .where(Message.game_session_id == game["id"])
    )
    no_action = _save_recommendation(db_session, game["id"], DirectorAction.no_action)
    suggestion = _save_recommendation(
        db_session,
        game["id"],
        DirectorAction.suggest_clue_hint,
        clue_id=clue.id,
    )
    fake_character_agent = FakeCharacterAgent()
    client.app.dependency_overrides[get_character_agent] = lambda: fake_character_agent

    applied = client.post(
        f"/api/games/{game['id']}/director/recommendations/{no_action.id}/apply"
    )
    advisory = client.post(
        f"/api/games/{game['id']}/director/recommendations/{suggestion.id}/apply"
    )
    assert applied.status_code == 200
    assert applied.json()["status"] == "applied"
    assert advisory.status_code == 200
    assert advisory.json()["status"] == "advisory"
    assert "clue" in advisory.json()["reason"].lower()
    assert fake_character_agent.calls == []
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(Message)
            .where(Message.game_session_id == game["id"])
        )
        == before_messages
    )
    assert get_vote_result(db_session, game["id"]).votes_cast == 0


@pytest.mark.parametrize("phase", ["investigation_1", "discussion_1"])
def test_apply_request_ai_speaker_generates_one_public_message_without_chain(
    client, db_session: Session, phase: str
) -> None:
    from app.agents.character_agent import get_character_agent

    game = _start_game(client, db_session)
    _set_phase(db_session, game["id"], phase)
    ai_character = next(
        character
        for character in _game_characters(db_session, game["id"])
        if character.controller_type == "ai"
    )
    record = _save_recommendation(
        db_session,
        game["id"],
        DirectorAction.request_ai_speaker,
        target_game_character_id=ai_character.id,
    )
    fake_agent = FakeCharacterAgent()
    client.app.dependency_overrides[get_character_agent] = lambda: fake_agent

    response = client.post(
        f"/api/games/{game['id']}/director/recommendations/{record.id}/apply"
    )
    assert response.status_code == 200
    assert response.json()["status"] == "applied"
    assert response.json()["public_message"]["channel_type"] == "public"
    assert len(fake_agent.calls) == 1
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(Message)
            .where(
                Message.game_session_id == game["id"],
                Message.channel_type == "public",
            )
        )
        == 1
    )
    duplicate = client.post(
        f"/api/games/{game['id']}/director/recommendations/{record.id}/apply"
    )
    assert duplicate.status_code == 409
    assert len(fake_agent.calls) == 1
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(Message)
            .where(
                Message.game_session_id == game["id"],
                Message.channel_type == "public",
            )
        )
        == 1
    )


def test_apply_rejects_human_speaker_and_too_early_phase_advance(
    client, db_session: Session
) -> None:
    from app.agents.character_agent import get_character_agent

    game = _start_game(client, db_session)
    characters = _game_characters(db_session, game["id"])
    human = next(
        character for character in characters if character.controller_type == "human"
    )
    ai_character = next(
        character for character in characters if character.controller_type == "ai"
    )
    human_speaker = _save_recommendation(
        db_session,
        game["id"],
        DirectorAction.request_ai_speaker,
        target_game_character_id=human.id,
    )
    wrong_phase_speaker = _save_recommendation(
        db_session,
        game["id"],
        DirectorAction.request_ai_speaker,
        target_game_character_id=ai_character.id,
    )
    phase_advance = _save_recommendation(
        db_session, game["id"], DirectorAction.recommend_phase_advance
    )
    fake_agent = FakeCharacterAgent()
    client.app.dependency_overrides[get_character_agent] = lambda: fake_agent

    rejected_speaker = client.post(
        f"/api/games/{game['id']}/director/recommendations/{human_speaker.id}/apply"
    )
    _set_phase(db_session, game["id"], "vote")
    rejected_phase_speaker = client.post(
        f"/api/games/{game['id']}/director/recommendations/{wrong_phase_speaker.id}/apply"
    )
    _set_phase(db_session, game["id"], "intro")
    rejected_phase = client.post(
        f"/api/games/{game['id']}/director/recommendations/{phase_advance.id}/apply"
    )
    assert rejected_speaker.json()["status"] == "rejected"
    assert rejected_phase_speaker.json()["status"] == "rejected"
    assert rejected_phase.json()["status"] == "rejected"
    assert db_session.get(GameSession, game["id"]).current_phase == "intro"
    assert fake_agent.calls == []


@pytest.mark.parametrize("phase", ["vote", "ending"])
def test_director_speaker_is_rejected_when_public_speech_is_not_allowed(
    client, db_session: Session, phase: str
) -> None:
    from app.agents.character_agent import get_character_agent

    game = _start_game(client, db_session)
    _set_phase(db_session, game["id"], phase)
    ai_character = next(
        character
        for character in _game_characters(db_session, game["id"])
        if character.controller_type == "ai"
    )
    recommendation = _save_recommendation(
        db_session,
        game["id"],
        DirectorAction.request_ai_speaker,
        target_game_character_id=ai_character.id,
    )
    fake_agent = FakeCharacterAgent()
    client.app.dependency_overrides[get_character_agent] = lambda: fake_agent

    response = client.post(
        f"/api/games/{game['id']}/director/recommendations/{recommendation.id}/apply"
    )

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert fake_agent.calls == []
    assert db_session.get(DirectorRecommendationRecord, recommendation.id).status == (
        "rejected"
    )


@pytest.mark.parametrize("status", ["applying", "applied", "rejected", "advisory"])
def test_director_apply_rejects_non_pending_recommendations_without_side_effects(
    client, db_session: Session, status: str
) -> None:
    from app.agents.character_agent import get_character_agent

    game = _start_game(client, db_session)
    _set_phase(db_session, game["id"], "discussion_1")
    ai_character = next(
        character
        for character in _game_characters(db_session, game["id"])
        if character.controller_type == "ai"
    )
    recommendation = _save_recommendation(
        db_session,
        game["id"],
        DirectorAction.request_ai_speaker,
        target_game_character_id=ai_character.id,
    )
    recommendation.status = status
    db_session.commit()
    fake_agent = FakeCharacterAgent()
    client.app.dependency_overrides[get_character_agent] = lambda: fake_agent

    response = client.post(
        f"/api/games/{game['id']}/director/recommendations/{recommendation.id}/apply"
    )

    assert response.status_code == 409
    assert status in response.json()["detail"]
    assert fake_agent.calls == []
    assert db_session.get(DirectorRecommendationRecord, recommendation.id).status == (
        status
    )
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(Message)
            .where(
                Message.game_session_id == game["id"],
                Message.channel_type == "public",
            )
        )
        == 0
    )


def test_apply_phase_advance_passes_flow_manager_when_time_is_satisfied(
    client, db_session: Session
) -> None:
    from app.agents.character_agent import get_character_agent

    game = _start_game(client, db_session)
    past = datetime.now(timezone.utc) - timedelta(seconds=11)
    _set_phase(db_session, game["id"], "discussion_1", past)
    record = _save_recommendation(
        db_session, game["id"], DirectorAction.recommend_phase_advance
    )
    client.app.dependency_overrides[get_character_agent] = FakeCharacterAgent

    response = client.post(
        f"/api/games/{game['id']}/director/recommendations/{record.id}/apply"
    )
    assert response.status_code == 200
    assert response.json()["status"] == "applied"
    assert response.json()["flow_state"]["current_phase"] == "act_2"
    advanced_game = db_session.get(GameSession, game["id"])
    assert advanced_game.current_phase == "act_2"
    assert advanced_game.phase_started_at.replace(tzinfo=timezone.utc) > past
    duplicate = client.post(
        f"/api/games/{game['id']}/director/recommendations/{record.id}/apply"
    )
    assert duplicate.status_code == 409
    assert db_session.get(GameSession, game["id"]).current_phase == "act_2"
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(Message)
            .where(
                Message.game_session_id == game["id"],
                Message.channel_type == "system",
                Message.content == "进入第二幕。",
            )
        )
        == 1
    )
