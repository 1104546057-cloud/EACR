"""Deterministic, ROS-independent fault scenarios for phase-two experiments."""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Mapping, Sequence


class FaultFamily(str, Enum):
    LOCALIZATION = "localization"
    COSTMAP = "costmap"
    PLANNER = "planner"
    CONTROL = "control"


@dataclass(frozen=True)
class FaultSpec:
    fault_id: str
    family: FaultFamily
    description: str
    parameters: Mapping[str, float | int | str] = field(default_factory=dict)
    rollback_required: bool = True

    def as_dict(self) -> dict:
        value = asdict(self)
        value["family"] = self.family.value
        value["parameters"] = dict(self.parameters)
        return value


@dataclass(frozen=True)
class FaultEvent:
    episode_id: str
    sequence_index: int
    fault: FaultSpec
    seed: int

    def as_dict(self) -> dict:
        return {
            "episode_id": self.episode_id,
            "sequence_index": self.sequence_index,
            "fault": self.fault.as_dict(),
            "seed": self.seed,
        }


@dataclass(frozen=True)
class FaultSequence:
    """A reproducible sequence of fault events generated from one seed."""

    seed: int
    events: tuple[FaultEvent, ...]

    @classmethod
    def from_specs(
        cls,
        specs: Sequence[FaultSpec],
        *,
        seed: int,
        episode_prefix: str = "phase2",
    ) -> "FaultSequence":
        if not specs:
            raise ValueError("at least one fault spec is required")
        rng = random.Random(seed)
        shuffled = list(specs)
        rng.shuffle(shuffled)
        events = tuple(
            FaultEvent(
                episode_id=f"{episode_prefix}_{index:03d}",
                sequence_index=index,
                fault=spec,
                seed=seed,
            )
            for index, spec in enumerate(shuffled, start=1)
        )
        return cls(seed=seed, events=events)

    def as_dict(self) -> dict:
        return {"seed": self.seed, "events": [event.as_dict() for event in self.events]}


DEFAULT_FAULT_SPECS: tuple[FaultSpec, ...] = (
    FaultSpec(
        "localization_initial_pose_offset",
        FaultFamily.LOCALIZATION,
        "AMCL initial pose is offset from the deterministic episode start.",
        {"offset_x": 0.65, "offset_y": -0.45, "offset_yaw": 0.35},
    ),
    FaultSpec(
        "costmap_static_obstacle",
        FaultFamily.COSTMAP,
        "A temporary obstacle is inserted into the Gazebo world and removed after the episode.",
        {"x": 0.7508496046, "y": 1.8354123831, "size_m": 0.80},
    ),
    FaultSpec(
        "planner_server_deactivated",
        FaultFamily.PLANNER,
        "An invalid planner request is probed while the planner parameter is perturbed and later restored.",
    ),
    FaultSpec(
        "controller_server_deactivated",
        FaultFamily.CONTROL,
        "The Nav2 controller minimum x-velocity threshold is raised and later restored.",
    ),
)
