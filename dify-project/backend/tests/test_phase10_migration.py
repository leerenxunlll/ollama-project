"""Verify the Phase 10 migration and its direct-knowledge backfill."""

from datetime import datetime, timezone
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.base import Base
from app.models import (
    Character,
    Clue,
    GameCharacter,
    GameCharacterClue,
    GameCharacterClueKnowledge,
    GameSession,
)
from app.services.seed import seed_development_data


def _config() -> Config:
    backend_root = Path(__file__).resolve().parents[1]
    return Config(str(backend_root / "alembic.ini"))


def test_empty_sqlite_database_upgrades_to_phase10_head(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "empty-phase10.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{database_path}")

    command.upgrade(_config(), "head")

    engine = create_engine(settings.database_url)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert {
        "game_character_clue_knowledge",
        "game_clue_disclosures",
        "game_clue_disclosure_attempts",
    }.issubset(tables)
    assert "last_processed_public_clue_disclosure_id" in {
        column["name"] for column in inspector.get_columns("game_runtime_states")
    }
    assert {
        index["name"] for index in inspector.get_indexes("game_clue_disclosures")
    } >= {
        "uq_public_clue_disclosure",
        "uq_private_clue_disclosure",
    }
    command.check(_config())
    engine.dispose()


def test_phase9_database_preserves_acquisitions_and_backfills_knowledge(
    tmp_path, monkeypatch
) -> None:
    database_path = tmp_path / "phase9-existing.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{database_path}")
    engine = create_engine(settings.database_url)
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)

    with Session(engine) as db:
        script = seed_development_data(db)
        characters = db.scalars(
            select(Character)
            .where(Character.script_id == script.id)
            .order_by(Character.id)
        ).all()
        game = GameSession(
            script_id=script.id,
            status="in_progress",
            current_phase="discussion_1",
            random_seed=1001,
            started_at=now,
            phase_started_at=now,
        )
        db.add(game)
        db.flush()
        runtime_characters = [
            GameCharacter(
                game_session_id=game.id,
                character_id=character.id,
                controller_type="human" if index == 0 else "ai",
            )
            for index, character in enumerate(characters)
        ]
        db.add_all(runtime_characters)
        db.flush()
        clue = db.scalar(select(Clue).where(Clue.script_id == script.id))
        acquisition = GameCharacterClue(
            game_character_id=runtime_characters[0].id,
            clue_id=clue.id,
            source="investigation",
            discovered_at=now,
        )
        db.add(acquisition)
        db.commit()
        game_id = game.id
        human_game_character_id = runtime_characters[0].id
        clue_id = clue.id
        acquisition_id = acquisition.id

    with engine.begin() as connection:
        connection.execute(text("DROP TABLE game_clue_disclosure_attempts"))
        connection.execute(text("DROP TABLE game_character_clue_knowledge"))
        connection.execute(text("DROP TABLE game_clue_disclosures"))
        connection.execute(
            text(
                "ALTER TABLE game_runtime_states "
                "DROP COLUMN last_processed_public_clue_disclosure_id"
            )
        )

    command.stamp(_config(), "20261012_phase9_runtime")
    command.upgrade(_config(), "head")
    command.check(_config())

    with Session(engine) as db:
        assert db.get(GameSession, game_id) is not None
        assert db.get(GameCharacterClue, acquisition_id) is not None
        knowledge = db.scalar(
            select(GameCharacterClueKnowledge).where(
                GameCharacterClueKnowledge.game_session_id == game_id,
                GameCharacterClueKnowledge.game_character_id == human_game_character_id,
                GameCharacterClueKnowledge.clue_id == clue_id,
            )
        )
        assert knowledge is not None
        assert knowledge.knowledge_source == "direct_acquisition"
        assert knowledge.first_known_at.replace(tzinfo=timezone.utc) == now
    engine.dispose()
