"""Verify Phase 11 upgrade paths from empty and Phase 10 SQLite databases."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine

from app.core.config import settings


def alembic_config() -> Config:
    project_root = Path(__file__).resolve().parents[1]
    return Config(str(project_root / "alembic.ini"))


def test_empty_database_upgrades_to_phase11_head(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "empty-phase11.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{database_path}")
    config = alembic_config()

    command.upgrade(config, "head")
    command.check(config)

    with create_engine(settings.database_url).connect() as connection:
        assert (
            connection.exec_driver_sql(
                "SELECT version_num FROM alembic_version"
            ).scalar_one()
            == "20261015_phase11_voting_replay"
        )
        tables = {
            row[0]
            for row in connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert "game_resolutions" in tables
        for table_name, expected_columns in {
            "messages": {"phase"},
            "game_character_clues": {"phase"},
            "game_clue_disclosures": {"phase"},
            "votes": {"decision_reason"},
        }.items():
            columns = {
                row[1]
                for row in connection.exec_driver_sql(
                    f"PRAGMA table_info({table_name})"
                )
            }
            assert expected_columns.issubset(columns)


def test_phase10_database_upgrades_without_losing_game_data(
    tmp_path, monkeypatch
) -> None:
    database_path = tmp_path / "phase10-existing.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{database_path}")
    config = alembic_config()
    command.upgrade(config, "20261013_phase10_evidence")
    engine = create_engine(settings.database_url)

    with engine.begin() as connection:
        script_id = connection.exec_driver_sql(
            "INSERT INTO scripts (title, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?)",
            ("Phase 10 retained script", "ready", "2026-10-15", "2026-10-15"),
        ).lastrowid
        game_id = connection.exec_driver_sql(
            "INSERT INTO game_sessions "
            "(script_id, status, current_phase, random_seed, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (script_id, "in_progress", "vote", 51, "2026-10-15"),
        ).lastrowid

    command.upgrade(config, "head")
    command.check(config)

    with engine.connect() as connection:
        assert (
            connection.exec_driver_sql(
                "SELECT title FROM scripts WHERE id = ?", (script_id,)
            ).scalar_one()
            == "Phase 10 retained script"
        )
        assert (
            connection.exec_driver_sql(
                "SELECT current_phase FROM game_sessions WHERE id = ?", (game_id,)
            ).scalar_one()
            == "vote"
        )
        assert (
            connection.exec_driver_sql(
                "SELECT version_num FROM alembic_version"
            ).scalar_one()
            == "20261015_phase11_voting_replay"
        )
    engine.dispose()
