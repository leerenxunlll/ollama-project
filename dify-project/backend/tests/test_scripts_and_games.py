"""Tests for script templates and game session creation."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Character, Clue, GameCharacter, GameSession
from app.services.seed import seed_development_data


def test_create_read_and_list_script(client) -> None:
    created = client.post(
        "/api/scripts",
        json={
            "title": "测试剧本",
            "summary": "用于 API 验证",
            "theme": "悬疑",
        },
    )

    assert created.status_code == 201
    assert created.json()["status"] == "draft"

    script_id = created.json()["id"]
    detail = client.get(f"/api/scripts/{script_id}")
    listing = client.get("/api/scripts")

    assert detail.status_code == 200
    assert detail.json()["title"] == "测试剧本"
    assert any(item["id"] == script_id for item in listing.json())


def test_development_seed_is_idempotent_and_has_templates(db_session: Session) -> None:
    script = seed_development_data(db_session)
    repeated = seed_development_data(db_session)

    characters = db_session.scalars(
        select(Character).where(Character.script_id == script.id)
    ).all()
    clues = db_session.scalars(select(Clue).where(Clue.script_id == script.id)).all()

    assert repeated.id == script.id
    assert len(characters) == 4
    assert len(clues) == 3
    assert len(script.characters) == 4
    assert len(script.clues) == 3


def test_game_uses_four_instances_without_changing_templates(
    client,
    db_session: Session,
) -> None:
    script = seed_development_data(db_session)
    template_state = [
        (character.id, character.private_background, character.is_killer)
        for character in db_session.scalars(
            select(Character)
            .where(Character.script_id == script.id)
            .order_by(Character.id)
        ).all()
    ]

    created = client.post("/api/games", json={"script_id": script.id})

    assert created.status_code == 201
    game_data = created.json()
    assert game_data["script_id"] == script.id
    assert game_data["status"] == "waiting_for_character_selection"
    assert len(game_data["game_characters"]) == 4
    assert [item["controller_type"] for item in game_data["game_characters"]] == [
        None,
        None,
        None,
        None,
    ]

    selected = client.post(
        f"/api/games/{game_data['id']}/select-character",
        json={"game_character_id": game_data["game_characters"][2]["id"]},
    )
    assert selected.status_code == 200
    assert selected.json()["status"] == "ready"
    assert [item["controller_type"] for item in selected.json()["game_characters"]] == [
        "ai",
        "ai",
        "human",
        "ai",
    ]

    read_back = client.get(f"/api/games/{game_data['id']}")
    assert read_back.status_code == 200
    assert len(read_back.json()["game_characters"]) == 4
    assert "random_seed" not in read_back.json()
    assert "is_killer" not in str(read_back.json())
    assert "private_background" not in str(read_back.json())

    second_game = client.post("/api/games", json={"script_id": script.id})
    assert second_game.status_code == 201
    assert second_game.json()["id"] != game_data["id"]
    assert second_game.json()["status"] == "waiting_for_character_selection"

    db_session.expire_all()
    session = db_session.get(GameSession, game_data["id"])
    assert session is not None
    runtime_characters = db_session.scalars(
        select(GameCharacter).where(GameCharacter.game_session_id == session.id)
    ).all()
    updated_templates = [
        (character.id, character.private_background, character.is_killer)
        for character in db_session.scalars(
            select(Character)
            .where(Character.script_id == script.id)
            .order_by(Character.id)
        ).all()
    ]
    assert len(runtime_characters) == 4
    assert updated_templates == template_state


def test_draft_script_cannot_start_a_game(client) -> None:
    script = client.post("/api/scripts", json={"title": "尚未完成"})

    response = client.post("/api/games", json={"script_id": script.json()["id"]})

    assert response.status_code == 409
