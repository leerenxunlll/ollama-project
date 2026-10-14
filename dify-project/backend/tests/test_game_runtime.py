"""Focused regression tests for the bounded Phase 9 runtime."""

from datetime import datetime, timedelta, timezone
from threading import Event, Thread

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.agents.character_agent import CharacterReply
from app.db.base import Base
from app.game.runtime_policy import RUNTIME_POLICY
from app.models import (
    Character,
    Clue,
    DirectorRecommendationRecord,
    GameCharacter,
    GameCharacterClue,
    GameClueDisclosure,
    GamePhaseAcknowledgement,
    GameRuntimeActionLog,
    GameRuntimeState,
    GameSession,
    Message,
    Vote,
)
from app.schemas.ai import CharacterEmotion, CharacterIntent, PublicTurnRequest
from app.schemas.director import (
    DirectorAction,
    DirectorNarrativeRisk,
    DirectorPace,
    DirectorRecommendation,
)
from app.services.character_response import persist_character_reply
from app.services.game_runtime import (
    _director_event,
    acknowledge_current_phase,
    mark_runtime_ready,
    pause_game_runtime,
    run_runtime_tick,
    start_game_runtime,
)
from app.services.public_turn import run_proactive_speaker_step, send_public_turn
from app.services.runtime_guards import StaleRuntimeAction
from app.services.seed import seed_development_data


def _create_game(
    db: Session,
    *,
    phase: str = "discussion_1",
    now: datetime | None = None,
    status: str = "in_progress",
) -> tuple[GameSession, list[GameCharacter]]:
    current_time = now or datetime.now(timezone.utc)
    script = seed_development_data(db)
    game = GameSession(
        script_id=script.id,
        status=status,
        current_phase=phase,
        random_seed=901,
        started_at=current_time - timedelta(minutes=10),
        phase_started_at=current_time - timedelta(minutes=2),
    )
    db.add(game)
    db.flush()
    templates = db.scalars(
        select(Character).where(Character.script_id == script.id).order_by(Character.id)
    ).all()
    characters = [
        GameCharacter(
            game_session_id=game.id,
            character_id=template.id,
            controller_type="human" if index == 0 else "ai",
        )
        for index, template in enumerate(templates)
    ]
    db.add_all(characters)
    db.commit()
    db.refresh(game)
    for character in characters:
        db.refresh(character)
    return game, characters


def _recommendation(
    action: DirectorAction,
    *,
    target_id: int | None = None,
) -> DirectorRecommendation:
    return DirectorRecommendation(
        pace=DirectorPace.stalled,
        narrative_risk=DirectorNarrativeRisk.low,
        recommended_action=action,
        reason="A bounded test recommendation.",
        target_game_character_id=target_id,
    )


class StubDirector:
    def __init__(self, recommendation: DirectorRecommendation) -> None:
        self.recommendation = recommendation
        self.calls = 0
        self.contexts = []

    def analyze(self, context):
        self.calls += 1
        self.contexts.append(context)
        return self.recommendation


class StubCharacter:
    def __init__(self) -> None:
        self.calls = 0

    def respond(self, _context, _interaction, _user_id):
        self.calls += 1
        return CharacterReply(
            speech="我愿意补充我确认过的情况。",
            inner_os="先说能够核实的部分。",
            emotion=CharacterEmotion.CALM,
            intent=CharacterIntent.COOPERATE,
            memory_updates=[],
        )


class PhaseChangingCharacter(StubCharacter):
    def __init__(self, db: Session, game_id: int) -> None:
        super().__init__()
        self.db = db
        self.game_id = game_id

    def respond(self, context, interaction, user_id):
        game = self.db.get(GameSession, self.game_id)
        game.current_phase = "vote"
        self.db.commit()
        return super().respond(context, interaction, user_id)


def test_runtime_status_and_start_pause_endpoints_are_development_controls(
    client, db_session: Session
) -> None:
    game, _characters = _create_game(db_session)

    initial = client.get(f"/api/games/{game.id}/runtime")
    assert initial.status_code == 200
    assert initial.json()["runtime_status"] == "not_started"
    assert db_session.get(GameRuntimeState, game.id) is None

    started = client.post(f"/api/games/{game.id}/runtime/start")
    assert started.status_code == 200
    assert started.json()["runtime_status"] == "enabled"

    paused = client.post(f"/api/games/{game.id}/runtime/pause")
    assert paused.status_code == 200
    assert paused.json()["runtime_status"] == "paused"

    tick = client.post(f"/api/games/{game.id}/runtime/tick")
    assert tick.status_code == 200
    assert tick.json()["reason_code"] == "runtime_paused"


