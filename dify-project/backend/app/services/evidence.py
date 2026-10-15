"""Deterministic acquisition, knowledge, and disclosure of canonical clues."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from app.game.flow_manager import can_public_speak
from app.game.state_machine import GameRuleError, can_investigate, clue_act_for_phase
from app.models import (
    Clue,
    GameCharacter,
    GameCharacterClue,
    GameCharacterClueKnowledge,
    GameClueDisclosure,
    GameRuntimeActionLog,
    GameSession,
    Message,
)
from app.schemas.evidence import (
    ClueDisclosureRead,
    ClueEvidenceRead,
    ClueHistoryEventRead,
    ClueShareRequest,
    MyClueStateRead,
    PublicCluesRead,
)
from app.schemas.game import InvestigationClueRead, InvestigationResultRead
from app.services.runtime_guards import assert_runtime_action_current


def search_for_human(
    db: Session,
    game_id: int,
    location: str,
    asserted_game_character_id: int | None = None,
) -> InvestigationResultRead:
    """Search for the unique Human character selected for this game."""
    _game(db, game_id)
    human = _human_character(db, game_id)
    if (
        asserted_game_character_id is not None
        and asserted_game_character_id != human.id
    ):
        raise LookupError("Character not found in this game")
    return search_for_character(
        db,
        game_id,
        human.id,
        location,
        required_controller="human",
    )


def search_for_ai(
    db: Session,
    game_id: int,
    game_character_id: int,
    location: str,
    *,
    expected_phase: str,
    expected_phase_started_at: datetime | None,
    runtime_claim_token: str,
    now: datetime,
    commit: bool = True,
) -> InvestigationResultRead:
    """Run one claimed Runtime investigation for an AI character."""
    return search_for_character(
        db,
        game_id,
        game_character_id,
        location,
        required_controller="ai",
        expected_phase=expected_phase,
        expected_phase_started_at=expected_phase_started_at,
        runtime_claim_token=runtime_claim_token,
        now=now,
        commit=commit,
    )


def search_for_character(
    db: Session,
    game_id: int,
    game_character_id: int,
    location: str,
    *,
    required_controller: str,
    expected_phase: str | None = None,
    expected_phase_started_at: datetime | None = None,
    runtime_claim_token: str | None = None,
    now: datetime | None = None,
    commit: bool = True,
) -> InvestigationResultRead:
    """Atomically grant the first canonical clue at one eligible location."""
    game = _game(db, game_id)
    phase = game.current_phase
    phase_started_at = game.phase_started_at
    character = db.get(GameCharacter, game_character_id)
    if character is None or character.game_session_id != game.id:
        raise LookupError("Character not found in this game")
    if character.controller_type != required_controller:
        raise GameRuleError("This character cannot perform the requested search")
    _require_search_phase(game)

    expected_phase = expected_phase or phase
    if expected_phase != phase:
        raise GameRuleError("Game phase changed before investigation")
    assert_runtime_action_current(
        db,
        game.id,
        claim_token=runtime_claim_token,
        expected_phase=expected_phase,
        expected_phase_started_at=(
            phase_started_at
            if expected_phase_started_at is None
            else expected_phase_started_at
        ),
        now=now,
    )

    act = clue_act_for_phase(game.current_phase)
    clues = db.scalars(
        select(Clue)
        .where(
            Clue.script_id == game.script_id,
            Clue.act == act,
            Clue.location == location,
        )
        .order_by(Clue.importance.desc(), Clue.id.asc())
    ).all()
    for clue in clues:
        inserted = db.execute(
            sqlite_insert(GameCharacterClue)
            .values(
                game_character_id=character.id,
                clue_id=clue.id,
                phase=game.current_phase,
                source="investigation",
            )
            .on_conflict_do_nothing(
                index_elements=[
                    GameCharacterClue.game_character_id,
                    GameCharacterClue.clue_id,
                ]
            )
        )
        if inserted.rowcount != 1:
            continue

        discovery = db.scalar(
            select(GameCharacterClue).where(
                GameCharacterClue.game_character_id == character.id,
                GameCharacterClue.clue_id == clue.id,
            )
        )
        db.execute(
            sqlite_insert(GameCharacterClueKnowledge)
            .values(
                game_session_id=game.id,
                game_character_id=character.id,
                clue_id=clue.id,
                knowledge_source="direct_acquisition",
                first_known_at=discovery.discovered_at,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    GameCharacterClueKnowledge.game_session_id,
                    GameCharacterClueKnowledge.game_character_id,
                    GameCharacterClueKnowledge.clue_id,
                ]
            )
        )
        if commit:
            db.commit()
        return InvestigationResultRead(
            game_id=game.id,
            game_character_id=character.id,
            location=location,
            found=True,
            clue=InvestigationClueRead.model_validate(clue),
        )

    if commit:
        db.commit()
    return InvestigationResultRead(
        game_id=game.id,
        game_character_id=character.id,
        location=location,
        found=False,
        clue=None,
    )


def next_ai_investigation(
    db: Session,
    game: GameSession,
    max_actions_per_phase: int,
) -> tuple[GameCharacter, int, str] | None:
    """Select the first AI below its deterministic per-phase action limit."""
    phase_key = _phase_key(game.phase_started_at)
    characters = db.scalars(
        select(GameCharacter)
        .where(
            GameCharacter.game_session_id == game.id,
            GameCharacter.controller_type == "ai",
        )
        .order_by(GameCharacter.id)
    ).all()
    for character in characters:
        for attempt in range(1, max_actions_per_phase + 1):
            event_key = f"ai-investigation:{phase_key}:{character.id}:{attempt}"
            exists = db.scalar(
                select(GameRuntimeActionLog.id).where(
                    GameRuntimeActionLog.game_session_id == game.id,
                    GameRuntimeActionLog.event_key == event_key,
                )
            )
            if exists is None:
                return character, attempt, event_key
    return None


def next_ai_investigation_location(
    db: Session, game: GameSession, game_character_id: int
) -> str | None:
    """Choose the first location with an undiscovered clue in stable order."""
    act = clue_act_for_phase(game.current_phase)
    locations = db.scalars(
        select(Clue.location)
        .where(Clue.script_id == game.script_id, Clue.act == act)
        .distinct()
        .order_by(Clue.location)
    ).all()
    for location in locations:
        available = db.scalar(
            select(Clue.id)
            .where(
                Clue.script_id == game.script_id,
                Clue.act == act,
                Clue.location == location,
                ~select(GameCharacterClue.id)
                .where(
                    GameCharacterClue.game_character_id == game_character_id,
                    GameCharacterClue.clue_id == Clue.id,
                )
                .exists(),
            )
            .limit(1)
        )
        if available is not None:
            return location
    return locations[0] if locations else None


def get_my_clues(db: Session, game_id: int) -> MyClueStateRead:
    """Return only the Human character's acquisitions and permitted knowledge."""
    game = _game(db, game_id)
    human = _human_character(db, game_id)
    acquired_rows = db.execute(
        select(GameCharacterClue, Clue)
        .join(Clue, Clue.id == GameCharacterClue.clue_id)
        .where(
            GameCharacterClue.game_character_id == human.id,
            Clue.script_id == game.script_id,
        )
        .order_by(GameCharacterClue.discovered_at, GameCharacterClue.id)
    ).all()
    private_rows = db.execute(
        select(GameClueDisclosure, Clue)
        .join(Clue, Clue.id == GameClueDisclosure.clue_id)
        .where(
            GameClueDisclosure.game_session_id == game.id,
            GameClueDisclosure.visibility == "private",
            GameClueDisclosure.target_game_character_id == human.id,
            Clue.script_id == game.script_id,
        )
        .order_by(GameClueDisclosure.created_at, GameClueDisclosure.id)
    ).all()
    public_rows = _public_clue_rows(db, game)
    return MyClueStateRead(
        game_id=game.id,
        human_game_character_id=human.id,
        acquired_clues=[
            _clue_read(
                clue,
                "direct_acquisition",
                discovery.discovered_at,
                human.id,
            )
            for discovery, clue in acquired_rows
        ],
        known_via_share_clues=[
            _clue_read(
                clue,
                "private_disclosure",
                disclosure.created_at,
                disclosure.source_game_character_id,
            )
            for disclosure, clue in private_rows
        ],
        publicly_disclosed_clues=[
            _clue_read(
                clue,
                "public_disclosure",
                disclosure.created_at,
                disclosure.source_game_character_id,
            )
            for disclosure, clue in public_rows
        ],
    )


