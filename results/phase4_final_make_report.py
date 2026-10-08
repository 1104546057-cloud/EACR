#!/usr/bin/env python3
"""Paper report for the frozen final evaluation.

The confirmatory aggregate remains scripts/aggregate_phase4_final.py.
Family-level intervals use that script's bootstrap implementation: 20,000
paired resamples of evaluation seeds, percentile indexes
int(0.025 * (draws - 1)) and int(0.975 * (draws - 1)).
"""

from __future__ import annotations

import importlib.util
import json
import random
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGGREGATE_PATH = ROOT / "results" / "phase4_final_aggregate.json"
REPORT_PATH = ROOT / "results" / "phase4_final_report.md"
TABLES_PATH = ROOT / "results" / "phase4_final_tables.json"
DRAWS = 20000

METRICS = (
    ("intervention_recovery_rate", "Intervention recovery", "higher"),
    ("sustained_recovery_rate", "Sustained recovery / strict joint success", "higher"),
    ("intervention_cost_mean", "Intervention cost", "lower"),
    ("useless_probe_rate", "Useless probe", "lower"),
    ("mttr_success_mean_sec", "Success-conditional MTTR (s)", "lower"),
)
METHOD_LABELS = {
    "eacr_static_m0": "Static M0",
    "eacr_evolving_online_m0": "Evolving online M0",
    "eacr_evolving_m20": "Evolving M20",
    "eacr_evolving_m50": "Evolving M50",
}


