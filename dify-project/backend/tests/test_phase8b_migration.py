"""Verify the Writer draft migration preserves Phase 8A SQLite data."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    Character,
    CharacterScriptChapter,
    Clue,
    GameSession,
    Script,
    ScriptDraft,
    SharedScriptChapter,
)


def alembic_config() -> Config:
    project_root = Path(__file__).resolve().parents[1]
    return Config(str(project_root / "alembic.ini"))


def test_empty_database_upgrades_to_phase8b_head(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "empty-writer.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{database_path}")
    config = alembic_config()

    command.upgrade(config, "head")
    command.check(config)

    with create_engine(settings.database_url).connect() as connection:
        assert connection.exec_driver_sql("PRAGMA integrity_check").scalar_one() == "ok"
        assert (
            connection.exec_driver_sql(
                "SELECT version_num FROM alembic_version"
            ).scalar_one()
            == "20261012_phase9_runtime"
        )
        tables = {
            row[0]
            for row in connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert "script_drafts" in tables


def test_phase8a_script_and_game_data_survive_writer_migration(
    tmp_path, monkeypatch
) -> None:
    database_path = tmp_path / "phase8a-writer.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{database_path}")
    config = alembic_config()
    command.upgrade(config, "20261008_phase8a")
    engine = create_engine(settings.database_url)

    with Session(engine) as db:
        script = Script(title="Phase 8A retained script", status="ready")
        db.add(script)
        db.flush()
        character = Character(
            script_id=script.id,
            name="Retained role",
            identity="Witness",
            public_background="Public fact",
            private_background="Private fact",
            personality="Quiet",
            speaking_style="Measured",
            personal_goal="Keep the old secret",
        )
        clue = Clue(
            script_id=script.id,
            name="Retained clue",
            description="A paper fragment",
            act="act_1",
            location="Archive",
        )
        db.add_all([character, clue])
        db.flush()
        shared = SharedScriptChapter(
            script_id=script.id,
            chapter_order=1,
            unlock_phase="intro",
            title="Retained public intro",
            content="A public chapter sentinel.",
        )
        personal = CharacterScriptChapter(
            character_id=character.id,
            chapter_order=1,
            unlock_phase="intro",
            title="Retained private intro",
            content="A private chapter sentinel.",
        )
        game = GameSession(script_id=script.id, random_seed=18, status="ready")
        db.add_all([shared, personal, game])
        db.commit()
        script_id, character_id, game_id = script.id, character.id, game.id

    # Simulate a Phase 8A database built before the Writer model existed.
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE script_drafts")

    command.upgrade(config, "head")
    command.check(config)

    with Session(engine) as db:
        assert (
            db.scalar(select(func.count(Script.id)).where(Script.id == script_id)) == 1
        )
        assert (
            db.scalar(
                select(func.count(Character.id)).where(Character.id == character_id)
            )
            == 1
        )
        assert (
            db.scalar(
                select(func.count(SharedScriptChapter.id)).where(
                    SharedScriptChapter.script_id == script_id
                )
            )
            == 1
        )
        assert (
            db.scalar(
                select(func.count(CharacterScriptChapter.id)).where(
                    CharacterScriptChapter.character_id == character_id
                )
            )
            == 1
        )
        assert (
            db.scalar(
                select(func.count(GameSession.id)).where(GameSession.id == game_id)
            )
            == 1
        )
        assert db.scalar(select(func.count(ScriptDraft.id))) == 0