def test_disabled_or_not_started_runtime_never_calls_agents(
    db_session: Session,
) -> None:
    game, _characters = _create_game(db_session)
    director = StubDirector(_recommendation(DirectorAction.no_action))
    character_agent = StubCharacter()

    result = run_runtime_tick(db_session, game.id, director, character_agent)

    assert result.reason_code == "runtime_not_started"
    assert director.calls == 0
    assert character_agent.calls == 0

    start_game_runtime(db_session, game.id)
    pause_game_runtime(db_session, game.id)
    paused = run_runtime_tick(db_session, game.id, director, character_agent)
    assert paused.reason_code == "runtime_paused"
    assert director.calls == 0
    assert character_agent.calls == 0


@pytest.mark.parametrize("phase", ["intro", "act_1", "act_2"])
def test_reading_phases_wait_for_acknowledgement_then_advance_once(
    db_session: Session, phase: str
) -> None:
    now = datetime.now(timezone.utc)
    game, _characters = _create_game(db_session, phase=phase, now=now)
    if phase == "intro":
        game.human_intro_acknowledged_at = None
        db_session.commit()
    start_game_runtime(db_session, game.id, now=now)
    director = StubDirector(_recommendation(DirectorAction.no_action))
    character_agent = StubCharacter()

    waiting = run_runtime_tick(db_session, game.id, director, character_agent, now=now)
    assert waiting.reason_code == "reading_not_acknowledged"
    assert waiting.phase_after == phase
    assert director.calls == 0

    ack = acknowledge_current_phase(db_session, game.id, now=now)
    again = acknowledge_current_phase(
        db_session, game.id, now=now + timedelta(seconds=1)
    )
    assert ack.acknowledged_at == again.acknowledged_at
    assert db_session.scalar(
        select(func.count()).select_from(GamePhaseAcknowledgement)
    ) == (0 if phase == "intro" else 1)

    advanced = run_runtime_tick(
        db_session,
        game.id,
        director,
        character_agent,
        now=now + timedelta(seconds=30),
    )
    assert advanced.action_type == "phase_advance"
    assert advanced.phase_after != phase
    assert director.calls == 0
    assert character_agent.calls == 0


def test_investigation_allows_ai_search_before_player_readiness(
    db_session: Session,
) -> None:
    now = datetime.now(timezone.utc)
    game, _characters = _create_game(db_session, phase="investigation_1", now=now)
    start_game_runtime(db_session, game.id, now=now)
    state = db_session.get(GameRuntimeState, game.id)
    state.last_processed_phase_started_at = game.phase_started_at
    db_session.commit()
    director = StubDirector(_recommendation(DirectorAction.no_action))
    character_agent = StubCharacter()

    waiting = run_runtime_tick(db_session, game.id, director, character_agent, now=now)
    assert waiting.phase_after == "investigation_1"
    assert waiting.action_type == "ai_investigation"
    assert waiting.reason_code == "clue_acquired"
    assert director.calls == 0
    assert (
        db_session.scalar(
            select(func.count(GameCharacterClue.id)).where(
                GameCharacterClue.game_character_id == _characters[1].id
            )
        )
        == 1
    )

    mark_runtime_ready(db_session, game.id, now=now)
    advanced = run_runtime_tick(
        db_session,
        game.id,
        director,
        character_agent,
        now=now + timedelta(seconds=30),
    )
    assert advanced.phase_after == "discussion_1"
    assert advanced.action_type == "phase_advance"
    assert director.calls == 0