def get_public_clues(db: Session, game_id: int) -> PublicCluesRead:
    """Return only canonical clues with a committed public disclosure."""
    game = _game(db, game_id)
    rows = _public_clue_rows(db, game)
    return PublicCluesRead(
        game_id=game.id,
        clues=[
            _clue_read(
                clue,
                "public_disclosure",
                disclosure.created_at,
                disclosure.source_game_character_id,
            )
            for disclosure, clue in rows
        ],
    )


def share_clue(
    db: Session,
    game_id: int,
    payload: ClueShareRequest,
) -> ClueDisclosureRead:
    """Validate and atomically publish or privately share one known clue."""
    game = _game(db, game_id)
    human = _human_character(db, game_id)
    request_id = str(payload.client_request_id)
    existing_request = db.scalar(
        select(GameClueDisclosure).where(
            GameClueDisclosure.game_session_id == game_id,
            GameClueDisclosure.client_request_id == request_id,
        )
    )
    if existing_request is not None:
        if (
            existing_request.source_game_character_id != human.id
            or not _matches_request(existing_request, payload)
        ):
            raise GameRuleError("client_request_id was already used for another action")
        return _disclosure_read(existing_request, replayed=True)

    _require_game_in_progress(game)
    phase = game.current_phase
    phase_started_at = game.phase_started_at
    if payload.visibility == "public" and not can_public_speak(
        game.status, game.current_phase
    ):
        raise GameRuleError("Public clue disclosure is not allowed in this phase")

    clue = db.get(Clue, payload.clue_id)
    if clue is None or clue.script_id != game.script_id:
        raise LookupError("Clue not found in this game's script")

    target = None
    if payload.visibility == "private":
        target = db.get(GameCharacter, payload.target_game_character_id)
        if target is None or target.game_session_id != game.id:
            raise LookupError("Target character not found in this game")
        if target.id == human.id:
            raise GameRuleError("A clue cannot be privately shared with yourself")
        if target.controller_type != "ai":
            raise GameRuleError("Private player sharing must target an AI character")
    if not _character_knows_clue(db, game, human, clue.id):
        raise GameRuleError("The Human character does not know this clue")

    assert_runtime_action_current(
        db,
        game.id,
        expected_phase=phase,
        expected_phase_started_at=phase_started_at,
    )
    duplicate = _existing_semantic_disclosure(
        db,
        game.id,
        clue.id,
        human.id,
        payload.visibility,
        target.id if target is not None else None,
    )
    if duplicate is not None:
        return _disclosure_read(duplicate, replayed=True)
    if target is not None and _character_knows_clue(db, game, target, clue.id):
        raise GameRuleError("Target character already knows this clue")

    message = Message(
        game_session_id=game.id,
        sender_game_character_id=human.id,
        channel_type=payload.visibility,
        receiver_game_character_id=target.id if target is not None else None,
        content=_disclosure_message_content(human, clue, payload.visibility),
        phase=game.current_phase,
    )
    db.add(message)
    try:
        db.flush()
        disclosure = GameClueDisclosure(
            game_session_id=game.id,
            clue_id=clue.id,
            source_game_character_id=human.id,
            visibility=payload.visibility,
            target_game_character_id=target.id if target is not None else None,
            related_message_id=message.id,
            phase=game.current_phase,
            client_request_id=request_id,
        )
        db.add(disclosure)
        db.flush()
        _grant_disclosure_knowledge(db, game, disclosure)
        db.commit()
        db.refresh(disclosure)
        return _disclosure_read(disclosure)
    except IntegrityError as error:
        db.rollback()
        replay = db.scalar(
            select(GameClueDisclosure).where(
                GameClueDisclosure.game_session_id == game_id,
                GameClueDisclosure.client_request_id == request_id,
            )
        )
        if replay is not None and _matches_request(replay, payload):
            return _disclosure_read(replay, replayed=True)
        duplicate = _existing_semantic_disclosure(
            db,
            game_id,
            payload.clue_id,
            human.id,
            payload.visibility,
            payload.target_game_character_id,
        )
        if duplicate is not None:
            return _disclosure_read(duplicate, replayed=True)
        raise GameRuleError(
            "Clue disclosure conflicted with another request"
        ) from error
    except Exception:
        db.rollback()
        raise


