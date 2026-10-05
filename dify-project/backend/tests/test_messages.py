"""Tests that message rows can express public and private channels."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import GameCharacter, GameSession, Message
from app.services.seed import seed_development_data


def test_public_and_private_message_participants(
    client,
    db_session: Session,
) -> None:
    script = seed_development_data(db_session)
    game_response = client.post("/api/games", json={"script_id": script.id})
    game_id = game_response.json()["id"]
    game = db_session.get(GameSession, game_id)
    assert game is not None
    characters = db_session.scalars(
        select(GameCharacter)
        .where(GameCharacter.game_session_id == game_id)
        .order_by(GameCharacter.id)
    ).all()

    public_message = Message(
        game_session_id=game_id,
        sender_game_character_id=characters[0].id,
        channel_type="public",
        receiver_game_character_id=None,
        content="大家都能看到这条消息。",
    )
    private_message = Message(
        game_session_id=game_id,
        sender_game_character_id=characters[0].id,
        channel_type="private",
        receiver_game_character_id=characters[1].id,
        content="只有指定接收方能看到。",
    )
    db_session.add_all([public_message, private_message])
    db_session.commit()

    assert public_message.receiver_game_character_id is None
    assert private_message.sender_game_character_id == characters[0].id
    assert private_message.receiver_game_character_id == characters[1].id
    assert private_message.sender_game_character is characters[0]
    assert private_message.receiver_game_character is characters[1]
