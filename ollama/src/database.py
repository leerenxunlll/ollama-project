"""SQLite schema initialization for chat history."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


DATABASE_PATH = Path(__file__).resolve().parents[1] / "data" / "chat.db"
DEFAULT_CONVERSATION_TITLE = "新对话"


def connect_database(database_path: Path | str = DATABASE_PATH) -> sqlite3.Connection:
    """Open a database connection with foreign key enforcement enabled."""
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.row_factory = sqlite3.Row
    return connection


def init_database(database_path: Path | str = DATABASE_PATH) -> None:
    """Create the chat history tables if they do not already exist."""
    connection = connect_database(database_path)
    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                title_generated INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conversation_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(conversations)")
        }
        if "title_generated" not in conversation_columns:
            connection.execute(
                """
                ALTER TABLE conversations
                ADD COLUMN title_generated INTEGER NOT NULL DEFAULT 1
                """
            )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                turn_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (conversation_id)
                    REFERENCES conversations(id)
                    ON DELETE CASCADE,
                UNIQUE (conversation_id, sequence)
            )
            """
        )
        connection.commit()
    finally:
        connection.close()


def create_conversation(
    title: str = DEFAULT_CONVERSATION_TITLE,
    database_path: Path | str = DATABASE_PATH,
) -> str:
    """Create a conversation and return its internal ID."""
    conversation_id = str(uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()
    title_generated = int(title != DEFAULT_CONVERSATION_TITLE)
    connection = connect_database(database_path)
    try:
        connection.execute(
            """
            INSERT INTO conversations (
                id, title, created_at, updated_at, title_generated
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (conversation_id, title, timestamp, timestamp, title_generated),
        )
        connection.commit()
    finally:
        connection.close()
    return conversation_id


def list_conversations(database_path: Path | str = DATABASE_PATH) -> list[dict]:
    """Return conversations from most recently updated to oldest."""
    connection = connect_database(database_path)
    try:
        rows = connection.execute(
            """
            SELECT id, title, created_at, updated_at
            FROM conversations
            ORDER BY updated_at DESC, created_at DESC, id
            """
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def save_turn(
    conversation_id: str,
    user_content: str,
    assistant_content: str,
    database_path: Path | str = DATABASE_PATH,
    conversation_title: str | None = None,
) -> None:
    """Save a turn and its first title suggestion in one transaction."""
    turn_id = str(uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()
    connection = connect_database(database_path)
    try:
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            next_sequence = connection.execute(
                """
                SELECT COALESCE(MAX(sequence), 0) + 1
                FROM messages
                WHERE conversation_id = ?
                """,
                (conversation_id,),
            ).fetchone()[0]
            connection.executemany(
                """
                INSERT INTO messages (
                    conversation_id, turn_id, role, content, sequence, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        conversation_id,
                        turn_id,
                        "user",
                        user_content,
                        next_sequence,
                        timestamp,
                    ),
                    (
                        conversation_id,
                        turn_id,
                        "assistant",
                        assistant_content,
                        next_sequence + 1,
                        timestamp,
                    ),
                ),
            )
            if next_sequence == 1 and conversation_title is not None:
                connection.execute(
                    """
                    UPDATE conversations
                    SET title = CASE WHEN title_generated = 0 THEN ? ELSE title END,
                        title_generated = 1,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (conversation_title, timestamp, conversation_id),
                )
            else:
                connection.execute(
                    "UPDATE conversations SET updated_at = ? WHERE id = ?",
                    (timestamp, conversation_id),
                )
    finally:
        connection.close()


def get_messages(
    conversation_id: str,
    database_path: Path | str = DATABASE_PATH,
) -> list[dict]:
    """Return messages for a conversation in sequence order."""
    connection = connect_database(database_path)
    try:
        rows = connection.execute(
            """
            SELECT id, conversation_id, turn_id, role, content, sequence, created_at
            FROM messages
            WHERE conversation_id = ?
            ORDER BY sequence
            """,
            (conversation_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def get_turns(
    conversation_id: str,
    database_path: Path | str = DATABASE_PATH,
) -> list[dict]:
    """Return conversation turns in the order of their user messages."""
    messages = get_messages(conversation_id, database_path)
    turns = {}
    for message in messages:
        turn = turns.setdefault(message["turn_id"], {"turn_id": message["turn_id"]})
        turn[f"{message['role']}_content"] = message["content"]
    return list(turns.values())


def delete_turn(
    conversation_id: str,
    turn_id: str,
    database_path: Path | str = DATABASE_PATH,
) -> int:
    """Delete one turn and update its conversation timestamp."""
    timestamp = datetime.now(timezone.utc).isoformat()
    connection = connect_database(database_path)
    try:
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                "DELETE FROM messages WHERE conversation_id = ? AND turn_id = ?",
                (conversation_id, turn_id),
            )
            if cursor.rowcount:
                connection.execute(
                    "UPDATE conversations SET updated_at = ? WHERE id = ?",
                    (timestamp, conversation_id),
                )
            return cursor.rowcount
    finally:
        connection.close()


def delete_conversation(
    conversation_id: str,
    database_path: Path | str = DATABASE_PATH,
) -> bool:
    """Delete a conversation; its messages are removed by the foreign key."""
    connection = connect_database(database_path)
    try:
        with connection:
            cursor = connection.execute(
                "DELETE FROM conversations WHERE id = ?", (conversation_id,)
            )
            return cursor.rowcount > 0
    finally:
        connection.close()
