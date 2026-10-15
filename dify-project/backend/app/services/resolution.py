"""Deterministic vote settlement and post-game canonical truth projection."""

from datetime import datetime

from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from app.game.flow_manager import tally_votes
from app.game.state_machine import GameRuleError
from app.models import (
    Character,
    Clue,
    GameCharacter,
    GameResolution,
    GameSession,
    Script,
    ScriptCanonicalData,
    Vote,
)
from app.schemas.ending import (
    CanonicalTimelineEvent,
    EndingClue,
    EndingTruth,
    GameEndingRead,
)
from app.schemas.voting import VoteReveal
from app.schemas.writer import WriterCaseTruth, WriterTimelineEvent


def finalize_game_resolution(
    db: Session, game: GameSession, resolved_at: datetime
) -> GameResolution:
    """Atomically lock vote→ending and persist the one canonical resolution."""
    existing = db.get(GameResolution, game.id)
    if existing is not None:
        return existing
    if game.status != "in_progress" or game.current_phase != "vote":
        raise GameRuleError("Only a voting game can be resolved")

    canonical = db.get(ScriptCanonicalData, game.script_id)
    if canonical is None:
        raise GameRuleError("Canonical Truth is missing for this script")
    try:
        truth = WriterCaseTruth.model_validate(canonical.case_truth_json)
        for event in canonical.timeline_json:
            WriterTimelineEvent.model_validate(event)
    except (ValidationError, TypeError) as error:
        raise GameRuleError("Canonical Truth is invalid for this script") from error

    role_character_id = canonical.role_character_ids_json.get(truth.culprit_role_key)
    if not isinstance(role_character_id, int):
        raise GameRuleError("Canonical culprit mapping is missing")
    culprit = db.scalar(
        select(GameCharacter).where(
            GameCharacter.game_session_id == game.id,
            GameCharacter.character_id == role_character_id,
        )
    )
    characters = list(
        db.scalars(
            select(GameCharacter)
            .where(GameCharacter.game_session_id == game.id)
            .order_by(GameCharacter.id)
        ).all()
    )
    if culprit is None or len(characters) != 4:
        raise GameRuleError(
            "Canonical culprit does not map to this four-character game"
        )

    script = db.get(Script, game.script_id)
    templates = list(
        db.scalars(select(Character).where(Character.script_id == game.script_id)).all()
    )
    template_ids = {character.id for character in templates}
    role_mapping = canonical.role_character_ids_json
    if (
        script is None
        or script.status != "ready"
        or len(templates) != 4
        or {character.character_id for character in characters} != template_ids
        or not isinstance(role_mapping, dict)
        or len(role_mapping) != 4
        or set(role_mapping.values()) != template_ids
    ):
        raise GameRuleError("Canonical data does not match the published script")
    killer_ids = {character.id for character in templates if character.is_killer}
    if killer_ids != {role_character_id}:
        raise GameRuleError("Canonical culprit does not match the published script")
    if (
        sum(character.controller_type == "human" for character in characters) != 1
        or sum(character.controller_type == "ai" for character in characters) != 3
    ):
        raise GameRuleError("The game must have one Human and three AI voters")

    votes = list(
        db.scalars(
            select(Vote).where(Vote.game_session_id == game.id).order_by(Vote.id)
        ).all()
    )
    voters = {vote.voter_game_character_id for vote in votes}
    if len(votes) != 4 or voters != {character.id for character in characters}:
        raise GameRuleError("All four characters must vote before resolution")

    character_ids = [character.id for character in characters]
    pairs = [
        (vote.voter_game_character_id, vote.target_game_character_id) for vote in votes
    ]
    _counts, winner_id, is_tie = tally_votes(pairs, character_ids)
    accused_id = None if is_tie else winner_id
    vote_result = (
        "tie"
        if is_tie
        else "culprit_identified"
        if winner_id == culprit.id
        else "wrong_accusation"
    )
    human = [
        character for character in characters if character.controller_type == "human"
    ]
    if len(human) != 1:
        raise GameRuleError("The game must have exactly one Human character")
    human_vote = next(
        (vote for vote in votes if vote.voter_game_character_id == human[0].id),
        None,
    )
    if human_vote is None:
        raise GameRuleError("The Human character has not voted")

    culprit_template = next(
        character for character in templates if character.id == culprit.character_id
    )
    culprit_name = culprit_template.name
    narrative = _ending_narrative(vote_result, culprit_name, truth.case_summary)

    phase_predicate = (
        GameSession.phase_started_at.is_(None)
        if game.phase_started_at is None
        else GameSession.phase_started_at == game.phase_started_at
    )
    transition = db.execute(
        update(GameSession)
        .where(
            GameSession.id == game.id,
            GameSession.status == "in_progress",
            GameSession.current_phase == "vote",
            phase_predicate,
        )
        .execution_options(synchronize_session=False)
        .values(
            status="finished",
            current_phase="ending",
            phase_started_at=resolved_at,
            ended_at=resolved_at,
        )
    )
    if transition.rowcount != 1:
        raise GameRuleError("The game was resolved by another request")

    game.status = "finished"
    game.current_phase = "ending"
    game.phase_started_at = resolved_at
    game.ended_at = resolved_at
    resolution = GameResolution(
        game_session_id=game.id,
        script_id=game.script_id,
        culprit_game_character_id=culprit.id,
        vote_result=vote_result,
        accused_game_character_id=accused_id,
        is_tie=is_tie,
        human_vote_target_id=human_vote.target_game_character_id,
        human_identified_culprit=(human_vote.target_game_character_id == culprit.id),
        case_outcome=vote_result,
        ending_narrative=narrative,
        resolved_at=resolved_at,
    )
    db.add(resolution)
    db.flush()
    return resolution


