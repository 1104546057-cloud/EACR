#!/usr/bin/env python3
"""Write the frozen, reproducible phase-three experiment protocol."""

from __future__ import annotations

import json
from pathlib import Path


WORKSPACE = Path(__file__).resolve().parents[1]


def main() -> None:
    protocol = {
        "protocol_id": "eacr_phase3_v1",
        "paper_scope": "EACR first paper; no LLM, RAG, MiniLLM",
        "map": "tb3_sandbox",
        "goal": {"x": 0.7508496046, "y": 1.8354123831, "yaw": 1.4751400097},
        "baselines": [
            "rule_based_recovery",
            "bayesian_fixed_recovery",
            "ig_without_evolving_experience",
            "eacr_static",
            "eacr_evolving",
        ],
        "fault_families": ["localization", "costmap", "planner", "control"],
        "experience_checkpoints": ["M_0", "M_20", "M_50"],
        "seeds": [20260926, 20260927, 20260928, 20260929, 20260930],
        "episodes_per_seed": 4,
        "navigation_timeout_sec": 60.0,
        "normal_navigation_reference_sec": 15.90,
        "ablation_conditions": [
            "full_eacr",
            "without_memory_update",
            "without_information_gain",
            "without_recovery_utility",
            "without_risk_constraint",
            "without_belief_update",
            "without_model_uncertainty",
        ],
        "metrics": [
            "action_ranking",
            "policy_kl_divergence",
            "outcome_prediction_nll",
            "brier_score",
            "ece",
            "useless_probe_rate",
            "intervention_cost",
            "mttr_sec",
            "recovery_success_rate",
            "sustained_recovery_rate",
        ],
        "rules": {
            "same_fault_sequence_per_seed": True,
            "same_initial_belief_and_actions": True,
            "ground_truth_used_only_for_evaluation": True,
            "test_feedback_initializes_no_model": True,
            "reset_before_each_episode": True,
        },
    }
    output = WORKSPACE / "results" / "phase3_protocol.json"
    output.write_text(json.dumps(protocol, ensure_ascii=False, indent=2) + "\n")
    print(output)


if __name__ == "__main__":
    main()
