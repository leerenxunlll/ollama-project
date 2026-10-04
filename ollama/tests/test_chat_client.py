"""Tests for chat client persistence without contacting Ollama."""

import io
import re
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from src import chat_client
from src.database import (
    connect_database,
    create_conversation,
    get_messages,
    get_turns,
    init_database,
    list_conversations,
    save_turn,
)


class ChatClientPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.database_path = Path(temporary_directory.name) / "chat.db"
        init_database(self.database_path)

    def test_successful_turn_saves_only_the_final_answer(self) -> None:
        responses = [
            {"message": {"content": "<think>内部推理</think>第一轮回答"}},
            {"message": {"content": "第二轮回答"}},
        ]
        requests = []

        def respond(messages):
            requests.append([message.copy() for message in messages])
            return responses.pop(0)

        with (
            patch(
                "builtins.input",
                side_effect=["第一轮问题", "第二轮问题", "exit"],
            ),
            patch.object(chat_client, "chat", side_effect=respond),
            redirect_stdout(io.StringIO()),
        ):
            chat_client.main(self.database_path)

        conversation = list_conversations(self.database_path)[0]
        self.assertEqual(conversation["title"], "第一轮问题")
        messages = get_messages(conversation["id"], self.database_path)
        self.assertEqual(
            [message["role"] for message in messages],
            ["user", "assistant", "user", "assistant"],
        )
        self.assertEqual(
            [message["content"] for message in messages],
            [
                "第一轮问题",
                "第一轮回答",
                "第二轮问题",
                "第二轮回答",
            ],
        )
        self.assertEqual(
            requests[1],
            [
                {"role": "user", "content": "第一轮问题"},
                {"role": "assistant", "content": "第一轮回答"},
                {"role": "user", "content": "第二轮问题"},
            ],
        )

    def test_restart_starts_a_fresh_context_and_keeps_old_history(self) -> None:
        requests = []

        def respond(messages):
            requests.append([message.copy() for message in messages])
            return {"message": {"content": "回答"}}

        with (
            patch(
                "builtins.input",
                side_effect=["第一次问题", "exit", "第二次问题", "exit"],
            ),
            patch.object(chat_client, "chat", side_effect=respond),
            redirect_stdout(io.StringIO()),
        ):
            chat_client.main(self.database_path)
            chat_client.main(self.database_path)

        self.assertEqual(
            requests,
            [
                [{"role": "user", "content": "第一次问题"}],
                [{"role": "user", "content": "第二次问题"}],
            ],
        )
        conversations = list_conversations(self.database_path)
        self.assertEqual(len(conversations), 2)
        stored_prompts = {
            get_messages(conversation["id"], self.database_path)[0]["content"]
            for conversation in conversations
        }
        self.assertEqual(stored_prompts, {"第一次问题", "第二次问题"})

    def test_ollama_failure_does_not_save_or_add_the_user_message(self) -> None:
        requests = []

        def fail_then_succeed(messages):
            requests.append([message.copy() for message in messages])
            if len(requests) == 1:
                return None
            return {"message": {"content": "成功回答"}}

        with (
            patch(
                "builtins.input",
                side_effect=["失败问题", "成功问题", "exit"],
            ),
            patch.object(chat_client, "chat", side_effect=fail_then_succeed),
            redirect_stdout(io.StringIO()),
        ):
            chat_client.main(self.database_path)

        self.assertEqual(
            requests,
            [
                [{"role": "user", "content": "失败问题"}],
                [{"role": "user", "content": "成功问题"}],
            ],
        )
        conversations = list_conversations(self.database_path)
        self.assertEqual(len(conversations), 1)
        self.assertEqual(conversations[0]["title"], "成功问题")
        messages = get_messages(conversations[0]["id"], self.database_path)
        self.assertEqual(
            [(message["role"], message["content"]) for message in messages],
            [("user", "成功问题"), ("assistant", "成功回答")],
        )

    def test_database_failure_reports_warning_and_ends_the_session(self) -> None:
        response = {"message": {"content": "回答"}}
        output = io.StringIO()
        with (
            patch("builtins.input", side_effect=["问题", "后续问题"]),
            patch.object(chat_client, "chat", return_value=response),
            patch.object(
                chat_client,
                "save_turn",
                side_effect=sqlite3.OperationalError("simulated write failure"),
            ),
            redirect_stdout(output),
        ):
            chat_client.main(self.database_path)

        self.assertIn("回答", output.getvalue())
        self.assertIn("聊天记录保存失败", output.getvalue())
        self.assertEqual(len(list_conversations(self.database_path)), 1)
        conversation = list_conversations(self.database_path)[0]
        self.assertEqual(get_messages(conversation["id"], self.database_path), [])

    def test_database_initialization_failure_is_reported(self) -> None:
        output = io.StringIO()
        with (
            patch.object(
                chat_client,
                "init_database",
                side_effect=sqlite3.OperationalError(
                    "simulated initialization failure"
                ),
            ),
            redirect_stdout(output),
        ):
            chat_client.main(self.database_path)

        self.assertIn("数据库初始化失败", output.getvalue())

    def test_list_open_history_and_continue_selected_conversation(self) -> None:
        now = datetime.now(timezone.utc)
        older_id = create_conversation("较早会话", self.database_path)
        save_turn(older_id, "较早问题", "较早回答", self.database_path)
        newer_id = create_conversation("最近会话", self.database_path)
        save_turn(newer_id, "最近问题", "最近回答", self.database_path)

        connection = connect_database(self.database_path)
        try:
            with connection:
                connection.execute(
                    "UPDATE conversations SET updated_at = ? WHERE id = ?",
                    ((now - timedelta(days=2)).isoformat(), older_id),
                )
                connection.execute(
                    "UPDATE conversations SET updated_at = ? WHERE id = ?",
                    ((now - timedelta(days=1)).isoformat(), newer_id),
                )
        finally:
            connection.close()

        conversations = list_conversations(self.database_path)
        selected_conversation = conversations[1]
        selected_messages = get_messages(
            selected_conversation["id"], self.database_path
        )
        requests = []
        output = io.StringIO()
        with (
            patch(
                "builtins.input",
                side_effect=[
                    "   ",
                    "/list",
                    "/new",
                    "/open 2",
                    "续聊问题",
                    "/history",
                    "/exit",
                ],
            ),
            patch.object(
                chat_client,
                "chat",
                side_effect=lambda messages: requests.append(messages)
                or {"message": {"content": "续聊回答"}},
            ),
            redirect_stdout(output),
        ):
            chat_client.main(self.database_path)

        expected_request = [
            {"role": message["role"], "content": message["content"]}
            for message in selected_messages
        ]
        expected_request.append({"role": "user", "content": "续聊问题"})
        self.assertEqual(requests, [expected_request])
        self.assertEqual(len(list_conversations(self.database_path)), 3)
        self.assertEqual(
            [
                (message["role"], message["content"])
                for message in get_messages(
                    selected_conversation["id"], self.database_path
                )
            ][-2:],
            [("user", "续聊问题"), ("assistant", "续聊回答")],
        )
        visible_output = re.sub(r"\033\[[0-9;]*m", "", output.getvalue())
        expected_display_time = datetime.fromisoformat(
            conversations[0]["updated_at"]
        ).astimezone().strftime("%Y-%m-%d %H:%M")
        self.assertIn("1. 最近会话", visible_output)
        self.assertIn("2. 较早会话", visible_output)
        self.assertIn(expected_display_time, visible_output)
        self.assertIn("[1] User: 较早问题", visible_output)
        self.assertIn("[2] User: 续聊问题", visible_output)
        self.assertNotIn(selected_conversation["id"], visible_output)

    def test_new_starts_an_independent_conversation(self) -> None:
        old_conversation_id = create_conversation("旧会话", self.database_path)
        save_turn(old_conversation_id, "旧问题", "旧回答", self.database_path)
        old_messages = get_messages(old_conversation_id, self.database_path)
        requests = []

        with (
            patch(
                "builtins.input",
                side_effect=["/open 1", "/new", "新问题", "/exit"],
            ),
            patch.object(
                chat_client,
                "chat",
                side_effect=lambda messages: requests.append(messages)
                or {"message": {"content": "新回答"}},
            ),
            redirect_stdout(io.StringIO()),
        ):
            chat_client.main(self.database_path)

        self.assertEqual(
            requests,
            [[{"role": "user", "content": "新问题"}]],
        )
        conversations = list_conversations(self.database_path)
        self.assertEqual(len(conversations), 2)
        self.assertEqual(
            get_messages(old_conversation_id, self.database_path), old_messages
        )
        new_conversation_id = next(
            conversation["id"]
            for conversation in conversations
            if conversation["id"] != old_conversation_id
        )
        self.assertEqual(
            [
                (message["role"], message["content"])
                for message in get_messages(new_conversation_id, self.database_path)
            ],
            [("user", "新问题"), ("assistant", "新回答")],
        )
        self.assertEqual(
            next(
                conversation["title"]
                for conversation in conversations
                if conversation["id"] == new_conversation_id
            ),
            "新问题",
        )

    def test_long_first_prompt_title_is_truncated_without_extra_model_call(
        self,
    ) -> None:
        prompt = "标题测试" * 10
        expected_title = f"{prompt[:27]}..."

        with (
            patch("builtins.input", side_effect=[prompt, "/exit"]),
            patch.object(
                chat_client,
                "chat",
                return_value={"message": {"content": "回答"}},
            ) as chat_mock,
            redirect_stdout(io.StringIO()),
        ):
            chat_client.main(self.database_path)

        conversation = list_conversations(self.database_path)[0]
        self.assertEqual(conversation["title"], expected_title)
        self.assertEqual(len(conversation["title"]), 30)
        chat_mock.assert_called_once()

    def test_delete_requires_confirmation_and_resets_active_session(self) -> None:
        deleted_id = create_conversation("待删除", self.database_path)
        save_turn(deleted_id, "旧问题", "旧回答", self.database_path)
        kept_id = create_conversation("保留会话", self.database_path)
        connection = connect_database(self.database_path)
        try:
            with connection:
                connection.execute(
                    "UPDATE conversations SET updated_at = ? WHERE id = ?",
                    ("2099-01-01T00:00:00+00:00", deleted_id),
                )
                connection.execute(
                    "UPDATE conversations SET updated_at = ? WHERE id = ?",
                    ("2000-01-01T00:00:00+00:00", kept_id),
                )
        finally:
            connection.close()

        commands = iter(
            [
                "/list",
                "/open 1",
                "/delete 1",
                "",
                "/list",
                "/delete 1",
                "yes",
                "新问题",
                "/exit",
            ]
        )
        prompts = []
        requests = []
        output = io.StringIO()

        def read_input(prompt):
            prompts.append(prompt)
            return next(commands)

        with (
            patch("builtins.input", side_effect=read_input),
            patch.object(
                chat_client,
                "chat",
                side_effect=lambda messages: requests.append(
                    [message.copy() for message in messages]
                )
                or {"message": {"content": "新回答"}},
            ),
            redirect_stdout(output),
        ):
            chat_client.main(self.database_path)

        confirmation_prompts = [prompt for prompt in prompts if "Delete" in prompt]
        self.assertEqual(len(confirmation_prompts), 2)
        self.assertTrue(
            all('"待删除"? [y/N]' in prompt for prompt in confirmation_prompts)
        )
        self.assertIn("已取消删除", output.getvalue())
        self.assertIn("已删除会话：待删除", output.getvalue())
        self.assertEqual(
            requests,
            [[{"role": "user", "content": "新问题"}]],
        )
        conversations = list_conversations(self.database_path)
        conversation_ids = {conversation["id"] for conversation in conversations}
        self.assertEqual(len(conversations), 2)
        self.assertIn(kept_id, conversation_ids)
        self.assertNotIn(deleted_id, conversation_ids)
        self.assertEqual(get_messages(deleted_id, self.database_path), [])

    def test_delete_turn_updates_history_and_model_context(self) -> None:
        conversation_id = create_conversation("三轮会话", self.database_path)
        for number in range(1, 4):
            save_turn(
                conversation_id,
                f"问题{number}",
                f"回答{number}",
                self.database_path,
            )
        original_turns = get_turns(conversation_id, self.database_path)
        requests = []
        output = io.StringIO()

        with (
            patch(
                "builtins.input",
                side_effect=[
                    "/open 1",
                    "/delete-turn 9",
                    "/delete-turn 2",
                    "/history",
                    "新问题",
                    "/history",
                    "/exit",
                ],
            ),
            patch.object(
                chat_client,
                "chat",
                side_effect=lambda messages: requests.append(
                    [message.copy() for message in messages]
                )
                or {"message": {"content": "新回答"}},
            ),
            redirect_stdout(output),
        ):
            chat_client.main(self.database_path)

        self.assertEqual(
            requests,
            [
                [
                    {"role": "user", "content": "问题1"},
                    {"role": "assistant", "content": "回答1"},
                    {"role": "user", "content": "问题3"},
                    {"role": "assistant", "content": "回答3"},
                    {"role": "user", "content": "新问题"},
                ]
            ],
        )
        self.assertIn("轮次编号无效：9", output.getvalue())
        self.assertIn("删除历史 Turn 不会重新生成后续回答", output.getvalue())
        self.assertIn("之后的消息可能仍引用已删除内容。", output.getvalue())
        visible_output = re.sub(r"\033\[[0-9;]*m", "", output.getvalue())
        self.assertIn("[1] User: 问题1", visible_output)
        self.assertIn("[2] User: 问题3", visible_output)
        self.assertIn("[3] User: 新问题", visible_output)
        stored_messages = get_messages(conversation_id, self.database_path)
        self.assertEqual(
            [message["content"] for message in stored_messages],
            ["问题1", "回答1", "问题3", "回答3", "新问题", "新回答"],
        )
        self.assertEqual(
            [
                message["turn_id"]
                for message in stored_messages
                if message["role"] == "user"
            ],
            [
                original_turns[0]["turn_id"],
                original_turns[2]["turn_id"],
                stored_messages[-2]["turn_id"],
            ],
        )

    def test_empty_history_and_invalid_commands_do_not_call_ollama(self) -> None:
        output = io.StringIO()
        with (
            patch(
                "builtins.input",
                side_effect=[
                    "/list",
                    "/history",
                    "/open 1",
                    "/open",
                    "/new extra",
                    "/unsupported",
                    "/delete",
                    "/delete 1",
                    "/delete-turn 1",
                    "/exit",
                ],
            ),
            patch.object(chat_client, "chat") as chat_mock,
            redirect_stdout(output),
        ):
            chat_client.main(self.database_path)

        self.assertFalse(chat_mock.called)
        self.assertEqual(list_conversations(self.database_path), [])
        visible_output = re.sub(r"\033\[[0-9;]*m", "", output.getvalue())
        self.assertIn("暂无历史会话", visible_output)
        self.assertIn("当前没有活动会话", visible_output)
        self.assertIn("会话编号无效", visible_output)
        self.assertIn("用法：/open <number>", visible_output)
        self.assertIn("用法：/new", visible_output)
        self.assertIn("未知命令", visible_output)
        self.assertIn("用法：/delete <number>", visible_output)
        self.assertIn("会话编号无效：1", visible_output)


if __name__ == "__main__":
    unittest.main()
