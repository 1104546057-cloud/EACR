#!/usr/bin/env python3
"""Aggregate valid Gazebo ablation records without mixing main baselines."""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ABLATIONS = {
    "full_eacr", "without_memory_update", "without_information_gain",
    "without_recovery_utility", "without_risk_constraint",
    "without_belief_update", "without_model_uncertainty",
}


def _nll(rows):
    values = []
    for row in rows:
        p = float(row.get("predicted_recovery_probability", 0.5) or 0.5)
        y = 1.0 if row.get("episode_success") else 0.0
        values.append(-(y * math.log(max(p, 1e-9)) + (1 - y) * math.log(max(1 - p, 1e-9))))
    return sum(values) / len(values) if values else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", type=Path, default=ROOT / "results")
    parser.add_argument("--output", type=Path, default=ROOT / "results" / "phase3_ablation_aggregate.json")
    args = parser.parse_args()

    candidates = []
    for path in args.results_dir.glob("phase3_gazebo_*.json"):
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        baseline = data.get("baseline")
        if baseline not in ABLATIONS or not data.get("protocol_compliant"):
            continue
        for row in data.get("episodes", []):
            if row.get("episode_evidence_valid"):
                candidates.append((path.stat().st_mtime_ns, baseline, data.get("seed"), row))

    newest = {}
    for stamp, baseline, seed, row in candidates:
        key = (baseline, seed, row.get("fault_family"))
        if key not in newest or stamp > newest[key][0]:
            newest[key] = (stamp, row)

    grouped = defaultdict(list)
    for (baseline, _seed, _family), (_, row) in newest.items():
        grouped[baseline].append(row)

    by_condition = {}
    for baseline in sorted(ABLATIONS):
        rows = grouped.get(baseline, [])
        by_condition[baseline] = {
            "valid_cells": len(rows),
            "expected_cells": 20,
            "coverage_complete": len(rows) == 20,
            "fault_effect_observed_rate": sum(bool(r.get("fault_effect_observed")) for r in rows) / len(rows) if rows else None,
            "recovery_success_rate": sum(bool(r.get("episode_success")) for r in rows) / len(rows) if rows else None,
            "mean_intervention_cost": sum(float(r.get("intervention_cost") or 0.0) for r in rows) / len(rows) if rows else None,
            "mean_mttr_sec": sum(float(r.get("recovery_navigation_duration_sec") or 0.0) for r in rows) / len(rows) if rows else None,
            "outcome_prediction_nll": _nll(rows),
            "updated_online_count": sum(bool(r.get("experience_updated_online")) for r in rows),
        }

    artifact = {
        "protocol_id": "eacr_phase3_v1",
        "source": "real Gazebo paired episodes only",
        "conditions": sorted(ABLATIONS),
        "by_condition": by_condition,
        "all_conditions_complete": all(item["coverage_complete"] for item in by_condition.values()),
    }
    args.output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(artifact, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
