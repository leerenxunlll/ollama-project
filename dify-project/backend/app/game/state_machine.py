"""Deterministic lifecycle and narrative phase rules."""

from collections.abc import Sequence

PHASE_SEQUENCE = (
    "intro",
    "act_1",
    "investigation_1",
    "discussion_1",
    "act_2",
    "investigation_2",
    "discussion_2",
    "final_discussion",
    "vote",
    "ending",
)

PHASE_TRANSITIONS = dict(zip(PHASE_SEQUENCE, PHASE_SEQUENCE[1:]))
INVESTIGATION_ACTS = {
    "investigation_1": "act_1",
    "investigation_2": "act_2",
}


class GameRuleError(ValueError):
    """An action conflicts with deterministic game rules."""


def validate_start(status: str, controller_types: Sequence[str | None]) -> None:
    """Require a ready game with one human and three AI characters."""
    if status != "ready":
        raise GameRuleError("Game must be ready before it can start")
    if len(controller_types) != 4:
        raise GameRuleError("Game must have exactly four characters")
    if controller_types.count("human") != 1 or controller_types.count("ai") != 3:
        raise GameRuleError("Game must have one human and three AI characters")


def next_phase(current_phase: str) -> str | None:
    """Return the one legal next phase, if the current phase is known."""
    return PHASE_TRANSITIONS.get(current_phase)


def require_next_phase(current_phase: str) -> str:
    """Return the next phase or reject an unknown/final phase."""
    target_phase = next_phase(current_phase)
    if target_phase is None:
        raise GameRuleError("Game has no next phase")
    return target_phase


def can_investigate(status: str, current_phase: str) -> bool:
    """Investigation is available only in the two fixed investigation phases."""
    return status == "in_progress" and current_phase in INVESTIGATION_ACTS


def clue_act_for_phase(current_phase: str) -> str:
    """Map an investigation phase to the script's explicit clue act value."""
    try:
        return INVESTIGATION_ACTS[current_phase]
    except KeyError as error:
        raise GameRuleError("Current phase does not allow investigation") from error
