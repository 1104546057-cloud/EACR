"""Deterministic baseline policies sharing the EACR action interface."""

from __future__ import annotations

from typing import Iterable, Mapping

from .policy import PolicyWeights, choose_action
from .types import ActionScore, ActionSpec, Context, Decision
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


class StrongEvidenceRulePolicy:
    """Frozen parameter-to-recovery rule using only pre-action online evidence.

    A visible parameter anomaly wins over AMCL displacement.  Conflicting
    parameter anomalies are resolved in the fixed planner, controller,
    costmap order.  When no anomaly is readable, inspect the most probable
    fault; this still consumes the single action opportunity.
    """

    INSPECTIONS = {
        "localization_drift": "inspect_tf",
        "costmap_blockage": "inspect_costmap",
        "planner_failure": "inspect_planner",
        "controller_failure": "inspect_controller",
    }

    def choose(self, actions: Iterable[ActionSpec], belief: Mapping[str, float], evidence: Mapping) -> Decision:
        actions = tuple(actions)
        safe = {a.action_id: a for a in actions if a.allowed and a.hard_safe and a.risk <= 0.40}
        parameters = evidence.get("nav2_parameters", {})
        parameters = parameters if isinstance(parameters, Mapping) else {}
        plugins = parameters.get("planner_plugins")
        threshold = parameters.get("min_x_velocity_threshold")
        padding = parameters.get("footprint_padding")
        matches = []
        if evidence.get("planner_lifecycle_state_id") not in (None, 3):
            matches.append(("reconfigure_planner", "planner_lifecycle_inactive"))
        elif isinstance(plugins, list) and "GridBased" not in plugins:
            matches.append(("reconfigure_planner", "planner_plugins_missing_GridBased"))
        if isinstance(threshold, (int, float)) and threshold > 1.0:
            matches.append(("reconfigure_controller", "controller_threshold_over_1"))
        if isinstance(padding, (int, float)) and padding > 0.5:
            matches.append(("clear_costmaps", "footprint_padding_over_0_5"))
        distance = evidence.get("amcl_distance_to_start_m")
        if isinstance(distance, (int, float)) and distance > 0.35:
            matches.append(("relocalize_amcl", "amcl_displacement_over_0_35"))
        if not matches and belief:
            fault = max(sorted(belief), key=lambda key: belief[key])
            matches.append((self.INSPECTIONS.get(fault, "slow_observe"), "no_direct_anomaly_inspect_dominant_belief"))
        if not matches:
            matches.append(("slow_observe", "no_readable_evidence"))
        selected = next(((a, reason) for a, reason in matches if a in safe), None)
        priority = [action_id for action_id, _ in matches]
        priority.extend(a.action_id for a in actions if a.action_id not in priority)
        ranking = tuple(ActionScore(
            action_id, 0.0, 0.0, safe[action_id].cost if action_id in safe else next(a.cost for a in actions if a.action_id == action_id),
            0.0, float(len(priority) - index), action_id in safe,
            None if action_id in safe else "hard_safety_or_risk_block",
        ) for index, action_id in enumerate(priority))
        if selected is None:
            return Decision(None, True, "no_safe_evidence_action", ranking)
        action_id, reason = selected
        return Decision(action_id, False, reason + (";conflict" if len(matches) > 1 else ""), ranking)


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
