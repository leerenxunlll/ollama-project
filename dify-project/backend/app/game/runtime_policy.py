"""Central timing limits for the client-ticked V0.1 runtime."""

from dataclasses import dataclass

READING_PHASES = frozenset({"intro", "act_1", "act_2"})
INVESTIGATION_PHASES = frozenset({"investigation_1", "investigation_2"})
DISCUSSION_PHASES = frozenset({"discussion_1", "discussion_2"})
RUNTIME_READY_PHASES = INVESTIGATION_PHASES | DISCUSSION_PHASES | {"final_discussion"}


@dataclass(frozen=True)
class RuntimePolicy:
    """One place for bounded scheduling intervals, actions, and recovery lease."""

    director_analysis_cooldown_seconds: int = 50
    proactive_speech_cooldown_seconds: int = 60
    human_inactivity_threshold_seconds: int = 60
    runtime_tick_interval_seconds: int = 10
    action_lease_seconds: int = 240
    ai_investigations_per_character_per_phase: int = 1
    ai_vote_max_attempts: int = 3
    ai_vote_retry_seconds: int = 30


RUNTIME_POLICY = RuntimePolicy()
