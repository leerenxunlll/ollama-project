"""Verify the Phase 9 migration on isolated SQLite databases."""

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
    DirectorRecommendationRecord,
    GameCharacter,
    GameSession,
    Message,
)
from app.services.seed import seed_development_data


def _config() -> Config:
    backend_root = Path(__file__).resolve().parents[1]
    return Config(str(backend_root / "alembic.ini"))


def test_empty_sqlite_database_upgrades_to_phase9_head(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "empty-phase9.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{database_path}")

    command.upgrade(_config(), "head")

    inspector = inspect(create_engine(settings.database_url))
    tables = set(inspector.get_table_names())
    assert {
        "game_runtime_states",
        "game_phase_acknowledgements",
        "game_runtime_action_logs",
    }.issubset(tables)
    assert "source_phase" in {
        column["name"] for column in inspector.get_columns("director_recommendations")
    }
    command.check(_config())


def test_phase8c_database_upgrade_preserves_gameplay_records(
    tmp_path, monkeypatch
) -> None:
    database_path = tmp_path / "phase8c-existing.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{database_path}")
    engine = create_engine(settings.database_url)
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)

    with Session(engine) as db:
        script = seed_development_data(db)
        templates = db.scalars(
            select(Character)
            .where(Character.script_id == script.id)
            .order_by(Character.id)
        ).all()
        game = GameSession(
            script_id=script.id,
            status="in_progress",
            current_phase="discussion_1",
            random_seed=902,
            started_at=now,
            phase_started_at=now,
        )
        db.add(game)
        db.flush()
        characters = [
            GameCharacter(
                game_session_id=game.id,
                character_id=template.id,
                controller_type="human" if index == 0 else "ai",
            )
            for index, template in enumerate(templates)
        ]
        db.add_all(characters)
        db.flush()
        message = Message(
            game_session_id=game.id,
            sender_game_character_id=characters[0].id,
            channel_type="public",
            content="Phase 8C record survives.",
        )
        recommendation = DirectorRecommendationRecord(
            game_session_id=game.id,
            pace="on_track",
            narrative_risk="low",
            recommended_action="no_action",
            reason="Existing record.",
            status="applied",
        )
        db.add_all([message, recommendation])
        db.commit()
        game_id = game.id
        message_id = message.id
        recommendation_id = recommendation.id
        script_id = script.id

    with engine.begin() as connection:
        connection.execute(text("DROP TABLE game_runtime_action_logs"))
        connection.execute(text("DROP TABLE game_phase_acknowledgements"))
        connection.execute(text("DROP TABLE game_runtime_states"))
        connection.execute(
            text(
                "ALTER TABLE director_recommendations "
                "DROP COLUMN source_last_public_message_id"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE director_recommendations "
                "DROP COLUMN source_phase_started_at"
            )
        )
        connection.execute(
            text("ALTER TABLE director_recommendations DROP COLUMN source_phase")
        )

    command.stamp(_config(), "20261012_phase8c_mapping")
    command.upgrade(_config(), "head")
    command.check(_config())

    with Session(engine) as db:
        assert db.get(GameSession, game_id) is not None
        assert db.get(Message, message_id).content == "Phase 8C record survives."
        assert (
            db.get(DirectorRecommendationRecord, recommendation_id).status == "applied"
        )
        assert db.get(GameSession, game_id).script_id == script_id
        assert inspect(engine).has_table("game_runtime_states")
        assert db.get(GameSession, game_id).runtime_state is None
    engine.dispose()
