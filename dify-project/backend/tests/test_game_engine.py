"""Focused tests for deterministic game phases, investigation, and messages."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.game.state_machine import PHASE_SEQUENCE
from app.models import (
    Clue,
    GameCharacter,
    GameCharacterClue,
    GameSession,
    Message,
    Script,
)
from app.services.seed import seed_development_data


def _create_game(client, db_session: Session) -> dict:
    script = seed_development_data(db_session)
    response = client.post("/api/games", json={"script_id": script.id})
    assert response.status_code == 201
    return response.json()


def _select_human(client, game: dict, character_index: int = 0) -> dict:
    response = client.post(
        f"/api/games/{game['id']}/select-character",
        json={"game_character_id": game["game_characters"][character_index]["id"]},
    )
    assert response.status_code == 200
    return response.json()


def _start_game(client, db_session: Session) -> tuple[dict, dict]:
    game = _create_game(client, db_session)
    _select_human(client, game)
    response = client.post(f"/api/games/{game['id']}/start")
    assert response.status_code == 200
    return game, response.json()


def _advance_to(client, db_session: Session, game_id: int, target_phase: str) -> dict:
    state = client.get(f"/api/games/{game_id}/state").json()
    while state["current_phase"] != target_phase:
        response = _advance_one_phase(client, db_session, game_id)
        assert response.status_code == 200
        state = response.json()
    return state


def _advance_one_phase(client, db_session: Session, game_id: int):
    """Fast-forward test time while exercising the real one-step API."""
    game = db_session.get(GameSession, game_id)
    game.phase_started_at = datetime.now(timezone.utc) - timedelta(seconds=30)
    db_session.commit()
    if game.current_phase == "vote":
        characters = db_session.scalars(
            select(GameCharacter)
            .where(GameCharacter.game_session_id == game_id)
            .order_by(GameCharacter.id)
        ).all()
        for index, character in enumerate(characters):
            vote = client.post(
                f"/api/games/{game_id}/votes",
                json={
                    "voter_game_character_id": character.id,
                    "target_game_character_id": characters[
                        (index + 1) % len(characters)
                    ].id,
                },
            )
            assert vote.status_code == 201
    return client.post(f"/api/games/{game_id}/advance-phase")


def test_start_requires_ready_game_and_sets_initial_state(
    client, db_session: Session
) -> None:
    waiting_game = _create_game(client, db_session)
    rejected = client.post(f"/api/games/{waiting_game['id']}/start")
    assert rejected.status_code == 409

    ready_game = _select_human(client, waiting_game)
    started = client.post(f"/api/games/{ready_game['id']}/start")

    assert started.status_code == 200
    state = started.json()
    assert state["status"] == "in_progress"
    assert state["current_phase"] == "intro"
    assert state["started_at"] is not None
    assert state["next_phase"] == "act_1"
    assert state["can_investigate"] is False
    assert "random_seed" not in state
    assert "is_killer" not in str(state)
    assert "private_background" not in str(state)

    duplicate = client.post(f"/api/games/{ready_game['id']}/start")
    assert duplicate.status_code == 409

    system_messages = db_session.scalars(
        select(Message).where(
            Message.game_session_id == ready_game["id"],
            Message.channel_type == "system",
        )
    ).all()
    assert [message.content for message in system_messages] == ["游戏开始。"]
    assert system_messages[0].sender_game_character_id is None


def test_start_rejects_invalid_controller_counts(client, db_session: Session) -> None:
    game = _create_game(client, db_session)
    ready = _select_human(client, game)
    runtime_characters = db_session.scalars(
        select(GameCharacter)
        .where(GameCharacter.game_session_id == ready["id"])
        .order_by(GameCharacter.id)
    ).all()
    runtime_characters[1].controller_type = "human"
    db_session.commit()

    response = client.post(f"/api/games/{ready['id']}/start")

    assert response.status_code == 409
    assert db_session.get(GameSession, ready["id"]).status == "ready"


def test_phases_advance_in_order_and_ending_finishes_game(
    client, db_session: Session
) -> None:
    game, state = _start_game(client, db_session)
    visited_phases = [state["current_phase"]]

    while state["next_phase"] is not None:
        response = _advance_one_phase(client, db_session, game["id"])
        assert response.status_code == 200
        state = response.json()
        visited_phases.append(state["current_phase"])

    assert tuple(visited_phases) == PHASE_SEQUENCE
    assert state["status"] == "finished"
    assert state["current_phase"] == "ending"
    assert state["ended_at"] is not None
    assert state["next_phase"] is None
    assert state["can_investigate"] is False

    after_finish = client.post(f"/api/games/{game['id']}/advance-phase")
    assert after_finish.status_code == 409
    ending_messages = db_session.scalars(
        select(Message).where(
            Message.game_session_id == game["id"],
            Message.channel_type == "system",
        )
    ).all()
    assert ending_messages[-1].content == "游戏结束。"


def test_advance_requires_started_game_and_ignores_requested_target(
    client, db_session: Session
) -> None:
    waiting_game = _create_game(client, db_session)
    rejected = client.post(f"/api/games/{waiting_game['id']}/advance-phase")
    assert rejected.status_code == 409

    game, _ = _start_game(client, db_session)

    response = _advance_one_phase(client, db_session, game["id"])

    assert response.status_code == 200
    assert response.json()["current_phase"] == "act_1"
    assert response.json()["current_phase"] != "vote"


def test_investigation_is_rejected_outside_investigation_phase(
    client, db_session: Session
) -> None:
    game, state = _start_game(client, db_session)
    character_id = game["game_characters"][0]["id"]

    locations = client.get(f"/api/games/{game['id']}/investigation/locations")
    search = client.post(
        f"/api/games/{game['id']}/investigation/search",
        json={"game_character_id": character_id, "location": "旧仓库办公室"},
    )

    assert state["current_phase"] == "intro"
    assert locations.status_code == 409
    assert search.status_code == 409


def test_act_one_search_grants_clue_and_context_only_to_searching_character(
    client, db_session: Session
) -> None:
    game = _create_game(client, db_session)
    _select_human(client, game)
    _start = client.post(f"/api/games/{game['id']}/start")
    assert _start.status_code == 200
    _advance_to(client, db_session, game["id"], "investigation_1")
    character_id = game["game_characters"][0]["id"]
    other_character_id = game["game_characters"][1]["id"]

    locations = client.get(f"/api/games/{game['id']}/investigation/locations")
    assert locations.status_code == 200
    assert locations.json()["locations"] == ["仓库侧门", "旧仓库办公室"]

    before_context = client.get(
        f"/api/games/{game['id']}/characters/{character_id}/context"
    ).json()
    assert before_context["known_clues"] == []

    result = client.post(
        f"/api/games/{game['id']}/investigation/search",
        json={"game_character_id": character_id, "location": "旧仓库办公室"},
    )

    assert result.status_code == 200
    assert result.json()["found"] is True
    assert result.json()["clue"]["name"] == "潮湿的登记页"
    discovery = db_session.scalar(
        select(GameCharacterClue).where(
            GameCharacterClue.game_character_id == character_id
        )
    )
    assert discovery is not None
    assert discovery.source == "investigation"

    after_context = client.get(
        f"/api/games/{game['id']}/characters/{character_id}/context"
    ).json()
    other_context = client.get(
        f"/api/games/{game['id']}/characters/{other_character_id}/context"
    ).json()
    assert [item["name"] for item in after_context["known_clues"]] == ["潮湿的登记页"]
    assert other_context["known_clues"] == []

    duplicate = client.post(
        f"/api/games/{game['id']}/investigation/search",
        json={"game_character_id": character_id, "location": "旧仓库办公室"},
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["found"] is False
    assert (
        db_session.scalar(
            select(func.count(GameCharacterClue.id)).where(
                GameCharacterClue.game_character_id == character_id
            )
        )
        == 1
    )


def test_search_uses_highest_importance_then_lowest_id(
    client, db_session: Session
) -> None:
    game, _ = _start_game(client, db_session)
    script = db_session.get(Script, game["script_id"])
    db_session.add_all(
        [
            Clue(
                script_id=script.id,
                name="低优先级",
                description="低优先级线索。",
                act="act_1",
                location="钟楼",
                importance=1,
            ),
            Clue(
                script_id=script.id,
                name="高优先级较晚记录",
                description="高优先级线索。",
                act="act_1",
                location="钟楼",
                importance=3,
            ),
            Clue(
                script_id=script.id,
                name="高优先级较早记录",
                description="同优先级且 ID 更小。",
                act="act_1",
                location="钟楼",
                importance=3,
            ),
        ]
    )
    db_session.commit()
    _advance_to(client, db_session, game["id"], "investigation_1")

    response = client.post(
        f"/api/games/{game['id']}/investigation/search",
        json={
            "game_character_id": game["game_characters"][0]["id"],
            "location": "钟楼",
        },
    )

    assert response.status_code == 200
    assert response.json()["clue"]["name"] == "高优先级较晚记录"


def test_act_two_search_only_grants_act_two_clues(client, db_session: Session) -> None:
    game, _ = _start_game(client, db_session)
    script = db_session.get(Script, game["script_id"])
    db_session.add(
        Clue(
            script_id=script.id,
            name="Act 2 线索",
            description="第二幕线索。",
            act="act_2",
            location="旧船坞",
            importance=1,
        )
    )
    db_session.commit()
    _advance_to(client, db_session, game["id"], "investigation_2")

    response = client.post(
        f"/api/games/{game['id']}/investigation/search",
        json={
            "game_character_id": game["game_characters"][0]["id"],
            "location": "旧仓库办公室",
        },
    )
    act_two_result = client.post(
        f"/api/games/{game['id']}/investigation/search",
        json={
            "game_character_id": game["game_characters"][0]["id"],
            "location": "旧船坞",
        },
    )

    assert response.status_code == 200
    assert response.json()["found"] is False
    assert act_two_result.json()["clue"]["name"] == "Act 2 线索"


def test_search_rejects_foreign_game_character_and_ignores_foreign_script_clue(
    client, db_session: Session
) -> None:
    game, _ = _start_game(client, db_session)
    other_game = _create_game(client, db_session)
    _advance_to(client, db_session, game["id"], "investigation_1")
    other_script = Script(
        title="另一份测试剧本",
        status="ready",
    )
    db_session.add(other_script)
    db_session.flush()
    db_session.add(
        Clue(
            script_id=other_script.id,
            name="不属于本局剧本",
            description="不能在本局取得。",
            act="act_1",
            location="封存档案室",
            importance=9,
        )
    )
    db_session.commit()

    foreign_character = client.post(
        f"/api/games/{game['id']}/investigation/search",
        json={
            "game_character_id": other_game["game_characters"][0]["id"],
            "location": "封存档案室",
        },
    )
    foreign_clue = client.post(
        f"/api/games/{game['id']}/investigation/search",
        json={
            "game_character_id": game["game_characters"][0]["id"],
            "location": "封存档案室",
        },
    )

    assert foreign_character.status_code == 404
    assert foreign_clue.status_code == 200
    assert foreign_clue.json()["found"] is False
    assert db_session.scalar(select(func.count(GameCharacterClue.id))) == 0


def test_player_message_api_enforces_public_private_and_session_boundaries(
    client, db_session: Session
) -> None:
    first_game = _create_game(client, db_session)
    other_game = _create_game(client, db_session)
    selected = client.post(
        f"/api/games/{first_game['id']}/select-character",
        json={"game_character_id": first_game["game_characters"][0]["id"]},
    )
    assert selected.status_code == 200
    started = client.post(f"/api/games/{first_game['id']}/start")
    assert started.status_code == 200
    sender_id = first_game["game_characters"][0]["id"]
    receiver_id = first_game["game_characters"][1]["id"]
    foreign_id = other_game["game_characters"][0]["id"]

    public = client.post(
        f"/api/games/{first_game['id']}/messages",
        json={
            "sender_game_character_id": sender_id,
            "channel_type": "public",
            "content": "公开讨论。",
        },
    )
    private = client.post(
        f"/api/games/{first_game['id']}/messages",
        json={
            "sender_game_character_id": sender_id,
            "channel_type": "private",
            "receiver_game_character_id": receiver_id,
            "content": "私下交流。",
        },
    )
    public_with_receiver = client.post(
        f"/api/games/{first_game['id']}/messages",
        json={
            "sender_game_character_id": sender_id,
            "channel_type": "public",
            "receiver_game_character_id": receiver_id,
            "content": "不应有接收方。",
        },
    )
    private_without_receiver = client.post(
        f"/api/games/{first_game['id']}/messages",
        json={
            "sender_game_character_id": sender_id,
            "channel_type": "private",
            "content": "缺少接收方。",
        },
    )
    system_forgery = client.post(
        f"/api/games/{first_game['id']}/messages",
        json={
            "sender_game_character_id": sender_id,
            "channel_type": "system",
            "content": "伪造系统消息。",
        },
    )
    self_message = client.post(
        f"/api/games/{first_game['id']}/messages",
        json={
            "sender_game_character_id": sender_id,
            "channel_type": "private",
            "receiver_game_character_id": sender_id,
            "content": "不能发给自己。",
        },
    )
    foreign_sender = client.post(
        f"/api/games/{first_game['id']}/messages",
        json={
            "sender_game_character_id": foreign_id,
            "channel_type": "public",
            "content": "跨局发送。",
        },
    )
    foreign_receiver = client.post(
        f"/api/games/{first_game['id']}/messages",
        json={
            "sender_game_character_id": sender_id,
            "channel_type": "private",
            "receiver_game_character_id": foreign_id,
            "content": "跨局接收。",
        },
    )

    assert public.status_code == 201
    assert public.json()["receiver_game_character_id"] is None
    assert private.status_code == 201
    assert private.json()["sender_game_character_id"] == sender_id
    assert private.json()["receiver_game_character_id"] == receiver_id
    assert public_with_receiver.status_code == 422
    assert private_without_receiver.status_code == 422
    assert system_forgery.status_code == 422
    assert self_message.status_code == 409
    assert foreign_sender.status_code == 404
    assert foreign_receiver.status_code == 404
    assert (
        db_session.scalar(
            select(func.count(Message.id)).where(
                Message.game_session_id == first_game["id"],
                Message.channel_type.in_(("public", "private")),
            )
        )
        == 2
    )


def test_public_message_obeys_phase_gate_while_private_message_rules_stay_unchanged(
    client, db_session: Session
) -> None:
    game, _state = _start_game(client, db_session)
    game_record = db_session.get(GameSession, game["id"])
    game_record.current_phase = "vote"
    db_session.commit()
    sender_id = game["game_characters"][0]["id"]
    receiver_id = game["game_characters"][1]["id"]

    public = client.post(
        f"/api/games/{game['id']}/messages",
        json={
            "sender_game_character_id": sender_id,
            "channel_type": "public",
            "content": "投票阶段不能再发公开消息。",
        },
    )
    private = client.post(
        f"/api/games/{game['id']}/messages",
        json={
            "sender_game_character_id": sender_id,
            "channel_type": "private",
            "receiver_game_character_id": receiver_id,
            "content": "现有私聊规则保持不变。",
        },
    )

    assert public.status_code == 409
    assert private.status_code == 201
    assert db_session.scalar(select(func.count(Message.id))) == 2