def test_investigation_tick_runs_one_bounded_ai_search_per_character(
    db_session: Session,
) -> None:
    now = datetime.now(timezone.utc)
    game, characters = _create_game(db_session, phase="investigation_1", now=now)
    start_game_runtime(db_session, game.id, now=now)
    state = db_session.get(GameRuntimeState, game.id)
    state.last_processed_phase_started_at = game.phase_started_at
    db_session.commit()
    director = StubDirector(_recommendation(DirectorAction.no_action))
    character_agent = StubCharacter()

    results = [
        run_runtime_tick(
            db_session,
            game.id,
            director,
            character_agent,
            now=now + timedelta(seconds=index),
        )
        for index in range(3)
    ]
    repeated = run_runtime_tick(
        db_session,
        game.id,
        director,
        character_agent,
        now=now + timedelta(seconds=4),
    )

    for result in results:
        assert result.action_type == "ai_investigation"
    assert repeated.reason_code == "no_new_event"
    assert director.calls == 0
    assert character_agent.calls == 0
    for character in characters[1:]:
        assert (
            db_session.scalar(
                select(func.count(GameCharacterClue.id)).where(
                    GameCharacterClue.game_character_id == character.id
                )
            )
            == 1
        )
    assert (
        db_session.scalar(
            select(func.count(GameCharacterClue.id)).where(
                GameCharacterClue.game_character_id == characters[0].id
            )
        )
        == 0
    )


