#!/usr/bin/env python3
"""Read-only audit of the frozen phase-four cells for follow-up experiments."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


METHODS = (
    "eacr_static_m0",
    "eacr_evolving_online_m0",
    "eacr_evolving_m20",
    "eacr_evolving_m50",
)
FAMILIES = ("localization", "costmap", "planner", "control")
SUCCEEDED = 4  # action_msgs/msg/GoalStatus.STATUS_SUCCEEDED


def _load_cell(repo_root: Path, cell: dict) -> list[dict]:
    path = repo_root / cell["path"]
    data = json.loads(path.read_text())
    rows = data["episodes"]
    if data.get("protocol_compliant") is not True or len(rows) != 4:
        raise ValueError(f"invalid selected cell: {path}")
    if any(row.get("episode_evidence_valid") is not True for row in rows):
        raise ValueError(f"invalid selected episode: {path}")
    return rows


def _candidate_set(row: dict) -> frozenset[str]:
    ranking = (row.get("decision") or {}).get("ranking") or []
    return frozenset(item["action_id"] for item in ranking)


def audit(repo_root: Path, aggregate_path: Path) -> dict:
    aggregate_bytes = aggregate_path.read_bytes()
    source = json.loads(aggregate_bytes)
    if source.get("confirmatory_ready") is not True:
        raise ValueError("the selected aggregate is not confirmatory_ready")
    cells = source["cell_metrics"]
    by_key = {(item["method"], item["seed"], item["fault_family"]): item
              for item in cells}
    if len(cells) != 320 or len(by_key) != 320:
        raise ValueError("expected 320 distinct original cells")

    records = {key: _load_cell(repo_root, item) for key, item in by_key.items()}
    method_family: dict[str, dict[str, dict]] = defaultdict(dict)
    for method in METHODS:
        for family in FAMILIES:
            rows = [row for (m, _, f), episodes in records.items()
                    if m == method and f == family for row in episodes]
            status = Counter(str(row.get("fault_navigation_status")) for row in rows)
            failed = [row for row in rows if row.get("fault_behavior_observed") is True]
            method_family[method][family] = {
                "episode_count": len(rows),
                "fault_navigation_status_counts": dict(status),
                "fault_navigation_success_count": sum(
                    row.get("fault_navigation_status") == SUCCEEDED for row in rows),
                "behavior_failure_count": len(failed),
                "intervention_recovery_count": sum(bool(row.get("recovery_success")) for row in rows),
                "strict_joint_success_count": sum(bool(row.get("episode_success")) for row in rows),
                "behavior_failure_intervention_recovery_count": sum(
                    bool(row.get("recovery_success")) for row in failed),
                "behavior_failure_strict_joint_success_count": sum(
                    bool(row.get("episode_success")) for row in failed),
                "action_counts": dict(Counter(row.get("selected_action") for row in rows)),
            }

    comparisons: dict[str, dict[str, dict]] = defaultdict(dict)
    for method in METHODS[1:]:
        for family in FAMILIES:
            counts: Counter[str] = Counter()
            transitions: Counter[str] = Counter()
            for seed in source["frozen_seeds"]:
                static_rows = records[("eacr_static_m0", seed, family)]
                other_rows = records[(method, seed, family)]
                for left, right in zip(static_rows, other_rows, strict=True):
                    if left.get("fault_id") != right.get("fault_id"):
                        raise ValueError(f"fault sequence differs: {method}/{seed}/{family}")
                    counts["paired_episode_count"] += 1
                    counts["same_belief_count"] += (
                        left.get("belief_before_action") == right.get("belief_before_action"))
                    counts["same_candidate_set_count"] += (
                        _candidate_set(left) == _candidate_set(right))
                    different = left.get("selected_action") != right.get("selected_action")
                    counts["action_change_count"] += different
                    if different:
                        transitions[f"{left.get('selected_action')} → {right.get('selected_action')}"] += 1
                    if (left.get("fault_behavior_observed") is True
                            and right.get("fault_behavior_observed") is True):
                        counts["both_behavior_failed_count"] += 1
                        counts["static_strict_success_on_both_failed"] += bool(
                            left.get("episode_success"))
                        counts["other_strict_success_on_both_failed"] += bool(
                            right.get("episode_success"))
                        counts["static_intervention_recovery_on_both_failed"] += bool(
                            left.get("recovery_success"))
                        counts["other_intervention_recovery_on_both_failed"] += bool(
                            right.get("recovery_success"))
            comparisons[method][family] = {
                **dict(counts), "action_transitions": dict(transitions.most_common())}

    return {
        "source_aggregate": str(aggregate_path.relative_to(repo_root)),
        "source_aggregate_sha256": hashlib.sha256(aggregate_bytes).hexdigest(),
        "selected_cell_count": len(cells),
        "selected_episode_count": sum(len(rows) for rows in records.values()),
        "method_family": method_family,
        "paired_vs_static": comparisons,
        "interpretation": (
            "Read-only descriptive audit; no new method outcomes or inferential claims. "
            "Behavior-failed paired counts use only episode pairs where both methods' "
            "pre-intervention fault navigation failed."
        ),
    }


def markdown(result: dict) -> str:
    lines = [
        "# 原最终评估只读审计：补充实验基线",
        "",
        f"输入：`{result['source_aggregate']}`（SHA-256 `{result['source_aggregate_sha256']}`）。",
        f"有效 cell `{result['selected_cell_count']}`，episode `{result['selected_episode_count']}`。",
        "以下为描述性计数，不是新增确认性检验。",
        "",
        "## 故障态导航与行为失败后的结果",
        "",
        "| 方法 | 故障族 | 故障态导航成功 | 行为失败 | 行为失败中严格联合成功 | 全部严格联合成功 |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for method in METHODS:
        for family in FAMILIES:
            row = result["method_family"][method][family]
            lines.append(
                f"| {method} | {family} | {row['fault_navigation_success_count']}/{row['episode_count']} "
                f"| {row['behavior_failure_count']}/{row['episode_count']} "
                f"| {row['behavior_failure_strict_joint_success_count']}/{row['behavior_failure_count']} "
                f"| {row['strict_joint_success_count']}/{row['episode_count']} |")
    lines += [
        "",
        "## 与 Static 配对：相同 belief、候选集与动作变化",
        "",
        "| 方法 | 故障族 | belief 相同 | 候选集相同 | 动作改变 | 双方都发生行为失败 | 该子集严格联合成功 Static → 对照 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for method in METHODS[1:]:
        for family in FAMILIES:
            row = result["paired_vs_static"][method][family]
            n = row["paired_episode_count"]
            both = row.get("both_behavior_failed_count", 0)
            lines.append(
                f"| {method} | {family} | {row.get('same_belief_count', 0)}/{n} "
                f"| {row.get('same_candidate_set_count', 0)}/{n} "
                f"| {row.get('action_change_count', 0)}/{n} "
                f"| {both}/{n} "
                f"| {row.get('static_strict_success_on_both_failed', 0)}/{both} → "
                f"{row.get('other_strict_success_on_both_failed', 0)}/{both} |")
    lines += [
        "",
        "`fault_navigation_status` 是干预前 Nav2 目标结果；它和干预恢复率不是同一指标。",
        "双方法行为失败子集可能很小，不能据此单独主张优越性。",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output-prefix", type=Path, default=Path("results/supplementary_original_audit"))
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    aggregate_path = repo_root / "results/phase4_final_aggregate.json"
    result = audit(repo_root, aggregate_path)
    prefix = args.output_prefix
    if not prefix.is_absolute():
        prefix = repo_root / prefix
    prefix.parent.mkdir(parents=True, exist_ok=True)
    prefix.with_suffix(".json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    prefix.with_suffix(".md").write_text(markdown(result))
    print(prefix.with_suffix(".md"))


if __name__ == "__main__":
    main()
