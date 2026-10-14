"""Persist one validated character reply and its private cognitive state."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.character_agent import CharacterReply
from app.models import CharacterMemory, CharacterThought, GameCharacter, Message
from app.services.evidence import record_character_disclosure
from app.services.runtime_guards import assert_runtime_action_current


def persist_character_reply(
    db: Session,
    game_character: GameCharacter,
    ai_message: Message,
    reply: CharacterReply,
    related_messages: tuple[Message, ...] = (),
    *,
    commit: bool = True,
    expected_phase: str | None = None,
    expected_phase_started_at: datetime | None = None,
    runtime_claim_token: str | None = None,
    now: datetime | None = None,
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
        if expected_phase is not None or runtime_claim_token is not None:
            assert_runtime_action_current(
                db,
                ai_message.game_session_id,
                claim_token=runtime_claim_token,
                expected_phase=expected_phase,
                expected_phase_started_at=expected_phase_started_at,
                now=now,
            )
        db.add_all([*related_messages, ai_message])
        db.flush()
        disclosure_intent = getattr(reply, "clue_disclosure_intent", None)
        if disclosure_intent is not None:
            record_character_disclosure(
                db,
                game_id=ai_message.game_session_id,
                source=game_character,
                clue_id=disclosure_intent.clue_id,
                visibility=disclosure_intent.visibility,
                target_game_character_id=(disclosure_intent.target_game_character_id),
                speech_message=ai_message,
            )
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
