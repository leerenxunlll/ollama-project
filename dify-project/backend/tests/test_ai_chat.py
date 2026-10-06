"""Tests for the single human-to-AI private chat flow."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agents.character_agent import (
    CharacterAgent,
    CharacterReply,
    get_character_agent,
)
from app.agents.dify_client import DifyProviderError
from app.game.state_machine import PHASE_SEQUENCE
from app.models import (
    CharacterMemory,
    CharacterThought,
    Clue,
    GameCharacter,
    GameCharacterClue,
    Message,
)
from app.schemas.ai import CharacterEmotion, CharacterIntent, MemoryUpdate
from app.schemas.context import CharacterContext
from app.schemas.interaction import CharacterInteraction
from app.services.seed import seed_development_data


class FakeCharacterAgent:
    """Capture the safe context sent to an agent without making a network call."""

    def __init__(
        self,
        error: Exception | None = None,
        reply: CharacterReply | None = None,
    ) -> None:
        self.error = error
        self.reply = reply or CharacterReply(
            speech="那晚我一直在旧仓库。",
            inner_os="他在确认我是否知道旧仓库发生的事。",
            emotion=CharacterEmotion.NERVOUS,
            intent=CharacterIntent.DEFLECT,
            memory_updates=[MemoryUpdate(content="玩家追问了旧仓库。", importance=3)],
        )
        self.context = None
        self.interaction = None
        self.query = None
        self.user_id = None

    def respond(
        self,
        context: CharacterContext,
        interaction: CharacterInteraction,
        user_id: str,
    ) -> CharacterReply:
        self.context = context
        self.interaction = interaction
        self.query = interaction.current_message
        self.user_id = user_id
        if self.error is not None:
            raise self.error
        return self.reply


class FakeDifyClient:
    """Return a controlled raw Answer without making an external request."""

    def __init__(self, answer: str) -> None:
        self.answer = answer

    def chat(
        self,
        character_context: str,
        interaction_context: str,
        query: str,
        user_id: str,
    ) -> str:
        return self.answer


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


def test_application_starts_without_dify_configuration(client, monkeypatch) -> None:
    from app.api import ai as ai_api

    monkeypatch.setattr(ai_api.settings, "dify_api_url", "")
    monkeypatch.setattr(ai_api.settings, "dify_character_api_key", "")
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
    assert agent.interaction.mode == "private_reply"
    assert agent.interaction.channel == "private"
    assert agent.interaction.source_game_character_id == human_id
    assert agent.interaction.source_character_name == "林澈"
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
    assert "inner_os" not in response.text
    assert "memory_updates" not in response.text
    assert human_message["id"] != ai_message["id"]
    thought = db_session.scalar(select(CharacterThought))
    assert thought is not None
    assert thought.game_session_id == game_id
    assert thought.game_character_id == target_id
    assert thought.ai_message_id == ai_message["id"]
    assert thought.inner_os == "他在确认我是否知道旧仓库发生的事。"
    assert thought.intent == "deflect"
    assert target.current_emotion == "nervous"
    assert target.current_goal is None
    memories = db_session.scalars(select(CharacterMemory)).all()
    assert len(memories) == 1
    assert memories[0].game_character_id == target_id
    assert memories[0].game_session_id == game_id
    assert memories[0].source_message_id == ai_message["id"]
    debug = client.get(f"/api/games/{game_id}/characters/{target_id}/thoughts")
    assert debug.status_code == 200
    debug_state = debug.json()
    assert debug_state["current_emotion"] == "nervous"
    assert debug_state["latest_thought"]["inner_os"] == (
        "他在确认我是否知道旧仓库发生的事。"
    )
    assert debug_state["latest_thought"]["intent"] == "deflect"
    assert [item["content"] for item in debug_state["memories"]] == [
        "玩家追问了旧仓库。"
    ]
    normal_game = client.get(f"/api/games/{game_id}")
    assert "inner_os" not in normal_game.text
    assert "memories" not in normal_game.text
    public_message = client.post(
        f"/api/games/{game_id}/messages",
        json={
            "sender_game_character_id": human_id,
            "channel_type": "public",
            "content": "我有一条公开发言。",
        },
    )
    assert public_message.status_code == 201
    assert "inner_os" not in public_message.text
    state = client.get(f"/api/games/{game_id}/state").json()
    assert state["status"] == "in_progress"
    assert state["current_phase"] == "intro"


def test_duplicate_memories_are_skipped_after_whitespace_normalization(
    client, db_session: Session
) -> None:
    game = _create_game(client, db_session)
    _start_game(client, game)
    human_id = game["game_characters"][0]["id"]
    target_id = game["game_characters"][1]["id"]
    source_message = Message(
        game_session_id=game["id"],
        sender_game_character_id=human_id,
        channel_type="private",
        receiver_game_character_id=target_id,
        content="历史消息",
    )
    db_session.add(source_message)
    db_session.flush()
    db_session.add(
        CharacterMemory(
            game_session_id=game["id"],
            game_character_id=target_id,
            content="玩家提到 旧仓库",
            importance=3,
            source_message_id=source_message.id,
        )
    )
    db_session.commit()
    reply = CharacterReply(
        speech="我记下了。",
        inner_os="这件事已经听过。",
        emotion=CharacterEmotion.CALM,
        intent=CharacterIntent.COOPERATE,
        memory_updates=[
            MemoryUpdate(content="玩家提到 \n 旧仓库", importance=4),
            MemoryUpdate(content="玩家说了新的重要信息。", importance=2),
        ],
    )
    _install_agent(client, FakeCharacterAgent(reply=reply))

    response = client.post(
        f"/api/games/{game['id']}/ai-chat",
        json={"target_game_character_id": target_id, "content": "你记得吗？"},
    )

    assert response.status_code == 200
    memories = db_session.scalars(
        select(CharacterMemory).where(CharacterMemory.game_character_id == target_id)
    ).all()
    assert len(memories) == 2
    assert sum(memory.content == "玩家提到 旧仓库" for memory in memories) == 1


def test_database_failure_rolls_back_the_entire_character_turn(
    client, db_session: Session, monkeypatch
) -> None:
    game = _create_game(client, db_session)
    _start_game(client, game)
    target_id = game["game_characters"][1]["id"]
    _install_agent(client, FakeCharacterAgent())
    before_messages = db_session.scalar(select(func.count(Message.id)))

    def fail_commit() -> None:
        raise RuntimeError("injected commit failure")

    monkeypatch.setattr(db_session, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="injected commit failure"):
        client.post(
            f"/api/games/{game['id']}/ai-chat",
            json={"target_game_character_id": target_id, "content": "问题"},
        )

    assert db_session.scalar(select(func.count(Message.id))) == before_messages
    assert db_session.scalar(select(func.count(CharacterThought.id))) == 0
    assert db_session.scalar(select(func.count(CharacterMemory.id))) == 0
    target = db_session.get(GameCharacter, target_id)
    assert target is not None and target.current_emotion is None


def test_character_thought_debug_endpoint_is_development_only(
    client, db_session: Session, monkeypatch
) -> None:
    from app.api import games as games_api

    game = _create_game(client, db_session)
    ai_character_id = game["game_characters"][1]["id"]
    monkeypatch.setattr(games_api.settings, "app_env", "production")

    response = client.get(
        f"/api/games/{game['id']}/characters/{ai_character_id}/thoughts"
    )

    assert response.status_code == 404


def test_thought_database_constraints_require_matching_session_and_sender(
    client, db_session: Session
) -> None:
    first_game = _create_game(client, db_session)
    second_game = _create_game(client, db_session)
    first_character_id = first_game["game_characters"][1]["id"]
    second_character_id = second_game["game_characters"][1]["id"]
    foreign_message = Message(
        game_session_id=second_game["id"],
        sender_game_character_id=second_character_id,
        channel_type="private",
        receiver_game_character_id=second_game["game_characters"][0]["id"],
        content="别局的 AI 回复",
    )
    db_session.add(foreign_message)
    db_session.flush()
    db_session.add(
        CharacterThought(
            game_session_id=first_game["id"],
            game_character_id=first_character_id,
            ai_message_id=foreign_message.id,
            inner_os="不可跨局关联",
            emotion="calm",
            intent="observe",
        )
    )

    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


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


def test_malformed_dify_output_leaves_no_turn_data(client, db_session: Session) -> None:
    game = _create_game(client, db_session)
    _start_game(client, game)
    before_messages = db_session.scalar(select(func.count(Message.id)))
    client.app.dependency_overrides[get_character_agent] = lambda: CharacterAgent(
        FakeDifyClient('{"speech":"partial answer"}')
    )

    response = client.post(
        f"/api/games/{game['id']}/ai-chat",
        json={
            "target_game_character_id": game["game_characters"][1]["id"],
            "content": "你昨晚在哪里？",
        },
    )

    assert response.status_code == 502
    assert response.json()["detail"] == (
        "Dify returned invalid structured character output"
    )
    assert db_session.scalar(select(func.count(Message.id))) == before_messages
    assert db_session.scalar(select(func.count(CharacterThought.id))) == 0
    assert db_session.scalar(select(func.count(CharacterMemory.id))) == 0


def test_valid_mock_dify_output_completes_the_full_character_turn(
    client, db_session: Session
) -> None:
    game = _create_game(client, db_session)
    _start_game(client, game)
    target_id = game["game_characters"][1]["id"]
    structured_answer = (
        '{"speech":"我记得这件事。",'
        '"inner_os":"这条信息可能很重要。",'
        '"emotion":"confident",'
        '"intent":"cooperate",'
        '"memory_updates":[{"content":"玩家带着蓝色手帕。",'
        '"importance":4}]}'
    )
    client.app.dependency_overrides[get_character_agent] = lambda: CharacterAgent(
        FakeDifyClient(structured_answer)
    )

    response = client.post(
        f"/api/games/{game['id']}/ai-chat",
        json={
            "target_game_character_id": target_id,
            "content": "请记住我带了蓝色手帕。",
        },
    )

    assert response.status_code == 200
    assert response.json()["ai_message"]["content"] == "我记得这件事。"
    assert "inner_os" not in response.text
    assert db_session.scalar(select(func.count(CharacterThought.id))) == 1
    stored_memory = db_session.scalar(select(CharacterMemory))
    assert stored_memory is not None
    assert stored_memory.content == "玩家带着蓝色手帕。"
    character = db_session.get(GameCharacter, target_id)
    assert character is not None and character.current_emotion == "confident"


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
