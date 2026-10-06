"""Database-backed flow snapshots and deterministic vote operations."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.game.flow_manager import build_flow_state, tally_votes
from app.game.state_machine import GameRuleError
from app.models import GameCharacter, GameSession, Vote
from app.schemas.flow import GameFlowState, VoteCreate, VoteRead, VoteResultRead


def get_game_flow_state(
    db: Session, game_id: int, now: datetime | None = None
) -> GameFlowState:
    """Build a safe flow snapshot without returning script secrets or vote tally."""
    game = _get_game(db, game_id)
    character_ids = list(
        db.scalars(
            select(GameCharacter.id)
            .where(GameCharacter.game_session_id == game.id)
            .order_by(GameCharacter.id)
        ).all()
    )
    votes_cast = int(
        db.scalar(
            select(func.count())
            .select_from(Vote)
            .where(Vote.game_session_id == game.id)
        )
        or 0
    )
    return build_flow_state(
        game_id=game.id,
        status=game.status,
        current_phase=game.current_phase,
        phase_started_at=game.phase_started_at,
        votes_cast=votes_cast,
        total_voters=len(character_ids),
        now=now,
    )


def create_vote(db: Session, game_id: int, payload: VoteCreate) -> VoteRead:
    """Validate and persist one immutable development vote."""
    game = _get_game(db, game_id)
    if game.status != "in_progress" or game.current_phase != "vote":
        raise GameRuleError("Votes are only accepted during the active vote phase")

    voter = _get_game_character(db, game.id, payload.voter_game_character_id)
    target = _get_game_character(db, game.id, payload.target_game_character_id)
    if voter.id == target.id:
        raise GameRuleError("A character cannot vote for itself")
    existing_vote = db.scalar(
        select(Vote.id).where(
            Vote.game_session_id == game.id,
            Vote.voter_game_character_id == voter.id,
        )
    )
    if existing_vote is not None:
        raise GameRuleError("A character can only vote once")

    vote = Vote(
        game_session_id=game.id,
        voter_game_character_id=voter.id,
        target_game_character_id=target.id,
    )
    db.add(vote)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise GameRuleError("A character can only vote once") from error
    db.refresh(vote)
    return VoteRead.model_validate(vote)


def get_vote_result(db: Session, game_id: int) -> VoteResultRead:
    """Return the full deterministic tally for the development debug endpoint."""
    game = _get_game(db, game_id)
    character_ids = list(
        db.scalars(
            select(GameCharacter.id)
            .where(GameCharacter.game_session_id == game.id)
            .order_by(GameCharacter.id)
        ).all()
    )
    votes = list(
        db.execute(
            select(Vote.voter_game_character_id, Vote.target_game_character_id)
            .where(Vote.game_session_id == game.id)
            .order_by(Vote.id)
        ).all()
    )
    counts, winner_id, is_tie = tally_votes(
        [(voter_id, target_id) for voter_id, target_id in votes], character_ids
    )
    votes_cast = len(votes)
    total_voters = len(character_ids)
    return VoteResultRead(
        game_id=game.id,
        vote_count_by_target=counts,
        winner_game_character_id=winner_id,
        is_tie=is_tie,
        votes_cast=votes_cast,
        total_voters=total_voters,
        voting_complete=total_voters > 0 and votes_cast >= total_voters,
        submitted_voter_game_character_ids=sorted(voter_id for voter_id, _ in votes),
    )


def _get_game(db: Session, game_id: int) -> GameSession:
    game = db.get(GameSession, game_id)
    if game is None:
        raise LookupError("Game not found")
    return game


def _get_game_character(
    db: Session, game_id: int, game_character_id: int
) -> GameCharacter:
    character = db.get(GameCharacter, game_character_id)
    if character is None or character.game_session_id != game_id:
        raise LookupError("Character not found in this game")
    return character
