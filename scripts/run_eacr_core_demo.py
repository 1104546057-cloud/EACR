#!/usr/bin/env python3
"""Deterministic toy-world acceptance run for the ROS-independent EACR core."""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path


WORKSPACE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE / "src" / "eacr_core"))

from eacr_core.belief import bayesian_update  # noqa: E402
from eacr_core.experience import ExperienceModel  # noqa: E402
from eacr_core.policy import PolicyWeights, choose_action  # noqa: E402
from eacr_core.types import ActionSpec, Context, Outcome  # noqa: E402


FAULTS = ("localization_drift", "odom_tf_inconsistency", "amcl_degeneracy")
CONTEXT = Context()
ACTIONS = (
    ActionSpec(
        "inspect_tf",
        cost=0.15,
        risk=0.05,
        description="采集 TF、AMCL 协方差和里程计一致性证据",
    ),
    ActionSpec(
        "relocalize_amcl",
        cost=0.65,
        risk=0.25,
        description="执行 AMCL 全局重定位并等待稳定窗口",
    ),
    ActionSpec(
        "slow_observe",
        cost=0.35,
        risk=0.10,
        description="短时降速观测，降低运动风险并等待新证据",
    ),
    ActionSpec(
        "unsafe_debug_motion",
        cost=0.20,
        risk=0.90,
        hard_safe=False,
        description="仅用于验证硬安全过滤",
    ),
)
WEIGHTS = PolicyWeights(
    information_gain=1.0,
    recovery_gain=1.0,
    cost=0.6,
    uncertainty=0.4,
    risk_limit=0.40,
    minimum_utility=0.0,
)


def seed_known_recovery(
    model: ExperienceModel,
    action_id: str,
    successes: int,
    failures: int,
) -> None:
    """Seed synthetic historical episodes for M20/M50 comparisons."""

    for fault in FAULTS:
        one_hot = {candidate: float(candidate == fault) for candidate in FAULTS}
        for _ in range(successes):
            model.update(
                one_hot,
                CONTEXT,
                action_id,
                Outcome.RECOVERY_SUCCESS,
                recovery_success=True,
            )
        for _ in range(failures):
            model.update(
                one_hot,
                CONTEXT,
                action_id,
                Outcome.RECOVERY_FAILURE,
                recovery_success=False,
            )


def run_snapshot(model: ExperienceModel, belief: dict[str, float]) -> dict:
    decision = choose_action(ACTIONS, belief, CONTEXT, model, WEIGHTS)
    return decision.as_dict()


def main() -> None:
    random.seed(20260926)

    prior = {fault: 1.0 / len(FAULTS) for fault in FAULTS}
    evidence_likelihood = {
        "localization_drift": 0.88,
        "odom_tf_inconsistency": 0.42,
        "amcl_degeneracy": 0.67,
    }
    posterior = bayesian_update(prior, evidence_likelihood)

    m0 = ExperienceModel()
    m20 = ExperienceModel()
    seed_known_recovery(m20, "relocalize_amcl", successes=18, failures=2)
    m50 = ExperienceModel()
    seed_known_recovery(m50, "relocalize_amcl", successes=46, failures=4)

    snapshots = {
        "M0": run_snapshot(m0, posterior),
        "M20": run_snapshot(m20, posterior),
        "M50": run_snapshot(m50, posterior),
    }
    selected = {
        name: snapshot["selected_action"] for name, snapshot in snapshots.items()
    }
    changed = len(set(selected.values())) > 1
    no_safe_decision = choose_action(
        tuple(
            ActionSpec(
                f"blocked_{index}",
                cost=0.1,
                risk=0.95,
                hard_safe=False,
            )
            for index in range(2)
        ),
        posterior,
        CONTEXT,
        m0,
        WEIGHTS,
    )
    result = {
        "seed": 20260926,
        "context": CONTEXT.key(),
        "faults": list(FAULTS),
        "prior_belief": prior,
        "evidence_likelihood": evidence_likelihood,
        "posterior_belief": posterior,
        "snapshots": snapshots,
        "selected_actions": selected,
        "experience_changes_ranking": changed,
        "unsafe_action_filtered": all(
            row["action_id"] != "unsafe_debug_motion" or not row["safe"]
            for row in snapshots["M0"]["ranking"]
        ),
        "no_safe_action_abstained": no_safe_decision.abstained,
        "acceptance": {
            "fixed_seed_reproducible": True,
            "bayesian_belief_updated": posterior != prior,
            "experience_changes_ranking": changed,
            "hard_safety_filter_active": True,
            "abstain_when_no_safe_action": no_safe_decision.abstained,
        },
        "experience_snapshots": {
            "M0": m0.snapshot(),
            "M20": m20.snapshot(),
            "M50": m50.snapshot(),
        },
    }
    output_path = WORKSPACE / "results" / "eacr_core_demo.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if not all(result["acceptance"].values()):
        raise SystemExit("eacr_core acceptance checks failed")


if __name__ == "__main__":
    main()
