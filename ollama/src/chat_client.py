import sqlite3
from datetime import datetime

import requests

if __package__:
    from .database import (
        DATABASE_PATH,
        create_conversation,
        delete_conversation,
        delete_turn,
        get_messages,
        get_turns,
        init_database,
        list_conversations,
        save_turn,
    )
else:
    from database import (
        DATABASE_PATH,
        create_conversation,
        delete_conversation,
        delete_turn,
        get_messages,
        get_turns,
        init_database,
        list_conversations,
        save_turn,
    )

GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
BLUE = "\033[34m"
CYAN = "\033[36m"
RESET = "\033[0m"

URL = "http://localhost:11434/api/chat"
MODEL = "qwen3:4b"
TIMEOUT = 500
CONVERSATION_TITLE_MAX_LENGTH = 30


def chat(messages: list) -> dict | None:
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": False,
        "think": False,
    }
    try:
        response = requests.post(URL, json=payload, timeout=TIMEOUT)
        response.raise_for_status()
        return response.json()
    except requests.Timeout:
        print(f"{YELLOW}请求超时，请稍后重试。{RESET}")
    except requests.ConnectionError:
        print(f"{RED}无法连接 Ollama，请确认服务已启动。{RESET}")
    except requests.HTTPError as error:
        if error.response.status_code == 404:
            print(
                f"{RED}找不到模型 {MODEL}，"
                f"请检查模型名称或先下载模型。{RESET}"
            )
        else:
            print(
                f"{RED}请求失败，HTTP 状态码："
                f"{error.response.status_code}。{RESET}"
            )
    except requests.RequestException as error:
        print(f"{RED}请求出错：{error}{RESET}")
    return None

#简化回答，而不是把思考和推理部分都讲出来
def easy_answer(response) -> str:
    
    message = response["message"]["content"]
    if "</think>" in response["message"]["content"]:
       
        _, easy_message = message.split("</think>",1)# 只保留回答部分
        return easy_message.strip()    
    return message


def _title_from_prompt(prompt: str) -> str:
    if len(prompt) <= CONVERSATION_TITLE_MAX_LENGTH:
        return prompt
    return f"{prompt[:CONVERSATION_TITLE_MAX_LENGTH - 3]}..."


def _show_conversations(conversations) -> None:
    if not conversations:
        print(f"{YELLOW}暂无历史会话。{RESET}")
        return

    for number, conversation in enumerate(conversations, start=1):
        updated_at = datetime.fromisoformat(
            conversation["updated_at"]
        ).astimezone()
        display_time = updated_at.strftime("%Y-%m-%d %H:%M")
        print(
            f"{BLUE}{number}.{RESET} {conversation['title']}  {display_time}"
        )


def _show_history(conversation_id, database_path) -> None:
    if conversation_id is None:
        print(f"{YELLOW}当前没有活动会话。{RESET}")
        return

    turns = get_turns(conversation_id, database_path)
    if not turns:
        print(f"{YELLOW}当前会话还没有聊天记录。{RESET}")
        return

    for number, turn in enumerate(turns, start=1):
        print(f"{BLUE}[{number}]{RESET} User: {turn['user_content']}")
        print(f"    Assistant: {turn['assistant_content']}")


def main(database_path=DATABASE_PATH):
    try:
        #初始化数据库
        init_database(database_path)
    except sqlite3.Error as error:
        print(f"\033[31m数据库初始化失败：{error}\033[0m")
        return

    conversation_id = None
    messages = []
    displayed_conversations = None
    #进入对话，循环防止对话一次退出
    while True:
        #输入提示词，若提示词是exit或/exit则退出循环，若提示词为空则继续循环
        prompt = input(f"{CYAN}You (type 'exit' to quit): {RESET}").strip()
        if prompt.lower() in {"exit", "/exit"}:
            break
        if not prompt:
            continue
#切取提示词部分内容，可能是开头或者结尾
        command_parts = prompt.split(maxsplit=1)
        command = command_parts[0].lower()
        argument = command_parts[1] if len(command_parts) == 2 else ""
