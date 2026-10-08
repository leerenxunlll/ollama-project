"""File-backed SQLite tests for atomic Director apply claims."""

from datetime import datetime, timedelta, timezone
from threading import Event, Thread
from typing import Any

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker

from app.agents.character_agent import CharacterReply
from app.db.base import Base
from app.models import (
    Character,
    DirectorRecommendationRecord,
    GameCharacter,
    GameSession,
    Message,
    Script,
)
from app.schemas.ai import CharacterEmotion, CharacterIntent
from app.schemas.director import DirectorAction
from app.services import director_actions
from app.services.director_actions import (
    DirectorApplyConflict,
    apply_director_recommendation,
)


class BlockingCharacterAgent:
    """Pause one Character response while a second apply request arrives."""

    def __init__(self, entered: Event, release: Event) -> None:
        self.entered = entered
        self.release = release
        self.calls = 0

    def respond(
        self, _context: Any, _interaction: Any, _user_id: str
    ) -> CharacterReply:
        self.calls += 1
        self.entered.set()
        if not self.release.wait(timeout=10):
            raise TimeoutError("Test did not release the Character response")
        return CharacterReply(
            speech="这件事我可以公开说明。",
            inner_os="并发测试内心状态。",
            emotion=CharacterEmotion.CALM,
            intent=CharacterIntent.OBSERVE,
            memory_updates=[],
        )


@pytest.fixture
def apply_database(tmp_path):
    """Create one independent file-backed SQLite game and pending recommendation."""
    database_path = tmp_path / "director-apply.db"
    engine = create_engine(f"sqlite:///{database_path}", connect_args={"timeout": 10})

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as db:
        script = Script(title="并发测试", status="ready")
        db.add(script)
        db.flush()
        characters = [
            Character(
                script_id=script.id,
                name=f"角色{index}",
                identity="测试角色",
                public_background="公开背景",
                private_background="私有背景",
                personality="谨慎",
                speaking_style="简短",
                personal_goal="完成测试",
                is_killer=False,
            )
            for index in range(4)
        ]
        db.add_all(characters)
        db.flush()
        past = datetime.now(timezone.utc) - timedelta(minutes=5)
        game = GameSession(
            script_id=script.id,
            status="in_progress",
            current_phase="discussion_1",
            random_seed=17,
            started_at=past,
            phase_started_at=past,
        )
        db.add(game)
        db.flush()
        game_characters = [
            GameCharacter(
                game_session_id=game.id,
                character_id=character.id,
                controller_type="human" if index == 0 else "ai",
            )
            for index, character in enumerate(characters)
        ]
        db.add_all(game_characters)
        db.flush()
        recommendation = DirectorRecommendationRecord(
            game_session_id=game.id,
            pace="stalled",
            narrative_risk="low",
            recommended_action=DirectorAction.request_ai_speaker.value,
            target_game_character_id=game_characters[1].id,
            reason="测试时请求一名 AI 发言。",
        )
        db.add(recommendation)
        db.commit()
        ids = game.id, recommendation.id

    try:
        yield session_factory, ids
    finally:
        engine.dispose()


def test_concurrent_request_ai_speaker_claim_creates_one_public_message(
    apply_database,
) -> None:
    session_factory, (game_id, recommendation_id) = apply_database
    entered = Event()
    release = Event()
    agent = BlockingCharacterAgent(entered, release)
    results: list[object] = []
    errors: list[Exception] = []

    def first_apply() -> None:
        try:
            with session_factory() as db:
                results.append(
                    apply_director_recommendation(db, game_id, recommendation_id, agent)
                )
        except Exception as error:  # pragma: no cover - asserted after join
            errors.append(error)

    worker = Thread(target=first_apply, daemon=True)
    worker.start()
    try:
        assert entered.wait(timeout=5)
        with session_factory() as db:
            record = db.get(DirectorRecommendationRecord, recommendation_id)
            assert record.status == "applying"
            with pytest.raises(DirectorApplyConflict):
                apply_director_recommendation(db, game_id, recommendation_id, agent)
    finally:
        release.set()
        worker.join(timeout=10)

    assert not worker.is_alive()
    assert errors == []
    assert len(results) == 1
    assert results[0].status == "applied"
    assert agent.calls == 1
    with session_factory() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(Message)
                .where(
                    Message.game_session_id == game_id,
                    Message.channel_type == "public",
                )
            )
            == 1
        )


def test_concurrent_phase_advance_claim_advances_exactly_once(
    apply_database, monkeypatch: pytest.MonkeyPatch
) -> None:
    session_factory, (game_id, recommendation_id) = apply_database
    with session_factory() as db:
        record = db.get(DirectorRecommendationRecord, recommendation_id)
        record.recommended_action = DirectorAction.recommend_phase_advance.value
        record.target_game_character_id = None
        db.commit()

    entered = Event()
    release = Event()
    original_advance = director_actions.advance_game_phase

    def blocking_advance(*args, **kwargs):
        entered.set()
        if not release.wait(timeout=10):
            raise TimeoutError("Test did not release phase advancement")
        return original_advance(*args, **kwargs)

    monkeypatch.setattr(director_actions, "advance_game_phase", blocking_advance)
    results: list[object] = []
    errors: list[Exception] = []

    def first_apply() -> None:
        try:
            with session_factory() as db:
                results.append(
                    apply_director_recommendation(
                        db,
                        game_id,
                        recommendation_id,
                        BlockingCharacterAgent(Event(), Event()),
                    )
                )
        except Exception as error:  # pragma: no cover - asserted after join
            errors.append(error)

    worker = Thread(target=first_apply, daemon=True)
    worker.start()
    try:
        assert entered.wait(timeout=5)
        with session_factory() as db:
            with pytest.raises(DirectorApplyConflict):
                apply_director_recommendation(
                    db,
                    game_id,
                    recommendation_id,
                    BlockingCharacterAgent(Event(), Event()),
                )
    finally:
        release.set()
        worker.join(timeout=10)

    assert not worker.is_alive()
    assert errors == []
    assert len(results) == 1
    assert results[0].status == "applied"
    with session_factory() as db:
        game = db.get(GameSession, game_id)
        assert game.current_phase == "act_2"
        assert (
            db.scalar(
                select(func.count())
                .select_from(Message)
                .where(
                    Message.game_session_id == game_id,
                    Message.channel_type == "system",
                    Message.content == "进入第二幕。",
                )
            )
            == 1
        )
