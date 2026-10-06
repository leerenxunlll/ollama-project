"""Validate one human-to-character turn and persist it after a Dify reply."""

import logging
from time import perf_counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.character_agent import CharacterAgent
from app.game.state_machine import GameRuleError
from app.models import GameCharacter, GameSession, Message
from app.schemas.ai import AIChatRequest, AIChatResponse
from app.schemas.game import MessageRead
from app.schemas.interaction import CharacterInteraction
from app.services.character_context import build_character_context
from app.services.character_response import persist_character_reply

logger = logging.getLogger(__name__)


def send_character_message(
    db: Session,
    game_id: int,
    payload: AIChatRequest,
    agent: CharacterAgent,
) -> AIChatResponse:
    """Call one eligible AI, then atomically store both messages."""
    game = db.get(GameSession, game_id)
    if game is None:
        raise LookupError("Game not found")
    if game.status != "in_progress":
        raise GameRuleError("AI chat requires an in-progress game")

    human_characters = list(
        db.scalars(
            select(GameCharacter).where(
                GameCharacter.game_session_id == game_id,
                GameCharacter.controller_type == "human",
            )
        ).all()
    )
    if len(human_characters) != 1:
        raise GameRuleError("The human character is not determined")
    human_character = human_characters[0]

    target_character = db.get(GameCharacter, payload.target_game_character_id)
    if target_character is None or target_character.game_session_id != game_id:
        raise LookupError("Target character not found in this game")
    if target_character.id == human_character.id:
        raise GameRuleError("The human character cannot be an AI chat target")
    if target_character.controller_type != "ai":
        raise GameRuleError("AI chat target must be AI-controlled")

    context = build_character_context(db, game_id, target_character.id)
    user_id = f"game-{game_id}-character-{target_character.id}"
    started_at = perf_counter()
    logger.info(
        "AI chat started game_id=%s target_game_character_id=%s",
        game_id,
        target_character.id,
    )
    interaction = CharacterInteraction(
        mode="private_reply",
        channel="private",
        source_game_character_id=human_character.id,
        source_character_name=human_character.character.name,
        current_message=payload.content,
    )
    try:
        reply = agent.respond(context, interaction, user_id)
    except Exception as error:
        logger.warning(
            "AI chat failed game_id=%s target_game_character_id=%s "
            "latency_ms=%s error_type=%s",
            game_id,
            target_character.id,
            round((perf_counter() - started_at) * 1000),
            type(error).__name__,
        )
        raise

    logger.info(
        "AI chat succeeded game_id=%s target_game_character_id=%s latency_ms=%s",
        game_id,
        target_character.id,
        round((perf_counter() - started_at) * 1000),
    )

    human_message = Message(
        game_session_id=game_id,
        sender_game_character_id=human_character.id,
        channel_type="private",
        receiver_game_character_id=target_character.id,
        content=payload.content,
    )
    ai_message = Message(
        game_session_id=game_id,
        sender_game_character_id=target_character.id,
        channel_type="private",
        receiver_game_character_id=human_character.id,
        content=reply.speech,
    )
    persist_character_reply(
        db,
        target_character,
        ai_message,
        reply,
        related_messages=(human_message,),
    )
    return AIChatResponse(
        human_message=MessageRead.model_validate(human_message),
        ai_message=MessageRead.model_validate(ai_message),
    )
