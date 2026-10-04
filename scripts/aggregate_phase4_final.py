#!/usr/bin/env python3
"""Confirmatory aggregate for the frozen EACR final evaluation.

This script is deliberately separate from the Gazebo runner.  It treats a
``(method, seed, fault_family)`` cell as the unit of episode aggregation and
uses the 20 evaluation seeds as the cluster unit for paired bootstrap CIs.
It always writes an audit object.  A confirmatory conclusion is emitted only
when every acceptance gate in ``docs/EACR_FINAL_STATISTICAL_SPEC_v1.md`` is
met.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any


FAMILIES = ("localization", "costmap", "planner", "control")
METHODS = (
    "eacr_static_m0",
    "eacr_evolving_online_m0",
    "eacr_evolving_m20",
    "eacr_evolving_m50",
)
SEEDS = (
    1069364068, 683001511, 450637390, 1207356449, 1578549000,
    252445555, 729528073, 1092085222, 200776800, 1464253601,
    365260637, 225495283, 1725492561, 1054169594, 1613439514,
    1691408245, 849115063, 1146002680, 1534671149, 1320660730,
)

# These are the immutable hashes recorded in the full four-family training
# manifest.  The paths are checked relative to the repository root.
CHECKPOINT_SHA256 = {
    "M_20": "6fcfd7dac372c181223b86c683a54b21d255c51f07af522cb3e5eae9a10c4473",
    "M_50": "79e9e84b58b634f34ff71a6a42f5ccca81792b60aa757155544a555557a739ab",
}


def _json_files(inputs: list[Path]) -> list[Path]:
    files: set[Path] = set()
    for root in inputs:
        if root.is_file() and root.suffix == ".json":
            files.add(root)
        elif root.is_dir():
            files.update(root.rglob("phase3_gazebo_*.json"))
    return sorted(files)


def _method(item: dict[str, Any]) -> str | None:
    baseline = item.get("baseline")
    checkpoint = str(item.get("experience_checkpoint", "M_0"))
    if baseline == "eacr_static" and checkpoint == "M_0":
        return "eacr_static_m0"
    if baseline != "eacr_evolving":
        return None
    if checkpoint == "M_0" and bool(item.get("online_experience_update")):
        return "eacr_evolving_online_m0"
    if checkpoint == "M_20":
        return "eacr_evolving_m20"
    if checkpoint == "M_50":
        return "eacr_evolving_m50"
    return None


def _mean(values: list[float]) -> float | None:
    return mean(values) if values else None


def _sha256(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _resolve_snapshot(repo_root: Path, item: dict[str, Any]) -> tuple[Path | None, str | None]:
    raw = item.get("experience_snapshot_path")
    if not raw:
        return None, None
    path = Path(str(raw))
    if not path.is_absolute():
        path = repo_root / path
    return path, _sha256(path)


def _cell_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    recovery = [float(bool(row.get("recovery_success"))) for row in rows]
    sustained = [float(bool(row.get("episode_success"))) for row in rows]
    costs = [float(row["intervention_cost"]) for row in rows
             if row.get("intervention_cost") is not None]
    probes = [float(str(row.get("selected_action", "")).startswith("inspect")
                    and not bool(row.get("episode_success"))) for row in rows]
    recovery_times = [float(row["time_to_recovery_sec"]) for row in rows
                      if row.get("recovery_success")
                      and row.get("time_to_recovery_sec") is not None]
    return {
        "intervention_recovery_rate": _mean(recovery),
        "sustained_recovery_rate": _mean(sustained),
        "strict_joint_success_rate": _mean(sustained),
        "intervention_cost_mean": _mean(costs),
        "useless_probe_rate": _mean(probes),
        "mttr_success_mean_sec": _mean(recovery_times),
        "mttr_success_median_sec": median(recovery_times) if recovery_times else None,
        "mttr_success_n": len(recovery_times),
        "episode_count": len(rows),
    }


def _valid_record(path: Path, item: dict[str, Any], repo_root: Path,
                  excluded: Counter[str]) -> dict[str, Any] | None:
    method = _method(item)
    if method is None:
        excluded["unrecognised_method"] += 1
        return None
    try:
        seed = int(item["seed"])
    except (KeyError, TypeError, ValueError):
        excluded["missing_seed"] += 1
        return None
    if seed not in SEEDS:
        excluded["seed_not_in_frozen_manifest"] += 1
        return None
    rows = item.get("episodes")
    if not isinstance(rows, list) or len(rows) != 4:
        excluded["wrong_episode_count"] += 1
        return None
    if item.get("protocol_compliant") is not True:
        excluded["protocol_noncompliant"] += 1
        return None
    if item.get("infrastructure_failure"):
        excluded["infrastructure_failure"] += 1
        return None
    if not all(row.get("episode_evidence_valid") is True for row in rows):
        excluded["invalid_episode_evidence"] += 1
        return None
    families = {row.get("fault_family") for row in rows}
    if len(families) != 1 or next(iter(families)) not in FAMILIES:
        excluded["mixed_or_unknown_fault_family"] += 1
        return None
    family = str(next(iter(families)))
    # Every episode must expose the fields that define the frozen estimands.
    if any(row.get("intervention_cost") is None for row in rows):
        excluded["missing_intervention_cost"] += 1
        return None
    config = {
        "fault_scale": item.get("fault_scale"),
        "experience_prior_mode": item.get("experience_prior_mode"),
        "use_belief_action_scope": item.get("use_belief_action_scope"),
        "fault_repetitions": item.get("fault_repetitions"),
        "resume_experience_state": item.get("resume_experience_state"),
    }
    if config["fault_scale"] != 1.5:
        excluded["wrong_fault_scale"] += 1
        return None
    if config["experience_prior_mode"] != "weak_shared_m0":
        excluded["wrong_prior_mode"] += 1
        return None
    if config["use_belief_action_scope"] is not True:
        excluded["wrong_action_scope"] += 1
        return None
    if config["fault_repetitions"] != 4:
        excluded["wrong_fault_repetitions"] += 1
        return None
    if config["resume_experience_state"] is not False:
        excluded["resume_state_not_false"] += 1
        return None
    if method in {"eacr_static_m0", "eacr_evolving_m20", "eacr_evolving_m50"}:
        if method == "eacr_static_m0" and item.get("online_experience_update") is not False:
            excluded["static_online_update"] += 1
            return None
        if method in {"eacr_evolving_m20", "eacr_evolving_m50"} and item.get("online_experience_update") is not False:
            excluded["checkpoint_online_update"] += 1
            return None
    if method == "eacr_evolving_online_m0" and item.get("online_experience_update") is not True:
        excluded["online_m0_update_missing"] += 1
        return None
    snapshot_path, snapshot_sha = _resolve_snapshot(repo_root, item)
    if method in {"eacr_evolving_m20", "eacr_evolving_m50"}:
        expected = CHECKPOINT_SHA256["M_20" if method.endswith("m20") else "M_50"]
        if snapshot_sha != expected or item.get("experience_snapshot_sha256") != expected:
            excluded["checkpoint_sha_mismatch"] += 1
            return None
    return {
        "path": str(path),
        "method": method,
        "seed": seed,
        "fault_family": family,
        "metrics": _cell_metrics(rows),
        "config": config,
        "snapshot_path": str(snapshot_path) if snapshot_path else None,
        "snapshot_sha256": snapshot_sha,
    }


def _bootstrap(values: list[float], rng: random.Random, draws: int) -> list[float | None]:
    if not values:
        return [None, None]
    if len(values) == 1:
        return [values[0], values[0]]
    estimates = [mean(values[rng.randrange(len(values))] for _ in values)
                 for _ in range(draws)]
    estimates.sort()
    lo = estimates[int(0.025 * (len(estimates) - 1))]
    hi = estimates[int(0.975 * (len(estimates) - 1))]
    return [lo, hi]


def _seed_metrics(cells: list[dict[str, Any]]) -> dict[int, dict[str, float | None]]:
    grouped: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for cell in cells:
        grouped[(cell["method"], cell["seed"])].append(cell)
    out: dict[int, dict[str, float | None]] = {}
    metric_names = ("intervention_recovery_rate", "sustained_recovery_rate",
                    "intervention_cost_mean", "useless_probe_rate")
    for (method, seed), rows in grouped.items():
        if {row["fault_family"] for row in rows} != set(FAMILIES):
            continue
        metrics = {name: _mean([float(row["metrics"][name]) for row in rows])
                   for name in metric_names}
        mttr = [float(row["metrics"]["mttr_success_mean_sec"])
                for row in rows if row["metrics"]["mttr_success_mean_sec"] is not None]
        metrics["mttr_success_mean_sec"] = _mean(mttr)
        metrics["method"] = method  # type: ignore[assignment]
        out[seed] = metrics
    return out


def _comparison(static: dict[int, dict[str, Any]], evolving: dict[int, dict[str, Any]],
                metric: str, draws: int, seed: int) -> dict[str, Any]:
    paired = [s for s in SEEDS if s in static and s in evolving
              and static[s].get(metric) is not None and evolving[s].get(metric) is not None]
    deltas = [float(evolving[s][metric]) - float(static[s][metric]) for s in paired]
    rng = random.Random(seed)
    mean_delta = _mean(deltas)
    return {
        "paired_seed_count": len(deltas),
        "mean_delta": mean_delta,
        "bootstrap_95ci": _bootstrap(deltas, rng, draws),
        "sign_counts": {
            "positive": sum(delta > 0 for delta in deltas),
            "negative": sum(delta < 0 for delta in deltas),
            "zero": sum(delta == 0 for delta in deltas),
        },
        "seed_deltas": dict(zip(paired, deltas)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", action="append", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--bootstrap-draws", type=int, default=20000)
    args = parser.parse_args()

    excluded: Counter[str] = Counter()
    records: list[dict[str, Any]] = []
    for path in _json_files(args.input):
        try:
            item = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            excluded["unreadable"] += 1
            continue
        record = _valid_record(path, item, args.repo_root, excluded)
        if record is not None:
            records.append(record)

    cell_groups: dict[tuple[str, int, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        key = (record["method"], record["seed"], record["fault_family"])
        cell_groups[key].append(record)
    duplicates = {"|".join(map(str, key)): len(values)
                  for key, values in cell_groups.items() if len(values) > 1}
    cells = [max(values, key=lambda value: Path(value["path"]).stat().st_mtime_ns)
             for values in cell_groups.values()]

    by_method = {method: [cell for cell in cells if cell["method"] == method]
                 for method in METHODS}
    keys_by_method = {method: {(cell["seed"], cell["fault_family"])
                               for cell in by_method[method]} for method in METHODS}
    expected_keys = {(seed, family) for seed in SEEDS for family in FAMILIES}
    common_keys = set.intersection(*(keys_by_method[method] for method in METHODS))
    acceptance = {
        "all_methods_present": all(by_method[method] for method in METHODS),
        "each_method_has_80_cells": all(len(by_method[method]) == 80 for method in METHODS),
        "each_cell_has_4_episodes": all(cell["metrics"]["episode_count"] == 4 for cell in cells),
        "common_20x4_keys": common_keys == expected_keys,
        "no_duplicate_cells": not duplicates,
        "excluded_seed_544047076": 544047076 not in {cell["seed"] for cell in cells},
        "config_consistent": len({json.dumps(cell["config"], sort_keys=True)
                                   for cell in cells}) <= 4,
        "m20_m50_snapshot_sha_valid": not any(
            cell["method"] in {"eacr_evolving_m20", "eacr_evolving_m50"}
            and cell["snapshot_sha256"] != CHECKPOINT_SHA256["M_20" if cell["method"].endswith("m20") else "M_50"]
            for cell in cells
        ),
    }
    confirmatory_ready = all(acceptance.values())

    seed_by_method = {method: _seed_metrics(by_method[method]) for method in METHODS}
    comparisons: dict[str, dict[str, Any]] = {}
    for method in METHODS[1:]:
        comparisons[method] = {}
        for index, metric in enumerate(("intervention_recovery_rate",
                                        "sustained_recovery_rate",
                                        "intervention_cost_mean",
                                        "useless_probe_rate",
                                        "mttr_success_mean_sec")):
            comparisons[method][metric] = _comparison(
                seed_by_method["eacr_static_m0"], seed_by_method[method],
                metric, args.bootstrap_draws, 20261004 + index)

    result = {
        "protocol_id": "eacr_evolving_advantage_v1",
        "confirmatory_ready": confirmatory_ready,
        "frozen_seeds": list(SEEDS),
        "families": list(FAMILIES),
        "methods": METHODS,
        "valid_cell_count": len(cells),
        "valid_episode_count": sum(cell["metrics"]["episode_count"] for cell in cells),
        "excluded_counts": dict(excluded),
        "duplicate_cells": duplicates,
        "acceptance": acceptance,
        "cell_metrics": sorted(cells, key=lambda cell: (cell["method"], cell["seed"], cell["fault_family"])),
        "seed_metrics": seed_by_method,
        "paired_comparisons": comparisons,
        "bootstrap": {"unit": "evaluation_seed", "draws": args.bootstrap_draws,
                      "seed": 20261004},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"confirmatory_ready": confirmatory_ready,
                      "valid_cell_count": len(cells),
                      "valid_episode_count": result["valid_episode_count"],
                      "acceptance": acceptance,
                      "excluded_counts": dict(excluded)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
