"""Persist one validated character reply and its private cognitive state."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.character_agent import CharacterReply
from app.models import CharacterMemory, CharacterThought, GameCharacter, Message


def persist_character_reply(
    db: Session,
    game_character: GameCharacter,
    ai_message: Message,
    reply: CharacterReply,
    related_messages: tuple[Message, ...] = (),
    *,
    commit: bool = True,
) -> Message:
    """Atomically save a character message, thought, memory, and emotion."""
    existing_memory_content = db.scalars(
        select(CharacterMemory.content).where(
            CharacterMemory.game_session_id == ai_message.game_session_id,
            CharacterMemory.game_character_id == game_character.id,
        )
    ).all()
    seen_memories = {_normalize_memory(content) for content in existing_memory_content}

    try:
        db.add_all([*related_messages, ai_message])
        db.flush()
        db.add(
            CharacterThought(
                game_session_id=ai_message.game_session_id,
                game_character_id=game_character.id,
                ai_message_id=ai_message.id,
                inner_os=reply.inner_os,
                emotion=reply.emotion.value,
                intent=reply.intent.value,
            )
        )
        for update in reply.memory_updates:
            normalized_content = _normalize_memory(update.content)
            if normalized_content in seen_memories:
                continue
            db.add(
                CharacterMemory(
                    game_session_id=ai_message.game_session_id,
                    game_character_id=game_character.id,
                    content=update.content,
                    importance=update.importance,
                    source_message_id=ai_message.id,
                )
            )
            seen_memories.add(normalized_content)
        game_character.current_emotion = reply.emotion.value
        db.refresh(ai_message)
        if commit:
            db.commit()
    except Exception:
        db.rollback()
        raise

    return ai_message


def _normalize_memory(content: str) -> str:
    """Collapse whitespace for exact duplicate checks without semantic matching."""
    return " ".join(content.split())
