"""Verify Phase 8C migration creation and preservation of prior game data."""

from datetime import datetime, timezone
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import GameSession, Script, ScriptDraft


def alembic_config() -> Config:
    project_root = Path(__file__).resolve().parents[1]
    return Config(str(project_root / "alembic.ini"))


def test_empty_database_upgrades_to_phase8c_head(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "empty-phase8c.db"
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
            == "20261013_phase10_evidence"
        )
        tables = {
            row[0]
            for row in connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert {
            "script_drafts",
            "script_review_runs",
            "script_revision_records",
            "script_canonical_data",
        }.issubset(tables)


def test_phase8b_draft_and_published_game_data_survive_upgrade(
    tmp_path, monkeypatch
) -> None:
    database_path = tmp_path / "phase8b-retained.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{database_path}")
    config = alembic_config()
    command.upgrade(config, "20261008_phase8b")
    engine = create_engine(settings.database_url)
    now = datetime.now(timezone.utc).isoformat()

    with engine.begin() as connection:
        script_id = connection.exec_driver_sql(
            "INSERT INTO scripts "
            "(title, status, created_at, updated_at) VALUES (?, ?, ?, ?)",
            ("Retained published Script", "ready", now, now),
        ).lastrowid
        game_id = connection.exec_driver_sql(
            "INSERT INTO game_sessions "
            "(script_id, status, current_phase, random_seed, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (script_id, "ready", "intro", 123, now),
        ).lastrowid
        draft_id = connection.exec_driver_sql(
            "INSERT INTO script_drafts "
            "(status, generation_request_json, chapter_packs_json, "
            "step_durations_seconds_json, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                "draft_complete",
                '{"theme":"test"}',
                '{"intro":{},"act_1":{},"act_2":{}}',
                "{}",
                now,
                now,
            ),
        ).lastrowid

    command.upgrade(config, "head")
    command.check(config)

    with Session(engine) as db:
        assert (
            db.scalar(select(func.count(Script.id)).where(Script.id == script_id)) == 1
        )
        assert (
            db.scalar(
                select(func.count(GameSession.id)).where(GameSession.id == game_id)
            )
            == 1
        )
        draft = db.get(ScriptDraft, draft_id)
        assert draft is not None
        assert draft.status == "draft_complete"
        assert draft.content_revision == 1
        assert draft.publication_status == "unpublished"
        assert draft.accepted_medium_issue_indexes_json == []
    engine.dispose()


def test_existing_phase8c_database_gets_missing_clue_event_mapping(
    tmp_path, monkeypatch
) -> None:
    database_path = tmp_path / "phase8c-without-clue-map.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{database_path}")
    config = alembic_config()
    command.upgrade(config, "20261011_phase8c")
    engine = create_engine(settings.database_url)

    with engine.begin() as connection:
        connection.exec_driver_sql(
            "ALTER TABLE script_canonical_data DROP COLUMN clue_event_keys_json"
        )

    command.upgrade(config, "head")
    command.check(config)

    with engine.connect() as connection:
        columns = {
            row[1]
            for row in connection.exec_driver_sql(
                "PRAGMA table_info(script_canonical_data)"
            )
        }
        revision = connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one()
    assert "clue_event_keys_json" in columns
    assert revision == "20261013_phase10_evidence"
    engine.dispose()
