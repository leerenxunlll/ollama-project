"""Tests for the single human-to-AI private chat flow."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.character_agent import CharacterReply, get_character_agent
from app.agents.dify_client import DifyProviderError
from app.game.state_machine import PHASE_SEQUENCE
from app.models import Clue, GameCharacter, GameCharacterClue, Message
from app.schemas.context import CharacterContext
from app.services.seed import seed_development_data


class FakeCharacterAgent:
    """Capture the safe context sent to an agent without making a network call."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.context = None
        self.query = None
        self.user_id = None

    def respond(
        self, context: CharacterContext, query: str, user_id: str
    ) -> CharacterReply:
        self.context = context
        self.query = query
        self.user_id = user_id
        if self.error is not None:
            raise self.error
        return CharacterReply(speech="那晚我一直在旧仓库。")


def _create_game(client, db_session: Session) -> dict:
    script = seed_development_data(db_session)
    response = client.post("/api/games", json={"script_id": script.id})
    assert response.status_code == 201
    return response.json()


def _start_game(client, game: dict) -> dict:
    human_id = game["game_characters"][0]["id"]
    response = client.post(
        f"/api/games/{game['id']}/select-character",
        json={"game_character_id": human_id},
    )
    assert response.status_code == 200
    response = client.post(f"/api/games/{game['id']}/start")
    assert response.status_code == 200
    return response.json()


def _install_agent(client, agent: FakeCharacterAgent) -> None:
    client.app.dependency_overrides[get_character_agent] = lambda: agent


def test_ai_status_reports_configuration_without_exposing_key(
    client, monkeypatch
) -> None:
    from app.api import ai as ai_api

    monkeypatch.setattr(ai_api.settings, "dify_api_url", "")
    monkeypatch.setattr(ai_api.settings, "dify_character_api_key", "")
    unconfigured = client.get("/api/ai/status")
    assert unconfigured.status_code == 200
    assert unconfigured.json() == {"configured": False}

    monkeypatch.setattr(ai_api.settings, "dify_api_url", "https://dify.example/v1")
    monkeypatch.setattr(ai_api.settings, "dify_character_api_key", "private-test-key")
    configured = client.get("/api/ai/status")
    assert configured.status_code == 200
    assert configured.json() == {"configured": True}
    assert "private-test-key" not in configured.text


def test_application_starts_without_dify_configuration(client) -> None:
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/ai/status").json() == {"configured": False}


def test_waiting_ready_and_finished_games_reject_ai_chat(
    client, db_session: Session
) -> None:
    game = _create_game(client, db_session)
    payload = {
        "target_game_character_id": game["game_characters"][1]["id"],
        "content": "你昨晚在哪里？",
    }

    waiting = client.post(f"/api/games/{game['id']}/ai-chat", json=payload)
    assert waiting.status_code == 409

    human_id = game["game_characters"][0]["id"]
    ready = client.post(
        f"/api/games/{game['id']}/select-character",
        json={"game_character_id": human_id},
    )
    assert ready.status_code == 200
    ready_response = client.post(f"/api/games/{game['id']}/ai-chat", json=payload)
    assert ready_response.status_code == 409

    client.post(f"/api/games/{game['id']}/start")
    for _ in range(len(PHASE_SEQUENCE) - 1):
        response = client.post(f"/api/games/{game['id']}/advance-phase")
        assert response.status_code == 200
    finished = client.post(f"/api/games/{game['id']}/ai-chat", json=payload)
    assert finished.status_code == 409
    assert db_session.scalar(select(func.count(Message.id))) == len(PHASE_SEQUENCE)


def test_ai_chat_rejects_foreign_character_human_self_and_non_ai_target(
    client, db_session: Session
) -> None:
    game = _create_game(client, db_session)
    _start_game(client, game)
    other_game = _create_game(client, db_session)
    foreign_target = other_game["game_characters"][1]["id"]

    response = client.post(
        f"/api/games/{game['id']}/ai-chat",
        json={"target_game_character_id": foreign_target, "content": "问题"},
    )
    assert response.status_code == 404

    human_id = game["game_characters"][0]["id"]
    response = client.post(
        f"/api/games/{game['id']}/ai-chat",
        json={"target_game_character_id": human_id, "content": "问题"},
    )
    assert response.status_code == 409

    non_ai = db_session.get(GameCharacter, game["game_characters"][1]["id"])
    assert non_ai is not None
    non_ai.controller_type = None
    db_session.commit()
    response = client.post(
        f"/api/games/{game['id']}/ai-chat",
        json={"target_game_character_id": non_ai.id, "content": "问题"},
    )
    assert response.status_code == 409


