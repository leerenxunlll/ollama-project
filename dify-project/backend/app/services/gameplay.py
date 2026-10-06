"""Database operations for deterministic game actions."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.game.state_machine import (
    GameRuleError,
    can_investigate,
    clue_act_for_phase,
    next_phase,
    require_next_phase,
    validate_start,
)
from app.models import Clue, GameCharacter, GameCharacterClue, GameSession, Message
from app.schemas.game import (
    GameStateRead,
    InvestigationClueRead,
    InvestigationLocationsRead,
    InvestigationResultRead,
    PlayerMessageCreate,
)
from app.services.game_flow import get_game_flow_state

PHASE_MESSAGES = {
    "act_1": "进入第一幕。",
    "investigation_1": "进入第一轮搜证。",
    "discussion_1": "进入第一轮讨论。",
    "act_2": "进入第二幕。",
    "investigation_2": "进入第二轮搜证。",
    "discussion_2": "进入第二轮讨论。",
    "final_discussion": "进入最终讨论。",
    "vote": "进入投票阶段。",
    "ending": "游戏结束。",
}


def get_game_state(db: Session, game_id: int) -> GameStateRead:
    """Return only non-sensitive lifecycle and phase fields."""
    game = _get_game(db, game_id)
    return _state_response(game)


def start_game(db: Session, game_id: int) -> GameStateRead:
    """Validate the role assignment, then begin the first narrative phase."""
    game = _get_game(db, game_id)
    characters = list(
        db.scalars(
            select(GameCharacter)
            .where(GameCharacter.game_session_id == game_id)
            .order_by(GameCharacter.id)
        ).all()
    )
    validate_start(game.status, [character.controller_type for character in characters])

    now = datetime.now(timezone.utc)
    game.status = "in_progress"
    game.current_phase = "intro"
    game.started_at = now
    game.phase_started_at = now
    db.add(
        Message(
            game_session_id=game.id,
            sender_game_character_id=None,
            channel_type="system",
            receiver_game_character_id=None,
            content="游戏开始。",
        )
    )
    db.commit()
    db.refresh(game)
    return _state_response(game)


def advance_game_phase(
    db: Session,
    game_id: int,
    now: datetime | None = None,
    *,
    commit: bool = True,
) -> GameStateRead:
    """Validate flow timing, then move exactly one step along the phase graph."""
    game = _get_game(db, game_id)
    if game.status != "in_progress":
        raise GameRuleError("Only an in-progress game can advance")

    transition_time = now or datetime.now(timezone.utc)
    flow_state = get_game_flow_state(db, game_id, transition_time)
    if not flow_state.minimum_time_satisfied:
        raise GameRuleError("The current phase minimum duration has not elapsed")
    if game.current_phase == "vote" and not flow_state.vote_progress.voting_complete:
        raise GameRuleError(
            "All game characters must vote before the phase can advance"
        )

    target_phase = require_next_phase(game.current_phase)
    game.current_phase = target_phase
    game.phase_started_at = transition_time
    content = PHASE_MESSAGES[target_phase]
    if target_phase == "ending":
        game.status = "finished"
        game.ended_at = transition_time

    db.add(
        Message(
            game_session_id=game.id,
            sender_game_character_id=None,
            channel_type="system",
            receiver_game_character_id=None,
            content=content,
        )
    )
    if commit:
        db.commit()
        db.refresh(game)
    return _state_response(game)


def get_investigation_locations(
    db: Session, game_id: int
) -> InvestigationLocationsRead:
    """List locations containing clues for the current investigation act."""
    game = _get_game(db, game_id)
    _require_investigation(game)
    act = clue_act_for_phase(game.current_phase)
    locations = list(
        db.scalars(
            select(Clue.location)
            .where(Clue.script_id == game.script_id, Clue.act == act)
            .distinct()
            .order_by(Clue.location)
        ).all()
    )
    return InvestigationLocationsRead(
        game_id=game.id,
        current_phase=game.current_phase,
        locations=locations,
    )


def search_location(
    db: Session,
    game_id: int,
    game_character_id: int,
    location: str,
) -> InvestigationResultRead:
    """Grant the first undiscovered matching clue to one runtime character."""
    game = _get_game(db, game_id)
    _require_investigation(game)
    character = db.get(GameCharacter, game_character_id)
    if character is None or character.game_session_id != game.id:
        raise LookupError("Character not found in this game")

    act = clue_act_for_phase(game.current_phase)
    clues = db.scalars(
        select(Clue)
        .where(
            Clue.script_id == game.script_id,
            Clue.act == act,
            Clue.location == location,
        )
        .order_by(Clue.importance.desc(), Clue.id.asc())
    ).all()
    for clue in clues:
        already_known = db.scalar(
            select(GameCharacterClue.id).where(
                GameCharacterClue.game_character_id == character.id,
                GameCharacterClue.clue_id == clue.id,
            )
        )
        if already_known is not None:
            continue

        db.add(
            GameCharacterClue(
                game_character_id=character.id,
                clue_id=clue.id,
                source="investigation",
            )
        )
        db.commit()
        return InvestigationResultRead(
            game_id=game.id,
            game_character_id=character.id,
            location=location,
            found=True,
            clue=InvestigationClueRead.model_validate(clue),
        )

    return InvestigationResultRead(
        game_id=game.id,
        game_character_id=character.id,
        location=location,
        found=False,
        clue=None,
    )


def create_player_message(
    db: Session, game_id: int, payload: PlayerMessageCreate
) -> Message:
    """Persist a public/private message from participants in the same game."""
    game = _get_game(db, game_id)
    sender = db.get(GameCharacter, payload.sender_game_character_id)
    if sender is None or sender.game_session_id != game.id:
        raise LookupError("Sender not found in this game")

    receiver = None
    if payload.channel_type == "private":
        receiver = db.get(GameCharacter, payload.receiver_game_character_id)
        if receiver is None or receiver.game_session_id != game.id:
            raise LookupError("Receiver not found in this game")
        if receiver.id == sender.id:
            raise GameRuleError("Private messages must have a different receiver")

    message = Message(
        game_session_id=game.id,
        sender_game_character_id=sender.id,
        channel_type=payload.channel_type,
        receiver_game_character_id=receiver.id if receiver is not None else None,
        content=payload.content,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def _get_game(db: Session, game_id: int) -> GameSession:
    game = db.get(GameSession, game_id)
    if game is None:
        raise LookupError("Game not found")
    return game


def _require_investigation(game: GameSession) -> None:
    if not can_investigate(game.status, game.current_phase):
        raise GameRuleError("Investigation is not allowed in the current phase")


def _state_response(game: GameSession) -> GameStateRead:
    is_in_progress = game.status == "in_progress"
    return GameStateRead(
        game_id=game.id,
        status=game.status,
        current_phase=game.current_phase,
        started_at=game.started_at,
        ended_at=game.ended_at,
        next_phase=next_phase(game.current_phase) if is_in_progress else None,
        can_investigate=can_investigate(game.status, game.current_phase),
    )
