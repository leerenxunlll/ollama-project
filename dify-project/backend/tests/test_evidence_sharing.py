"""Phase 10 tests for clue discovery, knowledge, and formal disclosure."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from sqlite3 import Connection
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.agents.character_agent import parse_character_reply
from app.db.base import Base
from app.models import (
    Character,
    CharacterMemory,
    Clue,
    GameCharacter,
    GameCharacterClue,
    GameCharacterClueKnowledge,
    GameClueDisclosure,
    GameClueDisclosureAttempt,
    GameSession,
    Message,
    ScriptCanonicalData,
)
from app.schemas.ai import CharacterEmotion, CharacterIntent, ClueDisclosureIntent
from app.schemas.evidence import ClueShareRequest
from app.services import evidence as evidence_service
from app.services.character_context import build_character_context
from app.services.character_response import persist_character_reply
from app.services.director_context import build_director_context
from app.services.evidence import share_clue
from app.services.seed import seed_development_data


def _create_started_game(client, db: Session) -> dict:
    script = seed_development_data(db)
    response = client.post("/api/games", json={"script_id": script.id})
    assert response.status_code == 201
    game = response.json()
    human_id = game["game_characters"][0]["id"]
    selected = client.post(
        f"/api/games/{game['id']}/select-character",
        json={"game_character_id": human_id},
    )
    assert selected.status_code == 200
    assert (
        client.post(f"/api/games/{game['id']}/me/acknowledge-intro").status_code == 200
    )
    assert client.post(f"/api/games/{game['id']}/start").status_code == 200
    return game


def _set_phase(db: Session, game_id: int, phase: str) -> None:
    game = db.get(GameSession, game_id)
    game.status = "in_progress"
    game.current_phase = phase
    game.phase_started_at = datetime.now(timezone.utc)
    db.commit()


def _first_act_one_clue(db: Session, script_id: int) -> Clue:
    return db.scalar(
        select(Clue)
        .where(Clue.script_id == script_id, Clue.act == "act_1")
        .order_by(Clue.id)
        .limit(1)
    )


def _search(client, game: dict, human_id: int, location: str):
    return client.post(
        f"/api/games/{game['id']}/investigation/search",
        json={"game_character_id": human_id, "location": location},
    )


def _share_payload(clue_id: int, visibility: str, target_id: int | None = None) -> dict:
    return {
        "clue_id": clue_id,
        "visibility": visibility,
        "target_game_character_id": target_id,
        "client_request_id": str(uuid4()),
    }


def _ai_reply(intent: ClueDisclosureIntent):
    from app.agents.character_agent import CharacterReply

    return CharacterReply(
        speech="我想正式分享一条线索。",
        inner_os="我决定披露自己已经确认的信息。",
        emotion=CharacterEmotion.CALM,
        intent=CharacterIntent.COOPERATE,
        memory_updates=[],
        clue_disclosure_intent=intent,
    )


def test_human_search_records_acquisition_and_filters_context(
    client, db_session: Session
) -> None:
    game = _create_started_game(client, db_session)
    human_id = game["game_characters"][0]["id"]
    other_id = game["game_characters"][1]["id"]
    _set_phase(db_session, game["id"], "investigation_1")

    locations = client.get(f"/api/games/{game['id']}/investigation/locations")
    assert locations.status_code == 200
    assert "潮湿的登记页" not in locations.text
    assert "仓库侧门" in locations.text

    result = _search(client, game, human_id, "旧仓库办公室")
    assert result.status_code == 200
    clue_id = result.json()["clue"]["id"]
    acquired = db_session.scalar(
        select(GameCharacterClue).where(
            GameCharacterClue.game_character_id == human_id,
            GameCharacterClue.clue_id == clue_id,
        )
    )
    knowledge = db_session.scalar(
        select(GameCharacterClueKnowledge).where(
            GameCharacterClueKnowledge.game_session_id == game["id"],
            GameCharacterClueKnowledge.game_character_id == human_id,
            GameCharacterClueKnowledge.clue_id == clue_id,
        )
    )
    assert acquired is not None
    assert knowledge.knowledge_source == "direct_acquisition"
    assert [
        clue.clue_id
        for clue in build_character_context(
            db_session, game["id"], human_id
        ).acquired_clues
    ] == [clue_id]
    assert build_character_context(db_session, game["id"], other_id).known_clues == []

    duplicate = _search(client, game, human_id, "旧仓库办公室")
    assert duplicate.status_code == 200
    assert duplicate.json()["found"] is False
    assert (
        db_session.scalar(
            select(func.count(GameCharacterClue.id)).where(
                GameCharacterClue.game_character_id == human_id,
                GameCharacterClue.clue_id == clue_id,
            )
        )
        == 1
    )


def test_character_context_excludes_future_clues_and_script_truth(
    client, db_session: Session
) -> None:
    game = _create_started_game(client, db_session)
    human_id = game["game_characters"][0]["id"]
    script_id = game["script_id"]
    future_clue = db_session.scalar(
        select(Clue).where(Clue.script_id == script_id, Clue.act == "act_2")
    )
    future_clue.description = "FUTURE_CLUE_SENTINEL"
    db_session.add(
        ScriptCanonicalData(
            script_id=script_id,
            case_truth_json={"secret": "SCRIPT_TRUTH_SENTINEL"},
            timeline_json=[],
            role_character_ids_json={},
            clue_ids_json={},
            clue_event_keys_json={},
        )
    )
    db_session.commit()

    context_json = build_character_context(
        db_session, game["id"], human_id
    ).model_dump_json()

    assert "FUTURE_CLUE_SENTINEL" not in context_json
    assert "SCRIPT_TRUTH_SENTINEL" not in context_json


def test_character_memory_remains_private_to_its_owner(
    client, db_session: Session
) -> None:
    game = _create_started_game(client, db_session)
    first_ai_id = game["game_characters"][1]["id"]
    second_ai_id = game["game_characters"][2]["id"]
    message = Message(
        game_session_id=game["id"],
        sender_game_character_id=first_ai_id,
        channel_type="public",
        content="我会记住这次对话。",
    )
    db_session.add(message)
    db_session.flush()
    db_session.add(
        CharacterMemory(
            game_session_id=game["id"],
            game_character_id=first_ai_id,
            content="ALICE_MEMORY_SENTINEL",
            importance=3,
            source_message_id=message.id,
        )
    )
    db_session.commit()

    first_context = build_character_context(db_session, game["id"], first_ai_id)
    second_context_json = build_character_context(
        db_session, game["id"], second_ai_id
    ).model_dump_json()

    assert [memory.content for memory in first_context.memories] == [
        "ALICE_MEMORY_SENTINEL"
    ]
    assert "ALICE_MEMORY_SENTINEL" not in second_context_json


def test_search_cannot_impersonate_an_ai_or_search_outside_investigation(
    client, db_session: Session
) -> None:
    game = _create_started_game(client, db_session)
    _set_phase(db_session, game["id"], "investigation_1")
    ai_id = game["game_characters"][1]["id"]
    impersonation = _search(client, game, ai_id, "旧仓库办公室")
    assert impersonation.status_code == 404

    _set_phase(db_session, game["id"], "vote")
    rejected = _search(client, game, game["game_characters"][0]["id"], "旧仓库办公室")
    assert rejected.status_code == 409
    assert db_session.scalar(select(func.count(GameCharacterClue.id))) == 0


def test_private_share_grants_only_target_and_is_idempotent(
    client, db_session: Session
) -> None:
    game = _create_started_game(client, db_session)
    human_id = game["game_characters"][0]["id"]
    bob_id, carol_id = (
        game["game_characters"][1]["id"],
        game["game_characters"][2]["id"],
    )
    _set_phase(db_session, game["id"], "investigation_1")
    found = _search(client, game, human_id, "旧仓库办公室").json()["clue"]

    payload = _share_payload(found["id"], "private", bob_id)
    response = client.post(f"/api/games/{game['id']}/clues/share", json=payload)
    assert response.status_code == 200
    disclosure = response.json()
    assert disclosure["visibility"] == "private"
    assert disclosure["source_game_character_id"] == human_id
    assert disclosure["target_game_character_id"] == bob_id
    private_message = db_session.get(Message, disclosure["related_message_id"])
    assert private_message.channel_type == "private"
    assert private_message.receiver_game_character_id == bob_id
    assert client.get(f"/api/games/{game['id']}/public-messages").json() == []

    bob_context = build_character_context(db_session, game["id"], bob_id)
    carol_context = build_character_context(db_session, game["id"], carol_id)
    assert [item.clue_id for item in bob_context.known_via_share_clues] == [found["id"]]
    assert found["id"] not in {item.clue_id for item in carol_context.known_clues}
    assert private_message.content in [
        item.content for item in bob_context.private_messages
    ]
    assert private_message.content not in [
        item.content for item in carol_context.private_messages
    ]

    director = build_director_context(db_session, game["id"])
    assert private_message.content not in [
        item.content for item in director.public_state.recent_messages
    ]
    progress = next(
        item for item in director.clue_progress if item.clue_id == found["id"]
    )
    assert progress.private_disclosure_count == 1
    assert not progress.publicly_disclosed

    replay = client.post(f"/api/games/{game['id']}/clues/share", json=payload)
    assert replay.status_code == 200
    assert replay.json()["id"] == disclosure["id"]
    assert replay.json()["replayed"] is True
    assert db_session.scalar(select(func.count(GameClueDisclosure.id))) == 1
    assert (
        db_session.scalar(
            select(func.count(Message.id)).where(Message.channel_type == "private")
        )
        == 1
    )


def test_share_clue_is_idempotent_across_independent_sqlite_sessions(tmp_path) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'evidence-concurrency.db'}",
        connect_args={"check_same_thread": False, "timeout": 10},
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection: Connection, _record: object) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as setup:
        script = seed_development_data(setup)
        now = datetime.now(timezone.utc)
        game = GameSession(
            script_id=script.id,
            status="in_progress",
            current_phase="discussion_1",
            random_seed=1234,
            started_at=now,
            phase_started_at=now,
        )
        setup.add(game)
        setup.flush()
        templates = setup.scalars(
            select(Character)
            .where(Character.script_id == script.id)
            .order_by(Character.id)
        ).all()
        runtime_characters = [
            GameCharacter(
                game_session_id=game.id,
                character_id=template.id,
                controller_type="human" if index == 0 else "ai",
            )
            for index, template in enumerate(templates)
        ]
        setup.add_all(runtime_characters)
        setup.flush()
        human = runtime_characters[0]
        ai = runtime_characters[1]
        clue = setup.scalar(
            select(Clue).where(Clue.script_id == script.id).order_by(Clue.id).limit(1)
        )
        setup.add(
            GameCharacterClue(
                game_character_id=human.id,
                clue_id=clue.id,
                source="investigation",
            )
        )
        setup.add(
            GameCharacterClueKnowledge(
                game_session_id=game.id,
                game_character_id=human.id,
                clue_id=clue.id,
                knowledge_source="direct_acquisition",
                first_known_at=now,
            )
        )
        setup.commit()
        game_id = game.id
        clue_id = clue.id
        target_id = ai.id

    payload = ClueShareRequest.model_validate(
        _share_payload(clue_id, "private", target_id)
    )
    barrier = Barrier(2)

    def submit_share():
        with factory() as session:
            barrier.wait(timeout=5)
            return share_clue(session, game_id, payload)

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(submit_share)
            second = pool.submit(submit_share)
            results = [first.result(timeout=15), second.result(timeout=15)]

        assert results[0].id == results[1].id
        with factory() as verify:
            assert (
                verify.scalar(
                    select(func.count(GameClueDisclosure.id)).where(
                        GameClueDisclosure.game_session_id == game_id
                    )
                )
                == 1
            )
            assert (
                verify.scalar(
                    select(func.count(Message.id)).where(
                        Message.game_session_id == game_id,
                        Message.channel_type == "private",
                    )
                )
                == 1
            )
            assert (
                verify.scalar(
                    select(func.count(GameCharacterClueKnowledge.id)).where(
                        GameCharacterClueKnowledge.game_session_id == game_id,
                        GameCharacterClueKnowledge.game_character_id == target_id,
                        GameCharacterClueKnowledge.clue_id == clue_id,
                    )
                )
                == 1
            )
    finally:
        engine.dispose()


def test_failed_share_transaction_leaves_no_partial_disclosure(
    client, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    game = _create_started_game(client, db_session)
    human_id = game["game_characters"][0]["id"]
    target_id = game["game_characters"][1]["id"]
    _set_phase(db_session, game["id"], "investigation_1")
    clue = _search(client, game, human_id, "旧仓库办公室").json()["clue"]
    payload = ClueShareRequest.model_validate(
        _share_payload(clue["id"], "private", target_id)
    )

    def fail_knowledge_grant(*_args, **_kwargs):
        raise RuntimeError("simulated knowledge write failure")

    monkeypatch.setattr(
        evidence_service, "_grant_disclosure_knowledge", fail_knowledge_grant
    )
    with pytest.raises(RuntimeError, match="simulated knowledge write failure"):
        share_clue(db_session, game["id"], payload)

    assert (
        db_session.scalar(
            select(func.count(GameClueDisclosure.id)).where(
                GameClueDisclosure.game_session_id == game["id"]
            )
        )
        == 0
    )
    assert (
        db_session.scalar(
            select(func.count(Message.id)).where(
                Message.game_session_id == game["id"], Message.channel_type == "private"
            )
        )
        == 0
    )
    assert (
        db_session.scalar(
            select(func.count(GameCharacterClueKnowledge.id)).where(
                GameCharacterClueKnowledge.game_session_id == game["id"],
                GameCharacterClueKnowledge.game_character_id == target_id,
                GameCharacterClueKnowledge.clue_id == clue["id"],
            )
        )
        == 0
    )


def test_public_disclosure_grants_knowledge_without_fake_acquisitions(
    client, db_session: Session
) -> None:
    game = _create_started_game(client, db_session)
    characters = game["game_characters"]
    human_id = characters[0]["id"]
    _set_phase(db_session, game["id"], "investigation_1")
    found = _search(client, game, human_id, "旧仓库办公室").json()["clue"]
    _set_phase(db_session, game["id"], "discussion_1")

    payload = _share_payload(found["id"], "public")
    response = client.post(f"/api/games/{game['id']}/clues/share", json=payload)
    assert response.status_code == 200
    disclosure = response.json()
    public_clues = client.get(f"/api/games/{game['id']}/clues/public").json()["clues"]
    assert [clue["clue_id"] for clue in public_clues] == [found["id"]]

    for character in characters:
        context = build_character_context(db_session, game["id"], character["id"])
        assert found["id"] in {
            item.clue_id for item in context.publicly_disclosed_clues
        }
    assert (
        db_session.scalar(
            select(func.count(GameCharacterClue.id)).where(
                GameCharacterClue.clue_id == found["id"]
            )
        )
        == 1
    )
    assert db_session.scalar(
        select(func.count(GameCharacterClueKnowledge.id)).where(
            GameCharacterClueKnowledge.game_session_id == game["id"],
            GameCharacterClueKnowledge.clue_id == found["id"],
        )
    ) == len(characters)
    assert len(client.get(f"/api/games/{game['id']}/public-messages").json()) == 1

    repeated = client.post(
        f"/api/games/{game['id']}/clues/share",
        json=_share_payload(found["id"], "public"),
    )
    assert repeated.status_code == 200
    assert repeated.json()["id"] == disclosure["id"]
    assert repeated.json()["replayed"] is True
    assert db_session.scalar(select(func.count(GameClueDisclosure.id))) == 1
    director = build_director_context(db_session, game["id"])
    progress = next(
        item for item in director.clue_progress if item.clue_id == found["id"]
    )
    assert progress.publicly_disclosed


def test_share_rejects_unknown_clues_foreign_targets_and_wrong_phases(
    client, db_session: Session
) -> None:
    game = _create_started_game(client, db_session)
    human_id = game["game_characters"][0]["id"]
    ai_id = game["game_characters"][1]["id"]
    _set_phase(db_session, game["id"], "discussion_1")
    clue = _first_act_one_clue(db_session, game["script_id"])

    unknown = client.post(
        f"/api/games/{game['id']}/clues/share",
        json=_share_payload(clue.id, "private", ai_id),
    )
    assert unknown.status_code == 409
    assert db_session.scalar(select(func.count(GameClueDisclosure.id))) == 0

    foreign_target = client.post(
        f"/api/games/{game['id']}/clues/share",
        json=_share_payload(clue.id, "private", 999999),
    )
    assert foreign_target.status_code == 404

    _set_phase(db_session, game["id"], "investigation_1")
    found = _search(client, game, human_id, clue.location).json()["clue"]
    _set_phase(db_session, game["id"], "vote")
    forbidden_public = client.post(
        f"/api/games/{game['id']}/clues/share",
        json=_share_payload(found["id"], "public"),
    )
    assert forbidden_public.status_code == 409
    assert db_session.scalar(select(func.count(GameClueDisclosure.id))) == 0


def test_plain_chat_claim_does_not_create_canonical_clue_or_disclosure(
    client, db_session: Session
) -> None:
    game = _create_started_game(client, db_session)
    human_id = game["game_characters"][0]["id"]
    _set_phase(db_session, game["id"], "discussion_1")
    before_count = db_session.scalar(select(func.count(Clue.id)))
    message = client.post(
        f"/api/games/{game['id']}/messages",
        json={
            "sender_game_character_id": human_id,
            "channel_type": "public",
            "content": "我找到了不存在的金钥匙。",
        },
    )
    assert message.status_code == 201
    assert db_session.scalar(select(func.count(Clue.id))) == before_count
    assert db_session.scalar(select(func.count(GameClueDisclosure.id))) == 0


def test_ai_disclosure_is_validated_and_saved_with_its_speech(
    client, db_session: Session
) -> None:
    game = _create_started_game(client, db_session)
    human_id, ai_id, recipient_id = (item["id"] for item in game["game_characters"][:3])
    _set_phase(db_session, game["id"], "investigation_1")
    found = _search(client, game, human_id, "旧仓库办公室").json()["clue"]
    _set_phase(db_session, game["id"], "discussion_1")
    private = client.post(
        f"/api/games/{game['id']}/clues/share",
        json=_share_payload(found["id"], "private", ai_id),
    )
    assert private.status_code == 200

    ai = db_session.get(GameCharacter, ai_id)
    ai_message = Message(
        game_session_id=game["id"],
        sender_game_character_id=ai_id,
        channel_type="public",
        content="我愿意让大家查看这条线索。",
    )
    reply = _ai_reply(ClueDisclosureIntent(clue_id=found["id"], visibility="public"))
    persist_character_reply(
        db_session,
        ai,
        ai_message,
        reply,
        expected_phase="discussion_1",
        expected_phase_started_at=db_session.get(
            GameSession, game["id"]
        ).phase_started_at,
    )
    disclosure = db_session.scalar(
        select(GameClueDisclosure).where(
            GameClueDisclosure.source_game_character_id == ai_id,
            GameClueDisclosure.clue_id == found["id"],
            GameClueDisclosure.visibility == "public",
        )
    )
    assert disclosure is not None
    assert (
        db_session.get(Message, disclosure.related_message_id).channel_type == "public"
    )
    assert [
        clue.clue_id
        for clue in build_character_context(
            db_session, game["id"], recipient_id
        ).publicly_disclosed_clues
    ] == [found["id"]]
    repeated_reply = Message(
        game_session_id=game["id"],
        sender_game_character_id=ai_id,
        channel_type="public",
        content="这条已经展示过的线索值得再讨论。",
    )
    persist_character_reply(
        db_session,
        ai,
        repeated_reply,
        reply,
        expected_phase="discussion_1",
        expected_phase_started_at=db_session.get(
            GameSession, game["id"]
        ).phase_started_at,
    )
    assert (
        db_session.scalar(
            select(func.count(GameClueDisclosure.id)).where(
                GameClueDisclosure.clue_id == found["id"],
                GameClueDisclosure.visibility == "public",
            )
        )
        == 1
    )


def test_ai_private_reply_cannot_create_a_public_disclosure(
    client, db_session: Session
) -> None:
    game = _create_started_game(client, db_session)
    ai_id = game["game_characters"][1]["id"]
    human_id = game["game_characters"][0]["id"]
    _set_phase(db_session, game["id"], "discussion_1")
    clue = db_session.scalar(
        select(Clue).where(Clue.script_id == game["script_id"]).order_by(Clue.id)
    )
    db_session.add(
        GameCharacterClue(
            game_character_id=ai_id,
            clue_id=clue.id,
            source="investigation",
        )
    )
    db_session.commit()

    ai_message = Message(
        game_session_id=game["id"],
        sender_game_character_id=ai_id,
        channel_type="private",
        receiver_game_character_id=human_id,
        content="这条线索我只私下告诉你。",
    )
    reply = _ai_reply(ClueDisclosureIntent(clue_id=clue.id, visibility="public"))
    persist_character_reply(
        db_session,
        db_session.get(GameCharacter, ai_id),
        ai_message,
        reply,
        expected_phase="discussion_1",
        expected_phase_started_at=db_session.get(
            GameSession, game["id"]
        ).phase_started_at,
    )

    attempt = db_session.scalar(select(GameClueDisclosureAttempt))
    assert attempt.reason_code == "public_disclosure_requires_public_reply"
    assert db_session.scalar(select(func.count(GameClueDisclosure.id))) == 0
    assert (
        db_session.scalar(
            select(func.count(Message.id)).where(Message.channel_type == "public")
        )
        == 0
    )


def test_invalid_ai_disclosure_is_audited_without_granting_knowledge(
    client, db_session: Session
) -> None:
    game = _create_started_game(client, db_session)
    ai_id = game["game_characters"][1]["id"]
    _set_phase(db_session, game["id"], "discussion_1")
    ai = db_session.get(GameCharacter, ai_id)
    fake_clue_id = 999999
    ai_message = Message(
        game_session_id=game["id"],
        sender_game_character_id=ai_id,
        channel_type="public",
        content="我认为自己知道一条线索。",
    )
    reply = _ai_reply(ClueDisclosureIntent(clue_id=fake_clue_id, visibility="public"))
    persist_character_reply(
        db_session,
        ai,
        ai_message,
        reply,
        expected_phase="discussion_1",
        expected_phase_started_at=db_session.get(
            GameSession, game["id"]
        ).phase_started_at,
    )

    attempt = db_session.scalar(select(GameClueDisclosureAttempt))
    assert attempt.requested_clue_id == fake_clue_id
    assert attempt.reason_code == "clue_not_in_script"
    assert db_session.scalar(select(func.count(GameClueDisclosure.id))) == 0
    assert (
        db_session.scalar(
            select(func.count(GameCharacterClueKnowledge.id)).where(
                GameCharacterClueKnowledge.clue_id == fake_clue_id
            )
        )
        == 0
    )


def test_ai_cannot_disclose_a_canonical_clue_it_does_not_know(
    client, db_session: Session
) -> None:
    game = _create_started_game(client, db_session)
    ai_id = game["game_characters"][1]["id"]
    _set_phase(db_session, game["id"], "discussion_1")
    clue = _first_act_one_clue(db_session, game["script_id"])
    ai = db_session.get(GameCharacter, ai_id)
    ai_message = Message(
        game_session_id=game["id"],
        sender_game_character_id=ai_id,
        channel_type="public",
        content="我想公开这条线索。",
    )
    persist_character_reply(
        db_session,
        ai,
        ai_message,
        _ai_reply(ClueDisclosureIntent(clue_id=clue.id, visibility="public")),
        expected_phase="discussion_1",
        expected_phase_started_at=db_session.get(
            GameSession, game["id"]
        ).phase_started_at,
    )

    attempt = db_session.scalar(select(GameClueDisclosureAttempt))
    assert attempt.reason_code == "clue_not_known"
    assert attempt.requested_clue_id == clue.id
    assert db_session.scalar(select(func.count(GameClueDisclosure.id))) == 0
    assert db_session.scalar(select(func.count(GameCharacterClueKnowledge.id))) == 0


def test_old_character_structured_output_remains_valid() -> None:
    old_output = {
        "speech": "你好。",
        "inner_os": "我先保持谨慎。",
        "emotion": "calm",
        "intent": "observe",
        "memory_updates": [],
    }
    parsed = parse_character_reply(__import__("json").dumps(old_output))
    assert parsed.clue_disclosure_intent is None


def test_disclosure_intent_requires_a_target_for_private_sharing() -> None:
    with pytest.raises(ValueError):
        ClueDisclosureIntent(clue_id=1, visibility="private")
