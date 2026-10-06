"""Tests for deterministic AI speaker selection."""

from dataclasses import FrozenInstanceError

import pytest

from app.game.turn_manager import (
    MAX_AI_RESPONSES_PER_HUMAN_TURN,
    Speaker,
    select_initial_responders,
    select_next_ai,
    select_reaction_responder,
)


@pytest.fixture
def ai_speakers() -> list[Speaker]:
    """Return speakers deliberately out of ID order."""
    return [
        Speaker(game_character_id=30, name="Chen Wei"),
        Speaker(game_character_id=10, name="Lin Yue"),
        Speaker(game_character_id=20, name="Zhao An"),
    ]


def test_initial_responders_follow_mention_order_and_are_limited(
    ai_speakers: list[Speaker],
) -> None:
    responders = select_initial_responders(
        "Chen Wei, then Zhao An, and finally Lin Yue.",
        ai_speakers,
        last_ai_speaker_id=None,
    )

    assert [speaker.game_character_id for speaker in responders] == [30, 20]
    assert len(responders) == MAX_AI_RESPONSES_PER_HUMAN_TURN


def test_mentions_are_case_insensitive_and_ties_use_stable_id_order() -> None:
    speakers = [
        Speaker(game_character_id=22, name="Ann"),
        Speaker(game_character_id=11, name="Anna"),
    ]

    responders = select_initial_responders("ANNA", speakers, last_ai_speaker_id=None)

    assert [speaker.game_character_id for speaker in responders] == [11, 22]


@pytest.mark.parametrize(
    ("last_speaker_id", "expected_id"),
    [(None, 10), (10, 20), (20, 30), (30, 10), (999, 10)],
)
def test_no_mention_uses_round_robin_order(
    ai_speakers: list[Speaker], last_speaker_id: int | None, expected_id: int
) -> None:
    responders = select_initial_responders(
        "Please continue.", ai_speakers, last_speaker_id
    )

    assert [speaker.game_character_id for speaker in responders] == [expected_id]


def test_next_ai_returns_the_only_available_speaker() -> None:
    only_speaker = Speaker(game_character_id=7, name="Avery Stone")

    assert select_next_ai([only_speaker], last_ai_speaker_id=7) == only_speaker


def test_reaction_skips_current_and_already_replied_speakers(
    ai_speakers: list[Speaker],
) -> None:
    responder = select_reaction_responder(
        "Lin Yue, Zhao An, Chen Wei.",
        ai_speakers,
        replied_ids={10, 20},
    )

    assert responder == Speaker(game_character_id=30, name="Chen Wei")


def test_reaction_returns_none_when_every_mentioned_speaker_replied(
    ai_speakers: list[Speaker],
) -> None:
    responder = select_reaction_responder(
        "Zhao An, then Lin Yue.",
        ai_speakers,
        replied_ids={10, 20},
    )

    assert responder is None


def test_reaction_uses_first_unreplied_mention(
    ai_speakers: list[Speaker],
) -> None:
    responder = select_reaction_responder(
        "Chen Wei answered before Lin Yue.",
        ai_speakers,
        replied_ids=set(),
    )

    assert responder == Speaker(game_character_id=30, name="Chen Wei")


def test_speaker_is_immutable() -> None:
    speaker = Speaker(game_character_id=1, name="Avery Stone")

    with pytest.raises(FrozenInstanceError):
        speaker.name = "Changed Name"  # type: ignore[misc]