def get_clue_history(db: Session, game_id: int) -> list[ClueHistoryEventRead]:
    """Return only acquisition and disclosure events visible to the Human."""
    game = _game(db, game_id)
    human = _human_character(db, game_id)
    events: list[ClueHistoryEventRead] = []
    acquired_rows = db.execute(
        select(GameCharacterClue, Clue)
        .join(Clue, Clue.id == GameCharacterClue.clue_id)
        .where(
            GameCharacterClue.game_character_id == human.id,
            Clue.script_id == game.script_id,
        )
    ).all()
    for acquisition, clue in acquired_rows:
        events.append(
            ClueHistoryEventRead(
                event_id=f"acquired:{acquisition.id}",
                event_type="clue_acquired",
                clue_id=clue.id,
                clue_name=clue.name,
                actor_name=human.character.name,
                target_name=None,
                occurred_at=acquisition.discovered_at,
            )
        )

    source_character = aliased(GameCharacter)
    target_character = aliased(GameCharacter)
    disclosure_rows = db.execute(
        select(GameClueDisclosure, Clue, source_character, target_character)
        .join(Clue, Clue.id == GameClueDisclosure.clue_id)
        .join(
            source_character,
            source_character.id == GameClueDisclosure.source_game_character_id,
        )
        .outerjoin(
            target_character,
            target_character.id == GameClueDisclosure.target_game_character_id,
        )
        .where(
            GameClueDisclosure.game_session_id == game.id,
            Clue.script_id == game.script_id,
        )
        .order_by(GameClueDisclosure.created_at, GameClueDisclosure.id)
    ).all()
    for disclosure, clue, source, target in disclosure_rows:
        if disclosure.visibility == "private" and human.id not in {
            disclosure.source_game_character_id,
            disclosure.target_game_character_id,
        }:
            continue
        events.append(
            ClueHistoryEventRead(
                event_id=f"disclosure:{disclosure.id}",
                event_type=(
                    "clue_disclosed_publicly"
                    if disclosure.visibility == "public"
                    else "clue_shared_privately"
                ),
                clue_id=clue.id,
                clue_name=clue.name,
                actor_name=source.character.name,
                target_name=target.character.name if target is not None else None,
                occurred_at=disclosure.created_at,
            )
        )
    return sorted(
        events,
        key=lambda event: (event.occurred_at, event.event_id),
        reverse=True,
    )


