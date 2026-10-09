#!/usr/bin/env python3
"""Render the final Chinese supplementary-experiment report after A and B finish."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
A_PATH = ROOT / 'results/supplementary_A_aggregate.json'
B_PATH = ROOT / 'results/supplementary_B_aggregate.json'
A_PROTOCOL = ROOT / 'results/supplementary_protocol_A_v1.json'
B_PROTOCOL = ROOT / 'results/supplementary_protocol_B_v1.json'
GEOMETRY_AUDIT = ROOT / 'results/supplementary_transfer_geometry_audit.json'
ORIGINAL_AUDIT = ROOT / 'results/supplementary_original_audit.json'
A_COMPLETION_AUDIT = ROOT / 'results/supplementary_A_completion_audit.json'
A_SOURCE_CORRECTION = ROOT / 'results/supplementary_A_source_provenance_correction_01.json'
OUT = ROOT / 'docs/EACR_补充实验结果报告.md'
FAMILIES = ('localization', 'costmap', 'planner', 'control')
FAMILY_LABELS = {
    'localization': '定位', 'costmap': '代价地图', 'planner': '规划器', 'control': '控制器',
}
METHOD_LABELS = {
    'eacr_static_m0': 'Static M0', 'eacr_evolving_m50': 'Frozen M50',
    'eacr_strong_rule': '强规则', 'static_m0': 'Static M0',
    'frozen_m50': 'Frozen M50', 'strong_rule': '强规则',
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def pct(numerator: Any, denominator: Any) -> str:
    if numerator is None or denominator in (None, 0):
        return '—'
    return f'{numerator}/{denominator} ({100.0 * numerator / denominator:.1f}%)'


def fnum(value: Any, digits: int = 3) -> str:
    return '—' if value is None else f'{float(value):.{digits}f}'


def ci_text(summary: dict[str, Any] | None, digits: int = 3) -> str:
    if not summary or summary.get('mean_difference') is None:
        return '—'
    ci = summary.get('ci95')
    mean = float(summary['mean_difference'])
    if not ci:
        return f'{mean:.{digits}f}'
    return (f'{mean:.{digits}f} [{float(ci[0]):.{digits}f}, {float(ci[1]):.{digits}f}] '
            f'(seed +/−/= {summary.get("positive_seeds", "?")}/'
            f'{summary.get("negative_seeds", "?")}/{summary.get("zero_seeds", "?")})')


def family_rows(aggregate: dict[str, Any], method_id: str, family: str) -> dict[str, Any]:
    return aggregate['method_family'][method_id][family]


def validate_complete(a: dict[str, Any], b: dict[str, Any], a_protocol: dict[str, Any], b_protocol: dict[str, Any]) -> None:
    if a.get('protocol_id') != 'eacr_supplementary_A_v1':
        raise ValueError('A aggregate does not match the frozen A protocol')
    if b.get('protocol_id') != 'eacr_supplementary_B_v1':
        raise ValueError('B aggregate does not match the frozen B protocol')
    expected_a = {'eacr_static_m0', 'eacr_evolving_m50', 'eacr_strong_rule'}
    expected_b = {'static_m0', 'frozen_m50', 'strong_rule'}
    for name, protocol in (('A', a_protocol), ('B', b_protocol)):
        if protocol.get('action_budget') != 1 or protocol.get('action_library_size') != 9:
            raise ValueError(f'{name} protocol must freeze one action from the shared nine-action library')
    pilot = b_protocol.get('engineering_pilot', {})
    required_pilot_checks = {
        'normal_navigation', 'episode_reset', 'fault_injection', 'online_evidence',
        'behavioral_effect', 'rollback', 'post_action_recovery', 'm50_experience_key_hit',
        'nav2_bt_audit',
    }
    if pilot.get('status') != 'passed' or not required_pilot_checks.issubset(pilot.get('checks', {})):
        raise ValueError('B protocol lacks a passing, fully itemized engineering pilot record')
    if any(pilot['checks'].get(key) is not True for key in required_pilot_checks):
        raise ValueError('B engineering pilot did not pass every required check')
    for name, aggregate, expected_methods, protocol in (
        ('A', a, expected_a, a_protocol), ('B', b, expected_b, b_protocol),
    ):
        if aggregate.get('seed_count') != 10 or aggregate.get('family_count') != 4:
            raise ValueError(f'{name} aggregate is incomplete: expected 10 seeds and 4 families')
        seeds = protocol.get('seeds', [])
        if len(seeds) != 10 or len(set(seeds)) != 10:
            raise ValueError(f'{name} protocol must define exactly 10 unique seeds')
        selected = aggregate.get('selected_cells', [])
        method_keys = 'method'
        tuples = set()
        for cell in selected:
            method = cell.get(method_keys)
            key = (method, cell.get('seed'), cell.get('fault_family'))
            if key in tuples:
                raise ValueError(f'{name} aggregate has a duplicate selected cell: {key}')
            tuples.add(key)
        expected_keys = {
            (method, seed, family)
            for method in expected_methods for seed in seeds for family in FAMILIES
        }
        if len(selected) != 120 or tuples != expected_keys:
            raise ValueError(f'{name} aggregate must select exactly 120 cells across the frozen three methods')
        for method in expected_methods:
            for family in FAMILIES:
                rows = aggregate['method_family'][method][family]
                count = rows.get('episodes', rows.get('episode_count'))
                if count != 40:
                    raise ValueError(f'{name} aggregate {method}/{family} has {count} episodes, expected 40')


def outcome_table(aggregate: dict[str, Any], methods: tuple[str, ...], title: str) -> list[str]:
    lines = [f'### {title}', '',
             '| 方法 | 故障族 | 动作前 Nav2 成功 | 行为失败 | 失败后修复动作成功 | 失败后严格恢复 | 全样本严格联合成功 | 平均干预成本 | 成功恢复 MTTR（秒） |',
             '|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for method in methods:
        for family in FAMILIES:
            row = family_rows(aggregate, method, family)
            n = row.get('episodes', row.get('episode_count', 0))
            pre_n = row.get('pre_action_nav_success', row.get('pre_action_nav2_success_count'))
            pre_rate = row.get('pre_action_nav_success_rate', row.get('pre_action_nav2_success_rate'))
            failed_n = row.get('behavior_failed', row.get('behavior_failed_count', 0))
            action_n = row.get('behavior_failed_recovery_action_count', row.get('behavior_failed_repair_action_count'))
            action_rate = row.get('behavior_failed_recovery_action_rate', row.get('behavior_failed_repair_action_rate'))
            strict_n = row.get('behavior_failed_strict_recovery_count')
            strict_rate = row.get('behavior_failed_strict_recovery_rate')
            all_n = row.get('strict_joint_success', row.get('strict_joint_success_count'))
            all_rate = row.get('strict_joint_success_rate')
            cost = row.get('intervention_cost_mean', row.get('intervention_cost_mean_all_episodes'))
            mttr = row.get('success_conditional_mttr_mean_sec', row.get('successful_recovery_mttr_mean_sec'))
            lines.append(
                f'| {METHOD_LABELS.get(method, method)} | {FAMILY_LABELS[family]} | '
                f'{pct(pre_n, n)} | {failed_n}/{n} | {pct(action_n, failed_n)} | '
                f'{pct(strict_n, failed_n)} | {pct(all_n, n)} | {fnum(cost)} | {fnum(mttr, 1)} |'
            )
        lines.append('')
    return lines


def common_failure_fields(pair: dict[str, Any], variant: str) -> tuple[str, str, str, str]:
    if variant == 'A':
        strict = pair.get('common_failure_paired_strict_success', {})
        action = pair.get('common_failure_paired_repair_action', {})
        strict_text = (f'n={strict.get("n_episode_pairs", 0)}; left '
                       f'{pct(strict.get("left_strict_success"), strict.get("n_episode_pairs"))}; '
                       f'right {pct(strict.get("right_strict_success"), strict.get("n_episode_pairs"))}')
        action_text = (f'n={action.get("n_episode_pairs", 0)}; '
                       f'left {pct(action.get("left_success"), action.get("n_episode_pairs"))}; '
                       f'right {pct(action.get("right_success"), action.get("n_episode_pairs"))}')
        return strict_text, ci_text(strict.get('paired_seed_cluster_difference')), action_text, ci_text(action.get('paired_seed_cluster_difference'))
    strict = pair.get('common_behavior_failure_pairs', {})
    action = pair.get('common_behavior_failure_repair_action_pairs', {})
    strict_text = (f'n={strict.get("pair_count", 0)}; left '
                   f'{pct(strict.get("left_strict_success_count"), strict.get("pair_count"))}; right '
                   f'{pct(strict.get("right_strict_success_count"), strict.get("pair_count"))}')
    action_text = (f'n={action.get("pair_count", 0)}; left '
                   f'{pct(action.get("left_repair_action_success_count"), action.get("pair_count"))}; right '
                   f'{pct(action.get("right_repair_action_success_count"), action.get("pair_count"))}')
    return strict_text, ci_text(strict.get('seed_cluster_left_minus_right')), action_text, ci_text(action.get('seed_cluster_left_minus_right'))


def paired_section(aggregate: dict[str, Any], variant: str, title: str) -> list[str]:
    lines = [f'### {title}', '',
             '差值方向均为比较键中的 left − right；成功率差以比例表示，成本差沿用日志中的干预成本单位。CI 以 seed 为 cluster bootstrap。', '',
             '| 配对比较 | 全局严格成功差（95% CI；正/负/零 seed） | 全局成本差（95% CI） |',
             '|---|---:|---:|']
    for comparison, result in aggregate.get('paired', {}).items():
        success = result.get('strict_joint_success') if variant == 'A' else result.get('overall_strict_joint_success')
        cost = result.get('intervention_cost_mean_left_minus_right') if variant == 'A' else result.get('overall_intervention_cost_mean_left_minus_right')
        lines.append(f'| {comparison.replace("_minus_", " − ")} | {ci_text(success)} | {ci_text(cost)} |')
    lines += ['', '| 配对比较 | 故障族 | 严格成功差（95% CI） | 成本差（95% CI） | 共同失败严格恢复（L/R） | 严格恢复差（95% CI） | 共同失败修复动作成功（L/R） | 动作成功差（95% CI） |',
              '|---|---|---:|---:|---:|---:|---:|---:|']
    for comparison, result in aggregate.get('paired', {}).items():
        for family in FAMILIES:
            pair = result['family_details'][family]
            success = pair.get('strict_joint_success') if variant == 'A' else pair.get('strict_joint_success_left_minus_right')
            cost = pair.get('intervention_cost_mean_left_minus_right')
            strict_text, strict_ci, action_text, action_ci = common_failure_fields(pair, variant)
            lines.append(
                f'| {comparison.replace("_minus_", " − ")} | {FAMILY_LABELS[family]} | '
                f'{ci_text(success)} | {ci_text(cost)} | {strict_text} | {strict_ci} | {action_text} | {action_ci} |'
            )
    return lines


def mechanism_section(aggregate: dict[str, Any], variant: str, title: str) -> list[str]:
    lines = [f'### {title}', '', '| 配对比较 | 故障族 | 原始证据相同 | belief 相同 | 候选动作集合相同 | 首选动作不同 |',
             '|---|---|---:|---:|---:|---:|']
    for comparison, result in aggregate.get('paired', {}).items():
        for family in FAMILIES:
            mechanism = result['family_details'][family].get('mechanism', {})
            pairs = mechanism.get('paired_episodes', mechanism.get('episode_pairs', 0))
            evidence = mechanism.get('same_online_evidence_rate')
            if evidence is None:
                evidence = mechanism.get('same_online_evidence', 0) / pairs if pairs else None
            belief = mechanism.get('same_belief_rate')
            if belief is None:
                belief = mechanism.get('same_belief', 0) / pairs if pairs else None
            candidate = mechanism.get('same_candidate_set_rate')
            if candidate is None:
                candidate = mechanism.get('same_candidates', 0) / pairs if pairs else None
            different = mechanism.get('different_action', 0)
            lines.append(
                f'| {comparison.replace("_minus_", " − ")} | {FAMILY_LABELS[family]} | '
                f'{fnum(evidence*100,1) + "%" if evidence is not None else "—"} | '
                f'{fnum(belief*100,1) + "%" if belief is not None else "—"} | '
                f'{fnum(candidate*100,1) + "%" if candidate is not None else "—"} | {different}/{pairs} |'
            )
    return lines


def evidence_diagnostics_section(aggregate: dict[str, Any], title: str) -> list[str]:
    """Report whether paired policy inputs truly match, including field-level drift."""
    lines = [
        f'### {title}', '',
        '| 配对比较 | 故障族 | 证据字段结构一致 | Nav2 参数读数一致 | AMCL 状态标志一致 | AMCL 距离阈值状态一致（>0.35 m） | planner lifecycle 异常判据一致 | 起点距离绝对差均值/最大值（m） | 不一致字段（配对数） |',
        '|---|---|---:|---:|---:|---:|---:|---:|---|',
    ]
    for comparison, result in aggregate.get('paired', {}).items():
        for family in FAMILIES:
            mechanism = result['family_details'][family].get('mechanism', {})
            pairs = mechanism.get('paired_episodes', mechanism.get('episode_pairs', 0))
            schema = mechanism.get('same_online_evidence_schema_rate')
            parameters = mechanism.get('same_nav2_parameter_readbacks_rate')
            amcl_flags = mechanism.get('same_amcl_status_flags_rate')
            amcl_threshold = mechanism.get('same_amcl_distance_threshold_state', {})
            amcl_threshold_rate = amcl_threshold.get('rate')
            lifecycle_predicate = mechanism.get('same_planner_lifecycle_anomaly_predicate_rate')
            distance = mechanism.get('amcl_distance_abs_delta_m', {})
            mean_delta, max_delta = distance.get('mean'), distance.get('max')
            distance_text = (
                f'{fnum(mean_delta, 4)}/{fnum(max_delta, 4)} (n={distance.get("n", 0)})'
                if mean_delta is not None and max_delta is not None else '—'
            )
            mismatches = mechanism.get('online_evidence_field_mismatch_counts', {})
            mismatch_text = ', '.join(
                f'{field}:{count}' for field, count in sorted(mismatches.items())
            ) or '无'
            lifecycle = mechanism.get('planner_lifecycle_non_normal_counts', {})
            if lifecycle:
                mismatch_text += f'；非正常 planner lifecycle：{lifecycle}'
            lines.append(
                f'| {comparison.replace("_minus_", " − ")} | {FAMILY_LABELS[family]} | '
                f'{fnum(schema*100,1) + "%" if schema is not None else "—"} | '
                f'{fnum(parameters*100,1) + "%" if parameters is not None else "—"} | '
                f'{fnum(amcl_flags*100,1) + "%" if amcl_flags is not None else "—"} | '
                f'{pct(amcl_threshold.get("same"), amcl_threshold.get("n"))} | '
                f'{fnum(lifecycle_predicate*100,1) + "%" if lifecycle_predicate is not None else "—"} | '
                f'{distance_text} | {mismatch_text} |'
            )
    lines += [
        '',
        '字段结构一致率为 100% 才表示两边记录了同一组在线证据字段；参数读数、AMCL 标志及规则实际使用的 AMCL 距离阈值/lifecycle 异常判据另行核对。数值字段允许自然测量波动，因此同时列出差异大小。字段差异会限制“原始输入完全相同”的结论；阈值状态一致只能说明该规则对照在相应判据上得到相同分类，不能替代原始字段一致。',
    ]
    return lines


def exclusion_section(aggregate: dict[str, Any], title: str) -> list[str]:
    excluded = aggregate.get('excluded_attempts', [])
    counts = Counter(str(item.get('reason', 'unspecified')) for item in excluded)
    lines = [f'### {title}', '', f'排除项记录数：{len(excluded)}。', '']
    if counts:
        lines += ['| 排除原因 | 条数 |', '|---|---:|']
        lines.extend(f'| {reason} | {count} |' for reason, count in sorted(counts.items()))
    else:
        lines.append('没有登记的无效或额外尝试。')
    lines += ['', '具体路径、行号、协议缺口和手工中断原因保存在对应 aggregate 的 `excluded_attempts` 字段中。']
    return lines


def render_report(a: dict[str, Any], b: dict[str, Any], a_protocol: dict[str, Any], b_protocol: dict[str, Any], geometry: dict[str, Any] | None,
                  original_audit: dict[str, Any] | None = None,
                  a_completion_audit: dict[str, Any] | None = None,
                  a_source_correction: dict[str, Any] | None = None) -> str:
    validate_complete(a, b, a_protocol, b_protocol)
    if not geometry or geometry.get('static_checks_pass') is not True:
        raise ValueError('transfer geometry audit is missing or failed')
    bt = (b.get('nav2_engineering_reference') or {}).get('bt_audit') or {}
    if bt.get('audit_missing') or not bt.get('path') or not bt.get('sha256'):
        raise ValueError('Nav2 BT engineering-reference audit is missing or incomplete')
    methods_a = ('eacr_static_m0', 'eacr_evolving_m50', 'eacr_strong_rule')
    methods_b = ('static_m0', 'frozen_m50', 'strong_rule')
    lines = [
        '# EACR 补充实验结果报告', '',
        f'生成时间：{dt.datetime.now(dt.timezone.utc).isoformat()}。本报告由 `scripts/render_supplementary_report_postfreeze.py` 从 A/B 机器汇总生成，并补充原评估只读审计与来源说明。', '',
        '## 1. 实验范围与协议', '',
        f'- A：原场景 `{a_protocol.get("scene")}`，强规则新增 40 个有效 cell；与同 seed、同故障族的原 Static M0/Frozen M50 记录配对。seed：`{a_protocol.get("seeds")}`。',
        f'- B：新场景 `{b_protocol.get("expected_run", {}).get("actual_map_id", "transfer_courtyard")}`，Static M0、Frozen M50、强规则各 40 个有效 cell；三方法共用冻结 seed 和故障序列。seed：`{b_protocol.get("seeds")}`。',
        f'- B 工程 pilot 状态：`{b_protocol.get("engineering_pilot", {}).get("status")}`；验证记录：`{b_protocol.get("engineering_pilot", {}).get("report_path", "未登记")}`。',
        '- 每 cell 4 次重复，方法间按 seed 和故障族配对；置信区间以 seed 为 cluster，不能把 episode 当作独立 seed。',
        f'- A 冻结为单次动作预算 `{a_protocol.get("action_budget")}`、九动作全集 `{a_protocol.get("action_library_size")}`；B 的动作预算与动作库按冻结 B 协议记录。',
        '- 严格联合成功定义为故障效果可观察、恢复动作成功、回滚成功且动作后独立 Nav2 导航成功；故障行为失败后的严格恢复再按故障态 Nav2 abort/timeout 分层。',
        '- 严格联合成功、故障行为失败后的严格恢复、恢复动作/参数回滚成功、动作前 Nav2 表现和干预成本分别报告。',
        '', '| 冻结对象 | 协议 ID | 协议 SHA-256 | 分析脚本 SHA-256 |', '|---|---|---|---|',
        f'| A | {a.get("protocol_id")} | {a.get("protocol_sha256", "—")} | {a.get("analysis_script_sha256", "—")} |',
        f'| B | {b.get("protocol_id")} | {b.get("protocol_sha256", "—")} | {b.get("analysis_script_sha256", "—")} |',
    ]
    if original_audit:
        static_planner = original_audit.get('method_family', {}).get('eacr_static_m0', {}).get('planner', {})
        planner_n = static_planner.get('episode_count')
        lines += [
            '', '## 1.1 原评估数据审计：配置修复与行为恢复分开', '',
            f'- 原始数据只读审计覆盖 {original_audit.get("selected_cell_count", "—")} 个 cell、{original_audit.get("selected_episode_count", "—")} 个 episode，来源 SHA-256：`{original_audit.get("source_aggregate_sha256", "未登记")}`。',
            f'- 原 Static M0 的 planner 故障共 {static_planner.get("episode_count", "—")} 次；故障态、动作前 Nav2 导航仍成功 {static_planner.get("fault_navigation_success_count", "—")}/{planner_n}，行为失败 {static_planner.get("behavior_failure_count", "—")}/{planner_n}，严格联合成功 {static_planner.get("strict_joint_success_count", "—")}/{planner_n}。',
            '- 这说明异常参数读数或故障注入本身不能替代“导航行为确实失败”的证据。下文分别报告故障效果是否可观察、故障行为失败、失败后的恢复和全样本严格联合成功。',
        ]
    lines += ['', '## 2. A 组：原场景强规则对照', '',
    ]
    lines += outcome_table(a, methods_a, '各方法 × 故障族结果（每格 40 episode）')
    lines += ['', *paired_section(a, 'A', '按 seed 配对比较'), '', *mechanism_section(a, 'A', '同信息与动作选择机制'), '',
              *evidence_diagnostics_section(a, 'A 在线证据逐字段核验'), '',
              *exclusion_section(a, 'A 组无效尝试与排除项'), '', '## 3. B 组：跨场景迁移', '']
    lines += outcome_table(b, methods_b, '各方法 × 故障族结果（每格 40 episode）')
    lines += ['', *paired_section(b, 'B', '按 seed 配对比较'), '', *mechanism_section(b, 'B', '同信息与动作选择机制'), '',
              *evidence_diagnostics_section(b, 'B 在线证据逐字段核验'), '',
              *exclusion_section(b, 'B 组无效尝试与排除项'), '']
    nav2 = b.get('nav2_engineering_reference', {})
    bt = nav2.get('bt_audit', {})
    node_counts = bt.get('node_tag_counts', {})
    lines += ['## 4. Nav2 工程参照', '',
              f'- 默认行为树文件：`{bt.get("path", "未登记")}`；SHA-256：`{bt.get("sha256", "未登记")}`。',
              f'- 结构节点计数：ClearEntireCostmap={node_counts.get("ClearEntireCostmap", "—")}, Spin={node_counts.get("Spin", "—")}, Wait={node_counts.get("Wait", "—")}, BackUp={node_counts.get("BackUp", "—")}。',
              '- 这是动作前故障态 `NavigateToPose` 的工程参照，不是同动作库算法基线。仅有最终 action status 时不能推断默认行为树实际执行了哪些恢复节点。',
              '- Nav2 默认树没有 EACR 的参数重配置动作，因此不会把其能力边界当成算法优势；按四类故障分别报告动作前导航结果。', '']
    lines += ['## 5. 跨场景静态几何审计与边界', '']
    if geometry:
        route = geometry.get('route', {})
        world = geometry.get('world', {})
        lines += [
            f'- 静态检查通过：`{geometry.get("static_checks_pass")}`；起点栅格值 `{route.get("start_pixel_value")}`，目标栅格值 `{route.get("goal_pixel_value")}`。',
            f'- 允许未知区域时栅格路径存在 `{route.get("grid_path_allow_unknown_true_exists")}`；禁止未知区域时存在 `{route.get("grid_path_allow_unknown_false_exists")}`；占据像素差异 `{world.get("occupied_pixel_mismatch_count_vs_box_geometry", "—")}`。',
            '- 该审计只证明地图与 world 静态一致性/栅格连通性，不能替代 B 组真实 ROS/Nav2 normal-nav、故障注入、在线证据、回滚及恢复 pilot。',
        ]
    else:
        lines.append('- 静态几何审计缺失；需补充后再归档。')
    lines += ['', '## 6. 解释约束与局限', '',
              '- 若强规则追平或优于 Frozen M50，结论应是本实验没有证明经验模型在这些明显可读故障上优于充分知情规则；不能把原实验中的策略变化等同于必要性。',
              '- Planner 的故障态行为与异常配置修复分开呈现；故障读数异常本身不等于从真实导航失败中恢复。',
              '- 结果只支持本协议覆盖的场景、地图/路线、故障实例与强度；不把一个迁移地图或特定 seed 外推成普遍鲁棒性。',
              '- 对 Nav2 BT 只报告可核验的树结构和动作前导航结果；没有行为树执行 trace 时，不声称某个恢复节点被执行。',
              '']
    if a_completion_audit and a_source_correction:
        if a_source_correction.get('exact_frozen_matrix_source_recovered') is False:
            lines += [
                '### A 组调度脚本来源说明', '',
                f'- A 组数据完整性审计为 {a_completion_audit.get("observed_valid_cells", "—")}/{a_completion_audit.get("expected_valid_cells", "—")} 个有效 cell、{a_completion_audit.get("observed_valid_episodes", "—")} 个有效 episode；该审计判断数据完整性独立于调度脚本来源问题。',
                f'- A 冻结记录中的调度脚本 SHA-256 为 `{a_source_correction.get("frozen_protocol_sha256", "未登记")}`；可用执行快照 SHA-256 为 `{a_source_correction.get("available_A_execution_snapshot_sha256", "未登记")}`。精确的冻结前调度脚本无法从现存文件或 Git 历史恢复；{a_source_correction.get("other_source_count", "—")} 项其他方法/运行/配置来源文件与冻结记录匹配。',
                '- 因此，A 组可以复核方法、动作、seed、cell 参数及原始数据，但不能声称调度器的逐字节版本已完全复现；来源更正记录中说明了该限制。',
                '',
            ]
    lines += ['## 7. 可复核文件', '',
              '- A 原始强规则记录：`results/supplementary_original_strong_rule/`。',
              '- B 原始记录：`results/supplementary_transfer_static_m0/`、`results/supplementary_transfer_m50/`、`results/supplementary_transfer_strong_rule/`。',
              '- 冻结协议：`results/supplementary_protocol_A_v1.json`、`results/supplementary_protocol_B_v1.json`。',
              '- 汇总与排除清单：`results/supplementary_A_aggregate.json`、`results/supplementary_B_aggregate.json`。',
              '- 原评估只读审计：`results/supplementary_original_audit.md`、`results/supplementary_original_audit.json`。',
              '- A 来源更正及快照：`results/supplementary_A_source_provenance_correction_01.json`、`results/supplementary_A_source_snapshot/manifest.json`。',
              '- Nav2 BT 与 transfer 几何审计：`results/supplementary_nav2_bt_audit.json`、`results/supplementary_transfer_geometry_audit.json`。',
              '- SHA-256 记录位于协议、汇总及各审计 JSON。', '']
    return '\n'.join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=OUT)
    args = parser.parse_args()
    a, b = load(A_PATH), load(B_PATH)
    a_protocol, b_protocol = load(A_PROTOCOL), load(B_PROTOCOL)
    geometry = load(GEOMETRY_AUDIT) if GEOMETRY_AUDIT.exists() else None
    original_audit = load(ORIGINAL_AUDIT)
    a_completion_audit = load(A_COMPLETION_AUDIT)
    a_source_correction = load(A_SOURCE_CORRECTION)
    report = render_report(
        a, b, a_protocol, b_protocol, geometry,
        original_audit, a_completion_audit, a_source_correction,
    )
    args.output.write_text(report)
    print(args.output)


if __name__ == '__main__':
    main()
