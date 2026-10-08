"""Verify Phase 6 SQLite data upgrades to the Phase 7 schema unchanged."""

from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.base import Base
from app.models import (
    Character,
    CharacterMemory,
    CharacterThought,
    GameCharacter,
    GameSession,
    Message,
)
from app.services.seed import seed_development_data


def _alembic_config() -> Config:
    project_root = Path(__file__).resolve().parents[1]
    return Config(str(project_root / "alembic.ini"))


def test_phase6_database_upgrade_adds_flow_and_director_tables_preserving_data(
    tmp_path: Path, monkeypatch
) -> None:
    database_path = tmp_path / "phase6.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{database_path}")
    engine = create_engine(settings.database_url)
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        script = seed_development_data(db)
        game = GameSession(
            script_id=script.id,
            status="in_progress",
            current_phase="discussion_1",
            random_seed=101,
            started_at=datetime.now(timezone.utc),
            phase_started_at=datetime.now(timezone.utc),
        )
        db.add(game)
        db.flush()
        characters = db.scalars(
            select(Character)
            .where(Character.script_id == script.id)
            .order_by(Character.id)
        ).all()
        game_characters = [
            GameCharacter(
                game_session_id=game.id,
                character_id=character.id,
                controller_type="ai",
            )
            for character in characters
        ]
        db.add_all(game_characters)
        db.flush()
        message = Message(
            game_session_id=game.id,
            sender_game_character_id=game_characters[0].id,
            channel_type="public",
            content="phase6 message preserved",
        )
        db.add(message)
        db.flush()
        db.add_all(
            [
                CharacterThought(
                    game_session_id=game.id,
                    game_character_id=game_characters[0].id,
                    ai_message_id=message.id,
                    inner_os="phase6 thought preserved",
                    emotion="calm",
                    intent="observe",
                ),
                CharacterMemory(
                    game_session_id=game.id,
                    game_character_id=game_characters[0].id,
                    content="phase6 memory preserved",
                    importance=3,
                    source_message_id=message.id,
                ),
            ]
        )
        db.commit()
        game_id = game.id
        message_id = message.id
        script_id = script.id
        started_at = game.started_at

    with engine.begin() as connection:
        connection.execute(text("DROP TABLE director_recommendations"))
        connection.execute(text("DROP TABLE votes"))
        connection.execute(
            text("ALTER TABLE game_sessions DROP COLUMN phase_started_at")
        )

    config = _alembic_config()
    command.stamp(config, "20261005_phase5")
    command.upgrade(config, "head")
    command.check(config)

    inspector = inspect(engine)
    assert {"votes", "director_recommendations"}.issubset(inspector.get_table_names())
    assert "phase_started_at" in {
        column["name"] for column in inspector.get_columns("game_sessions")
    }
    status_check = next(
        constraint["sqltext"]
        for constraint in inspector.get_check_constraints("director_recommendations")
        if constraint["name"] == "ck_director_recommendations_status"
    )
    assert "applying" in status_check
    with engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT COUNT(*) FROM scripts WHERE id = :script_id"),
                {"script_id": script_id},
            )
            == 1
        )
        assert (
            connection.scalar(
                text("SELECT COUNT(*) FROM game_sessions WHERE id = :game_id"),
                {"game_id": game_id},
            )
            == 1
        )
        assert (
            connection.scalar(
                text("SELECT content FROM messages WHERE id = :message_id"),
                {"message_id": message_id},
            )
            == "phase6 message preserved"
        )
        assert (
            connection.scalar(
                text(
                    "SELECT inner_os FROM character_thoughts WHERE ai_message_id = :id"
                ),
                {"id": message_id},
            )
            == "phase6 thought preserved"
        )
        assert (
            connection.scalar(
                text(
                    "SELECT content FROM character_memories "
                    "WHERE source_message_id = :id"
                ),
                {"id": message_id},
            )
            == "phase6 memory preserved"
        )
        upgraded_phase_time = connection.scalar(
            text("SELECT phase_started_at FROM game_sessions WHERE id = :game_id"),
            {"game_id": game_id},
        )
        assert upgraded_phase_time is not None
        assert str(started_at.date()) in upgraded_phase_time
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO director_recommendations "
                "(game_session_id, pace, narrative_risk, recommended_action, "
                "reason, status, created_at) VALUES "
                "(:game_id, 'stalled', 'low', 'no_action', 'claim test', "
                "'applying', :created_at)"
            ),
            {"game_id": game_id, "created_at": datetime.now(timezone.utc)},
        )
    with engine.begin() as connection:
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "INSERT INTO director_recommendations "
                    "(game_session_id, pace, narrative_risk, recommended_action, "
                    "reason, status, created_at) VALUES "
                    "(:game_id, 'stalled', 'low', 'no_action', 'invalid test', "
                    "'unknown', :created_at)"
                ),
                {"game_id": game_id, "created_at": datetime.now(timezone.utc)},
            )
    engine.dispose()
