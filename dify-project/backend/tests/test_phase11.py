"""Phase 11 vote isolation, deterministic resolution, and replay tests."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier, Event

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.agents.vote_agent import get_character_vote_agent
from app.agents.vote_workflow_client import VoteWorkflowClient
from app.db.base import Base
from app.game.state_machine import GameRuleError
from app.models import (
    Character,
    CharacterMemory,
    CharacterThought,
    Clue,
    GameCharacter,
    GameCharacterClue,
    GameClueDisclosure,
    GameResolution,
    GameRuntimeActionLog,
    GameSession,
    Message,
    ScriptCanonicalData,
    Vote,
)
from app.schemas.flow import VoteCreate
from app.schemas.voting import CharacterVoteDecision
from app.services.game_flow import (
    InvalidAIVoteTarget,
    VoteConflict,
    build_character_vote_context,
    create_vote,
    run_ai_vote,
)
from app.services.game_replay import get_game_replay
from app.services.game_runtime import (
    pause_game_runtime,
    run_runtime_tick,
    start_game_runtime,
)
from app.services.gameplay import advance_game_phase
from app.services.resolution import get_game_ending
from app.services.seed import seed_development_data


class FixedVoteAgent:
    """Return one fixed target while retaining the context for assertions."""

    configured = True

    def __init__(
        self,
        target_id: int,
        *,
        entered: Event | None = None,
        release: Event | None = None,
    ):
        self.target_id = target_id
        self.entered = entered
        self.release = release
        self.contexts = []

    def decide(self, context):
        self.contexts.append(context)
        if self.entered is not None:
            self.entered.set()
        if self.release is not None:
            assert self.release.wait(timeout=8)
        return CharacterVoteDecision(
            target_game_character_id=self.target_id,
            reason="我根据自己确认的线索作出判断。",
            confidence=0.75,
        )


class NoopDirector:
    def analyze(self, _context):
        raise AssertionError("Vote phase must not call the Director")


class NoopCharacterAgent:
    def respond(self, *_args):
        raise AssertionError("Vote phase must not generate public speech")


def _create_vote_game(
    client, db: Session
) -> tuple[dict, GameSession, list[GameCharacter]]:
    script = seed_development_data(db)
    response = client.post("/api/games", json={"script_id": script.id})
    assert response.status_code == 201
    game_data = response.json()
    game_id = game_data["id"]
    human_id = game_data["game_characters"][0]["id"]
    assert (
        client.post(
            f"/api/games/{game_id}/select-character",
            json={"game_character_id": human_id},
        ).status_code
        == 200
    )
    assert client.post(f"/api/games/{game_id}/me/acknowledge-intro").status_code == 200
    assert client.post(f"/api/games/{game_id}/start").status_code == 200
    game = db.get(GameSession, game_id)
    game.current_phase = "vote"
    game.phase_started_at = datetime.now(timezone.utc) - timedelta(seconds=30)
    db.commit()
    characters = list(
        db.scalars(
            select(GameCharacter)
            .where(GameCharacter.game_session_id == game_id)
            .order_by(GameCharacter.id)
        ).all()
    )
    return game_data, game, characters


def _cast_votes(
    db: Session,
    game: GameSession,
    characters: list[GameCharacter],
    targets: tuple[int, ...],
) -> None:
    create_vote(
        db,
        game.id,
        VoteCreate(
            voter_game_character_id=characters[0].id,
            target_game_character_id=characters[targets[0]].id,
        ),
    )
    db.add_all(
        Vote(
            game_session_id=game.id,
            voter_game_character_id=characters[index].id,
            target_game_character_id=characters[targets[index]].id,
            decision_reason="角色的虚构投票理由。",
        )
        for index in range(1, 4)
    )
    db.commit()


def test_vote_context_contains_only_the_voter_authorized_knowledge(
    client, db_session: Session
) -> None:
    _game_data, game, characters = _create_vote_game(client, db_session)
    voter = characters[1]
    other_template = db_session.get(Character, characters[2].character_id)
    other_template.private_background = "OTHER_ROLE_PRIVATE_SENTINEL"
    canonical = db_session.get(ScriptCanonicalData, game.script_id)
    canonical.case_truth_json["sentinel"] = "SCRIPT_TRUTH_SENTINEL"
    private_message = Message(
        game_session_id=game.id,
        sender_game_character_id=characters[2].id,
        receiver_game_character_id=characters[3].id,
        channel_type="private",
        content="OTHER_PRIVATE_MESSAGE_SENTINEL",
        phase="discussion_1",
    )
    db_session.add(private_message)
    public_ai_message = Message(
        game_session_id=game.id,
        sender_game_character_id=characters[2].id,
        channel_type="public",
        content="公开发言。",
        phase="discussion_1",
    )
    db_session.add(public_ai_message)
    db_session.flush()
    db_session.add_all(
        [
            CharacterThought(
                game_session_id=game.id,
                game_character_id=characters[2].id,
                ai_message_id=public_ai_message.id,
                inner_os="OTHER_THOUGHT_SENTINEL",
                emotion="calm",
                intent="observe",
            ),
            CharacterMemory(
                game_session_id=game.id,
                game_character_id=characters[3].id,
                content="OTHER_MEMORY_SENTINEL",
                importance=3,
                source_message_id=public_ai_message.id,
            ),
        ]
    )
    clue = db_session.scalar(select(Clue).where(Clue.script_id == game.script_id))
    db_session.add(
        GameCharacterClue(
            game_character_id=voter.id,
            clue_id=clue.id,
            phase="investigation_1",
            source="human_search",
        )
    )
    db_session.add(
        Vote(
            game_session_id=game.id,
            voter_game_character_id=characters[2].id,
            target_game_character_id=characters[0].id,
            decision_reason="OTHER_VOTE_REASON_SENTINEL",
        )
    )
    db_session.commit()

    context = build_character_vote_context(db_session, game.id, voter.id)
    serialized = context.model_dump_json()

    assert context.current_phase == "vote"
    assert len(context.eligible_candidates) == 3
    assert voter.id not in {
        candidate.game_character_id for candidate in context.eligible_candidates
    }
    assert clue.name in serialized
    for sentinel in (
        "OTHER_ROLE_PRIVATE_SENTINEL",
        "SCRIPT_TRUTH_SENTINEL",
        "OTHER_PRIVATE_MESSAGE_SENTINEL",
        "OTHER_THOUGHT_SENTINEL",
        "OTHER_MEMORY_SENTINEL",
        "OTHER_VOTE_REASON_SENTINEL",
        "vote_count_by_target",
        "winner_game_character_id",
    ):
        assert sentinel not in serialized


def test_ai_vote_is_validated_immutable_and_never_self_targets(
    client, db_session: Session
) -> None:
    _game_data, game, characters = _create_vote_game(client, db_session)
    target_id = characters[0].id
    agent = FixedVoteAgent(target_id)

    vote = run_ai_vote(db_session, game.id, characters[1].id, agent)

    assert vote.voter_game_character_id == characters[1].id
    assert vote.target_game_character_id == target_id
    assert (
        db_session.get(Vote, vote.id).decision_reason
        == "我根据自己确认的线索作出判断。"
    )
    assert agent.contexts[0].voter_game_character_id == characters[1].id
    with pytest.raises((GameRuleError, VoteConflict)):
        run_ai_vote(db_session, game.id, characters[1].id, agent)

    killer_vote = run_ai_vote(
        db_session, game.id, characters[2].id, FixedVoteAgent(characters[0].id)
    )
    assert killer_vote.voter_game_character_id == characters[2].id
    assert killer_vote.target_game_character_id == characters[0].id
    with pytest.raises(InvalidAIVoteTarget):
        run_ai_vote(
            db_session,
            game.id,
            characters[3].id,
            FixedVoteAgent(characters[3].id),
        )
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(Vote)
            .where(Vote.game_session_id == game.id)
        )
        == 2
    )


def test_character_vote_key_does_not_fall_back_to_character_key(monkeypatch) -> None:
    from app.agents import vote_agent

    monkeypatch.setattr(vote_agent.settings, "dify_api_url", "https://dify.example/v1")
    monkeypatch.setattr(vote_agent.settings, "dify_character_api_key", "character-only")
    monkeypatch.setattr(vote_agent.settings, "dify_vote_api_key", "")

    agent = get_character_vote_agent()

    assert agent.configured is False
    assert agent.workflow_client.api_key == ""


def test_player_vote_status_hides_all_targets_and_ai_reasons(
    client, db_session: Session
) -> None:
    _game_data, game, characters = _create_vote_game(client, db_session)
    rejected_ai_vote = client.post(
        f"/api/games/{game.id}/votes",
        json={
            "voter_game_character_id": characters[1].id,
            "target_game_character_id": characters[0].id,
        },
    )
    assert rejected_ai_vote.status_code == 409

    before = client.get(f"/api/games/{game.id}/vote/status")
    assert before.status_code == 200
    assert before.json()["votes_cast"] == 0
    assert "target_game_character_id" not in before.text
    assert "decision_reason" not in before.text
    assert "vote_count_by_target" not in before.text

    human_vote = client.post(
        f"/api/games/{game.id}/votes",
        json={
            "voter_game_character_id": characters[0].id,
            "target_game_character_id": characters[1].id,
        },
    )
    after = client.get(f"/api/games/{game.id}/vote/status")
    assert human_vote.status_code == 201
    assert after.json()["human_has_voted"] is True
    assert after.json()["votes_cast"] == 1
    assert "target_game_character_id" not in after.text


def test_runtime_vote_tick_completes_one_ai_vote_and_pause_blocks_next(
    client, db_session: Session
) -> None:
    _game_data, game, characters = _create_vote_game(client, db_session)
    create_vote(
        db_session,
        game.id,
        VoteCreate(
            voter_game_character_id=characters[0].id,
            target_game_character_id=characters[1].id,
        ),
    )
    start_game_runtime(db_session, game.id)
    agent = FixedVoteAgent(characters[0].id)
    now = datetime.now(timezone.utc)

    first = run_runtime_tick(
        db_session,
        game.id,
        NoopDirector(),
        NoopCharacterAgent(),
        vote_agent=agent,
        now=now,
    )
    assert first.action_type == "ai_vote"
    assert first.vote_id is not None
    assert len(agent.contexts) == 1
    assert agent.contexts[0].voter_game_character_id == characters[1].id
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(Vote)
            .where(Vote.game_session_id == game.id)
        )
        == 2
    )

    second = run_runtime_tick(
        db_session,
        game.id,
        NoopDirector(),
        NoopCharacterAgent(),
        vote_agent=agent,
        now=now + timedelta(seconds=1),
    )
    assert second.action_type == "ai_vote"
    assert second.vote_id is not None
    assert len(agent.contexts) == 2
    assert agent.contexts[1].voter_game_character_id == characters[2].id
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(Vote)
            .where(Vote.game_session_id == game.id)
        )
        == 3
    )

    pause_game_runtime(db_session, game.id, now=now)
    paused = run_runtime_tick(
        db_session,
        game.id,
        NoopDirector(),
        NoopCharacterAgent(),
        vote_agent=agent,
        now=now + timedelta(seconds=1),
    )
    assert paused.reason_code == "runtime_paused"
    assert len(agent.contexts) == 2


@pytest.mark.parametrize(
    ("targets", "expected_result", "expected_accused_index"),
    [
        ((2, 2, 0, 2), "culprit_identified", 2),
        ((1, 0, 1, 1), "wrong_accusation", 1),
        ((1, 0, 3, 2), "tie", None),
    ],
)
def test_resolution_uses_canonical_truth_and_replay_uses_saved_events(
    client,
    db_session: Session,
    targets: tuple[int, ...],
    expected_result: str,
    expected_accused_index: int | None,
) -> None:
    _game_data, game, characters = _create_vote_game(client, db_session)
    _cast_votes(db_session, game, characters, targets)
    human_message = Message(
        game_session_id=game.id,
        sender_game_character_id=characters[0].id,
        channel_type="private",
        receiver_game_character_id=characters[1].id,
        content="HUMAN_PRIVATE_REPLAY_SENTINEL",
        phase="discussion_1",
    )
    ai_message = Message(
        game_session_id=game.id,
        sender_game_character_id=characters[1].id,
        channel_type="public",
        content="AI_PUBLIC_REPLAY_SENTINEL",
        phase="final_discussion",
    )
    disclosure_message = Message(
        game_session_id=game.id,
        sender_game_character_id=characters[1].id,
        channel_type="private",
        receiver_game_character_id=characters[2].id,
        content="正式分享已发现的线索。",
        phase="discussion_1",
    )
    db_session.add_all([human_message, ai_message, disclosure_message])
    db_session.flush()
    db_session.add_all(
        [
            CharacterThought(
                game_session_id=game.id,
                game_character_id=characters[1].id,
                ai_message_id=ai_message.id,
                inner_os="FICTIONAL_INNER_OS_SENTINEL",
                emotion="calm",
                intent="observe",
            ),
            CharacterMemory(
                game_session_id=game.id,
                game_character_id=characters[1].id,
                content="SUBJECTIVE_MEMORY_SENTINEL",
                importance=4,
                source_message_id=ai_message.id,
            ),
        ]
    )
    clue = db_session.scalar(select(Clue).where(Clue.script_id == game.script_id))
    db_session.add(
        GameCharacterClue(
            game_character_id=characters[1].id,
            clue_id=clue.id,
            phase="investigation_1",
            source="ai_investigation",
        )
    )
    db_session.add(
        GameClueDisclosure(
            game_session_id=game.id,
            clue_id=clue.id,
            source_game_character_id=characters[1].id,
            visibility="private",
            target_game_character_id=characters[2].id,
            related_message_id=disclosure_message.id,
            phase="discussion_1",
        )
    )
    db_session.commit()

    with pytest.raises(GameRuleError, match="resolved"):
        get_game_ending(db_session, game.id)
    with pytest.raises(GameRuleError, match="resolved"):
        get_game_replay(db_session, game.id)
    assert client.get(f"/api/games/{game.id}/ending").status_code == 409
    assert client.get(f"/api/games/{game.id}/replay").status_code == 409

    result = advance_game_phase(
        db_session, game.id, now=datetime.now(timezone.utc) + timedelta(seconds=1)
    )
    resolution = db_session.get(GameResolution, game.id)
    assert result.status == "finished"
    assert resolution is not None
    assert resolution.vote_result == expected_result
    assert resolution.is_tie is (expected_result == "tie")
    assert resolution.accused_game_character_id == (
        characters[expected_accused_index].id
        if expected_accused_index is not None
        else None
    )
    assert resolution.culprit_game_character_id == characters[2].id
    assert resolution.human_identified_culprit is (targets[0] == 2)

    ending = get_game_ending(db_session, game.id)
    replay = get_game_replay(db_session, game.id)
    serialized_replay = replay.model_dump_json()
    assert ending.truth.culprit_role_key == "role_3"
    assert len(ending.votes) == 4
    assert "HUMAN_PRIVATE_REPLAY_SENTINEL" in serialized_replay
    assert "FICTIONAL_INNER_OS_SENTINEL" in serialized_replay
    assert "SUBJECTIVE_MEMORY_SENTINEL" in serialized_replay
    assert "AI_PUBLIC_REPLAY_SENTINEL" in serialized_replay
    assert any(event.event_type == "clue_acquired" for event in replay.events)
    assert any(event.event_type == "clue_disclosure" for event in replay.events)
    assert not any(
        event.event_type == "message" and event.content == "正式分享已发现的线索。"
        for event in replay.events
    )
    assert any(event.event_type == "vote" for event in replay.events)
    assert sum(event.event_type == "game_ended" for event in replay.events) == 1

    ending_count = db_session.scalar(
        select(func.count())
        .select_from(Message)
        .where(
            Message.game_session_id == game.id,
            Message.channel_type == "system",
            Message.content == "游戏结束。",
        )
    )
    assert ending_count == 1
    before_reads = db_session.scalar(
        select(func.count()).select_from(GameRuntimeActionLog)
    )
    get_game_replay(db_session, game.id)
    assert (
        db_session.scalar(select(func.count()).select_from(GameRuntimeActionLog))
        == before_reads
    )


def test_ai_vote_runtime_uses_database_claim_across_independent_sessions(
    tmp_path,
) -> None:
    database_path = tmp_path / "phase11-runtime-claim.db"
    engine = create_engine(f"sqlite:///{database_path}", connect_args={"timeout": 8})

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record) -> None:
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as target_db:
        script = seed_development_data(target_db)
        game_record = GameSession(
            script_id=script.id,
            status="in_progress",
            current_phase="vote",
            random_seed=501,
            started_at=datetime.now(timezone.utc),
            phase_started_at=datetime.now(timezone.utc) - timedelta(seconds=30),
        )
        target_db.add(game_record)
        target_db.flush()
        templates = target_db.scalars(
            select(Character)
            .where(Character.script_id == script.id)
            .order_by(Character.id)
        ).all()
        copied_characters = [
            GameCharacter(
                game_session_id=game_record.id,
                character_id=template.id,
                controller_type="human" if index == 0 else "ai",
            )
            for index, template in enumerate(templates)
        ]
        target_db.add_all(copied_characters)
        target_db.flush()
        target_db.add(
            Vote(
                game_session_id=game_record.id,
                voter_game_character_id=copied_characters[0].id,
                target_game_character_id=copied_characters[1].id,
            )
        )
        target_db.commit()
        game_id = game_record.id
        first_ai_target_id = copied_characters[0].id
        start_game_runtime(target_db, game_id)

    entered = Event()
    release = Event()
    agent = FixedVoteAgent(first_ai_target_id, entered=entered, release=release)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    tick_time = datetime.now(timezone.utc)

    def tick():
        with factory() as session:
            return run_runtime_tick(
                session,
                game_id,
                NoopDirector(),
                NoopCharacterAgent(),
                vote_agent=agent,
                now=tick_time,
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(tick)
        assert entered.wait(timeout=5)
        second = pool.submit(tick)
        second_result = second.result(timeout=5)
        release.set()
        first_result = first.result(timeout=8)

    assert second_result.reason_code == "concurrent_tick_conflict"
    assert first_result.action_type == "ai_vote"
    assert len(agent.contexts) == 1
    with factory() as verify_db:
        assert (
            verify_db.scalar(
                select(func.count())
                .select_from(Vote)
                .where(Vote.game_session_id == game_id)
            )
            == 2
        )
    engine.dispose()


def test_resolution_compare_and_set_allows_only_one_independent_session(
    tmp_path,
) -> None:
    database_path = tmp_path / "phase11-resolution-claim.db"
    engine = create_engine(f"sqlite:///{database_path}", connect_args={"timeout": 8})

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record) -> None:
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    with factory() as db:
        script = seed_development_data(db)
        game = GameSession(
            script_id=script.id,
            status="in_progress",
            current_phase="vote",
            random_seed=502,
            started_at=now - timedelta(minutes=2),
            phase_started_at=now - timedelta(seconds=30),
        )
        db.add(game)
        db.flush()
        templates = db.scalars(
            select(Character)
            .where(Character.script_id == script.id)
            .order_by(Character.id)
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
        db.flush()
        db.add_all(
            Vote(
                game_session_id=game.id,
                voter_game_character_id=characters[index].id,
                target_game_character_id=characters[(index + 1) % 4].id,
            )
            for index in range(4)
        )
        db.commit()
        game_id = game.id

    barrier = Barrier(2)

    def settle():
        with factory() as db:
            barrier.wait(timeout=5)
            try:
                return advance_game_phase(db, game_id, now=now).status
            except GameRuleError:
                return "conflict"
            except OperationalError:
                return "database_conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _index: settle(), range(2)))

    assert results.count("finished") == 1
    assert results.count("conflict") == 1
    with factory() as db:
        assert db.get(GameResolution, game_id) is not None
        assert (
            db.scalar(
                select(func.count())
                .select_from(Message)
                .where(
                    Message.game_session_id == game_id,
                    Message.channel_type == "system",
                    Message.content == "游戏结束。",
                )
            )
            == 1
        )
    engine.dispose()


def test_runtime_pause_and_ai_vote_failure_never_create_a_fake_vote(
    client, db_session: Session
) -> None:
    _game_data, game, characters = _create_vote_game(client, db_session)
    start_game_runtime(db_session, game.id)
    agent = FixedVoteAgent(characters[0].id)
    agent.configured = False

    failed = run_runtime_tick(
        db_session, game.id, NoopDirector(), NoopCharacterAgent(), vote_agent=agent
    )

    assert failed.reason_code == "vote_workflow_not_configured"
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(Vote)
            .where(Vote.game_session_id == game.id)
        )
        == 0
    )
    pause_game_runtime(db_session, game.id)


def test_ai_vote_retry_policy_is_bounded_and_delayed(
    client, db_session: Session
) -> None:
    _game_data, game, characters = _create_vote_game(client, db_session)
    start_game_runtime(db_session, game.id)
    agent = FixedVoteAgent(characters[0].id)
    agent.configured = False
    base_time = datetime.now(timezone.utc)

    results = [
        run_runtime_tick(
            db_session,
            game.id,
            NoopDirector(),
            NoopCharacterAgent(),
            vote_agent=agent,
            now=base_time + timedelta(seconds=offset),
        )
        for offset in (0, 1, 31, 62, 93)
    ]

    assert [result.reason_code for result in results] == [
        "vote_workflow_not_configured",
        "ai_vote_retry_wait",
        "vote_workflow_not_configured",
        "vote_workflow_not_configured",
        "ai_vote_retry_limit",
    ]
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(Vote)
            .where(Vote.game_session_id == game.id)
        )
        == 0
    )


def test_workflow_client_reads_only_structured_result(monkeypatch) -> None:
    import app.agents.vote_workflow_client as client_module

    captured = {}

    class Response:
        status_code = 200

        def json(self):
            return {
                "data": {
                    "status": "succeeded",
                    "outputs": {"result": '{"target_game_character_id":7}'},
                }
            }

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr(client_module.httpx, "post", fake_post)
    result = VoteWorkflowClient("https://dify.example/v1", "test-key").run(
        '{"vote_context":true}', "game-1-voter-2"
    )

    assert result == {"target_game_character_id": 7}
    assert captured["url"] == "https://dify.example/v1/workflows/run"
    assert captured["json"]["response_mode"] == "blocking"
    assert captured["json"]["inputs"] == {"vote_context": '{"vote_context":true}'}


def test_phase11_does_not_change_old_game_rows_or_overwrite_existing_canonical_data(
    client, db_session: Session
) -> None:
    script = seed_development_data(db_session)
    canonical = db_session.get(ScriptCanonicalData, script.id)
    original_summary = canonical.case_truth_json["case_summary"]

    assert seed_development_data(db_session).id == script.id
    assert (
        db_session.get(ScriptCanonicalData, script.id).case_truth_json["case_summary"]
        == original_summary
    )
