"""Migration checks for empty and populated SQLite databases."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.base import Base
from app.models import Character, GameCharacter, GameSession, Message
from app.services.seed import seed_development_data


def _alembic_config() -> Config:
    """Use the repository migration configuration in an isolated test DB."""
    project_root = Path(__file__).resolve().parents[1]
    return Config(str(project_root / "alembic.ini"))


def test_empty_database_upgrades_to_head_and_matches_models(
    tmp_path: Path, monkeypatch
) -> None:
    database_path = tmp_path / "empty.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{database_path}")
    alembic_config = _alembic_config()

    command.upgrade(alembic_config, "head")
    command.check(alembic_config)

    engine = create_engine(settings.database_url)
    assert {"character_thoughts", "character_memories"}.issubset(
        inspect(engine).get_table_names()
    )
    engine.dispose()


def test_phase4_database_upgrade_preserves_existing_game_data(
    tmp_path: Path, monkeypatch
) -> None:
    database_path = tmp_path / "phase4.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{database_path}")
    engine = create_engine(settings.database_url)
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        script = seed_development_data(db)
        game = GameSession(script_id=script.id, status="ready", random_seed=123)
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
            sender_game_character_id=game_characters[1].id,
            channel_type="private",
            receiver_game_character_id=game_characters[0].id,
            content="preserved phase4 message",
        )
        db.add(message)
        db.commit()
        game_id = game.id
        message_id = message.id

    with engine.begin() as connection:
        connection.execute(text("DROP TABLE character_memories"))
        connection.execute(text("DROP TABLE character_thoughts"))
        connection.execute(text("DROP INDEX uq_game_characters_session_id_id"))
        connection.execute(text("DROP INDEX uq_messages_session_id_id"))
        connection.execute(text("DROP INDEX uq_messages_session_id_id_sender"))

    alembic_config = _alembic_config()
    command.stamp(alembic_config, "20261005_phase3")
    command.upgrade(alembic_config, "head")
    command.check(alembic_config)

    with engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT COUNT(*) FROM game_sessions WHERE id = :game_id"),
                {"game_id": game_id},
            )
            == 1
        )
        assert (
            connection.scalar(
                text(
                    "SELECT COUNT(*) FROM messages "
                    "WHERE id = :message_id AND content = 'preserved phase4 message'"
                ),
                {"message_id": message_id},
            )
            == 1
        )
    engine.dispose()
