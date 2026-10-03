"""Deterministic baseline policies sharing the EACR action interface."""

from __future__ import annotations

from typing import Iterable, Mapping

from .policy import PolicyWeights, choose_action
from .types import ActionSpec, Context, Decision
from .experience import ExperienceModel


class RuleBasedPolicy:
    """Fixed safe priority policy; never updates from outcomes."""

    def __init__(self, priority: tuple[str, ...] = (
        "inspect_tf",
        "inspect_costmap",
        "inspect_planner",
        "inspect_controller",
        "slow_observe",
        "relocalize_amcl",
        "clear_costmaps",
        "reconfigure_planner",
        "reconfigure_controller",
        "abstain_and_hold",
    )) -> None:
        self.priority = priority

    def choose(self, actions: Iterable[ActionSpec]) -> Decision:
        available = {action.action_id: action for action in actions}
        for action_id in self.priority:
            action = available.get(action_id)
            if action is not None and action.allowed and action.hard_safe:
                return Decision(action_id, False, "fixed_rule_priority", tuple())
        return Decision(None, True, "no_safe_action", tuple())


class BayesianFixedRecoveryPolicy:
    """Uses belief to select a fixed recovery mapping; no online experience."""

    def __init__(self, mapping: Mapping[str, str] | None = None) -> None:
        self.mapping = dict(mapping or {
            "localization_drift": "relocalize_amcl",
            "odom_tf_inconsistency": "inspect_tf",
            "amcl_degeneracy": "relocalize_amcl",
            "costmap_blockage": "clear_costmaps",
            "planner_failure": "reconfigure_planner",
            "controller_failure": "reconfigure_controller",
        })

    def choose(self, actions: Iterable[ActionSpec], belief: Mapping[str, float]) -> Decision:
        safe = {action.action_id for action in actions if action.allowed and action.hard_safe}
        if not safe or not belief:
            return Decision(None, True, "no_safe_action", tuple())
        best_fault = max(belief, key=belief.get)
        action_id = self.mapping.get(best_fault)
        if action_id not in safe:
            return Decision(None, True, "mapped_recovery_not_safe", tuple())
        return Decision(action_id, False, "fixed_recovery_mapping", tuple())


class EacrStaticPolicy:
    """Scores with a frozen experience model and never mutates it."""

    def __init__(self, model: ExperienceModel, weights: PolicyWeights = PolicyWeights()) -> None:
        self.model = model
        self.weights = weights

    def choose(
        self,
        actions: Iterable[ActionSpec],
        belief: Mapping[str, float],
        context: Context,
    ) -> Decision:
        return choose_action(actions, belief, context, self.model, self.weights)
