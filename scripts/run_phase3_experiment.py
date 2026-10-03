#!/usr/bin/env python3
"""Run the deterministic phase-three driver.

This first adapter exercises the frozen protocol and record/metric path with a
controlled outcome oracle.  It is deliberately marked as a dry run; the same
episode interface is used by the Gazebo adapter that supplies observed Nav2
outcomes.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE / "src" / "eacr_core"))

from eacr_core.action_library import default_action_library
from eacr_core.baselines import BayesianFixedRecoveryPolicy, RuleBasedPolicy
from eacr_core.experience import ExperienceModel
from eacr_core.metrics import brier_score, expected_calibration_error, mean_time_to_recovery, outcome_nll, policy_kl, recovery_rate
from eacr_core.policy import PolicyWeights, choose_action
from eacr_core.scenario import DEFAULT_FAULT_SPECS, FaultFamily, FaultSequence
from eacr_core.types import Context, Outcome

FAULT_BELIEF = {
    FaultFamily.LOCALIZATION: {"localization_drift": 0.70, "odom_tf_inconsistency": 0.20, "amcl_degeneracy": 0.10},
    FaultFamily.COSTMAP: {"costmap_blockage": 0.80, "planner_failure": 0.20},
    FaultFamily.PLANNER: {"planner_failure": 0.80, "costmap_blockage": 0.20},
    FaultFamily.CONTROL: {"controller_failure": 0.80, "odom_tf_inconsistency": 0.20},
}
TARGET_ACTION = {
    FaultFamily.LOCALIZATION: "relocalize_amcl",
    FaultFamily.COSTMAP: "clear_costmaps",
    FaultFamily.PLANNER: "reconfigure_planner",
    FaultFamily.CONTROL: "reconfigure_controller",
}


def historical_model(actions, sequence, updates: int) -> ExperienceModel:
    model = ExperienceModel()
    context = Context(environment_bin="phase3_dry_run")
    for event in sequence.events:
        target = TARGET_ACTION[event.fault.family]
        for fault in FAULT_BELIEF[event.fault.family]:
            belief = {candidate: float(candidate == fault) for candidate in FAULT_BELIEF[event.fault.family]}
            for _ in range(updates):
                model.update(belief, context, target, Outcome.RECOVERY_SUCCESS, True)
    return model


def outcome_for(event, action_id: str) -> tuple[Outcome, bool, float, float | None]:
    target = TARGET_ACTION[event.fault.family]
    if action_id == target:
        return Outcome.RECOVERY_SUCCESS, True, 0.90, 8.0
    if action_id and action_id.startswith("inspect"):
        return Outcome.DIAGNOSTIC_SUPPORT, False, 0.35, None
    return Outcome.RECOVERY_FAILURE, False, 0.20, None


def ranking_distribution(decision) -> dict[str, float]:
    scores = {score.action_id: score.utility for score in decision.ranking if score.safe}
    if not scores:
        return {}
    weights = {key: math.exp(value - max(scores.values())) for key, value in scores.items()}
    total = sum(weights.values())
    return {key: value / total for key, value in weights.items()}


def run_condition(condition: str, seed: int, sequence, actions) -> dict:
    context = Context(environment_bin="phase3_dry_run")
    model = historical_model(actions, sequence, 5 if condition == "eacr_static" else 0)
    records = []
    probabilities, observations, durations = [], [], []
    for event in sequence.events:
        belief = FAULT_BELIEF[event.fault.family]
        if condition == "rule_based_recovery":
            decision = RuleBasedPolicy().choose(actions)
        elif condition == "bayesian_fixed_recovery":
            decision = BayesianFixedRecoveryPolicy().choose(actions, belief)
        else:
            weights = PolicyWeights(
                information_gain=0.0 if condition == "ig_without_evolving_experience" else 1.0,
                recovery_gain=0.0 if condition == "without_recovery_utility" else 1.0,
                risk_limit=1.0 if condition == "without_risk_constraint" else 0.40,
                uncertainty=0.0 if condition == "without_model_uncertainty" else 0.4,
            )
            decision = choose_action(actions, belief, context, model, weights)
        action_id = decision.selected_action
        outcome, recovered, predicted, duration = outcome_for(event, action_id or "")
        probabilities.append(predicted)
        observations.append(recovered)
        durations.append(duration)
        if condition not in {"eacr_static", "ig_without_evolving_experience", "without_memory_update"} and action_id:
            model.update(belief, context, action_id, outcome, recovered)
        records.append({
            "episode_id": event.episode_id,
            "fault_family": event.fault.family.value,
            "action": action_id,
            "outcome": outcome.value,
            "recovered": recovered,
            "decision": decision.as_dict(),
        })
    return {
        "condition": condition,
        "seed": seed,
        "episodes": records,
        "metrics": {
            "policy_kl_vs_rule": 0.0,
            "outcome_prediction_nll": sum(outcome_nll(p, o) for p, o in zip(probabilities, observations)) / len(probabilities),
            "brier_score": sum(brier_score(p, o) for p, o in zip(probabilities, observations)) / len(probabilities),
            "ece": expected_calibration_error(probabilities, observations),
            "mttr_sec": mean_time_to_recovery(durations),
            "recovery_success_rate": recovery_rate(observations),
            "sustained_recovery_rate": recovery_rate(observations),
            "useless_probe_rate": sum(1 for r in records if r["action"] and r["action"].startswith("inspect") and not r["recovered"]) / len(records),
        },
        "experience_checkpoint": "M_0" if condition != "eacr_static" else "M_20",
    }


def main() -> None:
    protocol = json.loads((WORKSPACE / "results" / "phase3_protocol.json").read_text())
    actions = default_action_library()
    conditions = protocol["baselines"] + protocol["ablation_conditions"][1:]
    runs = []
    for seed in protocol["seeds"]:
        sequence = FaultSequence.from_specs(DEFAULT_FAULT_SPECS, seed=seed, episode_prefix=f"phase3_{seed}")
        for condition in conditions:
            runs.append(run_condition(condition, seed, sequence, actions))
    result = {
        "protocol_id": protocol["protocol_id"],
        "synthetic_dry_run": True,
        "gazebo_observation_adapter": "pending",
        "runs": runs,
        "acceptance": {
            "protocol_loaded": True,
            "all_seeds_present": len({run["seed"] for run in runs}) == len(protocol["seeds"]),
            "same_episode_count": all(len(run["episodes"]) == protocol["episodes_per_seed"] for run in runs),
            "metrics_present": all("recovery_success_rate" in run["metrics"] for run in runs),
        },
    }
    output = WORKSPACE / "results" / "phase3_dry_run.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result["acceptance"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
