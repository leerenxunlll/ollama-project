"""HTTP endpoints for starting and reading game sessions."""

import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.db.session import get_db
from app.game.character_selection import select_human_character
from app.models import Character, GameCharacter, GameSession, Script
from app.schemas.context import CharacterContext
from app.schemas.game import (
    CharacterSelection,
    GameCreate,
    GameRead,
    MyCharacterRead,
    SelectableCharacterRead,
)
from app.services.character_context import build_character_context

router = APIRouter()


@router.get("/games", response_model=list[GameRead])
def list_games(db: Session = Depends(get_db)) -> list[GameSession]:
    """List game sessions so the development page can select one."""
    return list(
        db.scalars(
            select(GameSession)
            .options(
                selectinload(GameSession.game_characters).selectinload(
                    GameCharacter.character
                )
            )
            .order_by(GameSession.created_at.desc(), GameSession.id.desc())
        ).all()
    )


@router.post("/games", response_model=GameRead, status_code=status.HTTP_201_CREATED)
def create_game(
    payload: GameCreate,
    db: Session = Depends(get_db),
) -> GameSession:
    """Create a game session only from a ready script with four characters."""
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
        status="waiting_for_character_selection",
        current_phase="introduction",
        random_seed=secrets.randbits(32),
    )
    db.add(game)
    db.flush()
    db.add_all(
        [
            GameCharacter(
                game_session_id=game.id,
                character_id=character.id,
                controller_type=None,
            )
            for character in characters
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


@router.get(
    "/games/{game_id}/characters/selectable",
    response_model=list[SelectableCharacterRead],
)
def get_selectable_characters(
    game_id: int,
    db: Session = Depends(get_db),
) -> list[SelectableCharacterRead]:
    """Return public character cards while a game waits for player choice."""
    game = db.get(GameSession, game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    if game.status != "waiting_for_character_selection":
        raise HTTPException(status_code=409, detail="Character selection is locked")

    characters = db.scalars(
        select(GameCharacter)
        .where(GameCharacter.game_session_id == game_id)
        .options(selectinload(GameCharacter.character))
        .order_by(GameCharacter.id)
    ).all()
    return [
        SelectableCharacterRead(
            game_character_id=game_character.id,
            character_id=game_character.character.id,
            name=game_character.character.name,
            age=game_character.character.age,
            identity=game_character.character.identity,
            public_background=game_character.character.public_background,
            personality=game_character.character.personality,
            speaking_style=game_character.character.speaking_style,
        )
        for game_character in characters
    ]


@router.post("/games/{game_id}/select-character", response_model=GameRead)
def choose_character(
    game_id: int,
    payload: CharacterSelection,
    db: Session = Depends(get_db),
) -> GameSession:
    """Assign the player once, then lock all controller assignments."""
    game = db.scalar(
        select(GameSession)
        .where(GameSession.id == game_id)
        .options(selectinload(GameSession.game_characters))
    )
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")

    try:
        select_human_character(db, game, payload.game_character_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

    db.commit()
    return db.scalar(
        select(GameSession)
        .where(GameSession.id == game_id)
        .options(
            selectinload(GameSession.game_characters).selectinload(
                GameCharacter.character
            )
        )
    )


@router.get("/games/{game_id}/me/character", response_model=MyCharacterRead)
def get_my_character(game_id: int, db: Session = Depends(get_db)) -> MyCharacterRead:
    """Return the selected human's role card; authentication is not implemented."""
    game = db.get(GameSession, game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")

    human_characters = list(
        db.scalars(
            select(GameCharacter)
            .where(
                GameCharacter.game_session_id == game_id,
                GameCharacter.controller_type == "human",
            )
            .options(selectinload(GameCharacter.character))
        ).all()
    )
    if len(human_characters) != 1:
        raise HTTPException(status_code=409, detail="Human character is not selected")

    runtime_character = human_characters[0]
    character = runtime_character.character
    return MyCharacterRead(
        game_character_id=runtime_character.id,
        character_id=character.id,
        name=character.name,
        age=character.age,
        identity=character.identity,
        public_background=character.public_background,
        private_background=character.private_background,
        personality=character.personality,
        speaking_style=character.speaking_style,
        personal_goal=character.personal_goal,
        current_emotion=runtime_character.current_emotion,
        current_goal=runtime_character.current_goal,
    )


@router.get(
    "/games/{game_id}/characters/{game_character_id}/context",
    response_model=CharacterContext,
)
def get_character_context(
    game_id: int,
    game_character_id: int,
    db: Session = Depends(get_db),
) -> CharacterContext:
    """Development-only context preview for future Character Agent debugging."""
    if settings.app_env != "development":
        raise HTTPException(status_code=404, detail="Not found")
    try:
        return build_character_context(db, game_id, game_character_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