def record_character_disclosure(
    db: Session,
    *,
    game_id: int,
    source: GameCharacter,
    clue_id: int,
    visibility: str,
    target_game_character_id: int | None,
    speech_message: Message,
) -> GameClueDisclosure | None:
    """Apply a validated optional model intent or store a safe rejection record."""
    from app.models import GameClueDisclosureAttempt

    game = _game(db, game_id)
    clue = db.get(Clue, clue_id)
    target = (
        db.get(GameCharacter, target_game_character_id)
        if target_game_character_id is not None
        else None
    )
    reason = None
    if game.status != "in_progress":
        reason = "game_not_in_progress"
    elif source.controller_type != "ai" or source.game_session_id != game.id:
        reason = "invalid_source_character"
    elif clue is None or clue.script_id != game.script_id:
        reason = "clue_not_in_script"
    elif not _character_knows_clue(db, game, source, clue_id):
        reason = "clue_not_known"
    elif visibility == "public" and speech_message.channel_type != "public":
        reason = "public_disclosure_requires_public_reply"
    elif visibility == "public" and not can_public_speak(
        game.status, game.current_phase
    ):
        reason = "public_disclosure_not_allowed"
    elif visibility == "private" and (
        target is None or target.game_session_id != game.id or target.id == source.id
    ):
        reason = "invalid_private_target"
    elif visibility not in {"private", "public"}:
        reason = "invalid_visibility"

    if reason is not None:
        db.add(
            GameClueDisclosureAttempt(
                game_session_id=game.id,
                game_character_id=source.id,
                message_id=speech_message.id,
                requested_clue_id=clue_id,
                reason_code=reason,
            )
        )
        return None

    duplicate = _existing_semantic_disclosure(
        db,
        game.id,
        clue.id,
        source.id,
        visibility,
        target.id if target is not None else None,
    )
    if duplicate is not None:
        return duplicate
    if target is not None and _character_knows_clue(db, game, target, clue.id):
        db.add(
            GameClueDisclosureAttempt(
                game_session_id=game.id,
                game_character_id=source.id,
                message_id=speech_message.id,
                requested_clue_id=clue_id,
                reason_code="target_already_knows_clue",
            )
        )
        return None

    content = _disclosure_message_content(source, clue, visibility)
    disclosure_message = Message(
        game_session_id=game.id,
        sender_game_character_id=source.id,
        channel_type=visibility,
        receiver_game_character_id=target.id if target is not None else None,
        content=content,
        phase=game.current_phase,
    )
    db.add(disclosure_message)
    db.flush()
    disclosure = GameClueDisclosure(
        game_session_id=game.id,
        clue_id=clue.id,
        source_game_character_id=source.id,
        visibility=visibility,
        target_game_character_id=target.id if target is not None else None,
        related_message_id=disclosure_message.id,
        phase=game.current_phase,
    )
    db.add(disclosure)
    db.flush()
    _grant_disclosure_knowledge(db, game, disclosure)
    return disclosure


