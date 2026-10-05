"""HTTP endpoints for starting and reading game sessions."""

import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models import Character, GameCharacter, GameSession, Script
from app.schemas.game import GameCreate, GameRead

router = APIRouter()


@router.post("/games", response_model=GameRead, status_code=status.HTTP_201_CREATED)
def create_game(
    payload: GameCreate,
    db: Session = Depends(get_db),
) -> GameSession:
    """Start a game only when the script is ready and has four characters."""
    script = db.get(Script, payload.script_id)
    if script is None:
        raise HTTPException(status_code=404, detail="Script not found")
    if script.status != "ready":
        raise HTTPException(status_code=409, detail="Script is not ready")

    characters = list(
        db.scalars(
            select(Character)
            .where(Character.script_id == script.id)
            .order_by(Character.id)
        ).all()
    )
    if len(characters) != 4:
        raise HTTPException(
            status_code=409,
            detail="A ready script must have exactly four characters",
        )

    game = GameSession(
        script_id=script.id,
        status="in_progress",
        current_phase="introduction",
        random_seed=secrets.randbits(32),
        started_at=datetime.now(timezone.utc),
    )
    db.add(game)
    db.flush()
    db.add_all(
        [
            GameCharacter(
                game_session_id=game.id,
                character_id=character.id,
                controller_type="human" if index == 0 else "ai",
            )
            for index, character in enumerate(characters)
        ]
    )
    db.commit()

    return db.scalar(
        select(GameSession)
        .where(GameSession.id == game.id)
        .options(
            selectinload(GameSession.game_characters).selectinload(
                GameCharacter.character
            )
        )
    )


@router.get("/games/{game_id}", response_model=GameRead)
def get_game(game_id: int, db: Session = Depends(get_db)) -> GameSession:
    """Return basic state and safe character summaries for one game."""
    game = db.scalar(
        select(GameSession)
        .where(GameSession.id == game_id)
        .options(
            selectinload(GameSession.game_characters).selectinload(
                GameCharacter.character
            )
        )
    )
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return game
