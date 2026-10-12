"""Build permission-filtered context for one game character."""

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, aliased, selectinload

from app.game.state_machine import unlocked_script_chapter_phases
from app.models import (
    Character,
    CharacterMemory,
    CharacterScriptChapter,
    Clue,
    GameCharacter,
    GameCharacterClue,
    GameSession,
    Message,
    SharedScriptChapter,
)
from app.schemas.context import (
    CharacterContext,
    ContextCharacter,
    ContextClue,
    ContextGame,
    ContextMemory,
    ContextMessage,
    ContextOtherCharacter,
    ContextScriptChapter,
)

MESSAGE_CONTEXT_LIMIT = 20
MEMORY_CONTEXT_LIMIT = 20


def build_character_context(
    db: Session, game_id: int, game_character_id: int
) -> CharacterContext:
    """Return only the selected runtime character's authorized information."""
    game = db.get(GameSession, game_id)
    if game is None:
        raise LookupError("Game not found")

    characters = list(
        db.scalars(
            select(GameCharacter)
            .where(GameCharacter.game_session_id == game_id)
            .options(selectinload(GameCharacter.character))
            .order_by(GameCharacter.id)
        ).all()
    )
    current_character = next(
        (character for character in characters if character.id == game_character_id),
        None,
    )
    if current_character is None:
        raise LookupError("Character not found in this game")
    if current_character.character.script_id != game.script_id:
        raise LookupError("Character template does not belong to this script")

    sender_character = aliased(GameCharacter)
    receiver_character = aliased(GameCharacter)
    visible_public_message = and_(
        Message.channel_type.in_(("public", "system")),
        or_(
            Message.sender_game_character_id.is_(None),
            sender_character.game_session_id == game_id,
        ),
    )
    visible_private_message = and_(
        Message.channel_type == "private",
        or_(
            Message.sender_game_character_id == current_character.id,
            Message.receiver_game_character_id == current_character.id,
        ),
        sender_character.game_session_id == game_id,
        receiver_character.game_session_id == game_id,
    )
    public_messages = list(
        db.scalars(
            select(Message)
            .outerjoin(
                sender_character,
                sender_character.id == Message.sender_game_character_id,
            )
            .outerjoin(
                receiver_character,
                receiver_character.id == Message.receiver_game_character_id,
            )
            .where(
                Message.game_session_id == game_id,
                visible_public_message,
            )
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(MESSAGE_CONTEXT_LIMIT)
        ).all()
    )
    private_messages = list(
        db.scalars(
            select(Message)
            .outerjoin(
                sender_character,
                sender_character.id == Message.sender_game_character_id,
            )
            .outerjoin(
                receiver_character,
                receiver_character.id == Message.receiver_game_character_id,
            )
            .where(
                Message.game_session_id == game_id,
                visible_private_message,
            )
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(MESSAGE_CONTEXT_LIMIT)
        ).all()
    )
    public_messages.reverse()
    private_messages.reverse()

    clue_rows = db.execute(
        select(GameCharacterClue, Clue)
        .join(Clue, Clue.id == GameCharacterClue.clue_id)
        .where(
            GameCharacterClue.game_character_id == current_character.id,
            Clue.script_id == game.script_id,
        )
        .order_by(GameCharacterClue.discovered_at, GameCharacterClue.id)
    ).all()
    memories = list(
        db.scalars(
            select(CharacterMemory)
            .where(
                CharacterMemory.game_session_id == game_id,
                CharacterMemory.game_character_id == current_character.id,
            )
            .order_by(
                CharacterMemory.importance.desc(),
                CharacterMemory.created_at.desc(),
                CharacterMemory.id.desc(),
            )
            .limit(MEMORY_CONTEXT_LIMIT)
        ).all()
    )
    unlocked_phases = unlocked_script_chapter_phases(game.status, game.current_phase)
    shared_script_chapters = db.scalars(
        select(SharedScriptChapter)
        .where(
            SharedScriptChapter.script_id == game.script_id,
            SharedScriptChapter.unlock_phase.in_(unlocked_phases),
        )
        .order_by(SharedScriptChapter.chapter_order, SharedScriptChapter.id)
    ).all()
    character_script_chapters = db.scalars(
        select(CharacterScriptChapter)
        .join(Character, Character.id == CharacterScriptChapter.character_id)
        .where(
            Character.script_id == game.script_id,
            CharacterScriptChapter.character_id == current_character.character_id,
            CharacterScriptChapter.unlock_phase.in_(unlocked_phases),
        )
        .order_by(CharacterScriptChapter.chapter_order, CharacterScriptChapter.id)
    ).all()

    character_template = current_character.character
    return CharacterContext(
        game=ContextGame(
            id=game.id,
            status=game.status,
            current_phase=game.current_phase,
        ),
        character=ContextCharacter(
            game_character_id=current_character.id,
            character_id=character_template.id,
            name=character_template.name,
            identity=character_template.identity,
            public_background=character_template.public_background,
            private_background=character_template.private_background,
            personality=character_template.personality,
            speaking_style=character_template.speaking_style,
            personal_goal=character_template.personal_goal,
            personal_history=character_template.personal_history,
            relationship_to_victim=character_template.relationship_to_victim,
            pre_case_experience=character_template.pre_case_experience,
            private_secrets=character_template.private_secrets_json or [],
            initial_knowledge=character_template.initial_knowledge_json or [],
            current_emotion=current_character.current_emotion,
            current_goal=current_character.current_goal,
        ),
        other_characters=[
            ContextOtherCharacter(
                game_character_id=runtime_character.id,
                name=runtime_character.character.name,
                identity=runtime_character.character.identity,
                public_background=runtime_character.character.public_background,
            )
            for runtime_character in characters
            if runtime_character.id != current_character.id
        ],
        public_messages=[_context_message(message) for message in public_messages],
        private_messages=[_context_message(message) for message in private_messages],
        known_clues=[
            ContextClue(
                clue_id=clue.id,
                name=clue.name,
                description=clue.description,
                act=clue.act,
                location=clue.location,
                is_core=clue.is_core,
                importance=clue.importance,
                discovered_at=discovery.discovered_at,
                source=discovery.source,
            )
            for discovery, clue in clue_rows
        ],
        memories=[
            ContextMemory(
                content=memory.content,
                importance=memory.importance,
                created_at=memory.created_at,
            )
            for memory in memories
        ],
        shared_script_chapters=[
            _context_script_chapter(chapter) for chapter in shared_script_chapters
        ],
        character_script_chapters=[
            _context_script_chapter(chapter) for chapter in character_script_chapters
        ],
    )


def _context_message(message: Message) -> ContextMessage:
    """Copy only explicitly allowed message fields into the context schema."""
    return ContextMessage(
        id=message.id,
        sender_game_character_id=message.sender_game_character_id,
        channel_type=message.channel_type,
        receiver_game_character_id=message.receiver_game_character_id,
        content=message.content,
        created_at=message.created_at,
    )


def _context_script_chapter(
    chapter: SharedScriptChapter | CharacterScriptChapter,
) -> ContextScriptChapter:
    """Copy the complete allowed story chapter into the agent schema."""
    return ContextScriptChapter(
        chapter_id=chapter.id,
        chapter_order=chapter.chapter_order,
        unlock_phase=chapter.unlock_phase,
        title=chapter.title,
        content=chapter.content,
    )
