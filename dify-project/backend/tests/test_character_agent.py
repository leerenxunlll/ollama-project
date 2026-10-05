"""Validation tests for structured character replies from Dify."""

import json

import pytest

from app.agents.character_agent import (
    CharacterOutputValidationError,
    parse_character_reply,
)


def _valid_output() -> dict:
    """Return a minimal valid structured character answer."""
    return {
        "speech": "我昨晚在旧仓库。",
        "inner_os": "他似乎有所怀疑。",
        "emotion": "nervous",
        "intent": "deflect",
        "memory_updates": [{"content": "玩家询问了旧仓库。", "importance": 3}],
    }


def test_valid_json_is_parsed_into_a_character_reply() -> None:
    reply = parse_character_reply(json.dumps(_valid_output(), ensure_ascii=False))

    assert reply.speech == "我昨晚在旧仓库。"
    assert reply.inner_os == "他似乎有所怀疑。"
    assert reply.emotion.value == "nervous"
    assert reply.intent.value == "deflect"
    assert reply.memory_updates[0].importance == 3


@pytest.mark.parametrize(
    "invalid_answer",
    [
        "not json",
        json.dumps(
            {key: value for key, value in _valid_output().items() if key != "speech"}
        ),
        json.dumps({**_valid_output(), "emotion": "joyful"}),
        json.dumps(
            {
                **_valid_output(),
                "memory_updates": [{"content": "无效", "importance": 6}],
            }
        ),
        json.dumps(
            {
                **_valid_output(),
                "memory_updates": [
                    {"content": "一", "importance": 1},
                    {"content": "二", "importance": 2},
                    {"content": "三", "importance": 3},
                ],
            }
        ),
        json.dumps({**_valid_output(), "speech": "   "}),
        f"```json\n{json.dumps(_valid_output())}\n```",
    ],
)
def test_invalid_structured_output_is_rejected(invalid_answer: str) -> None:
    with pytest.raises(CharacterOutputValidationError) as error:
        parse_character_reply(invalid_answer)

    assert str(error.value) == "Dify returned invalid structured character output"
    assert invalid_answer not in str(error.value)
