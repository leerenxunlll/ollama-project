"""Focused tests for bounded public turns and proactive AI steps."""

from collections.abc import Sequence

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.character_agent import CharacterReply
from app.agents.dify_client import DifyRequestError
from app.models import (
    CharacterMemory,
    CharacterThought,
    GameCharacter,
    GameSession,
    Message,
)
from app.schemas.ai import CharacterEmotion, CharacterIntent, MemoryUpdate
from app.schemas.context import CharacterContext
from app.schemas.interaction import CharacterInteraction
from app.services.seed import seed_development_data


class FakeCharacterAgent:
    """Return controlled replies while capturing each fresh authorized context."""

    def __init__(self, outcomes: Sequence[CharacterReply | Exception]) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[tuple[CharacterContext, CharacterInteraction, str]] = []

    def respond(
        self,
        context: CharacterContext,
        interaction: CharacterInteraction,
        user_id: str,
    ) -> CharacterReply:
        self.calls.append((context, interaction, user_id))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _reply(
    speech: str,
    memory: str = "角色记住了这轮公开发言。",
) -> CharacterReply:
    return CharacterReply(
        speech=speech,
        inner_os="我需要仔细回应。",
        emotion=CharacterEmotion.SUSPICIOUS,
        intent=CharacterIntent.OBSERVE,
        memory_updates=[MemoryUpdate(content=memory, importance=3)],
    )


def _start_game(client, db_session: Session) -> tuple[dict, dict[str, int]]:
    script = seed_development_data(db_session)
    created = client.post("/api/games", json={"script_id": script.id})
    assert created.status_code == 201
    game = created.json()
    character_ids = {
        item["character"]["name"]: item["id"] for item in game["game_characters"]
    }
    selected = client.post(
        f"/api/games/{game['id']}/select-character",
        json={"game_character_id": character_ids["林澈"]},
    )
    assert selected.status_code == 200
    started = client.post(f"/api/games/{game['id']}/start")
    assert started.status_code == 200
    return game, character_ids


def _install_agent(client, agent: FakeCharacterAgent) -> None:
    from app.agents.character_agent import get_character_agent

    client.app.dependency_overrides[get_character_agent] = lambda: agent


def _set_phase(db_session: Session, game_id: int, phase: str) -> None:
    game = db_session.get(GameSession, game_id)
    game.current_phase = phase
    db_session.commit()


@pytest.mark.parametrize("mentioned_name", ["许雁", "周序"])
def test_public_turn_single_mention_selects_named_character(
    client, db_session: Session, mentioned_name: str
) -> None:
    game, characters = _start_game(client, db_session)
    agent = FakeCharacterAgent([_reply("我听到了。")])
    _install_agent(client, agent)

    response = client.post(
        f"/api/games/{game['id']}/public-turn",
        json={"content": f"{mentioned_name}，请回答。"},
    )

    assert response.status_code == 200
    assert (
        response.json()["ai_responses"][0]["sender_game_character_id"]
        == (characters[mentioned_name])
    )
    assert agent.calls[0][2] == (
        f"game-{game['id']}-character-{characters[mentioned_name]}"
    )