def _grant_disclosure_knowledge(
    db: Session, game: GameSession, disclosure: GameClueDisclosure
) -> None:
    if disclosure.visibility == "public":
        recipients = db.scalars(
            select(GameCharacter).where(GameCharacter.game_session_id == game.id)
        ).all()
        source = "public_disclosure"
    else:
        recipients = [db.get(GameCharacter, disclosure.target_game_character_id)]
        source = "private_disclosure"
    for recipient in recipients:
        if recipient is None or _character_knows_clue(
            db, game, recipient, disclosure.clue_id
        ):
            continue
        db.add(
            GameCharacterClueKnowledge(
                game_session_id=game.id,
                game_character_id=recipient.id,
                clue_id=disclosure.clue_id,
                knowledge_source=source,
                source_disclosure_id=disclosure.id,
            )
        )


def _character_knows_clue(
    db: Session, game: GameSession, character: GameCharacter, clue_id: int
) -> bool:
    known = db.scalar(
        select(GameCharacterClueKnowledge.id).where(
            GameCharacterClueKnowledge.game_session_id == game.id,
            GameCharacterClueKnowledge.game_character_id == character.id,
            GameCharacterClueKnowledge.clue_id == clue_id,
        )
    )
    if known is not None:
        return True
    return (
        db.scalar(
            select(GameCharacterClue.id).where(
                GameCharacterClue.game_character_id == character.id,
                GameCharacterClue.clue_id == clue_id,
            )
        )
        is not None
    )


