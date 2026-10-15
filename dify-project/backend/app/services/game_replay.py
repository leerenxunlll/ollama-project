"""Read-only post-game timeline assembled from persisted game records."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.game.state_machine import GameRuleError
from app.models import (
    CharacterMemory,
    CharacterThought,
    Clue,
    GameCharacter,
    GameCharacterClue,
    GameClueDisclosure,
    GameResolution,
    GameSession,
    Message,
    Vote,
)
from app.schemas.ending import GameReplayEvent, GameReplayRead


def get_game_replay(db: Session, game_id: int) -> GameReplayRead:
    """Return a stable God-View timeline only after a valid resolution exists."""
    game = db.get(GameSession, game_id)
    if game is None:
        raise LookupError("Game not found")
    resolution = db.get(GameResolution, game_id)
    if (
        game.status != "finished"
        or game.current_phase != "ending"
        or resolution is None
    ):
        raise GameRuleError("Replay is unavailable until the game is resolved")
    if game.ended_at is None:
        raise GameRuleError("Replay is unavailable without a recorded end time")
    if resolution.script_id != game.script_id:
        raise GameRuleError("Resolution does not match the game's script")

    characters = list(
        db.scalars(
            select(GameCharacter)
            .where(GameCharacter.game_session_id == game.id)
            .options(selectinload(GameCharacter.character))
            .order_by(GameCharacter.id)
        ).all()
    )
    by_id = {character.id: character for character in characters}
    messages = list(
        db.scalars(
            select(Message)
            .where(Message.game_session_id == game.id)
            .order_by(Message.created_at, Message.id)
        ).all()
    )
    messages_by_id = {message.id: message for message in messages}
    phase_changes = [
        message
        for message in messages
        if message.channel_type == "system" and message.phase is not None
    ]
    disclosures = list(
        db.scalars(
            select(GameClueDisclosure)
            .where(GameClueDisclosure.game_session_id == game.id)
            .options(selectinload(GameClueDisclosure.clue))
            .order_by(GameClueDisclosure.created_at, GameClueDisclosure.id)
        ).all()
    )
    disclosure_message_ids = {
        disclosure.related_message_id
        for disclosure in disclosures
        if disclosure.related_message_id is not None
    }
    events: list[GameReplayEvent] = []

    if game.started_at is not None:
        events.append(
            GameReplayEvent(
                event_id="game-start:1",
                event_type="game_started",
                timestamp=game.started_at,
                phase="intro",
                actor_game_character_id=None,
                actor_name=None,
                visibility="public",
                content="游戏开始。",
            )
        )

    for message in messages:
        if message.id in disclosure_message_ids:
            continue
        sender = by_id.get(message.sender_game_character_id)
        events.append(
            GameReplayEvent(
                event_id=f"message:{message.id}",
                event_type="message",
                timestamp=message.created_at,
                phase=message.phase or _phase_at(message.created_at, phase_changes),
                actor_game_character_id=message.sender_game_character_id,
                actor_name=(sender.character.name if sender is not None else None),
                target_game_character_id=message.receiver_game_character_id,
                target_name=(
                    by_id[message.receiver_game_character_id].character.name
                    if message.receiver_game_character_id in by_id
                    else None
                ),
                visibility=(
                    "private" if message.channel_type == "private" else "public"
                ),
                content=message.content,
                related_message_id=message.id,
            )
        )

    for disclosure in disclosures:
        message = messages_by_id.get(disclosure.related_message_id)
        source = by_id.get(disclosure.source_game_character_id)
        target = by_id.get(disclosure.target_game_character_id)
        events.append(
            GameReplayEvent(
                event_id=f"clue-disclosure:{disclosure.id}",
                event_type="clue_disclosure",
                timestamp=(
                    message.created_at if message is not None else disclosure.created_at
                ),
                phase=disclosure.phase
                or (message.phase if message is not None else None)
                or _phase_at(
                    message.created_at
                    if message is not None
                    else disclosure.created_at,
                    phase_changes,
                ),
                actor_game_character_id=disclosure.source_game_character_id,
                actor_name=(source.character.name if source is not None else None),
                target_game_character_id=disclosure.target_game_character_id,
                target_name=(target.character.name if target is not None else None),
                visibility=disclosure.visibility,
                content=(
                    message.content
                    if message is not None
                    else f"正式披露线索：{disclosure.clue.name}。"
                ),
                related_message_id=disclosure.related_message_id,
                related_clue_id=disclosure.clue_id,
            )
        )

    thoughts = db.scalars(
        select(CharacterThought)
        .where(CharacterThought.game_session_id == game.id)
        .order_by(CharacterThought.created_at, CharacterThought.id)
    ).all()
    for thought in thoughts:
        character = by_id.get(thought.game_character_id)
        source_message = messages_by_id.get(thought.ai_message_id)
        events.append(
            GameReplayEvent(
                event_id=f"thought:{thought.id}",
                event_type="character_thought",
                timestamp=thought.created_at,
                phase=(
                    source_message.phase
                    if source_message is not None and source_message.phase is not None
                    else _phase_at(thought.created_at, phase_changes)
                ),
                actor_game_character_id=thought.game_character_id,
                actor_name=(
                    character.character.name if character is not None else None
                ),
                visibility="god",
                inner_os=thought.inner_os,
                emotion=thought.emotion,
                intent=thought.intent,
                related_message_id=thought.ai_message_id,
            )
        )

    memories = db.scalars(
        select(CharacterMemory)
        .where(CharacterMemory.game_session_id == game.id)
        .order_by(CharacterMemory.created_at, CharacterMemory.id)
    ).all()
    for memory in memories:
        character = by_id.get(memory.game_character_id)
        source_message = messages_by_id.get(memory.source_message_id)
        events.append(
            GameReplayEvent(
                event_id=f"memory:{memory.id}",
                event_type="character_memory",
                timestamp=memory.created_at,
                phase=_phase_at(memory.created_at, phase_changes),
                actor_game_character_id=memory.game_character_id,
                actor_name=(
                    character.character.name if character is not None else None
                ),
                visibility="god",
                content=memory.content,
                memory_importance=memory.importance,
                subjective=True,
                related_message_id=memory.source_message_id,
            )
        )

    acquisitions = db.execute(
        select(GameCharacterClue, Clue)
        .join(Clue, Clue.id == GameCharacterClue.clue_id)
        .where(
            GameCharacterClue.game_character_id.in_(list(by_id)),
            Clue.script_id == game.script_id,
        )
        .order_by(GameCharacterClue.discovered_at, GameCharacterClue.id)
    ).all()
    for acquisition, clue in acquisitions:
        character = by_id.get(acquisition.game_character_id)
        events.append(
            GameReplayEvent(
                event_id=f"clue-acquisition:{acquisition.id}",
                event_type="clue_acquired",
                timestamp=acquisition.discovered_at,
                phase=acquisition.phase
                or _phase_at(acquisition.discovered_at, phase_changes),
                actor_game_character_id=acquisition.game_character_id,
                actor_name=(
                    character.character.name if character is not None else None
                ),
                visibility="private",
                content=f"{clue.name}：{clue.description}",
                related_clue_id=clue.id,
            )
        )

    votes = db.scalars(
        select(Vote)
        .where(Vote.game_session_id == game.id)
        .order_by(Vote.created_at, Vote.id)
    ).all()
    for vote in votes:
        voter = by_id.get(vote.voter_game_character_id)
        target = by_id.get(vote.target_game_character_id)
        content = f"投给{target.character.name}。" if target is not None else "已投票。"
        if vote.decision_reason:
            content = f"{content}理由：{vote.decision_reason}"
        events.append(
            GameReplayEvent(
                event_id=f"vote:{vote.id}",
                event_type="vote",
                timestamp=vote.created_at,
                phase="vote",
                actor_game_character_id=vote.voter_game_character_id,
                actor_name=(voter.character.name if voter is not None else None),
                target_game_character_id=vote.target_game_character_id,
                target_name=(target.character.name if target is not None else None),
                visibility="god",
                content=content,
                related_vote_id=vote.id,
            )
        )

    events.append(
        GameReplayEvent(
            event_id="game-end:1",
            event_type="game_ended",
            timestamp=game.ended_at,
            phase="ending",
            actor_game_character_id=None,
            actor_name=None,
            visibility="public",
            content=resolution.ending_narrative,
        )
    )
    events.sort(key=_event_sort_key)
    return GameReplayRead(
        game_id=game.id,
        started_at=game.started_at,
        ended_at=game.ended_at,
        events=events,
    )


def _event_sort_key(event: GameReplayEvent) -> tuple[datetime, str]:
    timestamp = event.timestamp
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc), event.event_id


def _phase_at(timestamp: datetime, phase_changes: list[Message]) -> str | None:
    """Infer only from an earlier persisted system phase-change message."""
    event_time = _as_utc(timestamp)
    current_phase = None
    for message in phase_changes:
        if _as_utc(message.created_at) > event_time:
            break
        current_phase = message.phase
    return current_phase


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
