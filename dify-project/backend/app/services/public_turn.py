"""Orchestrate one bounded public conversation between game characters."""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.agents.character_agent import CharacterAgent
from app.game.state_machine import GameRuleError
from app.game.turn_manager import (
    MAX_AI_RESPONSES_PER_HUMAN_TURN,
    Speaker,
    select_initial_responders,
    select_next_ai,
    select_reaction_responder,
)
from app.models import GameCharacter, GameSession, Message
from app.schemas.ai import (
    AIProactiveStepResponse,
    PublicTurnFailure,
    PublicTurnRequest,
    PublicTurnResponse,
)
from app.schemas.game import MessageRead
from app.schemas.interaction import CharacterInteraction
from app.services.character_context import build_character_context
from app.services.character_response import persist_character_reply

logger = logging.getLogger(__name__)
PROACTIVE_TRIGGER = (
    "Make one natural public contribution based on the current game context."
)


def send_public_turn(
    db: Session,
    game_id: int,
    payload: PublicTurnRequest,
    agent: CharacterAgent,
) -> PublicTurnResponse:
    """Save one human message, then run at most two sequential AI replies."""
    game = db.get(GameSession, game_id)
    if game is None:
        raise LookupError("Game not found")
    if game.status != "in_progress":
        raise GameRuleError("Public chat requires an in-progress game")

    characters = _load_game_characters(db, game_id)
    humans = [
        character for character in characters if character.controller_type == "human"
    ]
    ai_characters = [
        character for character in characters if character.controller_type == "ai"
    ]
    if len(humans) != 1:
        raise GameRuleError("The human character is not determined")
    if not ai_characters:
        raise GameRuleError("At least one AI character is required")

    human_character = humans[0]
    human_message = Message(
        game_session_id=game_id,
        sender_game_character_id=human_character.id,
        channel_type="public",
        receiver_game_character_id=None,
        content=payload.content,
    )
    db.add(human_message)
    db.commit()
    db.refresh(human_message)

    speakers = _speakers(ai_characters)
    initial = select_initial_responders(
        payload.content,
        speakers,
        _last_ai_public_speaker_id(db, game_id),
    )
    pending = list(initial[1:])
    next_speaker = initial[0] if initial else None
    trigger_message = human_message
    character_by_id = {character.id: character for character in ai_characters}
    replied_ids: set[int] = set()
    ai_responses: list[MessageRead] = []
    failures: list[PublicTurnFailure] = []

    while (
        next_speaker is not None and len(ai_responses) < MAX_AI_RESPONSES_PER_HUMAN_TURN
    ):
        responder = character_by_id[next_speaker.game_character_id]
        interaction = CharacterInteraction(
            mode="public_reply",
            channel="public",
            source_game_character_id=trigger_message.sender_game_character_id,
            source_character_name=_character_name(
                characters, trigger_message.sender_game_character_id
            ),
            current_message=trigger_message.content,
        )
        context = build_character_context(db, game_id, responder.id)
        user_id = f"game-{game_id}-character-{responder.id}"
        try:
            reply = agent.respond(context, interaction, user_id)
        except Exception as error:
            db.rollback()
            logger.warning(
                "Public turn AI response failed game_id=%s "
                "target_game_character_id=%s error_type=%s",
                game_id,
                responder.id,
                type(error).__name__,
            )
            failures.append(
                PublicTurnFailure(
                    game_character_id=responder.id,
                    error_type=type(error).__name__,
                )
            )
            next_speaker = pending.pop(0) if pending else None
            trigger_message = human_message
            continue

        ai_message = Message(
            game_session_id=game_id,
            sender_game_character_id=responder.id,
            channel_type="public",
            receiver_game_character_id=None,
            content=reply.speech,
        )
        try:
            persist_character_reply(db, responder, ai_message, reply)
        except Exception as error:
            db.rollback()
            logger.warning(
                "Public turn AI reply persistence failed game_id=%s "
                "target_game_character_id=%s error_type=%s",
                game_id,
                responder.id,
                type(error).__name__,
            )
            failures.append(
                PublicTurnFailure(
                    game_character_id=responder.id,
                    error_type=type(error).__name__,
                )
            )
            break
        ai_responses.append(MessageRead.model_validate(ai_message))
        replied_ids.add(responder.id)

        if pending:
            next_speaker = pending.pop(0)
            trigger_message = human_message
        else:
            next_speaker = select_reaction_responder(
                reply.speech, speakers, replied_ids
            )
            trigger_message = ai_message

    return PublicTurnResponse(
        human_message=MessageRead.model_validate(human_message),
        ai_responses=ai_responses,
        status="partial" if failures else "completed",
        failures=failures,
    )


def run_proactive_step(
    db: Session,
    game_id: int,
    agent: CharacterAgent,
) -> AIProactiveStepResponse:
    """Ask the next round-robin AI for exactly one public contribution."""
    game = db.get(GameSession, game_id)
    if game is None:
        raise LookupError("Game not found")
    if game.status != "in_progress":
        raise GameRuleError("AI step requires an in-progress game")

    ai_characters = [
        character
        for character in _load_game_characters(db, game_id)
        if character.controller_type == "ai"
    ]
    speakers = _speakers(ai_characters)
    responder = select_next_ai(speakers, _last_ai_public_speaker_id(db, game_id))
    if responder is None:
        raise GameRuleError("At least one AI character is required")

    runtime_character = next(
        character
        for character in ai_characters
        if character.id == responder.game_character_id
    )
    interaction = CharacterInteraction(
        mode="proactive_public",
        channel="public",
        current_message=PROACTIVE_TRIGGER,
    )
    context = build_character_context(db, game_id, runtime_character.id)
    user_id = f"game-{game_id}-character-{runtime_character.id}"
    reply = agent.respond(context, interaction, user_id)
    ai_message = Message(
        game_session_id=game_id,
        sender_game_character_id=runtime_character.id,
        channel_type="public",
        receiver_game_character_id=None,
        content=reply.speech,
    )
    persist_character_reply(db, runtime_character, ai_message, reply)
    return AIProactiveStepResponse(ai_message=MessageRead.model_validate(ai_message))


def _load_game_characters(db: Session, game_id: int) -> list[GameCharacter]:
    return list(
        db.scalars(
            select(GameCharacter)
            .where(GameCharacter.game_session_id == game_id)
            .options(selectinload(GameCharacter.character))
            .order_by(GameCharacter.id)
        ).all()
    )


def _speakers(ai_characters: list[GameCharacter]) -> list[Speaker]:
    return [
        Speaker(game_character_id=character.id, name=character.character.name)
        for character in ai_characters
    ]


def _last_ai_public_speaker_id(db: Session, game_id: int) -> int | None:
    return db.scalar(
        select(Message.sender_game_character_id)
        .join(
            GameCharacter,
            GameCharacter.id == Message.sender_game_character_id,
        )
        .where(
            Message.game_session_id == game_id,
            Message.channel_type == "public",
            GameCharacter.game_session_id == game_id,
            GameCharacter.controller_type == "ai",
        )
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(1)
    )


def _character_name(
    characters: list[GameCharacter], game_character_id: int | None
) -> str | None:
    if game_character_id is None:
        return None
    character = next(
        (item for item in characters if item.id == game_character_id), None
    )
    return character.character.name if character is not None else None