def get_game_ending(db: Session, game_id: int) -> GameEndingRead:
    """Return canonical truth and all votes only after a valid resolution."""
    game, resolution, canonical = _resolved_game(db, game_id)
    try:
        truth = EndingTruth.model_validate(canonical.case_truth_json)
        timeline = [
            CanonicalTimelineEvent.model_validate(event)
            for event in canonical.timeline_json
        ]
    except (ValidationError, TypeError) as error:
        raise GameRuleError("Canonical Truth is invalid for this script") from error

    characters = list(
        db.scalars(
            select(GameCharacter)
            .where(GameCharacter.game_session_id == game.id)
            .options(selectinload(GameCharacter.character))
            .order_by(GameCharacter.id)
        ).all()
    )
    by_id = {character.id: character for character in characters}
    votes = list(
        db.scalars(
            select(Vote)
            .where(Vote.game_session_id == game.id)
            .order_by(Vote.voter_game_character_id)
        ).all()
    )
    key_clues = db.scalars(
        select(Clue)
        .where(Clue.script_id == game.script_id, Clue.is_core.is_(True))
        .order_by(Clue.id)
    ).all()
    vote_reveals = [
        VoteReveal(
            vote_id=vote.id,
            voter_game_character_id=vote.voter_game_character_id,
            voter_name=by_id[vote.voter_game_character_id].character.name,
            target_game_character_id=vote.target_game_character_id,
            target_name=by_id[vote.target_game_character_id].character.name,
            reason=vote.decision_reason,
            created_at=vote.created_at,
        )
        for vote in votes
    ]
    return GameEndingRead(
        game_id=game.id,
        script_id=game.script_id,
        culprit_game_character_id=resolution.culprit_game_character_id,
        culprit_name=by_id[resolution.culprit_game_character_id].character.name,
        vote_result=resolution.vote_result,
        accused_game_character_id=resolution.accused_game_character_id,
        is_tie=resolution.is_tie,
        human_vote_target_id=resolution.human_vote_target_id,
        human_identified_culprit=resolution.human_identified_culprit,
        case_outcome=resolution.case_outcome,
        ending_narrative=resolution.ending_narrative,
        resolved_at=resolution.resolved_at,
        truth=truth,
        canonical_timeline=timeline,
        key_clues=[
            EndingClue(
                clue_id=clue.id,
                name=clue.name,
                description=clue.description,
                act=clue.act,
                location=clue.location,
            )
            for clue in key_clues
        ],
        votes=vote_reveals,
    )


def _resolved_game(
    db: Session, game_id: int
) -> tuple[GameSession, GameResolution, ScriptCanonicalData]:
    game = db.get(GameSession, game_id)
    if game is None:
        raise LookupError("Game not found")
    resolution = db.get(GameResolution, game_id)
    if (
        game.status != "finished"
        or game.current_phase != "ending"
        or resolution is None
    ):
        raise GameRuleError("Ending is unavailable until the game is resolved")
    if resolution.script_id != game.script_id:
        raise GameRuleError("Resolution does not match the game's script")
    canonical = db.get(ScriptCanonicalData, game.script_id)
    if canonical is None:
        raise GameRuleError("Canonical Truth is missing for this script")
    return game, resolution, canonical


def _ending_narrative(vote_result: str, culprit_name: str, summary: str) -> str:
    if vote_result == "tie":
        outcome = "投票出现平局，没有形成唯一指认。"
    elif vote_result == "culprit_identified":
        outcome = f"全体投票正确指认了真正的凶手：{culprit_name}。"
    else:
        outcome = f"全体投票未能正确指认凶手。真正的凶手是：{culprit_name}。"
    return f"{outcome}{summary}"
