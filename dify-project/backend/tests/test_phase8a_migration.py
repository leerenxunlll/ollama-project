"""Verify Phase 7 data survives the Phase 8A SQLite schema migration."""

from datetime import datetime, timezone
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, insert, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    Character,
    CharacterMemory,
    CharacterScriptChapter,
    CharacterThought,
    Clue,
    DirectorRecommendationRecord,
    GameCharacter,
    GameCharacterClue,
    GameSession,
    Message,
    Script,
    SharedScriptChapter,
    Vote,
)


def _alembic_config() -> Config:
    """Use project migrations against the isolated test database."""
    project_root = Path(__file__).resolve().parents[1]
    return Config(str(project_root / "alembic.ini"))


def test_phase7_records_survive_upgrade_to_phase8a(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "phase7.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{database_path}")
    config = _alembic_config()
    command.upgrade(config, "20261007_phase7_atomic_apply")

    engine = create_engine(settings.database_url)
    now = datetime.now(timezone.utc)
    with Session(engine) as db:
        script = Script(title="Phase 7 migration fixture", status="ready")
        db.add(script)
        db.flush()
        characters = [
            Character(
                script_id=script.id,
                name=f"Migration role {index}",
                identity="Investigator",
                public_background="Public background",
                private_background="Private background",
                personality="Careful",
                speaking_style="Brief",
                personal_goal="Preserve migration data",
            )
            for index in range(4)
        ]
        clue = Clue(
            script_id=script.id,
            name="Migration clue",
            description="A clue retained across schema changes.",
            act="act_1",
            location="Archive",
            is_core=True,
            importance=3,
        )
        db.add_all([*characters, clue])
        db.flush()

        game_id = db.execute(
            insert(GameSession.__table__).values(
                script_id=script.id,
                status="in_progress",
                current_phase="intro",
                random_seed=52,
                created_at=now,
                started_at=now,
                phase_started_at=now,
            )
        ).inserted_primary_key[0]
        game_characters = [
            GameCharacter(
                game_session_id=game_id,
                character_id=character.id,
                controller_type="human" if index == 0 else "ai",
            )
            for index, character in enumerate(characters)
        ]
        db.add_all(game_characters)
        db.flush()
        message = Message(
            game_session_id=game_id,
            sender_game_character_id=game_characters[1].id,
            channel_type="public",
            content="Phase 7 public message sentinel",
        )
        db.add(message)
        db.flush()
        db.add_all(
            [
                GameCharacterClue(
                    game_character_id=game_characters[1].id,
                    clue_id=clue.id,
                    source="migration fixture",
                ),
                CharacterThought(
                    game_session_id=game_id,
                    game_character_id=game_characters[1].id,
                    ai_message_id=message.id,
                    inner_os="Phase 7 thought sentinel",
                    emotion="calm",
                    intent="observe",
                ),
                CharacterMemory(
                    game_session_id=game_id,
                    game_character_id=game_characters[1].id,
                    content="Phase 7 memory sentinel",
                    importance=3,
                    source_message_id=message.id,
                ),
                Vote(
                    game_session_id=game_id,
                    voter_game_character_id=game_characters[0].id,
                    target_game_character_id=game_characters[1].id,
                ),
                DirectorRecommendationRecord(
                    game_session_id=game_id,
                    pace="on_track",
                    narrative_risk="low",
                    recommended_action="no_action",
                    reason="Phase 7 recommendation sentinel",
                    status="applied",
                ),
            ]
        )
        script_id = script.id
        db.commit()

    command.upgrade(config, "head")
    command.check(config)

    with Session(engine) as db:
        assert (
            db.scalar(select(func.count(Script.id)).where(Script.id == script_id)) == 1
        )
        assert (
            db.scalar(
                select(func.count(Character.id)).where(Character.script_id == script_id)
            )
            == 4
        )
        assert (
            db.scalar(select(func.count(Clue.id)).where(Clue.script_id == script_id))
            == 1
        )
        assert (
            db.scalar(
                select(func.count(GameSession.id)).where(GameSession.id == game_id)
            )
            == 1
        )
        assert (
            db.scalar(
                select(func.count(GameCharacter.id)).where(
                    GameCharacter.game_session_id == game_id
                )
            )
            == 4
        )
        assert (
            db.scalar(
                select(func.count(Message.id)).where(Message.game_session_id == game_id)
            )
            == 1
        )
        assert (
            db.scalar(
                select(func.count(CharacterThought.id)).where(
                    CharacterThought.game_session_id == game_id
                )
            )
            == 1
        )
        assert (
            db.scalar(
                select(func.count(CharacterMemory.id)).where(
                    CharacterMemory.game_session_id == game_id
                )
            )
            == 1
        )
        assert db.scalar(select(func.count(GameCharacterClue.id))) == 1
        assert (
            db.scalar(
                select(func.count(Vote.id)).where(Vote.game_session_id == game_id)
            )
            == 1
        )
        assert (
            db.scalar(
                select(func.count(DirectorRecommendationRecord.id)).where(
                    DirectorRecommendationRecord.game_session_id == game_id
                )
            )
            == 1
        )
        assert db.get(GameSession, game_id).human_intro_acknowledged_at is None
        assert (
            db.scalar(
                select(func.count(SharedScriptChapter.id)).where(
                    SharedScriptChapter.script_id == script_id
                )
            )
            == 0
        )
        assert db.scalar(select(func.count(CharacterScriptChapter.id))) == 0
    engine.dispose()