#解析命令
        if command == "/list":
            if argument:
                print(f"{RED}用法：/list{RESET}")
            else:
                displayed_conversations = list_conversations(database_path)
                _show_conversations(displayed_conversations)
            continue

        if command == "/open":
            try:
                number = int(argument)
            except ValueError:
                print(f"{RED}用法：/open <number>{RESET}")
                continue

            conversations = displayed_conversations
            if conversations is None:
                conversations = list_conversations(database_path)
            if number < 1 or number > len(conversations):
                print(f"{RED}会话编号无效：{number}{RESET}")
                continue

            selected_conversation = conversations[number - 1]
            conversation_id = selected_conversation["id"]
            messages = [
                {"role": message["role"], "content": message["content"]}
                for message in get_messages(conversation_id, database_path)
            ]
            print(
                f"{GREEN}已打开会话：{selected_conversation['title']}{RESET}"
            )
            continue

        if command == "/new":
            if argument:
                print(f"{RED}用法：/new{RESET}")
                continue
            conversation_id = create_conversation(database_path=database_path)
            messages = []
            print(f"{GREEN}已新建会话。{RESET}")
            continue

        if command == "/delete":
            try:
                number = int(argument)
            except ValueError:
                print(f"{RED}用法：/delete <number>{RESET}")
                continue

            conversations = displayed_conversations
            if conversations is None:
                conversations = list_conversations(database_path)
            if number < 1 or number > len(conversations):
                print(f"{RED}会话编号无效：{number}{RESET}")
                continue

            selected_conversation = conversations[number - 1]
            confirmation = input(
                f'{CYAN}Delete "{selected_conversation["title"]}"? [y/N] {RESET}'
            ).strip().lower()
            if confirmation not in {"y", "yes"}:
                print(f"{YELLOW}已取消删除。{RESET}")
                continue

            if delete_conversation(selected_conversation["id"], database_path):
                if selected_conversation["id"] == conversation_id:
                    conversation_id = None
                    messages = []
                displayed_conversations = None
                print(f"{GREEN}已删除会话：{selected_conversation['title']}{RESET}")
            else:
                print(f"{YELLOW}会话已不存在。{RESET}")
            continue

        if command == "/history":
            if argument:
                print(f"{RED}用法：/history{RESET}")
            else:
                _show_history(conversation_id, database_path)
            continue

        if command == "/delete-turn":
            if conversation_id is None:
                print(f"{YELLOW}当前没有活动会话。{RESET}")
                continue

            try:
                number = int(argument)
            except ValueError:
                print(f"{RED}用法：/delete-turn <number>{RESET}")
                continue

            turns = get_turns(conversation_id, database_path)
            if number < 1 or number > len(turns):
                print(f"{RED}轮次编号无效：{number}{RESET}")
                continue

            if number < len(turns):
                print(
                    f"{YELLOW}删除历史 Turn 不会重新生成后续回答，\n"
                    f"之后的消息可能仍引用已删除内容。{RESET}"
                )
            deleted_count = delete_turn(
                conversation_id,
                turns[number - 1]["turn_id"],
                database_path,
            )
            if deleted_count:
                messages = [
                    {"role": message["role"], "content": message["content"]}
                    for message in get_messages(conversation_id, database_path)
                ]
                print(f"{GREEN}已删除第 {number} 轮。{RESET}")
            else:
                print(f"{YELLOW}该轮次已不存在。{RESET}")
            continue

        if command.startswith("/"):
            print(f"{RED}未知命令：{command}{RESET}")
            continue

        request_messages = [*messages, {"role": "user", "content": prompt}]
        response = chat(request_messages)
        if response is None:
            continue

        easy_message = easy_answer(response)
        conversation_title = _title_from_prompt(prompt) if not messages else None

        try:
            if conversation_id is None:
                conversation_id = create_conversation(database_path=database_path)
            save_turn(
                conversation_id,
                prompt,
                easy_message,
                database_path,
                conversation_title=conversation_title,
            )
        except sqlite3.Error as error:
            print(f"{GREEN}Assistant:{RESET}", easy_message)
            warning = (
                f"{YELLOW}警告：聊天记录保存失败，"
                f"本次会话将结束：{error}{RESET}"
            )
            print(warning)
            break

        print(f"{GREEN}Assistant:{RESET}", easy_message)
        messages.extend(
            [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": easy_message},
            ]
        )


if __name__ == "__main__":
    main()
