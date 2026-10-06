"""Build the bounded Director view from authoritative and public game data."""

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.game.state_machine import INVESTIGATION_ACTS
from app.models import GameCharacter, GameCharacterClue, GameSession, Message, Script
from app.schemas.director import (
    DirectorCharacterFact,
    DirectorClueFact,
    DirectorClueProgress,
    DirectorContext,
    DirectorParticipation,
    DirectorPublicMessage,
    DirectorPublicState,
    DirectorScriptContext,
    DirectorVotingState,
)
from app.services.game_flow import get_game_flow_state, get_vote_result

DIRECTOR_PUBLIC_MESSAGE_LIMIT = 50
DIRECTOR_INACTIVE_AFTER_SECONDS = 120


def build_director_context(
    db: Session, game_id: int, now: datetime | None = None
) -> DirectorContext:
    """Construct only script truth, objective state, and bounded public history."""
    game = db.get(GameSession, game_id)
    if game is None:
        raise LookupError("Game not found")
    script = db.scalar(
        select(Script)
        .where(Script.id == game.script_id)
        .options(selectinload(Script.characters), selectinload(Script.clues))
    )
    if script is None:
        raise LookupError("Script not found")

    characters = list(
        db.scalars(
            select(GameCharacter)
            .where(GameCharacter.game_session_id == game.id)
            .options(selectinload(GameCharacter.character))
            .order_by(GameCharacter.id)
        ).all()
    )
    character_by_id = {character.id: character for character in characters}
    messages = list(
        db.scalars(
            select(Message)
            .where(
                Message.game_session_id == game.id,
                Message.channel_type.in_(("public", "system")),
            )
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(DIRECTOR_PUBLIC_MESSAGE_LIMIT)
        ).all()
    )
    messages.reverse()
    public_messages = [
        DirectorPublicMessage(
            id=message.id,
            sender_game_character_id=message.sender_game_character_id,
            sender_name=(
                character_by_id[message.sender_game_character_id].character.name
                if message.sender_game_character_id in character_by_id
                else None
            ),
            channel_type=message.channel_type,
            content=message.content,
            created_at=message.created_at,
        )
        for message in messages
    ]

    acquisition_rows = db.execute(
        select(GameCharacterClue.clue_id, GameCharacterClue.game_character_id)
        .join(
            GameCharacter,
            GameCharacter.id == GameCharacterClue.game_character_id,
        )
        .where(GameCharacter.game_session_id == game.id)
    ).all()
    acquired_by_clue: dict[int, list[int]] = {}
    for clue_id, character_id in acquisition_rows:
        acquired_by_clue.setdefault(clue_id, []).append(character_id)

    phase_act = INVESTIGATION_ACTS.get(game.current_phase)
    clue_facts = [
        DirectorClueFact(
            id=clue.id,
            name=clue.name,
            description=clue.description,
            act=clue.act,
            location=clue.location,
            is_core=clue.is_core,
            importance=clue.importance,
        )
        for clue in sorted(script.clues, key=lambda item: item.id)
    ]
    clue_progress = [
        DirectorClueProgress(
            clue_id=clue.id,
            name=clue.name,
            act=clue.act,
            location=clue.location,
            is_core=clue.is_core,
            importance=clue.importance,
            available_in_current_phase=(
                phase_act is not None and clue.act == phase_act
            ),
            acquired_by_game_character_ids=sorted(acquired_by_clue.get(clue.id, [])),
        )
        for clue in sorted(script.clues, key=lambda item: item.id)
    ]

    participation_rows = db.execute(
        select(
            Message.sender_game_character_id,
            func.count(Message.id),
            func.max(Message.created_at),
        )
        .where(
            Message.game_session_id == game.id,
            Message.channel_type == "public",
            Message.sender_game_character_id.is_not(None),
        )
        .group_by(Message.sender_game_character_id)
    ).all()
    participation_by_character = {
        character_id: (count, last_spoke_at)
        for character_id, count, last_spoke_at in participation_rows
    }
    context_now = _as_utc(now or datetime.now(timezone.utc))
    participation = []
    for character in characters:
        message_count, last_spoke_at = participation_by_character.get(
            character.id, (0, None)
        )
        activity_anchor = last_spoke_at or game.started_at or game.created_at
        seconds_since_speech = max(
            0,
            int((context_now - _as_utc(activity_anchor)).total_seconds()),
        )
        participation.append(
            DirectorParticipation(
                game_character_id=character.id,
                character_name=character.character.name,
                controller_type=character.controller_type,
                public_message_count=message_count,
                last_public_speech_at=last_spoke_at,
                inactive_long_enough=(
                    seconds_since_speech >= DIRECTOR_INACTIVE_AFTER_SECONDS
                ),
            )
        )

    vote_result = get_vote_result(db, game.id)
    return DirectorContext(
        game_id=game.id,
        script=DirectorScriptContext(
            id=script.id,
            title=script.title,
            summary=script.summary,
            theme=script.theme,
            era=script.era,
            atmosphere=script.atmosphere,
            difficulty=script.difficulty,
            status=script.status,
            culprit_character_id=next(
                (
                    character.id
                    for character in script.characters
                    if character.is_killer
                ),
                None,
            ),
            characters=[
                DirectorCharacterFact.model_validate(character)
                for character in sorted(script.characters, key=lambda item: item.id)
            ],
            clues=clue_facts,
        ),
        game_flow=get_game_flow_state(db, game.id, now=now),
        voting_state=DirectorVotingState(
            vote_count_by_target=vote_result.vote_count_by_target,
            winner_game_character_id=vote_result.winner_game_character_id,
            is_tie=vote_result.is_tie,
            votes_cast=vote_result.votes_cast,
            total_voters=vote_result.total_voters,
            voting_complete=vote_result.voting_complete,
        ),
        public_state=DirectorPublicState(recent_messages=public_messages),
        clue_progress=clue_progress,
        participation=participation,
    )


def _as_utc(value: datetime) -> datetime:
    """Treat SQLite's naive UTC timestamps as UTC for elapsed-time summaries."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
