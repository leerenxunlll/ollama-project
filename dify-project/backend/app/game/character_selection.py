"""Deterministic rules for assigning the human-controlled character."""

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import GameCharacter, GameSession


def select_human_character(
    db: Session, game: GameSession, game_character_id: int
) -> GameCharacter:
    """Assign one character to the player and lock all four assignments."""
    if game.status != "waiting_for_character_selection":
        raise ValueError("Character selection is already locked")

    selected_character = next(
        (
            character
            for character in game.game_characters
            if character.id == game_character_id
        ),
        None,
    )
    if selected_character is None:
        raise LookupError("Character not found in this game")

    selection_claim = db.execute(
        update(GameSession)
        .where(
            GameSession.id == game.id,
            GameSession.status == "waiting_for_character_selection",
        )
        .values(status="ready")
    )
    if selection_claim.rowcount != 1:
        raise ValueError("Character selection is already locked")

    for character in game.game_characters:
        character.controller_type = (
            "human" if character.id == selected_character.id else "ai"
        )
    game.status = "ready"
    return selected_character
