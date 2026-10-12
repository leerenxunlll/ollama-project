"""Read and acknowledge phase-unlocked script chapters."""

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.game.state_machine import GameRuleError, unlocked_script_chapter_phases
from app.models import (
    Character,
    CharacterScriptChapter,
    GameCharacter,
    GameSession,
    SharedScriptChapter,
)
from app.schemas.story import IntroAcknowledgementRead, ScriptChapterRead


def get_public_chapters(db: Session, game_id: int) -> list[ScriptChapterRead]:
    """Return only public chapters unlocked in this game."""
    game = _get_game(db, game_id)
    phases = unlocked_script_chapter_phases(game.status, game.current_phase)
    chapters = db.scalars(
        select(SharedScriptChapter)
        .where(
            SharedScriptChapter.script_id == game.script_id,
            SharedScriptChapter.unlock_phase.in_(phases),
        )
        .order_by(SharedScriptChapter.chapter_order, SharedScriptChapter.id)
    ).all()
    return [_read_chapter(chapter) for chapter in chapters]


def get_human_chapters(db: Session, game_id: int) -> list[ScriptChapterRead]:
    """Return unlocked private chapters for the one selected human character."""
    game = _get_game(db, game_id)
    human = _get_human_character(db, game_id)
    phases = unlocked_script_chapter_phases(game.status, game.current_phase)
    chapters = db.scalars(
        select(CharacterScriptChapter)
        .join(Character, Character.id == CharacterScriptChapter.character_id)
        .where(
            CharacterScriptChapter.character_id == human.character_id,
            Character.script_id == game.script_id,
            CharacterScriptChapter.unlock_phase.in_(phases),
        )
        .order_by(CharacterScriptChapter.chapter_order, CharacterScriptChapter.id)
    ).all()
    return [_read_chapter(chapter) for chapter in chapters]


def acknowledge_human_intro(db: Session, game_id: int) -> IntroAcknowledgementRead:
    """Record the selected player's intro confirmation idempotently."""
    game = _get_game(db, game_id)
    if game.status != "ready" or game.current_phase != "intro":
        raise GameRuleError("Intro can only be acknowledged before the game starts")
    _get_human_character(db, game_id)

    if game.human_intro_acknowledged_at is None:
        db.execute(
            update(GameSession)
            .where(
                GameSession.id == game.id,
                GameSession.status == "ready",
                GameSession.current_phase == "intro",
                GameSession.human_intro_acknowledged_at.is_(None),
            )
            .values(human_intro_acknowledged_at=datetime.now(timezone.utc))
        )
        db.commit()
        db.refresh(game)
    if game.status != "ready" or game.current_phase != "intro":
        raise GameRuleError("Intro can only be acknowledged before the game starts")
    if game.human_intro_acknowledged_at is None:
        raise GameRuleError("Intro acknowledgement could not be saved")
    return IntroAcknowledgementRead(
        game_id=game.id,
        acknowledged=True,
        acknowledged_at=game.human_intro_acknowledged_at,
    )


def has_human_intro_chapter(db: Session, script_id: int, character_id: int) -> bool:
    """Check whether start must wait for this reusable character's intro."""
    return (
        db.scalar(
            select(CharacterScriptChapter.id)
            .join(Character, Character.id == CharacterScriptChapter.character_id)
            .where(
                Character.script_id == script_id,
                CharacterScriptChapter.character_id == character_id,
                CharacterScriptChapter.unlock_phase == "intro",
            )
            .limit(1)
        )
        is not None
    )


def _get_game(db: Session, game_id: int) -> GameSession:
    game = db.get(GameSession, game_id)
    if game is None:
        raise LookupError("Game not found")
    return game


def _get_human_character(db: Session, game_id: int) -> GameCharacter:
    humans = list(
        db.scalars(
            select(GameCharacter)
            .where(
                GameCharacter.game_session_id == game_id,
                GameCharacter.controller_type == "human",
            )
            .order_by(GameCharacter.id)
        ).all()
    )
    if len(humans) != 1:
        raise GameRuleError("Human character is not selected")
    return humans[0]


def _read_chapter(
    chapter: SharedScriptChapter | CharacterScriptChapter,
) -> ScriptChapterRead:
    return ScriptChapterRead(
        chapter_id=chapter.id,
        title=chapter.title,
        chapter_order=chapter.chapter_order,
        unlock_phase=chapter.unlock_phase,
        content=chapter.content,
    )