def test_ai_chat_passes_only_target_context_and_persists_private_pair(
    client, db_session: Session
) -> None:
    game = _create_game(client, db_session)
    _start_game(client, game)
    game_id = game["id"]
    human_id = game["game_characters"][0]["id"]
    target_id = game["game_characters"][1]["id"]
    other_ai_id = game["game_characters"][2]["id"]

    target = db_session.get(GameCharacter, target_id)
    other_ai = db_session.get(GameCharacter, other_ai_id)
    assert target is not None and other_ai is not None
    target.character.private_background = "TARGET_PRIVATE_SENTINEL"
    target.character.personal_goal = "TARGET_GOAL_SENTINEL"
    other_ai.character.private_background = "OTHER_PRIVATE_SENTINEL"
    other_ai.character.personal_goal = "OTHER_GOAL_SENTINEL"
    clues = db_session.scalars(
        select(Clue)
        .where(Clue.script_id == target.character.script_id)
        .order_by(Clue.id)
    ).all()
    assert len(clues) >= 2
    db_session.add_all(
        [
            GameCharacterClue(
                game_character_id=target_id, clue_id=clues[0].id, source="test"
            ),
            GameCharacterClue(
                game_character_id=other_ai_id, clue_id=clues[1].id, source="test"
            ),
            Message(
                game_session_id=game_id,
                sender_game_character_id=human_id,
                channel_type="private",
                receiver_game_character_id=target_id,
                content="VISIBLE_PRIVATE_SENTINEL",
            ),
            Message(
                game_session_id=game_id,
                sender_game_character_id=other_ai_id,
                channel_type="private",
                receiver_game_character_id=game["game_characters"][3]["id"],
                content="OTHER_PRIVATE_MESSAGE_SENTINEL",
            ),
        ]
    )
    db_session.commit()

    agent = FakeCharacterAgent()
    _install_agent(client, agent)
    response = client.post(
        f"/api/games/{game_id}/ai-chat",
        json={"target_game_character_id": target_id, "content": "你昨晚在哪里？"},
    )

    assert response.status_code == 200
    assert isinstance(agent.context, CharacterContext)
    context_json = agent.context.model_dump_json()
    assert agent.context.character.private_background == "TARGET_PRIVATE_SENTINEL"
    assert agent.context.character.personal_goal == "TARGET_GOAL_SENTINEL"
    assert "OTHER_PRIVATE_SENTINEL" not in context_json
    assert "OTHER_GOAL_SENTINEL" not in context_json
    assert "OTHER_PRIVATE_MESSAGE_SENTINEL" not in context_json
    assert "random_seed" not in context_json
    assert "is_killer" not in context_json
    assert [clue.clue_id for clue in agent.context.known_clues] == [clues[0].id]
    assert agent.query == "你昨晚在哪里？"
    assert agent.user_id == f"game-{game_id}-character-{target_id}"

    result = response.json()
    human_message = result["human_message"]
    ai_message = result["ai_message"]
    assert human_message["sender_game_character_id"] == human_id
    assert human_message["receiver_game_character_id"] == target_id
    assert human_message["channel_type"] == "private"
    assert human_message["content"] == "你昨晚在哪里？"
    assert ai_message["sender_game_character_id"] == target_id
    assert ai_message["receiver_game_character_id"] == human_id
    assert ai_message["channel_type"] == "private"
    assert ai_message["content"] == "那晚我一直在旧仓库。"
    assert human_message["id"] != ai_message["id"]
    state = client.get(f"/api/games/{game_id}/state").json()
    assert state["status"] == "in_progress"
    assert state["current_phase"] == "intro"


def test_dify_failure_leaves_no_half_round_messages(
    client, db_session: Session
) -> None:
    game = _create_game(client, db_session)
    _start_game(client, game)
    agent = FakeCharacterAgent(DifyProviderError("provider error"))
    _install_agent(client, agent)
    before = db_session.scalar(select(func.count(Message.id)))

    response = client.post(
        f"/api/games/{game['id']}/ai-chat",
        json={
            "target_game_character_id": game["game_characters"][1]["id"],
            "content": "你昨晚在哪里？",
        },
    )

    assert response.status_code == 502
    assert db_session.scalar(select(func.count(Message.id))) == before


def test_unconfigured_dify_returns_service_unavailable_without_writing(
    client, db_session: Session, monkeypatch
) -> None:
    from app.agents import character_agent

    monkeypatch.setattr(character_agent.settings, "dify_api_url", "")
    monkeypatch.setattr(character_agent.settings, "dify_character_api_key", "")
    game = _create_game(client, db_session)
    _start_game(client, game)
    before = db_session.scalar(select(func.count(Message.id)))

    response = client.post(
        f"/api/games/{game['id']}/ai-chat",
        json={
            "target_game_character_id": game["game_characters"][1]["id"],
            "content": "你昨晚在哪里？",
        },
    )

    assert response.status_code == 503
    assert "DIFY_CHARACTER_API_KEY" in response.json()["detail"]
    assert db_session.scalar(select(func.count(Message.id))) == before
