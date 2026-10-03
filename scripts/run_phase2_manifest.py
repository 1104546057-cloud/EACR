#!/usr/bin/env python3
"""Generate and validate the deterministic phase-two experiment manifest."""

from __future__ import annotations

import json
import sys
from pathlib import Path


WORKSPACE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE / "src" / "eacr_core"))

from eacr_core.action_library import default_action_library  # noqa: E402
from eacr_core.baselines import BayesianFixedRecoveryPolicy, EacrStaticPolicy, RuleBasedPolicy  # noqa: E402
from eacr_core.experience import ExperienceModel  # noqa: E402
from eacr_core.records import EpisodeRecorder  # noqa: E402
from eacr_core.scenario import DEFAULT_FAULT_SPECS, FaultFamily, FaultSequence  # noqa: E402
from eacr_core.types import Context  # noqa: E402


def main() -> None:
    seed = 20260926
    actions = default_action_library()
    sequence = FaultSequence.from_specs(DEFAULT_FAULT_SPECS, seed=seed)
    families = {event.fault.family for event in sequence.events}
    if families != set(FaultFamily):
        raise SystemExit(f"fault family coverage failed: {families}")
    if len(actions) < 8 or any(action.max_duration_sec <= 0.0 for action in actions):
        raise SystemExit("action library metadata is incomplete")

    belief = {
        "localization_drift": 0.50,
        "odom_tf_inconsistency": 0.20,
        "amcl_degeneracy": 0.30,
    }
    context = Context(environment_bin="phase2_manifest")
    model = ExperienceModel()
    action_ids = [action.action_id for action in actions]
    decisions = {
        "rule_based": RuleBasedPolicy().choose(actions).as_dict(),
        "bayesian_fixed_recovery": BayesianFixedRecoveryPolicy().choose(actions, belief).as_dict(),
        "eacr_static": EacrStaticPolicy(model).choose(actions, belief, context).as_dict(),
    }
    recorder = EpisodeRecorder("phase2_manifest", seed, WORKSPACE / "results")
    recorder.record("scenario_manifested", sequence=sequence.as_dict())
    recorder.record("action_library_manifested", action_ids=action_ids)
    recorder.record("baseline_decisions", decisions=decisions)
    event_path, summary_path = recorder.write(
        {
            "fault_family_count": len(families),
            "action_count": len(actions),
            "baseline_decisions": decisions,
        }
    )
    manifest = {
        "seed": seed,
        "fault_sequence": sequence.as_dict(),
        "action_library": [action.__dict__ for action in actions],
        "baselines": decisions,
        "acceptance": {
            "four_fault_families": len(families) == 4,
            "at_least_eight_actions": len(actions) >= 8,
            "all_actions_have_duration": all(action.max_duration_sec > 0.0 for action in actions),
            "event_record_written": event_path.exists() and summary_path.exists(),
        },
    }
    output_path = WORKSPACE / "results" / "phase2_manifest.json"
    output_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, default=str) + "\n")
    print(json.dumps(manifest, ensure_ascii=False, indent=2, default=str))
    if not all(manifest["acceptance"].values()):
        raise SystemExit("phase2 manifest acceptance failed")


if __name__ == "__main__":
    main()