def _aggregate_module():
    path = ROOT / "scripts" / "aggregate_phase4_final.py"
    spec = importlib.util.spec_from_file_location("phase4_final_aggregate", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fmt(value, digits=3):
    if value is None:
        return "—"
    return f"{value:.{digits}f}"


def _ci(interval):
    if not interval or interval[0] is None:
        return "—"
    return f"[{_fmt(interval[0])}, {_fmt(interval[1])}]"


def _includes_zero(interval) -> bool:
    if not interval or interval[0] is None or interval[1] is None:
        return True
    return interval[0] <= 0 <= interval[1]


def _verdict(direction: str, mean_delta, interval) -> str:
    if mean_delta is None or _includes_zero(interval):
        return "CI includes 0; no superiority claim"
    improved = mean_delta > 0 if direction == "higher" else mean_delta < 0
    if improved:
        return "CI excludes 0 in the favourable direction"
    return "CI excludes 0 in the unfavourable direction"


def _mean(values):
    values = [value for value in values if value is not None]
    if not values:
        return None
    return sum(values) / len(values)


def _family_comparison(module, cells, method: str, family: str, metric: str, rng_seed: int):
    static = {}
    evolving = {}
    for cell in cells:
        if cell["fault_family"] != family:
            continue
        value = cell["metrics"].get(metric)
        if cell["method"] == "eacr_static_m0":
            static[int(cell["seed"])] = value
        elif cell["method"] == method:
            evolving[int(cell["seed"])] = value
    paired = [seed for seed in module.SEEDS
              if static.get(seed) is not None and evolving.get(seed) is not None]
    deltas = [float(evolving[seed]) - float(static[seed]) for seed in paired]
    interval = module._bootstrap(deltas, random.Random(rng_seed), DRAWS)
    return {
        "method": method,
        "fault_family": family,
        "metric": metric,
        "paired_seed_count": len(deltas),
        "mean_delta": _mean(deltas),
        "bootstrap_95ci": interval,
        "sign_counts": {
            "positive": sum(delta > 0 for delta in deltas),
            "negative": sum(delta < 0 for delta in deltas),
            "zero": sum(delta == 0 for delta in deltas),
        },
        "bootstrap_seed": rng_seed,
        "bootstrap_draws": DRAWS,
    }


def _gap_report(payload) -> str:
    lines = [
        "# EACR 最终评估缺口报告",
        "",
        "确认性门槛没有全部通过。本报告只记录缺口，不给出相对 Static 的优越性结论。",
        "",
        "## 验收",
        "",
        "| 门槛 | 结果 |",
        "| --- | --- |",
    ]
    for key, value in payload.get("acceptance", {}).items():
        lines.append(f"| `{key}` | {'通过' if value else '未通过'} |")
    lines.extend([
        "",
        f"有效 cell：{payload.get('valid_cell_count')}",
        f"有效 episode：{payload.get('valid_episode_count')}",
        "",
        "## 排除计数",
        "",
        "```json",
        json.dumps(payload.get("excluded_counts", {}), ensure_ascii=False, indent=2),
        "```",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    module = _aggregate_module()
    payload = json.loads(AGGREGATE_PATH.read_text())
    if not payload.get("confirmatory_ready"):
        reduced = {
            "protocol_id": payload.get("protocol_id"),
            "confirmatory_ready": False,
            "acceptance": payload.get("acceptance"),
            "valid_cell_count": payload.get("valid_cell_count"),
            "valid_episode_count": payload.get("valid_episode_count"),
            "excluded_counts": payload.get("excluded_counts"),
            "duplicate_cells": payload.get("duplicate_cells"),
            "note": "Advantage comparisons withheld because an acceptance gate failed.",
        }
        AGGREGATE_PATH.write_text(json.dumps(reduced, ensure_ascii=False, indent=2) + "\n")
        REPORT_PATH.write_text(_gap_report(payload))
        TABLES_PATH.write_text(json.dumps(reduced, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({"confirmatory_ready": False, "report": str(REPORT_PATH)}))
        return

    cells = payload["cell_metrics"]
    seed_metrics = payload["seed_metrics"]
    levels = []
    for method in module.METHODS:
        rows = seed_metrics.get(method) or seed_metrics.get(str(method)) or {}
        item = {"method": method, "seed_count": len(rows)}
        for metric, _label, _direction in METRICS:
            item[metric] = _mean([
                row.get(metric) for row in rows.values() if isinstance(row, dict)
            ])
        levels.append(item)

    family_rows = []
    for method_index, method in enumerate(module.METHODS[1:], start=1):
        for family_index, family in enumerate(module.FAMILIES):
            for metric_index, (metric, _label, _direction) in enumerate(METRICS):
                rng_seed = 20261004 + 1000 * method_index + 100 * family_index + metric_index
                family_rows.append(_family_comparison(
                    module, cells, method, family, metric, rng_seed))

    tables = {
        "protocol_id": payload["protocol_id"],
        "confirmatory_ready": True,
        "method_seed_means": levels,
        "paired_comparisons": payload["paired_comparisons"],
        "family_paired_comparisons": family_rows,
        "bootstrap": payload.get("bootstrap"),
        "family_bootstrap": {
            "unit": "evaluation_seed within one fault family",
            "draws": DRAWS,
            "implementation": "scripts/aggregate_phase4_final.py:_bootstrap",
        },
    }
    TABLES_PATH.write_text(json.dumps(tables, ensure_ascii=False, indent=2) + "\n")

    lines = [
        "# EACR 最终确认性评估报告",
        "",
        "统计口径为 `docs/EACR_FINAL_STATISTICAL_SPEC_v1.md`。主比较是每个 Evolving 条件减去 Static M0。",
        "主置信区间把 20 个 evaluation seed 作为配对聚类，重采样 20,000 次。",
        "成功率差值为正更好；成本、无效探测和成功条件 MTTR 差值为负更好。",
        "区间包含 0 时，不把该比较写成确定性优越。",
        "",
        "## 方法水平",
        "",
        "每个数是 20 个 seed 的等权平均。一个 seed 内部四个故障族等权。",
        "",
        "| 方法 | IR | SR / strict joint | Cost | Useless probe | Success-conditional MTTR (s) |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in levels:
        lines.append(
            f"| {METHOD_LABELS[item['method']]} | {_fmt(item['intervention_recovery_rate'])} "
            f"| {_fmt(item['sustained_recovery_rate'])} | {_fmt(item['intervention_cost_mean'])} "
            f"| {_fmt(item['useless_probe_rate'])} | {_fmt(item['mttr_success_mean_sec'], 2)} |"
        )

    lines.extend([
        "",
        "## 相对 Static 的配对差",
        "",
        "| 方法 | 指标 | 种子数 | 平均差 | 95% CI | + / − / 0 | 读法 |",
        "| --- | --- | ---: | ---: | --- | --- | --- |",
    ])
    favourable_families = {method: {metric: [] for metric, _label, _direction in METRICS}
                           for method in module.METHODS[1:]}
    for method in module.METHODS[1:]:
        comparisons = payload["paired_comparisons"][method]
        for metric, label, direction in METRICS:
            row = comparisons[metric]
            signs = row["sign_counts"]
            lines.append(
                f"| {METHOD_LABELS[method]} | {label} | {row['paired_seed_count']} "
                f"| {_fmt(row['mean_delta'])} | {_ci(row['bootstrap_95ci'])} "
                f"| {signs['positive']} / {signs['negative']} / {signs['zero']} "
                f"| {_verdict(direction, row['mean_delta'], row['bootstrap_95ci'])} |"
            )

    lines.extend([
        "",
        "## 分故障族配对差",
        "",
        "每一行固定一个故障族，在 20 个 seed 上做配对 bootstrap。cell 内 4 次重复先取平均，不把 episode 当作独立样本。",
        "",
        "| 方法 | 故障族 | 指标 | 种子数 | 平均差 | 95% CI | + / − / 0 | 读法 |",
        "| --- | --- | --- | ---: | ---: | --- | --- | --- |",
    ])
    for row in family_rows:
        metric, label, direction = next(item for item in METRICS if item[0] == row["metric"])
        verdict = _verdict(direction, row["mean_delta"], row["bootstrap_95ci"])
        if verdict == "CI excludes 0 in the favourable direction":
            favourable_families[row["method"]][metric].append(row["fault_family"])
        signs = row["sign_counts"]
        lines.append(
            f"| {METHOD_LABELS[row['method']]} | {row['fault_family']} | {label} "
            f"| {row['paired_seed_count']} | {_fmt(row['mean_delta'])} | {_ci(row['bootstrap_95ci'])} "
            f"| {signs['positive']} / {signs['negative']} / {signs['zero']} | {verdict} |"
        )

    lines.extend(["", "## 优势是否只来自一个故障族", ""])
    for method in module.METHODS[1:]:
        for metric, label, _direction in METRICS:
            families = favourable_families[method][metric]
            if not families:
                lines.append(f"- {METHOD_LABELS[method]} / {label}：没有故障族的区间落在有利一侧且排除 0。")
            elif len(families) == 1:
                lines.append(
                    f"- {METHOD_LABELS[method]} / {label}：有利且排除 0 的结果只来自 `{families[0]}`。"
                )
            else:
                lines.append(
                    f"- {METHOD_LABELS[method]} / {label}：有利且排除 0 的故障族为 {', '.join(families)}。"
                )

    lines.extend([
        "",
        "## 口径",
        "",
        "- Intervention recovery 使用 `recovery_success`，不是恢复后的导航成功。",
        "- Sustained recovery 与 strict joint success 都使用 `episode_success`。",
        "- MTTR 使用成功恢复 episode 的 `time_to_recovery_sec`。没有成功恢复的 seed 保持缺失，不填 0。",
        "- 成本把成功和失败的已记录 action 都算进分母。",
        "- 本报告不提供未预注册的 p 值。",
        "",
    ])
    REPORT_PATH.write_text("\n".join(lines))
    print(json.dumps({"confirmatory_ready": True, "report": str(REPORT_PATH)}))


if __name__ == "__main__":
    main()
