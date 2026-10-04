"""Tests for SQLite chat history operations."""

import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from src.database import (
    connect_database,
    create_conversation,
    delete_conversation,
    delete_turn,
    get_messages,
    get_turns,
    init_database,
    list_conversations,
    save_turn,
)


class DatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.database_path = Path(temporary_directory.name) / "chat.db"
        init_database(self.database_path)

    def test_create_conversation_stores_utc_timestamps(self) -> None:
        conversation_id = create_conversation("项目讨论", self.database_path)

        conversations = list_conversations(self.database_path)
        self.assertEqual(len(conversations), 1)
        self.assertEqual(conversations[0]["id"], conversation_id)
        self.assertEqual(conversations[0]["title"], "项目讨论")

        created_at = datetime.fromisoformat(conversations[0]["created_at"])
        updated_at = datetime.fromisoformat(conversations[0]["updated_at"])
        self.assertEqual(created_at.utcoffset(), timedelta(0))
        self.assertEqual(updated_at.utcoffset(), timedelta(0))
        self.assertEqual(get_messages(conversation_id, self.database_path), [])

    def test_init_database_migrates_existing_conversations(self) -> None:
        legacy_path = self.database_path.parent / "legacy.db"
        connection = sqlite3.connect(legacy_path)
        try:
            connection.execute(
                """
                CREATE TABLE conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                INSERT INTO conversations (id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    "legacy-1",
                    "旧会话标题",
                    "2026-10-04T00:00:00+00:00",
                    "2026-10-04T00:00:00+00:00",
                ),
            )
            connection.commit()
        finally:
            connection.close()

        init_database(legacy_path)
        connection = connect_database(legacy_path)
        try:
            migrated = connection.execute(
                "SELECT title, title_generated FROM conversations WHERE id = ?",
                ("legacy-1",),
            ).fetchone()
        finally:
            connection.close()

        self.assertEqual(migrated["title"], "旧会话标题")
        self.assertEqual(migrated["title_generated"], 1)
        save_turn(
            "legacy-1",
            "后续问题",
            "后续回答",
            legacy_path,
            conversation_title="不应替换旧标题",
        )
        self.assertEqual(list_conversations(legacy_path)[0]["title"], "旧会话标题")

    def test_list_conversations_orders_by_recent_update(self) -> None:
        older_id = create_conversation("较早会话", self.database_path)
        newer_id = create_conversation("较新会话", self.database_path)
        connection = connect_database(self.database_path)
        try:
            with connection:
                connection.execute(
                    "UPDATE conversations SET updated_at = ? WHERE id = ?",
                    ("2026-10-03T00:00:00+00:00", older_id),
                )
                connection.execute(
                    "UPDATE conversations SET updated_at = ? WHERE id = ?",
                    ("2026-10-04T00:00:00+00:00", newer_id),
                )
        finally:
            connection.close()

        listed_ids = [
            conversation["id"]
            for conversation in list_conversations(self.database_path)
        ]
        self.assertEqual(listed_ids, [newer_id, older_id])

    def test_save_turn_reads_messages_in_sequence_order(self) -> None:
        conversation_id = create_conversation(database_path=self.database_path)
        save_turn(
            conversation_id, "第一个问题", "第一个回答", self.database_path
        )
        save_turn(
            conversation_id, "第二个问题", "第二个回答", self.database_path
        )

        messages = get_messages(conversation_id, self.database_path)
        self.assertEqual(
            [(message["role"], message["content"]) for message in messages],
            [
                ("user", "第一个问题"),
                ("assistant", "第一个回答"),
                ("user", "第二个问题"),
                ("assistant", "第二个回答"),
            ],
        )
        self.assertEqual([message["sequence"] for message in messages], [1, 2, 3, 4])
        self.assertEqual(messages[0]["turn_id"], messages[1]["turn_id"])
        self.assertEqual(messages[2]["turn_id"], messages[3]["turn_id"])
        self.assertNotEqual(messages[0]["turn_id"], messages[2]["turn_id"])
        self.assertEqual(
            [
                (turn["user_content"], turn["assistant_content"])
                for turn in get_turns(conversation_id, self.database_path)
            ],
            [("第一个问题", "第一个回答"), ("第二个问题", "第二个回答")],
        )

    def test_delete_turn_preserves_other_turns_and_allows_future_saves(self) -> None:
        conversation_id = create_conversation(database_path=self.database_path)
        for number in range(1, 4):
            save_turn(
                conversation_id,
                f"问题{number}",
                f"回答{number}",
                self.database_path,
            )
        turns = get_turns(conversation_id, self.database_path)

        deleted_count = delete_turn(
            conversation_id, turns[1]["turn_id"], self.database_path
        )

        self.assertEqual(deleted_count, 2)
        self.assertEqual(
            [
                (turn["user_content"], turn["assistant_content"])
                for turn in get_turns(conversation_id, self.database_path)
            ],
            [("问题1", "回答1"), ("问题3", "回答3")],
        )
        save_turn(conversation_id, "问题4", "回答4", self.database_path)
        messages = get_messages(conversation_id, self.database_path)
        self.assertEqual(
            [message["content"] for message in messages],
            ["问题1", "回答1", "问题3", "回答3", "问题4", "回答4"],
        )
        self.assertEqual(
            [message["sequence"] for message in messages], [1, 2, 5, 6, 7, 8]
        )

    def test_saving_turn_updates_utc_timestamps(self) -> None:
        created_at = datetime(2026, 10, 4, 12, tzinfo=timezone.utc)
        first_updated_at = datetime(2026, 10, 4, 13, tzinfo=timezone.utc)
        updated_at = datetime(2026, 10, 4, 14, tzinfo=timezone.utc)
        with patch("src.database.datetime") as clock:
            clock.now.side_effect = [created_at, first_updated_at, updated_at]
            conversation_id = create_conversation(database_path=self.database_path)
            save_turn(
                conversation_id,
                "首个问题",
                "首个回答",
                self.database_path,
                conversation_title="首个问题",
            )
            save_turn(
                conversation_id,
                "后续问题",
                "后续回答",
                self.database_path,
                conversation_title="不能覆盖原标题",
            )

        conversation = list_conversations(self.database_path)[0]
        self.assertEqual(conversation["title"], "首个问题")
        self.assertEqual(conversation["created_at"], created_at.isoformat())
        self.assertEqual(conversation["updated_at"], updated_at.isoformat())
        messages = get_messages(conversation_id, self.database_path)
        self.assertEqual(
            {message["created_at"] for message in messages},
            {first_updated_at.isoformat(), updated_at.isoformat()},
        )

    def test_deleting_all_turns_does_not_replace_conversation_title(self) -> None:
        conversation_id = create_conversation(database_path=self.database_path)
        save_turn(
            conversation_id,
            "新对话",
            "最初的回答",
            self.database_path,
            conversation_title="新对话",
        )
        turn_id = get_turns(conversation_id, self.database_path)[0]["turn_id"]
        delete_turn(conversation_id, turn_id, self.database_path)

        save_turn(
            conversation_id,
            "新问题",
            "新回答",
            self.database_path,
            conversation_title="新问题",
        )

        self.assertEqual(
            list_conversations(self.database_path)[0]["title"], "新对话"
        )

    def test_saved_messages_survive_reconnecting(self) -> None:
        conversation_id = create_conversation(database_path=self.database_path)
        save_turn(conversation_id, "问题", "回答", self.database_path)

        connection = connect_database(self.database_path)
        try:
            messages = connection.execute(
                "SELECT role, content FROM messages WHERE conversation_id = ? "
                "ORDER BY sequence",
                (conversation_id,),
            ).fetchall()
        finally:
            connection.close()

        self.assertEqual(
            [(message["role"], message["content"]) for message in messages],
            [("user", "问题"), ("assistant", "回答")],
        )

    def test_failed_turn_rolls_back_both_messages_and_timestamp(self) -> None:
        conversation_id = create_conversation(database_path=self.database_path)
        timestamp_before = list_conversations(self.database_path)[0]["updated_at"]

        connection = connect_database(self.database_path)
        try:
            connection.execute(
                """
                CREATE TRIGGER reject_assistant_message
                BEFORE INSERT ON messages
                WHEN NEW.role = 'assistant'
                BEGIN
                    SELECT RAISE(ABORT, 'forced test failure');
                END
                """
            )
            connection.commit()
        finally:
            connection.close()

        with self.assertRaises(sqlite3.IntegrityError):
            save_turn(
                conversation_id,
                "问题",
                "回答",
                self.database_path,
                conversation_title="不应保存",
            )

        self.assertEqual(get_messages(conversation_id, self.database_path), [])
        self.assertEqual(list_conversations(self.database_path)[0]["title"], "新对话")
        timestamp_after = list_conversations(self.database_path)[0]["updated_at"]
        self.assertEqual(timestamp_after, timestamp_before)

    def test_failed_title_update_rolls_back_turn(self) -> None:
        conversation_id = create_conversation(database_path=self.database_path)
        conversation_before = list_conversations(self.database_path)[0]
        connection = connect_database(self.database_path)
        try:
            connection.execute(
                """
                CREATE TRIGGER reject_conversation_title
                BEFORE UPDATE OF title ON conversations
                WHEN NEW.title = '触发失败'
                BEGIN
                    SELECT RAISE(ABORT, 'forced title update failure');
                END
                """
            )
            connection.commit()
        finally:
            connection.close()

        with self.assertRaises(sqlite3.IntegrityError):
            save_turn(
                conversation_id,
                "问题",
                "回答",
                self.database_path,
                conversation_title="触发失败",
            )

        conversation_after = list_conversations(self.database_path)[0]
        self.assertEqual(get_messages(conversation_id, self.database_path), [])
        self.assertEqual(conversation_after["title"], "新对话")
        self.assertEqual(
            conversation_after["updated_at"], conversation_before["updated_at"]
        )

    def test_delete_conversation_cascades_messages(self) -> None:
        conversation_id = create_conversation(database_path=self.database_path)
        save_turn(conversation_id, "问题", "回答", self.database_path)

        self.assertTrue(delete_conversation(conversation_id, self.database_path))
        self.assertFalse(delete_conversation(conversation_id, self.database_path))
        self.assertEqual(get_messages(conversation_id, self.database_path), [])
        self.assertEqual(list_conversations(self.database_path), [])


if __name__ == "__main__":
    unittest.main()
