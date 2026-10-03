"""Small, serializable value types used by the ROS-independent EACR core."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Mapping, Optional, Tuple


class Outcome(str, Enum):
    """Observable result classes defined by the EACR specification."""

    DIAGNOSTIC_SUPPORT = "diagnostic_support"
    DIAGNOSTIC_CONFLICT = "diagnostic_conflict"
    RECOVERY_SUCCESS = "recovery_success"
    RECOVERY_FAILURE = "recovery_failure"
    UNSAFE_OR_BLOCKED = "unsafe_or_blocked"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class Context:
    """Discrete context bin used as the experience-model key."""

    map_id: str = "tb3_sandbox"
    task_id: str = "goal_nav"
    robot_state: str = "navigating"
    environment_bin: str = "nominal"
    software_state: str = "nav2_jazzy"

    def key(self) -> str:
        return "|".join(
            (
                self.map_id,
                self.task_id,
                self.robot_state,
                self.environment_bin,
                self.software_state,
            )
        )


@dataclass(frozen=True)
class ActionSpec:
    """Candidate intervention metadata used by hard safety filtering."""

    action_id: str
    cost: float
    risk: float
    hard_safe: bool = True
    allowed: bool = True
    preconditions: Tuple[str, ...] = ()
    description: str = ""
    expected_observables: Tuple[str, ...] = ()
    max_duration_sec: float = 0.0
    rollback_action_id: Optional[str] = None
    fault_families: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ActionScore:
    action_id: str
    information_gain: float
    recovery_gain: float
    cost: float
    uncertainty: float
    utility: float
    safe: bool
    rejection_reason: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "action_id": self.action_id,
            "information_gain": self.information_gain,
            "recovery_gain": self.recovery_gain,
            "cost": self.cost,
            "uncertainty": self.uncertainty,
            "utility": self.utility if math.isfinite(self.utility) else None,
            "safe": self.safe,
            "rejection_reason": self.rejection_reason,
        }


@dataclass(frozen=True)
class Decision:
    selected_action: Optional[str]
    abstained: bool
    reason: str
    ranking: Tuple[ActionScore, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict:
        return {
            "selected_action": self.selected_action,
            "abstained": self.abstained,
            "reason": self.reason,
            "ranking": [score.as_dict() for score in self.ranking],
        }


def as_probability_map(values: Mapping[str, float]) -> dict[str, float]:
    """Make a plain float dictionary for deterministic serialization."""

    return {str(key): float(value) for key, value in values.items()}
