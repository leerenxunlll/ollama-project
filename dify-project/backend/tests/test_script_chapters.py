"""Tests for phase-unlocked story chapters and their information boundaries."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Character,
    CharacterMemory,
    CharacterScriptChapter,
    CharacterThought,
    GameCharacter,
    GameCharacterClue,
    GameSession,
    Message,
    Script,
    SharedScriptChapter,
)
from app.services.director_context import build_director_context
from app.services.seed import seed_development_data


def _create_game(client, db_session: Session) -> dict:
    script = seed_development_data(db_session)
    response = client.post("/api/games", json={"script_id": script.id})
    assert response.status_code == 201
    return response.json()


def _select_human(client, game: dict, index: int = 0) -> dict:
    response = client.post(
        f"/api/games/{game['id']}/select-character",
        json={"game_character_id": game["game_characters"][index]["id"]},
    )
    assert response.status_code == 200
    return response.json()


def _start_game(client, game: dict) -> dict:
    selected = _select_human(client, game)
    acknowledged = client.post(f"/api/games/{game['id']}/me/acknowledge-intro")
    assert acknowledged.status_code == 200
    started = client.post(f"/api/games/{game['id']}/start")
    assert started.status_code == 200
    return selected


def _chapter_phases(chapters: list[dict]) -> list[str]:
    return [chapter["unlock_phase"] for chapter in chapters]


def _advance_one_phase(client, db_session: Session, game_id: int) -> dict:
    game = db_session.get(GameSession, game_id)
    game.phase_started_at = datetime.now(timezone.utc) - timedelta(seconds=120)
    db_session.commit()
    response = client.post(f"/api/games/{game_id}/advance-phase")
    assert response.status_code == 200
    return response.json()


def test_intro_reading_selection_acknowledgement_and_start(client, db_session):
    game = _create_game(client, db_session)

    public_before_selection = client.get(f"/api/games/{game['id']}/story/public")
    private_before_selection = client.get(f"/api/games/{game['id']}/me/story")
    assert public_before_selection.status_code == 200
    assert _chapter_phases(public_before_selection.json()) == ["intro"]
    assert private_before_selection.status_code == 409

    _select_human(client, game)
    private_intro = client.get(f"/api/games/{game['id']}/me/story")
    assert private_intro.status_code == 200
    assert _chapter_phases(private_intro.json()) == ["intro"]
    assert client.post(f"/api/games/{game['id']}/start").status_code == 409

    first_ack = client.post(f"/api/games/{game['id']}/me/acknowledge-intro")
    second_ack = client.post(f"/api/games/{game['id']}/me/acknowledge-intro")
    assert first_ack.status_code == 200
    assert second_ack.status_code == 200
    assert first_ack.json() == second_ack.json()
    started = client.post(f"/api/games/{game['id']}/start")
    assert started.status_code == 200


def test_story_chapters_unlock_by_phase_and_remain_unlocked(client, db_session):
    game = _create_game(client, db_session)
    _start_game(client, game)

    public_intro = client.get(f"/api/games/{game['id']}/story/public").json()
    private_intro = client.get(f"/api/games/{game['id']}/me/story").json()
    assert _chapter_phases(public_intro) == ["intro"]
    assert _chapter_phases(private_intro) == ["intro"]
    ai_character_id = game["game_characters"][1]["id"]
    intro_context = client.get(
        f"/api/games/{game['id']}/characters/{ai_character_id}/context"
    ).json()
    assert _chapter_phases(intro_context["shared_script_chapters"]) == ["intro"]
    assert _chapter_phases(intro_context["character_script_chapters"]) == ["intro"]
    assert (
        db_session.scalar(
            select(func.count(Message.id)).where(Message.game_session_id == game["id"])
        )
        == 1
    )

    _advance_one_phase(client, db_session, game["id"])
    public_act_1 = client.get(f"/api/games/{game['id']}/story/public").json()
    private_act_1 = client.get(f"/api/games/{game['id']}/me/story").json()
    assert _chapter_phases(public_act_1) == ["intro", "act_1"]
    assert _chapter_phases(private_act_1) == ["intro", "act_1"]
    act_1_context = client.get(
        f"/api/games/{game['id']}/characters/{ai_character_id}/context"
    ).json()
    assert _chapter_phases(act_1_context["shared_script_chapters"]) == [
        "intro",
        "act_1",
    ]
    assert _chapter_phases(act_1_context["character_script_chapters"]) == [
        "intro",
        "act_1",
    ]

    _advance_one_phase(client, db_session, game["id"])
    _advance_one_phase(client, db_session, game["id"])
    _advance_one_phase(client, db_session, game["id"])
    public_act_2 = client.get(f"/api/games/{game['id']}/story/public").json()
    private_act_2 = client.get(f"/api/games/{game['id']}/me/story").json()
    assert _chapter_phases(public_act_2) == ["intro", "act_1", "act_2"]
    assert _chapter_phases(private_act_2) == ["intro", "act_1", "act_2"]

    other_template = db_session.scalars(
        select(Character)
        .where(Character.script_id == game["script_id"])
        .order_by(Character.id)
    ).all()[1]
    db_session.add(
        CharacterScriptChapter(
            character_id=other_template.id,
            chapter_order=90,
            unlock_phase="act_2",
            title="另一角色隐藏章节",
            content="FINISHED_OTHER_ROLE_SENTINEL",
        )
    )
    session = db_session.get(GameSession, game["id"])
    session.current_phase = "ending"
    session.status = "finished"
    db_session.commit()
    finished_private = client.get(f"/api/games/{game['id']}/me/story")
    assert _chapter_phases(finished_private.json()) == ["intro", "act_1", "act_2"]
    assert "FINISHED_OTHER_ROLE_SENTINEL" not in str(finished_private.json())


def test_character_and_human_story_exclude_other_roles_and_future_content(
    client, db_session: Session
):
    game = _create_game(client, db_session)
    _select_human(client, game)
    runtime_characters = db_session.scalars(
        select(GameCharacter)
        .where(GameCharacter.game_session_id == game["id"])
        .order_by(GameCharacter.id)
    ).all()
    templates = db_session.scalars(
        select(Character)
        .where(Character.script_id == game["script_id"])
        .order_by(Character.id)
    ).all()
    db_session.add_all(
        [
            CharacterScriptChapter(
                character_id=templates[1].id,
                chapter_order=90,
                unlock_phase="act_1",
                title="Alice 私人章节",
                content="ALICE_PRIVATE_CHAPTER_SENTINEL",
            ),
            CharacterScriptChapter(
                character_id=templates[2].id,
                chapter_order=90,
                unlock_phase="act_1",
                title="Bob 私人章节",
                content="BOB_PRIVATE_CHAPTER_SENTINEL",
            ),
            CharacterScriptChapter(
                character_id=templates[1].id,
                chapter_order=91,
                unlock_phase="act_2",
                title="未来私人章节",
                content="FUTURE_CHAPTER_SENTINEL",
            ),
            SharedScriptChapter(
                script_id=game["script_id"],
                chapter_order=91,
                unlock_phase="act_2",
                title="未来公共章节",
                content="FUTURE_PUBLIC_CHAPTER_SENTINEL",
            ),
        ]
    )
    session = db_session.get(GameSession, game["id"])
    session.status = "in_progress"
    session.current_phase = "act_1"
    db_session.commit()
    clue_count_before = db_session.scalar(select(func.count(GameCharacterClue.id)))

    ai_context = client.get(
        f"/api/games/{game['id']}/characters/{runtime_characters[1].id}/context"
    )
    assert ai_context.status_code == 200
    ai_payload = ai_context.json()
    ai_json = str(ai_payload)
    assert "ALICE_PRIVATE_CHAPTER_SENTINEL" in ai_json
    assert "BOB_PRIVATE_CHAPTER_SENTINEL" not in ai_json
    assert "FUTURE_CHAPTER_SENTINEL" not in ai_json
    assert "FUTURE_PUBLIC_CHAPTER_SENTINEL" not in ai_json
    assert ai_payload["shared_script_chapters"]
    assert ai_payload["character_script_chapters"]

    bob_context = client.get(
        f"/api/games/{game['id']}/characters/{runtime_characters[2].id}/context"
    )
    assert bob_context.status_code == 200
    bob_json = str(bob_context.json())
    assert "BOB_PRIVATE_CHAPTER_SENTINEL" in bob_json
    assert "ALICE_PRIVATE_CHAPTER_SENTINEL" not in bob_json
    assert "FUTURE_CHAPTER_SENTINEL" not in bob_json

    human_story = client.get(f"/api/games/{game['id']}/me/story")
    assert human_story.status_code == 200
    assert "ALICE_PRIVATE_CHAPTER_SENTINEL" not in str(human_story.json())
    assert "BOB_PRIVATE_CHAPTER_SENTINEL" not in str(human_story.json())
    assert "FUTURE_CHAPTER_SENTINEL" not in str(human_story.json())
    assert "BOB_PRIVATE_CHAPTER_SENTINEL" not in str(human_story.json())
    game_payload = client.get(f"/api/games/{game['id']}").json()
    state_payload = client.get(f"/api/games/{game['id']}/state").json()
    script_payload = client.get(f"/api/scripts/{game['script_id']}").json()
    assert "BOB_PRIVATE_CHAPTER_SENTINEL" not in str(game_payload)
    assert "ALICE_PRIVATE_CHAPTER_SENTINEL" not in str(state_payload)
    assert "FUTURE_PUBLIC_CHAPTER_SENTINEL" not in str(script_payload)
    assert "is_killer" not in str(game_payload)
    assert "is_killer" not in str(state_payload)
    assert "is_killer" not in str(script_payload)
    assert db_session.scalar(select(func.count(GameCharacterClue.id))) == (
        clue_count_before
    )


def test_director_gets_all_script_chapters_but_no_runtime_private_state(
    client, db_session: Session
):
    game = _create_game(client, db_session)
    _select_human(client, game)
    runtime_characters = db_session.scalars(
        select(GameCharacter)
        .where(GameCharacter.game_session_id == game["id"])
        .order_by(GameCharacter.id)
    ).all()
    templates = db_session.scalars(
        select(Character)
        .where(Character.script_id == game["script_id"])
        .order_by(Character.id)
    ).all()
    db_session.add_all(
        [
            CharacterScriptChapter(
                character_id=templates[0].id,
                chapter_order=90,
                unlock_phase="act_2",
                title="Alice 隐藏章节",
                content="ALICE_PRIVATE_CHAPTER_SENTINEL",
            ),
            CharacterScriptChapter(
                character_id=templates[1].id,
                chapter_order=90,
                unlock_phase="act_2",
                title="Bob 隐藏章节",
                content="BOB_PRIVATE_CHAPTER_SENTINEL",
            ),
            SharedScriptChapter(
                script_id=game["script_id"],
                chapter_order=90,
                unlock_phase="act_2",
                title="未解锁公共章节",
                content="FUTURE_CHAPTER_SENTINEL",
            ),
        ]
    )
    public_message = Message(
        game_session_id=game["id"],
        sender_game_character_id=runtime_characters[1].id,
        channel_type="public",
        content="AI public message",
    )
    private_message = Message(
        game_session_id=game["id"],
        sender_game_character_id=runtime_characters[0].id,
        channel_type="private",
        receiver_game_character_id=runtime_characters[1].id,
        content="DIRECTOR_PRIVATE_MESSAGE_SENTINEL",
    )
    db_session.add_all([public_message, private_message])
    db_session.flush()
    db_session.add_all(
        [
            CharacterThought(
                game_session_id=game["id"],
                game_character_id=runtime_characters[1].id,
                ai_message_id=public_message.id,
                inner_os="DIRECTOR_THOUGHT_SENTINEL",
                emotion="calm",
                intent="observe",
            ),
            CharacterMemory(
                game_session_id=game["id"],
                game_character_id=runtime_characters[1].id,
                content="DIRECTOR_MEMORY_SENTINEL",
                importance=3,
                source_message_id=public_message.id,
            ),
        ]
    )
    db_session.commit()

    context_json = build_director_context(db_session, game["id"]).model_dump_json()
    assert "ALICE_PRIVATE_CHAPTER_SENTINEL" in context_json
    assert "BOB_PRIVATE_CHAPTER_SENTINEL" in context_json
    assert "FUTURE_CHAPTER_SENTINEL" in context_json
    assert "DIRECTOR_PRIVATE_MESSAGE_SENTINEL" not in context_json
    assert "DIRECTOR_THOUGHT_SENTINEL" not in context_json
    assert "DIRECTOR_MEMORY_SENTINEL" not in context_json


def test_intro_acknowledgement_is_per_game_and_legacy_game_starts_without_it(
    client, db_session: Session
):
    script = seed_development_data(db_session)
    first = client.post("/api/games", json={"script_id": script.id}).json()
    second = client.post("/api/games", json={"script_id": script.id}).json()
    _select_human(client, first)
    _select_human(client, second, index=1)
    assert (
        client.post(f"/api/games/{first['id']}/me/acknowledge-intro").status_code == 200
    )
    assert (
        db_session.get(GameSession, first["id"]).human_intro_acknowledged_at is not None
    )
    assert db_session.get(GameSession, second["id"]).human_intro_acknowledged_at is None
    assert client.post(f"/api/games/{second['id']}/start").status_code == 409

    legacy_script = Script(title="Legacy without chapters", status="ready")
    legacy_script.characters = [
        Character(
            name=f"角色 {index}",
            identity="测试身份",
            public_background="公开背景",
            private_background="旧剧本私有背景",
            personality="谨慎",
            speaking_style="简短",
            personal_goal="完成旧测试",
        )
        for index in range(4)
    ]
    db_session.add(legacy_script)
    db_session.flush()
    legacy_game = GameSession(
        script_id=legacy_script.id,
        status="ready",
        current_phase="intro",
        random_seed=5,
    )
    legacy_game.game_characters = [
        GameCharacter(
            character=character,
            controller_type="human" if index == 0 else "ai",
        )
        for index, character in enumerate(legacy_script.characters)
    ]
    db_session.add(legacy_game)
    db_session.commit()

    started = client.post(f"/api/games/{legacy_game.id}/start")
    assert started.status_code == 200


def test_development_seed_is_idempotent_and_does_not_touch_other_scripts(
    db_session: Session,
):
    sample = seed_development_data(db_session)
    shared_count = db_session.scalar(
        select(func.count(SharedScriptChapter.id)).where(
            SharedScriptChapter.script_id == sample.id
        )
    )
    private_count = db_session.scalar(
        select(func.count(CharacterScriptChapter.id))
        .join(Character)
        .where(Character.script_id == sample.id)
    )
    assert shared_count == 3
    assert private_count == 12

    editable_chapter = db_session.scalar(
        select(SharedScriptChapter).where(
            SharedScriptChapter.script_id == sample.id,
            SharedScriptChapter.chapter_order == 1,
        )
    )
    editable_chapter.content = "MANUALLY_EDITED_SAMPLE_SENTINEL"
    other_script = Script(title="Unrelated script", status="ready")
    other_script.characters = [
        Character(
            name="Other role",
            identity="Test role",
            public_background="Public facts",
            private_background="Private facts",
            personality="Careful",
            speaking_style="Brief",
            personal_goal="Test isolation",
        )
    ]
    db_session.add(other_script)
    db_session.commit()
    other_character_id = other_script.characters[0].id

    seed_development_data(db_session)

    db_session.refresh(editable_chapter)
    assert editable_chapter.content == "MANUALLY_EDITED_SAMPLE_SENTINEL"
    assert (
        db_session.scalar(
            select(func.count(SharedScriptChapter.id)).where(
                SharedScriptChapter.script_id == sample.id
            )
        )
        == shared_count
    )
    assert (
        db_session.scalar(
            select(func.count(CharacterScriptChapter.id))
            .join(Character)
            .where(Character.script_id == sample.id)
        )
        == private_count
    )
    assert (
        db_session.scalar(
            select(func.count(SharedScriptChapter.id)).where(
                SharedScriptChapter.script_id == other_script.id
            )
        )
        == 0
    )
    assert (
        db_session.scalar(
            select(func.count(CharacterScriptChapter.id)).where(
                CharacterScriptChapter.character_id == other_character_id
            )
        )
        == 0
    )