def test_failed_ai_investigation_is_logged_and_not_retried(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = datetime.now(timezone.utc)
    game, characters = _create_game(db_session, phase="investigation_1", now=now)
    start_game_runtime(db_session, game.id, now=now)
    state = db_session.get(GameRuntimeState, game.id)
    state.last_processed_phase_started_at = game.phase_started_at
    db_session.commit()
    director = StubDirector(_recommendation(DirectorAction.no_action))
    character_agent = StubCharacter()
    attempted_character_ids: list[int] = []

    def fail_search(_db, _game_id, character_id, *_args, **_kwargs):
        attempted_character_ids.append(character_id)
        raise RuntimeError("search failed")

    monkeypatch.setattr("app.services.game_runtime.search_for_ai", fail_search)

    results = [
        run_runtime_tick(
            db_session,
            game.id,
            director,
            character_agent,
            now=now + timedelta(seconds=index),
        )
        for index in range(3)
    ]
    exhausted = run_runtime_tick(
        db_session,
        game.id,
        director,
        character_agent,
        now=now + timedelta(seconds=4),
    )

    assert attempted_character_ids == [character.id for character in characters[1:]]
    assert all(result.execution_status == "failed" for result in results)
    assert exhausted.reason_code == "no_new_event"
    failure_logs = db_session.scalars(
        select(GameRuntimeActionLog).where(
            GameRuntimeActionLog.game_session_id == game.id,
            GameRuntimeActionLog.action_type == "ai_investigation",
        )
    ).all()
    assert len(failure_logs) == 3
    assert all(log.execution_status == "failed" for log in failure_logs)


def test_active_human_discussion_defers_director_phase_advance(
    db_session: Session,
) -> None:
    now = datetime.now(timezone.utc)
    game, characters = _create_game(db_session, now=now)
    db_session.add(
        Message(
            game_session_id=game.id,
            sender_game_character_id=characters[0].id,
            channel_type="public",
            content="我还有一个问题。",
            created_at=now - timedelta(seconds=5),
        )
    )
    db_session.commit()
    start_game_runtime(db_session, game.id, now=now)
    director = StubDirector(_recommendation(DirectorAction.recommend_phase_advance))
    character_agent = StubCharacter()

    first = run_runtime_tick(db_session, game.id, director, character_agent, now=now)
    second = run_runtime_tick(
        db_session, game.id, director, character_agent, now=now + timedelta(seconds=1)
    )

    assert first.reason_code == "human_active"
    assert second.reason_code == "human_active"
    assert game.current_phase == "discussion_1"
    assert director.calls == 1
    assert character_agent.calls == 0


def test_ready_discussion_advances_without_director(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    game, _characters = _create_game(db_session, now=now)
    start_game_runtime(db_session, game.id, now=now)
    mark_runtime_ready(db_session, game.id, now=now)
    director = StubDirector(_recommendation(DirectorAction.no_action))

    result = run_runtime_tick(db_session, game.id, director, StubCharacter(), now=now)

    assert result.phase_after == "act_2"
    assert result.action_type == "phase_advance"
    assert director.calls == 0


def test_final_discussion_requires_readiness_even_with_director_advance(
    db_session: Session,
) -> None:
    now = datetime.now(timezone.utc)
    game, _characters = _create_game(db_session, phase="final_discussion", now=now)
    start_game_runtime(db_session, game.id, now=now)
    record = DirectorRecommendationRecord(
        game_session_id=game.id,
        pace="stalled",
        narrative_risk="low",
        recommended_action="recommend_phase_advance",
        reason="test only",
        source_phase="final_discussion",
        source_phase_started_at=game.phase_started_at,
        status="pending",
    )
    db_session.add(record)
    db_session.commit()
    director = StubDirector(_recommendation(DirectorAction.no_action))
    character_agent = StubCharacter()

    advisory = run_runtime_tick(db_session, game.id, director, character_agent, now=now)
    assert advisory.phase_after == "final_discussion"
    assert advisory.reason_code == "advisory_only"
    assert db_session.get(DirectorRecommendationRecord, record.id).status == "advisory"

    mark_runtime_ready(db_session, game.id, now=now)
    ready = run_runtime_tick(db_session, game.id, director, character_agent, now=now)
    assert ready.phase_after == "vote"
    assert ready.action_type == "phase_advance"
    assert director.calls == 0


def test_director_request_creates_only_one_ai_speech(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    game, characters = _create_game(db_session, now=now)
    start_game_runtime(db_session, game.id, now=now)
    director = StubDirector(
        _recommendation(
            DirectorAction.request_ai_speaker,
            target_id=characters[1].id,
        )
    )
    character_agent = StubCharacter()

    first = run_runtime_tick(db_session, game.id, director, character_agent, now=now)
    second = run_runtime_tick(
        db_session, game.id, director, character_agent, now=now + timedelta(seconds=1)
    )
    speeches = db_session.scalars(
        select(Message).where(
            Message.game_session_id == game.id,
            Message.channel_type == "public",
            Message.sender_game_character_id == characters[1].id,
        )
    ).all()

    assert first.action_type == "proactive_speech"
    assert first.public_message_id is not None
    assert second.reason_code == "no_new_event"
    assert len(speeches) == 1
    assert character_agent.calls == 1
    assert director.calls == 1


def test_runtime_event_is_deduplicated_and_cooldown_applies(
    db_session: Session,
) -> None:
    now = datetime.now(timezone.utc)
    game, characters = _create_game(db_session, now=now)
    db_session.add(
        Message(
            game_session_id=game.id,
            sender_game_character_id=characters[0].id,
            channel_type="public",
            content="第一条公开问题。",
            created_at=now - timedelta(seconds=100),
        )
    )
    db_session.commit()
    start_game_runtime(db_session, game.id, now=now)
    director = StubDirector(_recommendation(DirectorAction.no_action))
    character_agent = StubCharacter()

    first = run_runtime_tick(db_session, game.id, director, character_agent, now=now)
    duplicate = run_runtime_tick(
        db_session, game.id, director, character_agent, now=now + timedelta(seconds=1)
    )
    assert first.action_type == "director_analysis"
    assert duplicate.reason_code == "no_new_event"
    assert director.calls == 1

    db_session.add(
        Message(
            game_session_id=game.id,
            sender_game_character_id=characters[0].id,
            channel_type="public",
            content="第二条公开问题。",
            created_at=now + timedelta(seconds=2),
        )
    )
    db_session.commit()
    cooldown = run_runtime_tick(
        db_session, game.id, director, character_agent, now=now + timedelta(seconds=2)
    )
    assert cooldown.reason_code == "cooldown_active"
    assert director.calls == 1


def test_public_clue_disclosure_event_is_consumed_once(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    game, characters = _create_game(db_session, now=now)
    start_game_runtime(db_session, game.id, now=now)
    state = db_session.get(GameRuntimeState, game.id)
    state.last_processed_phase_started_at = game.phase_started_at
    clue = db_session.scalar(
        select(Clue.id).where(Clue.script_id == game.script_id).limit(1)
    )
    assert clue is not None
    message = Message(
        game_session_id=game.id,
        sender_game_character_id=characters[0].id,
        channel_type="public",
        content="我决定公开这条线索。",
        created_at=now,
    )
    db_session.add(message)
    db_session.flush()
    disclosure = GameClueDisclosure(
        game_session_id=game.id,
        clue_id=clue,
        source_game_character_id=characters[0].id,
        visibility="public",
        target_game_character_id=None,
        related_message_id=message.id,
    )
    db_session.add(disclosure)
    db_session.flush()
    state.last_processed_public_message_id = message.id
    db_session.commit()

    event = _director_event(db_session, game, state, now, RUNTIME_POLICY)

    assert event is not None
    event_key, event_type, watermark_updates = event
    assert event_key == f"public-clue-disclosure:{disclosure.id}"
    assert event_type == "public_clue_disclosure"
    for field, value in watermark_updates.items():
        setattr(state, field, value)
    db_session.commit()
    assert _director_event(db_session, game, state, now, RUNTIME_POLICY) is None


def test_vote_never_autocompletes_and_only_advances_after_four_votes(
    db_session: Session,
) -> None:
    now = datetime.now(timezone.utc)
    game, characters = _create_game(db_session, phase="vote", now=now)
    start_game_runtime(db_session, game.id, now=now)
    director = StubDirector(_recommendation(DirectorAction.no_action))
    character_agent = StubCharacter()

    waiting = run_runtime_tick(db_session, game.id, director, character_agent, now=now)
    assert waiting.reason_code == "vote_incomplete"
    assert game.current_phase == "vote"

    db_session.add_all(
        [
            Vote(
                game_session_id=game.id,
                voter_game_character_id=character.id,
                target_game_character_id=characters[(index + 1) % 4].id,
            )
            for index, character in enumerate(characters)
        ]
    )
    db_session.commit()
    advanced = run_runtime_tick(
        db_session, game.id, director, character_agent, now=now + timedelta(seconds=30)
    )
    assert advanced.phase_after == "ending"
    assert director.calls == 0
    assert character_agent.calls == 0


def test_expired_runtime_lease_is_recovered_without_retrying_old_event(
    db_session: Session,
) -> None:
    now = datetime.now(timezone.utc)
    game, _characters = _create_game(db_session, now=now)
    start_game_runtime(db_session, game.id, now=now)
    state = db_session.get(GameRuntimeState, game.id)
    state.claim_token = "expired-token"
    state.lease_expires_at = now - timedelta(seconds=1)
    state.action_status = "processing"
    old_log = GameRuntimeActionLog(
        game_session_id=game.id,
        event_key="abandoned-event",
        event_type="phase_entry",
        action_type="director_analysis",
        execution_status="processing",
        claim_token="expired-token",
        started_at=now - timedelta(minutes=5),
    )
    db_session.add(old_log)
    db_session.commit()
    director = StubDirector(_recommendation(DirectorAction.no_action))

    run_runtime_tick(db_session, game.id, director, StubCharacter(), now=now)

    db_session.refresh(old_log)
    db_session.refresh(state)
    assert old_log.execution_status == "failed"
    assert old_log.reason_code == "lease_expired"
    assert state.claim_token is None
    assert director.calls == 1


def test_file_sqlite_allows_only_one_concurrent_tick(tmp_path) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'runtime-concurrency.db'}",
        connect_args={"check_same_thread": False, "timeout": 5},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    with factory() as setup_session:
        game, _characters = _create_game(setup_session, now=now)
        game_id = game.id
        start_game_runtime(setup_session, game_id, now=now)

    entered_director = Event()
    release_director = Event()
    results = []

    class BlockingDirector(StubDirector):
        def analyze(self, context):
            self.calls += 1
            entered_director.set()
            assert release_director.wait(timeout=5)
            return self.recommendation

    def first_tick() -> None:
        with factory() as db:
            results.append(
                run_runtime_tick(
                    db,
                    game_id,
                    BlockingDirector(_recommendation(DirectorAction.no_action)),
                    StubCharacter(),
                    now=now,
                )
            )

    thread = Thread(target=first_tick)
    thread.start()
    try:
        assert entered_director.wait(timeout=5)
        with factory() as second_session:
            second = run_runtime_tick(
                second_session,
                game_id,
                StubDirector(_recommendation(DirectorAction.no_action)),
                StubCharacter(),
                now=now,
            )
        assert second.execution_status == "conflict"
        assert second.reason_code == "concurrent_tick_conflict"
    finally:
        release_director.set()
        thread.join(timeout=10)

    assert not thread.is_alive()
    assert len(results) == 1
    assert results[0].action_type == "director_analysis"
    with factory() as db:
        assert (
            db.scalar(select(func.count()).select_from(DirectorRecommendationRecord))
            == 1
        )
        assert db.scalar(select(func.count()).select_from(GameRuntimeActionLog)) == 1
    engine.dispose()


def test_old_claim_token_cannot_clear_a_replacement_claim(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    game, _characters = _create_game(db_session, now=now)
    start_game_runtime(db_session, game.id, now=now)
    state = db_session.get(GameRuntimeState, game.id)
    state.claim_token = "replacement-token"
    state.lease_expires_at = now + timedelta(minutes=1)
    state.claimed_phase = game.current_phase
    state.claimed_phase_started_at = game.phase_started_at
    db_session.commit()

    result = run_runtime_tick(
        db_session,
        game.id,
        StubDirector(_recommendation(DirectorAction.no_action)),
        StubCharacter(),
        now=now,
    )

    db_session.refresh(state)
    assert result.execution_status == "conflict"
    assert state.claim_token == "replacement-token"


def test_stale_character_reply_is_not_persisted(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    game, characters = _create_game(db_session, now=now)
    stale_message = Message(
        game_session_id=game.id,
        sender_game_character_id=characters[1].id,
        channel_type="public",
        content="迟到的发言。",
    )
    reply = StubCharacter().respond(None, None, "test")

    with pytest.raises(StaleRuntimeAction):
        persist_character_reply(
            db_session,
            characters[1],
            stale_message,
            reply,
            expected_phase="act_2",
            expected_phase_started_at=now,
            now=now,
        )

    assert (
        db_session.scalar(
            select(func.count())
            .select_from(Message)
            .where(Message.content == "迟到的发言。")
        )
        == 0
    )


def test_proactive_and_public_turn_replies_are_dropped_after_phase_change(
    db_session: Session,
) -> None:
    now = datetime.now(timezone.utc)
    proactive_game, proactive_characters = _create_game(db_session, now=now)
    proactive_agent = PhaseChangingCharacter(db_session, proactive_game.id)

    with pytest.raises(StaleRuntimeAction):
        run_proactive_speaker_step(
            db_session,
            proactive_game.id,
            proactive_characters[1].id,
            proactive_agent,
        )
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(Message)
            .where(
                Message.game_session_id == proactive_game.id,
                Message.sender_game_character_id == proactive_characters[1].id,
                Message.channel_type == "public",
            )
        )
        == 0
    )

    public_game, public_characters = _create_game(db_session, now=now)
    public_agent = PhaseChangingCharacter(db_session, public_game.id)
    result = send_public_turn(
        db_session,
        public_game.id,
        PublicTurnRequest(content="我想询问案发当晚的情况。"),
        public_agent,
    )
    assert result.status == "partial"
    assert result.failures[0].error_type == "StaleRuntimeAction"
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(Message)
            .where(
                Message.game_session_id == public_game.id,
                Message.sender_game_character_id == public_characters[0].id,
                Message.channel_type == "public",
            )
        )
        == 1
    )
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(Message)
            .where(
                Message.game_session_id == public_game.id,
                Message.sender_game_character_id == public_characters[1].id,
                Message.channel_type == "public",
            )
        )
        == 0
    )


def test_runtime_status_and_logs_never_return_or_persist_private_context(
    client, db_session: Session
) -> None:
    game, characters = _create_game(db_session)
    start_game_runtime(db_session, game.id)
    db_session.add(
        Message(
            game_session_id=game.id,
            sender_game_character_id=characters[0].id,
            channel_type="private",
            receiver_game_character_id=characters[1].id,
            content="ALICE_PRIVATE_SENTINEL",
        )
    )
    db_session.commit()

    status = client.get(f"/api/games/{game.id}/runtime")

    assert status.status_code == 200
    assert "ALICE_PRIVATE_SENTINEL" not in status.text
    logs = db_session.scalars(
        select(GameRuntimeActionLog).where(
            GameRuntimeActionLog.game_session_id == game.id
        )
    ).all()
    assert all("ALICE_PRIVATE_SENTINEL" not in (row.reason_code or "") for row in logs)
