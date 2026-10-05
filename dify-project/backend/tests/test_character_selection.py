"""Tests that player selection exposes only authorized character details."""

from sqlalchemy.orm import Session

from app.services.seed import seed_development_data


def _create_game(client, db_session: Session) -> dict:
    script = seed_development_data(db_session)
    response = client.post("/api/games", json={"script_id": script.id})
    assert response.status_code == 201
    return response.json()


def test_selectable_character_cards_contain_public_fields_only(
    client, db_session: Session
) -> None:
    game = _create_game(client, db_session)
    games = client.get("/api/games")

    response = client.get(f"/api/games/{game['id']}/characters/selectable")

    assert games.status_code == 200
    assert any(item["id"] == game["id"] for item in games.json())
    assert response.status_code == 200
    cards = response.json()
    assert len(cards) == 4
    assert set(cards[0]) == {
        "game_character_id",
        "character_id",
        "name",
        "age",
        "identity",
        "public_background",
        "personality",
        "speaking_style",
    }
    assert "private_background" not in str(cards)
    assert "personal_goal" not in str(cards)
    assert "is_killer" not in str(cards)


def test_character_choice_assigns_one_human_and_locks_selection(
    client, db_session: Session
) -> None:
    game = _create_game(client, db_session)
    other_game = _create_game(client, db_session)
    foreign_character_id = other_game["game_characters"][0]["id"]

    foreign_choice = client.post(
        f"/api/games/{game['id']}/select-character",
        json={"game_character_id": foreign_character_id},
    )
    assert foreign_choice.status_code == 404

    choice = client.post(
        f"/api/games/{game['id']}/select-character",
        json={"game_character_id": game["game_characters"][1]["id"]},
    )
    assert choice.status_code == 200
    assert choice.json()["status"] == "ready"
    controllers = [item["controller_type"] for item in choice.json()["game_characters"]]
    assert controllers.count("human") == 1
    assert controllers.count("ai") == 3

    repeated_choice = client.post(
        f"/api/games/{game['id']}/select-character",
        json={"game_character_id": game["game_characters"][0]["id"]},
    )
    assert repeated_choice.status_code == 409
    selectable_after_choice = client.get(
        f"/api/games/{game['id']}/characters/selectable"
    )
    assert selectable_after_choice.status_code == 409


def test_my_character_returns_only_the_human_players_private_card(
    client, db_session: Session
) -> None:
    game = _create_game(client, db_session)
    unavailable = client.get(f"/api/games/{game['id']}/me/character")
    assert unavailable.status_code == 409

    selected_character_id = game["game_characters"][0]["id"]
    client.post(
        f"/api/games/{game['id']}/select-character",
        json={"game_character_id": selected_character_id},
    )
    response = client.get(f"/api/games/{game['id']}/me/character")

    assert response.status_code == 200
    card = response.json()
    assert card["game_character_id"] == selected_character_id
    assert card["private_background"] == "曾经调换过一份档案的存放位置。"
    assert card["personal_goal"] == "找回一份遗失记录。"
    assert "is_killer" not in card
    assert "其他角色" not in str(card)
    assert "收到一封没有署名的信" not in str(card)
    assert "保存着一张拍摄时间不明的照片" not in str(card)
    assert "弄清信件是谁送来的。" not in str(card)
    assert "避免旧仓库的事牵连家人。" not in str(card)
    assert "确认照片的拍摄时间。" not in str(card)


def test_killer_flag_is_not_automatically_included_in_own_role_card(
    client, db_session: Session
) -> None:
    game = _create_game(client, db_session)
    killer_character_id = game["game_characters"][2]["id"]
    choice = client.post(
        f"/api/games/{game['id']}/select-character",
        json={"game_character_id": killer_character_id},
    )
    assert choice.status_code == 200

    response = client.get(f"/api/games/{game['id']}/me/character")

    assert response.status_code == 200
    assert response.json()["game_character_id"] == killer_character_id
    assert "is_killer" not in response.json()
