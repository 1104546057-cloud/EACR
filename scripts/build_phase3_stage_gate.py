#!/usr/bin/env python3
"""Build an auditable phase-three readiness gate from real artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--main", type=Path, default=ROOT / "results/phase3_gazebo_aggregate.json")
    parser.add_argument("--experience", type=Path, default=ROOT / "results/phase3_experience_eacr_evolving_manifest.json")
    parser.add_argument("--ablation", type=Path, default=ROOT / "results/phase3_ablation_aggregate.json")
    parser.add_argument("--output", type=Path, default=ROOT / "results/phase3_stage_gate.json")
    args = parser.parse_args()

    main_artifact = _load(args.main) or {}
    experience_artifact = _load(args.experience) or {}
    ablation_artifact = _load(args.ablation) or {}

    main_acceptance = main_artifact.get("acceptance", {})
    main_ready = bool(main_acceptance) and all(bool(value) for value in main_acceptance.values())
    experience_ready = bool(experience_artifact.get("ready")) and int(
        experience_artifact.get("feedback_episodes_applied", 0) or 0
    ) >= 50
    ablation_ready = bool(ablation_artifact.get("all_conditions_complete"))

    gate = {
        "protocol_id": "eacr_phase3_v1",
        "sources": {
            "main": str(args.main),
            "experience": str(args.experience),
            "ablation": str(args.ablation),
        },
        "main_experiment_ready": main_ready,
        "main_acceptance": main_acceptance,
        "experience_checkpoint_ready": experience_ready,
        "experience_feedback_episodes_applied": experience_artifact.get("feedback_episodes_applied"),
        "ablation_ready": ablation_ready,
        "ablation_conditions": ablation_artifact.get("by_condition", {}),
        "planner_effect_definition": "configuration readback is reported separately from navigation behavior",
        "ready": bool(main_ready and experience_ready and ablation_ready),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(gate, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(gate, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
