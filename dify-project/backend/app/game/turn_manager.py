"""Deterministic selection of AI characters that may speak next."""

from collections.abc import Collection, Sequence
from dataclasses import dataclass

MAX_AI_RESPONSES_PER_HUMAN_TURN = 2


@dataclass(frozen=True)
class Speaker:
    """The minimal character information needed for speaker selection."""

    game_character_id: int
    name: str


def _ordered_speakers(ai_speakers: Sequence[Speaker]) -> list[Speaker]:
    """Return speakers in a stable order independent of caller input order."""
    return sorted(ai_speakers, key=lambda speaker: speaker.game_character_id)


def _mentioned_speakers(content: str, ai_speakers: Sequence[Speaker]) -> list[Speaker]:
    """Find speakers by full-name substring, ordered by first mention."""
    folded_content = content.casefold()
    matches: list[tuple[int, Speaker]] = []

    for speaker in _ordered_speakers(ai_speakers):
        folded_name = speaker.name.casefold()
        if not folded_name:
            continue

        position = folded_content.find(folded_name)
        if position >= 0:
            matches.append((position, speaker))

    matches.sort(key=lambda match: match[0])
    return [speaker for _, speaker in matches]


def select_next_ai(
    ai_speakers: Sequence[Speaker], last_ai_speaker_id: int | None
) -> Speaker | None:
    """Select the next speaker in ID order, wrapping around at the end."""
    ordered = _ordered_speakers(ai_speakers)
    if not ordered:
        return None

    for index, speaker in enumerate(ordered):
        if speaker.game_character_id == last_ai_speaker_id:
            return ordered[(index + 1) % len(ordered)]

    return ordered[0]


def select_initial_responders(
    content: str,
    ai_speakers: Sequence[Speaker],
    last_ai_speaker_id: int | None,
) -> list[Speaker]:
    """Choose up to two mentioned AIs, or the next round-robin AI."""
    mentioned = _mentioned_speakers(content, ai_speakers)
    if mentioned:
        return mentioned[:MAX_AI_RESPONSES_PER_HUMAN_TURN]

    next_speaker = select_next_ai(ai_speakers, last_ai_speaker_id)
    return [next_speaker] if next_speaker is not None else []


def select_reaction_responder(
    speech: str,
    ai_speakers: Sequence[Speaker],
    replied_ids: Collection[int],
) -> Speaker | None:
    """Choose the first mentioned AI that has not replied in this turn."""
    for speaker in _mentioned_speakers(speech, ai_speakers):
        if speaker.game_character_id not in replied_ids:
            return speaker
    return None
