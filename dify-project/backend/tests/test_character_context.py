"""Tests that character contexts enforce information boundaries."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Clue, GameCharacter, GameCharacterClue, Message
from app.services.seed import seed_development_data


def _create_game(client, db_session: Session) -> dict:
    script = seed_development_data(db_session)
    response = client.post("/api/games", json={"script_id": script.id})
    assert response.status_code == 201
    return response.json()


def test_character_context_filters_messages_secrets_clues_and_seed(
    client, db_session: Session
) -> None:
    game_data = _create_game(client, db_session)
    game_id = game_data["id"]
    character_ids = [item["id"] for item in game_data["game_characters"]]
    other_game = _create_game(client, db_session)
    other_game_character_id = other_game["game_characters"][0]["id"]
    db_characters = db_session.scalars(
        select(GameCharacter)
        .where(GameCharacter.game_session_id == game_id)
        .order_by(GameCharacter.id)
    ).all()
    selected_character_id = character_ids[0]
    db_session.add_all(
        [
            Message(
                game_session_id=game_id,
                sender_game_character_id=character_ids[0],
                channel_type="public",
                content="公开消息由当前角色发送",
            ),
            Message(
                game_session_id=game_id,
                sender_game_character_id=character_ids[1],
                channel_type="public",
                content="另一位角色的公开消息",
            ),
            Message(
                game_session_id=game_id,
                sender_game_character_id=None,
                channel_type="system",
                content="公开系统旁白",
            ),
            Message(
                game_session_id=game_id,
                sender_game_character_id=character_ids[0],
                channel_type="private",
                receiver_game_character_id=character_ids[1],
                content="当前角色发出的私聊",
            ),
            Message(
                game_session_id=game_id,
                sender_game_character_id=character_ids[2],
                channel_type="private",
                receiver_game_character_id=character_ids[0],
                content="发给当前角色的私聊",
            ),
            Message(
                game_session_id=game_id,
                sender_game_character_id=character_ids[1],
                channel_type="private",
                receiver_game_character_id=character_ids[2],
                content="其他角色之间的私聊",
            ),
            Message(
                game_session_id=game_id,
                sender_game_character_id=other_game_character_id,
                channel_type="private",
                receiver_game_character_id=character_ids[0],
                content="跨局私聊不可见",
            ),
            Message(
                game_session_id=game_id,
                sender_game_character_id=other_game_character_id,
                channel_type="public",
                content="跨局公开消息不可见",
            ),
        ]
    )
    clue = db_session.scalar(
        select(Clue).where(Clue.script_id == db_characters[0].character.script_id)
    )
    assert clue is not None
    db_session.add(
        GameCharacterClue(
            game_character_id=selected_character_id,
            clue_id=clue.id,
            source="test grant",
        )
    )
    db_session.commit()

    response = client.get(
        f"/api/games/{game_id}/characters/{selected_character_id}/context"
    )

    assert response.status_code == 200
    context = response.json()
    assert (
        context["character"]["private_background"] == "曾经调换过一份档案的存放位置。"
    )
    assert context["character"]["personal_goal"] == "找回一份遗失记录。"
    assert {item["game_character_id"] for item in context["other_characters"]} == set(
        character_ids[1:]
    )
    assert all(
        set(item) == {"game_character_id", "name", "identity", "public_background"}
        for item in context["other_characters"]
    )

    public_contents = {item["content"] for item in context["public_messages"]}
    assert public_contents == {
        "公开消息由当前角色发送",
        "另一位角色的公开消息",
        "公开系统旁白",
    }
    private_contents = {item["content"] for item in context["private_messages"]}
    assert private_contents == {"当前角色发出的私聊", "发给当前角色的私聊"}
    assert "其他角色之间的私聊" not in str(context)
    assert "跨局私聊不可见" not in str(context)
    assert "跨局公开消息不可见" not in str(context)
    private_by_content = {item["content"]: item for item in context["private_messages"]}
    assert private_by_content["当前角色发出的私聊"]["sender_game_character_id"] == (
        selected_character_id
    )
    assert private_by_content["发给当前角色的私聊"]["receiver_game_character_id"] == (
        selected_character_id
    )

    assert [item["clue_id"] for item in context["known_clues"]] == [clue.id]
    assert len(context["known_clues"]) == 1
    assert "random_seed" not in context["game"]
    assert "is_killer" not in str(context)
    assert "private_background" not in context["other_characters"][0]
    assert "personal_goal" not in context["other_characters"][0]
    assert "random_seed" not in str(context)
    assert "曾经调换过一份档案的存放位置。" not in str(context["other_characters"])
    assert "收到一封没有署名的信" not in str(context)
    assert "知道仓库侧门在案发当晚没有上锁" not in str(context)
    assert "保存着一张拍摄时间不明的照片" not in str(context)
    assert "弄清信件是谁送来的。" not in str(context)
    assert "避免旧仓库的事牵连家人。" not in str(context)
    assert "确认照片的拍摄时间。" not in str(context)


def test_context_rejects_a_character_from_another_game(client, db_session) -> None:
    first_game = _create_game(client, db_session)
    second_game = _create_game(client, db_session)
    foreign_character_id = second_game["game_characters"][0]["id"]

    response = client.get(
        f"/api/games/{first_game['id']}/characters/{foreign_character_id}/context"
    )

    assert response.status_code == 404


def test_context_debug_route_is_development_only(
    client, db_session, monkeypatch
) -> None:
    from app.api import games as games_api

    game_data = _create_game(client, db_session)
    game_character_id = game_data["game_characters"][0]["id"]
    monkeypatch.setattr(games_api.settings, "app_env", "production")

    response = client.get(
        f"/api/games/{game_data['id']}/characters/{game_character_id}/context"
    )

    assert response.status_code == 404
