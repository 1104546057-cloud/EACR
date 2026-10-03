#!/usr/bin/env python3
"""Validate the evolving-advantage protocol without starting Gazebo.

This is a protocol sanity check.  It verifies that weak shared priors,
repeated fault feedback, held-out seeds and checkpoint loading can produce an
auditable learning curve before the expensive Gazebo matrix is started.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "eacr_core"))

from eacr_core.action_library import default_action_library  # noqa: E402
from eacr_core.experience import ExperienceModel  # noqa: E402
from eacr_core.policy import PolicyWeights, choose_action  # noqa: E402
from eacr_core.scenario import DEFAULT_FAULT_SPECS, FaultSequence  # noqa: E402
from eacr_core.types import Context, Outcome  # noqa: E402


FAULTS = {
    "localization": "localization_drift",
    "costmap": "costmap_blockage",
    "planner": "planner_failure",
    "control": "controller_failure",
}
TARGETS = {
    "localization": "relocalize_amcl",
    "costmap": "clear_costmaps",
    "planner": "reconfigure_planner",
    "control": "reconfigure_controller",
}


def new_m0(context: Context, actions) -> ExperienceModel:
    model = ExperienceModel()
    model.seed_weak_prior(
        {fault: 0.25 for fault in FAULTS.values()},
        context,
        [action.action_id for action in actions],
    )
    return model


def belief_for(family: str) -> dict[str, float]:
    belief = {fault: 1.0 / 12.0 for fault in FAULTS.values()}
    belief[FAULTS[family]] = 0.75
    return belief


def update_from_outcome(model: ExperienceModel, context: Context, belief, action_id: str, family: str) -> bool:
    success = action_id == TARGETS[family]
    model.update(
        belief,
        context,
        action_id,
        Outcome.RECOVERY_SUCCESS if success else Outcome.RECOVERY_FAILURE,
        recovery_success=success,
    )
    return success


def scoped_actions(actions, family: str):
    return tuple(
        action for action in actions
        if family in action.fault_families or action.action_id == "slow_observe"
    )


def train_checkpoints(seeds: list[int], repetitions: int, context: Context, actions):
    model = new_m0(context, actions)
    checkpoints = {"M_0": model.snapshot()}
    applied = 0
    for seed in seeds:
        specs = tuple(spec for _ in range(repetitions) for spec in DEFAULT_FAULT_SPECS)
        sequence = FaultSequence.from_specs(specs, seed=seed, episode_prefix=f"adv_train_{seed}")
        for event in sequence.events:
            family = event.fault.family.value
            belief = belief_for(family)
            decision = choose_action(scoped_actions(actions, family), belief, context, model, PolicyWeights())
            if decision.selected_action is None:
                continue
            update_from_outcome(model, context, belief, decision.selected_action, family)
            applied += 1
            if applied in (20, 50):
                checkpoints[f"M_{applied}"] = model.snapshot()
    return checkpoints, applied


def evaluate(method: str, seeds: list[int], repetitions: int, context: Context, actions, checkpoints):
    total = 0
    success = 0
    ranking_changes = 0
    rows = []
    for seed in seeds:
        if method == "eacr_static_m0" or method == "eacr_evolving_online_m0":
            model = new_m0(context, actions)
        else:
            checkpoint_name = "M_20" if method.endswith("m20") else "M_50"
            model = ExperienceModel.from_snapshot(checkpoints[checkpoint_name])
        online = method == "eacr_evolving_online_m0"
        specs = tuple(spec for _ in range(repetitions) for spec in DEFAULT_FAULT_SPECS)
        sequence = FaultSequence.from_specs(specs, seed=seed, episode_prefix=f"adv_eval_{seed}")
        first_actions = {}
        for event in sequence.events:
            family = event.fault.family.value
            belief = belief_for(family)
            decision = choose_action(scoped_actions(actions, family), belief, context, model, PolicyWeights())
            action_id = decision.selected_action
            if action_id is None:
                continue
            if family not in first_actions:
                first_actions[family] = action_id
            elif first_actions[family] != action_id:
                ranking_changes += 1
            total += 1
            ok = update_from_outcome(model, context, belief, action_id, family) if online else action_id == TARGETS[family]
            success += int(ok)
        rows.append({"seed": seed, "success": success, "episodes": total})
    return {
        "method": method,
        "episodes": total,
        "successes": success,
        "recovery_success_rate": success / total if total else None,
        "ranking_changes": ranking_changes,
        "rows": rows,
    }


def main() -> None:
    protocol = json.loads((ROOT / "results" / "phase3_evolving_advantage_protocol.json").read_text())
    context = Context(environment_bin="tb3_sandbox_gazebo")
    actions = default_action_library()
    checkpoints, applied = train_checkpoints(
        protocol["training_seeds"],
        protocol["repetitions_per_fault_family"],
        context,
        actions,
    )
    results = [
        evaluate(
            method,
            protocol["evaluation_seeds"],
            protocol["repetitions_per_fault_family"],
            context,
            actions,
            checkpoints,
        )
        for method in protocol["methods"]
    ]
    output = {
        "protocol_id": protocol["protocol_id"],
        "synthetic_dry_run": True,
        "training_feedback_applied": applied,
        "checkpoints": sorted(checkpoints),
        "results": results,
    }
    path = ROOT / "results" / "phase3_evolving_advantage_dry_run.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({
        "training_feedback_applied": applied,
        "results": [
            {k: row[k] for k in ("method", "episodes", "successes", "recovery_success_rate", "ranking_changes")}
            for row in results
        ],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
