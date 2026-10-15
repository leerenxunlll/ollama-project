"""Database-backed flow snapshots and deterministic vote operations."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.agents.vote_agent import CharacterVoteAgent
from app.game.flow_manager import build_flow_state, tally_votes
from app.game.state_machine import GameRuleError
from app.models import GameCharacter, GameSession, Vote
from app.schemas.flow import GameFlowState, VoteCreate, VoteRead, VoteResultRead
from app.schemas.voting import (
    CharacterVoteCandidate,
    CharacterVoteContext,
    GameVoteStatus,
    VoteCharacterStatus,
)
from app.services.character_context import build_character_context
from app.services.runtime_guards import assert_runtime_action_current


class VoteConflict(GameRuleError):
    """A vote lost an immutable per-character or concurrency race."""


class InvalidAIVoteTarget(GameRuleError):
    """The AI selected a character outside the eligible candidate list."""


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
    """Persist the Human's immutable vote through the existing Vote model."""
    game = _get_game(db, game_id)
    if game.status != "in_progress" or game.current_phase != "vote":
        raise GameRuleError("Votes are only accepted during the active vote phase")

    voter = _get_game_character(db, game.id, payload.voter_game_character_id)
    if voter.controller_type != "human":
        raise GameRuleError("The player vote must come from the Human character")
    target = _get_game_character(db, game.id, payload.target_game_character_id)
    if voter.id == target.id:
        raise GameRuleError("A character cannot vote for itself")
    vote = _insert_vote(db, game.id, voter.id, target.id)
    db.add(vote)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise VoteConflict("A character can only vote once") from error
    db.refresh(vote)
    return VoteRead.model_validate(vote)


def build_character_vote_context(
    db: Session, game_id: int, voter_game_character_id: int
) -> CharacterVoteContext:
    """Build an AI vote context from its existing permission-filtered context."""
    game = _get_game(db, game_id)
    if game.status != "in_progress" or game.current_phase != "vote":
        raise GameRuleError("AI votes are only allowed during the active vote phase")
    voter = _get_game_character(db, game_id, voter_game_character_id)
    if voter.controller_type != "ai":
        raise GameRuleError("Only an AI character can use the vote workflow")
    existing = db.scalar(
        select(Vote.id).where(
            Vote.game_session_id == game.id,
            Vote.voter_game_character_id == voter.id,
        )
    )
    if existing is not None:
        raise GameRuleError("This AI character has already voted")

    candidates = list(
        db.scalars(
            select(GameCharacter)
            .where(
                GameCharacter.game_session_id == game.id,
                GameCharacter.id != voter.id,
            )
            .options(selectinload(GameCharacter.character))
            .order_by(GameCharacter.id)
        ).all()
    )
    roster = [voter, *candidates]
    if (
        len(roster) != 4
        or sum(character.controller_type == "human" for character in roster) != 1
        or sum(character.controller_type == "ai" for character in roster) != 3
    ):
        raise GameRuleError("The game must have one Human and three AI voters")
    return CharacterVoteContext(
        game_id=game.id,
        voter_game_character_id=voter.id,
        current_phase="vote",
        character_context=build_character_context(db, game.id, voter.id),
        eligible_candidates=[
            CharacterVoteCandidate(
                game_character_id=candidate.id,
                character_name=candidate.character.name,
                public_identity=candidate.character.identity,
            )
            for candidate in candidates
        ],
    )


def run_ai_vote(
    db: Session,
    game_id: int,
    voter_game_character_id: int,
    agent: CharacterVoteAgent,
    *,
    expected_phase: str = "vote",
    expected_phase_started_at: datetime | None = None,
    runtime_claim_token: str | None = None,
    now: datetime | None = None,
    commit: bool = True,
) -> VoteRead:
    """Ask one AI for a legal target, then persist through the shared Vote table."""
    game = _get_game(db, game_id)
    if game.current_phase != expected_phase:
        raise GameRuleError("The game phase changed before the AI vote")
    phase_started_at = (
        game.phase_started_at
        if expected_phase_started_at is None
        else expected_phase_started_at
    )
    context = build_character_vote_context(db, game_id, voter_game_character_id)
    candidate_ids = {
        candidate.game_character_id for candidate in context.eligible_candidates
    }

    # Release SQLite's read transaction before the remote Workflow request.
    db.commit()
    decision = agent.decide(context)
    if decision.target_game_character_id not in candidate_ids:
        raise InvalidAIVoteTarget("AI vote target is not an eligible candidate")

    assert_runtime_action_current(
        db,
        game_id,
        claim_token=runtime_claim_token,
        expected_phase=expected_phase,
        expected_phase_started_at=phase_started_at,
        now=now,
    )
    voter = _get_game_character(db, game_id, voter_game_character_id)
    target = _get_game_character(db, game_id, decision.target_game_character_id)
    vote = _insert_vote(
        db,
        game_id,
        voter.id,
        target.id,
        decision_reason=decision.reason,
    )
    db.add(vote)
    try:
        db.flush()
        if commit:
            db.commit()
    except IntegrityError as error:
        db.rollback()
        raise VoteConflict("An AI character can only vote once") from error
    if commit:
        db.refresh(vote)
    return VoteRead.model_validate(vote)


def get_game_vote_status(db: Session, game_id: int) -> GameVoteStatus:
    """Return vote completion flags without revealing targets or reasons."""
    game = _get_game(db, game_id)
    characters = list(
        db.scalars(
            select(GameCharacter)
            .where(GameCharacter.game_session_id == game.id)
            .options(selectinload(GameCharacter.character))
            .order_by(GameCharacter.id)
        ).all()
    )
    voted_ids = set(
        db.scalars(
            select(Vote.voter_game_character_id).where(Vote.game_session_id == game.id)
        ).all()
    )
    human = next(
        (character for character in characters if character.controller_type == "human"),
        None,
    )
    ai_characters = [
        character for character in characters if character.controller_type == "ai"
    ]
    return GameVoteStatus(
        game_id=game.id,
        current_phase=game.current_phase,
        votes_cast=len(voted_ids),
        total_voters=len(characters),
        human_has_voted=human is not None and human.id in voted_ids,
        ai_characters=[
            VoteCharacterStatus(
                game_character_id=character.id,
                character_name=character.character.name,
                has_voted=character.id in voted_ids,
            )
            for character in ai_characters
        ],
        voting_complete=bool(characters) and len(voted_ids) == len(characters),
    )


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


def _insert_vote(
    db: Session,
    game_id: int,
    voter_id: int,
    target_id: int,
    *,
    decision_reason: str | None = None,
) -> Vote:
    """Create a Vote row; the database uniqueness rule handles races."""
    existing_vote = db.scalar(
        select(Vote.id).where(
            Vote.game_session_id == game_id,
            Vote.voter_game_character_id == voter_id,
        )
    )
    if existing_vote is not None:
        raise VoteConflict("A character can only vote once")
    return Vote(
        game_session_id=game_id,
        voter_game_character_id=voter_id,
        target_game_character_id=target_id,
        decision_reason=decision_reason,
    )
