#!/usr/bin/env python3
"""Build auditable M_0/M_20/M_50 checkpoints from valid Gazebo feedback."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "eacr_core"))
from eacr_core.experience import ExperienceModel
from eacr_core.types import Context, Outcome


FAULTS = {
    "localization_drift": 0.25,
    "costmap_blockage": 0.25,
    "planner_failure": 0.25,
    "controller_failure": 0.25,
}
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", action="append", type=Path, required=True,
                        help="Training result directory; repeat for multiple fault families.")
    parser.add_argument("--output-prefix", type=Path,
                        default=ROOT / "results" / "phase3_experience_eacr_evolving")
    parser.add_argument("--prior-mode", choices=("domain", "weak_shared_m0"), default="domain")
    parser.add_argument("--protocol", type=Path,
                        default=ROOT / "results" / "phase3_evolving_advantage_protocol.json")
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    training_seeds = [int(seed) for seed in protocol["training_seeds"]]
    training_seed_set = set(training_seeds)
    family_order = list(protocol["fault_families"])

    model = ExperienceModel()
    context = Context(environment_bin="tb3_sandbox_gazebo")
    actions = [
        "inspect_tf", "slow_observe", "relocalize_amcl", "inspect_costmap",
        "clear_costmaps", "inspect_planner", "reconfigure_planner",
        "inspect_controller", "reconfigure_controller",
    ]
    if args.prior_mode == "weak_shared_m0":
        model.seed_weak_prior(FAULTS, context, actions)
    else:
        model.seed_domain_prior(FAULTS, context, actions)

    latest_runs: dict[tuple[int, str], tuple[int, Path, dict]] = {}
    excluded: dict[str, int] = {}
    for path in (p for directory in args.results_dir
                 for p in directory.glob("phase3_gazebo_eacr_evolving_*.json")):
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            excluded["unreadable"] = excluded.get("unreadable", 0) + 1
            continue
        rows = data.get("episodes", [])
        seed = int(data.get("seed", 0))
        family = rows[0].get("fault_family") if rows else None
        if seed not in training_seed_set or family not in family_order:
            excluded["outside_training_split"] = excluded.get("outside_training_split", 0) + 1
            continue
        valid = (
            data.get("protocol_compliant") is True
            and data.get("experience_prior_mode") == args.prior_mode
            and data.get("use_belief_action_scope") == protocol["use_belief_action_scope"]
            and float(data.get("fault_scale", 1.0)) == float(protocol["training_fault_scale"])
            and int(data.get("fault_repetitions", 0)) == int(protocol["repetitions_per_fault_family"])
            and not data.get("resume_experience_state", False)
            and len(rows) == int(protocol["repetitions_per_fault_family"])
            and all(row.get("fault_family") == family
                    and row.get("episode_evidence_valid")
                    and row.get("experience_updated_online") for row in rows)
        )
        if not valid:
            excluded["invalid_or_mismatched_run"] = excluded.get("invalid_or_mismatched_run", 0) + 1
            continue
        stamp = int(data.get("run_id", path.stat().st_mtime_ns))
        key = (seed, family)
        if key not in latest_runs or stamp > latest_runs[key][0]:
            latest_runs[key] = (stamp, path, data)

    # A retry replaces the whole invalid run. Keep all four ordered feedback
    # episodes from the latest valid run, never only one row per family.
    episodes = []
    source_files = []
    for seed in training_seeds:
        for family in family_order:
            selected = latest_runs.get((seed, family))
            if selected is None:
                continue
            _, path, data = selected
            source_files.append({"seed": seed, "family": family, "path": str(path.resolve()),
                                 "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
            episodes.extend((seed, family, row) for row in data["episodes"])

    checkpoints: dict[str, dict] = {
        "M_0": model.snapshot(),
    }
    applied = 0
    for _, _, row in episodes:
        action_id = row.get("selected_action")
        belief = row.get("belief_before_action")
        if not action_id or not isinstance(belief, dict):
            continue
        success = bool(row.get("episode_success"))
        model.update(
            {str(k): float(v) for k, v in belief.items()}, context, str(action_id),
            Outcome.RECOVERY_SUCCESS if success else Outcome.RECOVERY_FAILURE,
            recovery_success=success,
        )
        applied += 1
        if applied in (20, 50):
            checkpoints[f"M_{applied}"] = model.snapshot()

    manifest = {
        "protocol_id": protocol["protocol_id"],
        "source_baseline": "eacr_evolving",
        "prior_mode": args.prior_mode,
        "source_directories": [str(path.resolve()) for path in args.results_dir],
        "training_seeds": training_seeds,
        "evaluation_seeds_excluded": protocol["evaluation_seeds"],
        "source_files": source_files,
        "feedback_episodes_applied": applied,
        "unique_training_cells": len(latest_runs),
        "retained_training_episodes": len(episodes),
        "coverage_by_family": {family: sum(key[1] == family for key in latest_runs)
                               for family in family_order},
        "excluded_runs": excluded,
        "checkpoints": sorted(checkpoints),
        "minimum_required": {"M_20": 20, "M_50": 50},
        "ready": all(name in checkpoints for name in ("M_0", "M_20", "M_50"))
                 and all(sum(key[1] == family for key in latest_runs) == len(training_seeds)
                         for family in family_order),
    }
    for name, snapshot in checkpoints.items():
        output = Path(f"{args.output_prefix}_{name}.json")
        output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n")
        manifest.setdefault("paths", {})[name] = str(output)
    manifest_path = Path(f"{args.output_prefix}_manifest.json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
