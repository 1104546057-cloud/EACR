#!/usr/bin/env python3
"""Deterministic phase-two baseline runner smoke test.

This is an experiment-driver check, not a Gazebo performance claim. It uses a
fixed synthetic outcome oracle only to verify that all baselines consume the
same seed, fault sequence, action library, and event-record format.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


WORKSPACE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE / "src" / "eacr_core"))

from eacr_core.action_library import default_action_library  # noqa: E402
from eacr_core.baselines import BayesianFixedRecoveryPolicy, EacrStaticPolicy, RuleBasedPolicy  # noqa: E402
from eacr_core.experience import ExperienceModel  # noqa: E402
from eacr_core.policy import PolicyWeights, choose_action  # noqa: E402
from eacr_core.records import EpisodeRecorder  # noqa: E402
from eacr_core.scenario import DEFAULT_FAULT_SPECS, FaultFamily, FaultSequence  # noqa: E402
from eacr_core.types import Context, Outcome  # noqa: E402


SEED = 20260926
TARGET_ACTION = {
    FaultFamily.LOCALIZATION: "relocalize_amcl",
    FaultFamily.COSTMAP: "clear_costmaps",
    FaultFamily.PLANNER: "reconfigure_planner",
    FaultFamily.CONTROL: "reconfigure_controller",
}
FAULT_BELIEF = {
    FaultFamily.LOCALIZATION: {
        "localization_drift": 0.70,
        "odom_tf_inconsistency": 0.20,
        "amcl_degeneracy": 0.10,
    },
    FaultFamily.COSTMAP: {"costmap_blockage": 0.80, "planner_failure": 0.20},
    FaultFamily.PLANNER: {"planner_failure": 0.80, "costmap_blockage": 0.20},
    FaultFamily.CONTROL: {"controller_failure": 0.80, "odom_tf_inconsistency": 0.20},
}


def seed_static_model(model: ExperienceModel, actions: tuple, sequence: FaultSequence) -> None:
    """Create a frozen historical model for the static baseline."""

    context = Context(environment_bin="phase2_synthetic")
    for event in sequence.events:
        belief = FAULT_BELIEF[event.fault.family]
        target = TARGET_ACTION[event.fault.family]
        for fault in belief:
            one_hot = {candidate: float(candidate == fault) for candidate in belief}
            for _ in range(5):
                model.update(one_hot, context, target, Outcome.RECOVERY_SUCCESS, True)
            model.update(one_hot, context, target, Outcome.RECOVERY_FAILURE, False)


def synthetic_outcome(event, action_id: str) -> tuple[Outcome, bool]:
    target = TARGET_ACTION[event.fault.family]
    if action_id == target:
        return Outcome.RECOVERY_SUCCESS, True
    if action_id.startswith("inspect") and event.fault.family.value in {
        "localization", "costmap", "planner", "control"
    }:
        return Outcome.DIAGNOSTIC_SUPPORT, False
    return Outcome.INCONCLUSIVE, False


def run_baseline(name: str, actions: tuple, sequence: FaultSequence) -> dict:
    context = Context(environment_bin="phase2_synthetic")
    model = ExperienceModel()
    if name == "eacr_static":
        seed_static_model(model, actions, sequence)
    records = []
    for event in sequence.events:
        belief = FAULT_BELIEF[event.fault.family]
        if name == "rule_based":
            decision = RuleBasedPolicy().choose(actions)
        elif name == "bayesian_fixed_recovery":
            decision = BayesianFixedRecoveryPolicy().choose(actions, belief)
        else:
            decision = choose_action(
                actions,
                belief,
                context,
                model,
                PolicyWeights(minimum_utility=0.0),
            )
        action_id = decision.selected_action
        outcome, recovered = synthetic_outcome(event, action_id) if action_id else (
            Outcome.UNSAFE_OR_BLOCKED,
            False,
        )
        if name == "eacr_evolving" and action_id:
            model.update(belief, context, action_id, outcome, recovered)
        records.append({
            "episode_id": event.episode_id,
            "fault_family": event.fault.family.value,
            "fault_id": event.fault.fault_id,
            "decision": decision.as_dict(),
            "outcome": outcome.value,
            "verified_recovery": recovered,
        })
    successes = sum(int(record["verified_recovery"]) for record in records)
    return {
        "episodes": records,
        "success_rate": successes / len(records),
        "experience_snapshot": model.snapshot() if name.startswith("eacr_") else {},
    }


def main() -> None:
    actions = default_action_library()
    sequence = FaultSequence.from_specs(DEFAULT_FAULT_SPECS, seed=SEED)
    results = {
        name: run_baseline(name, actions, sequence)
        for name in (
            "rule_based",
            "bayesian_fixed_recovery",
            "eacr_static",
            "eacr_evolving",
        )
    }
    recorder = EpisodeRecorder("phase2_baseline_smoke", SEED, WORKSPACE / "results")
    recorder.record("scenario_shared", sequence=sequence.as_dict())
    recorder.record("baseline_results", results=results)
    event_path, summary_path = recorder.write({"baseline_names": list(results)})
    output = {
        "synthetic_validation_only": True,
        "seed": SEED,
        "shared_fault_sequence": sequence.as_dict(),
        "results": results,
        "records": {"events": str(event_path), "summary": str(summary_path)},
        "acceptance": {
            "same_sequence_for_all_baselines": all(
                [
                    results[name]["episodes"][0]["episode_id"]
                    == results["rule_based"]["episodes"][0]["episode_id"]
                    for name in results
                ]
            ),
            "all_baselines_present": len(results) == 4,
            "event_record_written": event_path.exists() and summary_path.exists(),
        },
    }
    output_path = WORKSPACE / "results" / "phase2_baseline_smoke.json"
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    if not all(output["acceptance"].values()):
        raise SystemExit("phase2 baseline smoke validation failed")


if __name__ == "__main__":
    main()