def test_public_turn_selects_explicit_names_in_order_and_returns_only_messages(
    client, db_session: Session
) -> None:
    game, characters = _start_game(client, db_session)
    agent = FakeCharacterAgent(
        [_reply("我想听听叶青的看法。"), _reply("我当时在候船室。")]
    )
    _install_agent(client, agent)

    response = client.post(
        f"/api/games/{game['id']}/public-turn",
        json={"content": "周序和许雁，你们怎么看？"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert [
        message["sender_game_character_id"] for message in body["ai_responses"]
    ] == [characters["周序"], characters["许雁"]]
    assert body["human_message"]["channel_type"] == "public"
    assert all(message["channel_type"] == "public" for message in body["ai_responses"])
    assert "inner_os" not in response.text
    assert "memory_updates" not in response.text
    assert [call[1].mode for call in agent.calls] == ["public_reply", "public_reply"]
    assert agent.calls[0][1].current_message == "周序和许雁，你们怎么看？"
    assert agent.calls[0][1].source_character_name == "林澈"


def test_second_responder_context_refreshes_and_keeps_other_private_state_hidden(
    client, db_session: Session
) -> None:
    game, characters = _start_game(client, db_session)
    alice_id = characters["许雁"]
    human_id = characters["林澈"]
    private_message = Message(
        game_session_id=game["id"],
        sender_game_character_id=alice_id,
        channel_type="private",
        receiver_game_character_id=human_id,
        content="PRIVATE_SENTINEL",
    )
    db_session.add(private_message)
    db_session.flush()
    db_session.add_all(
        [
            CharacterThought(
                game_session_id=game["id"],
                game_character_id=alice_id,
                ai_message_id=private_message.id,
                inner_os="THOUGHT_SENTINEL",
                emotion="calm",
                intent="observe",
            ),
            CharacterMemory(
                game_session_id=game["id"],
                game_character_id=alice_id,
                content="MEMORY_SENTINEL",
                importance=3,
                source_message_id=private_message.id,
            ),
        ]
    )
    db_session.commit()

    agent = FakeCharacterAgent(
        [_reply("周序可能知道仓库的事。", "ALICE_OWN_MEMORY"), _reply("我没有去过。")]
    )
    _install_agent(client, agent)
    response = client.post(
        f"/api/games/{game['id']}/public-turn",
        json={"content": "许雁，你怎么看？"},
    )

    assert response.status_code == 200
    first_context, first_interaction, _ = agent.calls[0]
    second_context, second_interaction, _ = agent.calls[1]
    assert agent.calls[0][2] == f"game-{game['id']}-character-{alice_id}"
    assert agent.calls[1][2] == f"game-{game['id']}-character-{characters['周序']}"
    assert first_interaction.source_character_name == "林澈"
    assert any(
        item.content == "许雁，你怎么看？" for item in first_context.public_messages
    )
    assert any(
        item.content == "PRIVATE_SENTINEL" for item in first_context.private_messages
    )
    assert any(item.content == "MEMORY_SENTINEL" for item in first_context.memories)
    assert second_interaction.source_character_name == "许雁"
    assert second_interaction.current_message == "周序可能知道仓库的事。"
    assert any(
        item.content == "周序可能知道仓库的事。"
        for item in second_context.public_messages
    )
    assert any(
        item.content == "许雁，你怎么看？" for item in second_context.public_messages
    )
    assert all(
        item.content != "PRIVATE_SENTINEL" for item in second_context.private_messages
    )
    assert all(item.content != "MEMORY_SENTINEL" for item in second_context.memories)
    assert "THOUGHT_SENTINEL" not in second_context.model_dump_json()


def test_public_turn_stops_after_two_even_when_second_mentions_third_ai(
    client, db_session: Session
) -> None:
    game, characters = _start_game(client, db_session)
    agent = FakeCharacterAgent(
        [
            _reply("周序昨晚去了仓库，叶青也许知道。"),
            _reply("叶青应该回答这个问题。"),
        ]
    )
    _install_agent(client, agent)

    response = client.post(
        f"/api/games/{game['id']}/public-turn",
        json={"content": "你们怎么看？"},
    )

    assert response.status_code == 200
    assert [call[2] for call in agent.calls] == [
        f"game-{game['id']}-character-{characters['许雁']}",
        f"game-{game['id']}-character-{characters['周序']}",
    ]
    assert len(response.json()["ai_responses"]) == 2
    assert len(agent.calls) == 2


def test_public_turn_does_not_chain_without_ai_mention_but_keeps_explicit_second(
    client, db_session: Session
) -> None:
    game, characters = _start_game(client, db_session)
    agent = FakeCharacterAgent([_reply("我昨晚在渡船上。")])
    _install_agent(client, agent)
    response = client.post(
        f"/api/games/{game['id']}/public-turn",
        json={"content": "你怎么看？"},
    )
    assert response.status_code == 200
    assert len(response.json()["ai_responses"]) == 1
    assert len(agent.calls) == 1

    second_game, second_characters = _start_game(client, db_session)
    explicitly_selected = FakeCharacterAgent(
        [_reply("我没有更多补充。"), _reply("我昨晚在书房。")]
    )
    _install_agent(client, explicitly_selected)
    second_response = client.post(
        f"/api/games/{second_game['id']}/public-turn",
        json={"content": "许雁和周序，请分别回答。"},
    )
    assert second_response.status_code == 200
    assert [
        item["sender_game_character_id"]
        for item in second_response.json()["ai_responses"]
    ] == [second_characters["许雁"], second_characters["周序"]]


def test_public_turn_persists_each_reply_thought_memory_and_emotion(
    client, db_session: Session
) -> None:
    game, characters = _start_game(client, db_session)
    agent = FakeCharacterAgent(
        [
            _reply("周序也应该说明一下。", "许雁记住了争论。"),
            _reply("我会说明。", "周序记住了回应。"),
        ]
    )
    _install_agent(client, agent)

    response = client.post(
        f"/api/games/{game['id']}/public-turn",
        json={"content": "许雁，你怎么看？"},
    )

    assert response.status_code == 200
    ai_messages = {
        message.sender_game_character_id: message
        for message in db_session.scalars(
            select(Message).where(
                Message.game_session_id == game["id"],
                Message.channel_type == "public",
                Message.sender_game_character_id.in_(
                    [characters["许雁"], characters["周序"]]
                ),
            )
        ).all()
    }
    assert {
        speaker_id: message.content for speaker_id, message in ai_messages.items()
    } == {
        characters["许雁"]: "周序也应该说明一下。",
        characters["周序"]: "我会说明。",
    }

    thoughts = db_session.scalars(
        select(CharacterThought).where(CharacterThought.game_session_id == game["id"])
    ).all()
    assert {
        thought.game_character_id: thought.ai_message_id for thought in thoughts
    } == {speaker_id: message.id for speaker_id, message in ai_messages.items()}

    assert (
        db_session.scalar(
            select(func.count(CharacterThought.id)).where(
                CharacterThought.game_session_id == game["id"]
            )
        )
        == 2
    )
    memories = db_session.scalars(
        select(CharacterMemory).where(CharacterMemory.game_session_id == game["id"])
    ).all()
    assert {memory.game_character_id: memory.content for memory in memories} == {
        characters["许雁"]: "许雁记住了争论。",
        characters["周序"]: "周序记住了回应。",
    }
    assert {
        memory.game_character_id: memory.source_message_id for memory in memories
    } == {speaker_id: message.id for speaker_id, message in ai_messages.items()}
    assert (
        db_session.get(GameCharacter, characters["许雁"]).current_emotion
        == "suspicious"
    )
    assert (
        db_session.get(GameCharacter, characters["周序"]).current_emotion
        == "suspicious"
    )


def test_first_ai_failure_keeps_human_message_and_returns_safe_partial_result(
    client, db_session: Session
) -> None:
    game, characters = _start_game(client, db_session)
    agent = FakeCharacterAgent([DifyRequestError("SECRET_CONTEXT_AND_KEY")])
    _install_agent(client, agent)

    response = client.post(
        f"/api/games/{game['id']}/public-turn",
        json={"content": "许雁，请回答。"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "partial"
    assert body["ai_responses"] == []
    assert body["failures"] == [
        {"game_character_id": characters["许雁"], "error_type": "DifyRequestError"}
    ]
    assert "SECRET_CONTEXT_AND_KEY" not in response.text
    messages = db_session.scalars(
        select(Message).where(
            Message.game_session_id == game["id"], Message.channel_type == "public"
        )
    ).all()
    assert [message.content for message in messages] == ["许雁，请回答。"]


def test_second_ai_failure_preserves_human_and_first_ai_reply(
    client, db_session: Session
) -> None:
    game, characters = _start_game(client, db_session)
    agent = FakeCharacterAgent(
        [_reply("周序，你来说明。"), DifyRequestError("provider detail")]
    )
    _install_agent(client, agent)

    response = client.post(
        f"/api/games/{game['id']}/public-turn",
        json={"content": "许雁和周序，请回答。"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "partial"
    assert [message["content"] for message in body["ai_responses"]] == [
        "周序，你来说明。"
    ]
    assert body["failures"] == [
        {"game_character_id": characters["周序"], "error_type": "DifyRequestError"}
    ]
    messages = db_session.scalars(
        select(Message)
        .where(Message.game_session_id == game["id"], Message.channel_type == "public")
        .order_by(Message.id)
    ).all()
    assert [message.content for message in messages] == [
        "许雁和周序，请回答。",
        "周序，你来说明。",
    ]
    assert (
        db_session.scalar(
            select(func.count(CharacterThought.id)).where(
                CharacterThought.game_session_id == game["id"]
            )
        )
        == 1
    )


def test_second_ai_persistence_failure_returns_partial_and_keeps_first_reply(
    client, db_session: Session, monkeypatch
) -> None:
    game, characters = _start_game(client, db_session)
    agent = FakeCharacterAgent([_reply("周序，你来说明。"), _reply("我会解释。")])
    _install_agent(client, agent)
    original_commit = db_session.commit
    commit_count = 0

    def fail_second_ai_commit():
        nonlocal commit_count
        commit_count += 1
        if commit_count == 3:
            raise RuntimeError("PRIVATE_DATABASE_DETAIL")
        return original_commit()

    monkeypatch.setattr(db_session, "commit", fail_second_ai_commit)

    response = client.post(
        f"/api/games/{game['id']}/public-turn",
        json={"content": "许雁和周序，请回答。"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "partial"
    response_speaker_ids = [
        message["sender_game_character_id"] for message in body["ai_responses"]
    ]
    assert response_speaker_ids == [characters["许雁"]]
    assert body["failures"] == [
        {"game_character_id": characters["周序"], "error_type": "RuntimeError"}
    ]
    assert "PRIVATE_DATABASE_DETAIL" not in response.text
    messages = db_session.scalars(
        select(Message)
        .where(Message.game_session_id == game["id"], Message.channel_type == "public")
        .order_by(Message.id)
    ).all()
    assert [message.content for message in messages] == [
        "许雁和周序，请回答。",
        "周序，你来说明。",
    ]


def test_proactive_step_saves_exactly_one_public_ai_message_and_rotates(
    client, db_session: Session
) -> None:
    game, characters = _start_game(client, db_session)
    first_agent = FakeCharacterAgent([_reply("周序，我觉得你也看见了那盏灯。")])
    _install_agent(client, first_agent)

    first = client.post(f"/api/games/{game['id']}/ai-step")

    assert first.status_code == 200
    assert first.json()["ai_message"]["sender_game_character_id"] == characters["许雁"]
    assert len(first_agent.calls) == 1
    assert first_agent.calls[0][1].mode == "proactive_public"
    assert first_agent.calls[0][1].source_game_character_id is None
    assert first_agent.calls[0][1].current_message.startswith("Make one natural")
    assert (
        len(
            db_session.scalars(
                select(Message).where(
                    Message.game_session_id == game["id"],
                    Message.channel_type == "public",
                )
            ).all()
        )
        == 1
    )

    second_agent = FakeCharacterAgent([_reply("码头上只剩一盏灯。")])
    _install_agent(client, second_agent)
    second = client.post(f"/api/games/{game['id']}/ai-step")

    assert second.status_code == 200
    assert second.json()["ai_message"]["sender_game_character_id"] == characters["周序"]
    assert len(second_agent.calls) == 1


@pytest.mark.parametrize("phase", ["investigation_1", "discussion_1"])
def test_public_turn_is_allowed_in_investigation_and_discussion(
    client, db_session: Session, phase: str
) -> None:
    game, _characters = _start_game(client, db_session)
    _set_phase(db_session, game["id"], phase)
    agent = FakeCharacterAgent([_reply("我可以补充。")])
    _install_agent(client, agent)

    response = client.post(
        f"/api/games/{game['id']}/public-turn",
        json={"content": "许雁，你怎么看？"},
    )

    assert response.status_code == 200
    assert response.json()["human_message"]["channel_type"] == "public"
    assert len(agent.calls) == 1


@pytest.mark.parametrize("phase", ["vote", "ending"])
def test_public_turn_rejects_vote_and_ending_before_saving_messages(
    client, db_session: Session, phase: str
) -> None:
    game, _characters = _start_game(client, db_session)
    _set_phase(db_session, game["id"], phase)
    agent = FakeCharacterAgent([])
    _install_agent(client, agent)

    response = client.post(
        f"/api/games/{game['id']}/public-turn",
        json={"content": "现在还能讨论吗？"},
    )

    assert response.status_code == 409
    assert agent.calls == []
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(Message)
            .where(Message.game_session_id == game["id"])
        )
        == 1
    )


@pytest.mark.parametrize(
    ("phase", "allowed"),
    [
        ("intro", True),
        ("investigation_1", True),
        ("discussion_1", True),
        ("vote", False),
        ("ending", False),
    ],
)
def test_ai_step_uses_public_speech_eligibility(
    client, db_session: Session, phase: str, allowed: bool
) -> None:
    game, _characters = _start_game(client, db_session)
    _set_phase(db_session, game["id"], phase)
    agent = (
        FakeCharacterAgent([_reply("我来补充。")])
        if allowed
        else FakeCharacterAgent([])
    )
    _install_agent(client, agent)

    response = client.post(f"/api/games/{game['id']}/ai-step")

    assert response.status_code == (200 if allowed else 409)
    assert len(agent.calls) == (1 if allowed else 0)
    assert db_session.scalar(
        select(func.count())
        .select_from(Message)
        .where(
            Message.game_session_id == game["id"],
            Message.channel_type == "public",
            Message.sender_game_character_id.is_not(None),
        )
    ) == (1 if allowed else 0)


def test_public_turn_requires_active_game_and_ai_step_is_development_only(
    client, db_session: Session, monkeypatch
) -> None:
    from app.api import games as games_api

    script = seed_development_data(db_session)
    waiting = client.post("/api/games", json={"script_id": script.id}).json()
    waiting_response = client.post(
        f"/api/games/{waiting['id']}/public-turn", json={"content": "你好"}
    )
    assert waiting_response.status_code == 409

    game, _ = _start_game(client, db_session)
    monkeypatch.setattr(games_api.settings, "app_env", "production")
    hidden_step = client.post(f"/api/games/{game['id']}/ai-step")
    assert hidden_step.status_code == 404


def test_public_message_history_excludes_private_messages(
    client, db_session: Session
) -> None:
    game, characters = _start_game(client, db_session)
    db_session.add_all(
        [
            Message(
                game_session_id=game["id"],
                sender_game_character_id=characters["林澈"],
                channel_type="public",
                content="PUBLIC_HISTORY_SENTINEL",
            ),
            Message(
                game_session_id=game["id"],
                sender_game_character_id=characters["许雁"],
                channel_type="private",
                receiver_game_character_id=characters["林澈"],
                content="PRIVATE_HISTORY_SENTINEL",
            ),
        ]
    )
    db_session.commit()

    response = client.get(f"/api/games/{game['id']}/public-messages")

    assert response.status_code == 200
    assert [message["content"] for message in response.json()] == [
        "PUBLIC_HISTORY_SENTINEL"
    ]
    assert "PRIVATE_HISTORY_SENTINEL" not in response.text