def _public_clue_rows(db: Session, game: GameSession):
    return db.execute(
        select(GameClueDisclosure, Clue)
        .join(Clue, Clue.id == GameClueDisclosure.clue_id)
        .where(
            GameClueDisclosure.game_session_id == game.id,
            GameClueDisclosure.visibility == "public",
            Clue.script_id == game.script_id,
        )
        .order_by(GameClueDisclosure.created_at, GameClueDisclosure.id)
    ).all()


def _clue_read(
    clue: Clue,
    knowledge_source: str,
    first_known_at: datetime,
    source_game_character_id: int | None,
) -> ClueEvidenceRead:
    return ClueEvidenceRead(
        clue_id=clue.id,
        name=clue.name,
        description=clue.description,
        act=clue.act,
        location=clue.location,
        importance=clue.importance,
        knowledge_source=knowledge_source,
        first_known_at=first_known_at,
        source_game_character_id=source_game_character_id,
    )


def _existing_semantic_disclosure(
    db: Session,
    game_id: int,
    clue_id: int,
    source_id: int,
    visibility: str,
    target_id: int | None,
) -> GameClueDisclosure | None:
    query = select(GameClueDisclosure).where(
        GameClueDisclosure.game_session_id == game_id,
        GameClueDisclosure.clue_id == clue_id,
        GameClueDisclosure.visibility == visibility,
    )
    if visibility == "public":
        return db.scalar(query.order_by(GameClueDisclosure.id).limit(1))
    return db.scalar(
        query.where(
            GameClueDisclosure.source_game_character_id == source_id,
            GameClueDisclosure.target_game_character_id == target_id,
        )
    )


def _disclosure_read(
    disclosure: GameClueDisclosure, *, replayed: bool = False
) -> ClueDisclosureRead:
    return ClueDisclosureRead(
        id=disclosure.id,
        game_id=disclosure.game_session_id,
        clue_id=disclosure.clue_id,
        source_game_character_id=disclosure.source_game_character_id,
        visibility=disclosure.visibility,
        target_game_character_id=disclosure.target_game_character_id,
        related_message_id=disclosure.related_message_id,
        created_at=disclosure.created_at,
        replayed=replayed,
    )


def _matches_request(disclosure: GameClueDisclosure, payload: ClueShareRequest) -> bool:
    return (
        disclosure.clue_id == payload.clue_id
        and disclosure.visibility == payload.visibility
        and disclosure.target_game_character_id == payload.target_game_character_id
    )


def _disclosure_message_content(
    source: GameCharacter, clue: Clue, visibility: str
) -> str:
    verb = "公开展示" if visibility == "public" else "私下分享"
    return f"{source.character.name}{verb}线索《{clue.name}》：{clue.description}"


def _human_character(db: Session, game_id: int) -> GameCharacter:
    humans = db.scalars(
        select(GameCharacter)
        .where(
            GameCharacter.game_session_id == game_id,
            GameCharacter.controller_type == "human",
        )
        .order_by(GameCharacter.id)
    ).all()
    if len(humans) != 1:
        raise GameRuleError("The unique Human character is not determined")
    return humans[0]


def _game(db: Session, game_id: int) -> GameSession:
    game = db.get(GameSession, game_id)
    if game is None:
        raise LookupError("Game not found")
    return game


def _require_search_phase(game: GameSession) -> None:
    if not can_investigate(game.status, game.current_phase):
        raise GameRuleError("Investigation is not allowed in the current phase")


def _require_game_in_progress(game: GameSession) -> None:
    if game.status != "in_progress":
        raise GameRuleError("Clue sharing requires an in-progress game")


def _phase_key(value: datetime | None) -> str:
    if value is None:
        return "none"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()
