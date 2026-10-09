#!/usr/bin/env python3
"""Analyze frozen transfer-scene M0/M50/strong-rule cells.

The B protocol is written only after the engineering pilot passes.  This
analyzer reads that frozen manifest, selects protocol-valid cells, pairs by
seed/fault family/repetition ID, and keeps the Nav2 pre-action navigation
reference separate from post-intervention recovery.
"""
from __future__ import annotations

import hashlib
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / 'results/supplementary_protocol_B_v1.json'
BT_AUDIT = ROOT / 'results/supplementary_nav2_bt_audit.json'
OUT = ROOT / 'results/supplementary_B_aggregate.json'
FAMILIES = ('localization', 'costmap', 'planner', 'control')
COMPARISONS = (
    ('frozen_m50', 'strong_rule'),
    ('frozen_m50', 'static_m0'),
    ('strong_rule', 'static_m0'),
)


def valid_record(path: Path, *, method: dict, method_id: str, seed: int,
                 family: str, expected: dict) -> tuple[dict, list[dict]] | None:
    try:
        record = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    rows = record.get('episodes', [])
    if record.get('protocol_compliant') is not True:
        return None
    if record.get('infrastructure_failure') is True:
        return None
    if record.get('baseline') != method['baseline'] or record.get('seed') != seed:
        return None
    if len(rows) != int(expected['fault_repetitions']):
        return None
    if any(row.get('fault_family') != family or row.get('episode_evidence_valid') is not True for row in rows):
        return None
    if record.get('experience_checkpoint') != method['experience_checkpoint']:
        return None
    if record.get('experience_snapshot_sha256') != method.get('experience_snapshot_sha256'):
        return None
    if record.get('experience_snapshot_path') != method.get('experience_snapshot_path'):
        return None
    for key in (
        'actual_map_id', 'experience_environment_bin', 'experience_prior_mode',
        'use_belief_action_scope', 'online_experience_update',
        'resume_experience_state', 'fault_repetitions', 'fault_scale', 'goal',
        'initial_pose',
    ):
        if record.get(key) != expected.get(key):
            return None
    return record, rows


def select_cells(protocol: dict) -> tuple[dict, list[dict]]:
    seeds = protocol['seeds']
    expected = protocol['expected_run']
    methods = protocol['methods']
    selected: dict[tuple[str, int, str], dict] = {}
    excluded: list[dict] = []

    for method_id, method in methods.items():
        result_dir = ROOT / method['result_dir']
        baseline = method['baseline']
        for seed in seeds:
            for family in FAMILIES:
                paths = sorted(result_dir.glob(f'phase3_gazebo_{baseline}_{seed}_*.json'))
                accepted = []
                for path in paths:
                    try:
                        candidate = json.loads(path.read_text())
                        eps = candidate.get('episodes', [])
                        candidate_family = eps[0].get('fault_family') if eps else None
                    except (OSError, ValueError, IndexError):
                        excluded.append({
                            'path': str(path.relative_to(ROOT)),
                            'reason': 'malformed_or_unreadable_json',
                        })
                        continue
                    if candidate_family != family:
                        continue
                    result = valid_record(
                        path, method=method, method_id=method_id, seed=seed,
                        family=family, expected=expected,
                    )
                    if result is None:
                        excluded.append({
                            'path': str(path.relative_to(ROOT)),
                            'reason': 'protocol_invalid_or_metadata_mismatch',
                            'protocol_compliant': candidate.get('protocol_compliant'),
                            'protocol_gaps': candidate.get('protocol_gaps', []),
                        })
                    else:
                        accepted.append((path, *result))
                if not accepted:
                    raise ValueError(f'missing valid B cell: {(method_id, seed, family)}')
                path, record, rows = accepted[0]
                selected[(method_id, seed, family)] = {
                    'path': str(path.relative_to(ROOT)), 'record': record,
                    'rows': rows,
                }
                for extra, _, _ in accepted[1:]:
                    excluded.append({
                        'path': str(extra.relative_to(ROOT)),
                        'reason': 'extra_valid_attempt_not_selected',
                    })

        manual_log = result_dir / 'invalid_attempts.jsonl'
        if manual_log.exists():
            for line_no, line in enumerate(manual_log.read_text().splitlines(), 1):
                if not line.strip():
                    continue
                try:
                    attempt = json.loads(line)
                except ValueError:
                    excluded.append({'path': str(manual_log.relative_to(ROOT)), 'line': line_no,
                                     'reason': 'invalid_manual_attempt_log_json'})
                    continue
                excluded.append({
                    'path': str(manual_log.relative_to(ROOT)), 'line': line_no,
                    'reason': attempt.get('reason', attempt.get('attempt_status', 'manually_logged_attempt')),
                    'attempt': attempt,
                })

    return selected, excluded


def seed_bootstrap(values: dict[int, float], *, draws: int = 10000, salt: int = 0) -> dict:
    seeds = sorted(values)
    if not seeds:
        return {'mean_difference': None, 'ci95': None, 'positive_seeds': 0,
                'negative_seeds': 0, 'zero_seeds': 0, 'seed_differences': {}}
    observed = sum(values.values()) / len(seeds)
    rng = random.Random(20261008 + salt)
    samples = sorted(sum(values[rng.choice(seeds)] for _ in seeds) / len(seeds) for _ in range(draws))
    return {
        'mean_difference': observed,
        'ci95': [samples[int(.025 * draws)], samples[int(.975 * draws) - 1]],
        'positive_seeds': sum(value > 0 for value in values.values()),
        'negative_seeds': sum(value < 0 for value in values.values()),
        'zero_seeds': sum(value == 0 for value in values.values()),
        'seed_differences': values,
    }


def episode_rate(rows: list[dict], field: str) -> float | None:
    return sum(bool(row.get(field)) for row in rows) / len(rows) if rows else None


def intervention_cost_mean(rows: list[dict]) -> float:
    return sum(float(row.get('intervention_cost') or 0.0) for row in rows) / len(rows) if rows else 0.0


def flatten_evidence(value: dict, prefix: str = '') -> dict[str, object]:
    """Flatten evidence paths to show which fields differ between paired methods."""
    flattened = {}
    for key, item in value.items():
        path = f'{prefix}.{key}' if prefix else key
        if isinstance(item, dict):
            flattened.update(flatten_evidence(item, path))
        else:
            flattened[path] = item
    return flattened


def summarize_method_family(rows: list[dict], method_id: str) -> dict:
    failed = [row for row in rows if row.get('fault_behavior_observed') is True]
    action_time = [
        row['time_to_recovery_sec'] for row in rows
        if row.get('recovery_success') is True and row.get('time_to_recovery_sec') is not None
    ]
    action_counts = Counter(str(row.get('selected_action')) for row in rows)
    result = {
        'episode_count': len(rows),
        'pre_action_nav2_status_counts': dict(Counter(str(row.get('fault_navigation_status')) for row in rows)),
        'pre_action_nav2_success_count': sum(row.get('fault_navigation_status') == 4 for row in rows),
        'pre_action_nav2_success_rate': episode_rate(
            [{'ok': row.get('fault_navigation_status') == 4} for row in rows], 'ok'),
        'behavior_failed_count': len(failed),
        'strict_joint_success_count': sum(bool(row.get('episode_success')) for row in rows),
        'strict_joint_success_rate': episode_rate(rows, 'episode_success'),
        # Configuration repair/action execution is intentionally separate
        # from a successful independent navigation after the intervention.
        'repair_action_success_count': sum(bool(row.get('recovery_success')) for row in rows),
        'behavior_failed_repair_action_count': sum(bool(row.get('recovery_success')) for row in failed),
        'behavior_failed_repair_action_rate': episode_rate(failed, 'recovery_success'),
        'behavior_failed_strict_recovery_count': sum(bool(row.get('episode_success')) for row in failed),
        'behavior_failed_strict_recovery_rate': episode_rate(failed, 'episode_success'),
        'post_action_nav2_status_counts': dict(Counter(str(row.get('recovery_navigation_status')) for row in rows)),
        'post_action_nav2_success_count': sum(row.get('recovery_navigation_status') == 4 for row in rows),
        'intervention_cost_mean_all_episodes': (
            sum(float(row.get('intervention_cost') or 0.0) for row in rows) / len(rows) if rows else None
        ),
        'successful_recovery_mttr_mean_sec': sum(action_time) / len(action_time) if action_time else None,
        'successful_recovery_mttr_n': len(action_time),
        'selected_action_counts': dict(action_counts),
        'decision_reason_counts': dict(Counter(
            str((row.get('decision') or {}).get('reason')) for row in rows
        )) if method_id == 'strong_rule' else {},
    }
    return result


def summarize(protocol: dict, selected: dict) -> dict:
    seeds = protocol['seeds']
    method_ids = tuple(protocol['methods'])
    family_metrics = {}
    for method_id in method_ids:
        family_metrics[method_id] = {}
        for family in FAMILIES:
            rows = [
                row for seed in seeds
                for row in selected[(method_id, seed, family)]['rows']
            ]
            family_metrics[method_id][family] = summarize_method_family(rows, method_id)

    paired = {}
    for comparison_index, (left, right) in enumerate(COMPARISONS):
        if left not in protocol['methods'] or right not in protocol['methods']:
            continue
        by_family = {}
        overall_seed_differences = {}
        overall_seed_cost_differences = {}
        for family_index, family in enumerate(FAMILIES):
            seed_differences = {}
            seed_cost_differences = {}
            common_failed = Counter()
            common_failure_by_seed = defaultdict(Counter)
            mechanisms = Counter()
            evidence_field_mismatches = Counter()
            amcl_distance_abs_deltas = []
            amcl_threshold_state_pairs = Counter()
            lifecycle_anomaly_predicate_pairs = Counter()
            planner_lifecycle_non_normal_counts = Counter()
            action_pairs = Counter()
            cross_rank_sums = Counter()
            cross_rank_counts = Counter()
            for seed in seeds:
                left_rows = selected[(left, seed, family)]['rows']
                right_rows = selected[(right, seed, family)]['rows']
                for a, b in zip(left_rows, right_rows, strict=True):
                    if (a.get('fault_id'), a.get('episode_id')) != (b.get('fault_id'), b.get('episode_id')):
                        raise ValueError(f'B methods not paired by fault/episode ID: {(left, right, seed, family)}')
                    mechanisms['episode_pairs'] += 1
                    a_evidence = a.get('online_evidence') or {}
                    b_evidence = b.get('online_evidence') or {}
                    mechanisms['same_online_evidence'] += a_evidence == b_evidence
                    a_flat = flatten_evidence(a_evidence)
                    b_flat = flatten_evidence(b_evidence)
                    mechanisms['same_online_evidence_schema'] += set(a_flat) == set(b_flat)
                    a_parameters = a_evidence.get('nav2_parameters')
                    b_parameters = b_evidence.get('nav2_parameters')
                    mechanisms['same_nav2_parameter_readbacks'] += (
                        isinstance(a_parameters, dict) and isinstance(b_parameters, dict)
                        and a_parameters == b_parameters
                    )
                    mechanisms['same_amcl_status_flags'] += all(
                        key in a_evidence and key in b_evidence and a_evidence[key] == b_evidence[key]
                        for key in ('amcl_available', 'amcl_fresh_after_injection')
                    )
                    for field in set(a_flat) | set(b_flat):
                        if a_flat.get(field, '<missing>') != b_flat.get(field, '<missing>'):
                            evidence_field_mismatches[field] += 1
                    a_distance = a_evidence.get('amcl_distance_to_start_m')
                    b_distance = b_evidence.get('amcl_distance_to_start_m')
                    if isinstance(a_distance, (int, float)) and isinstance(b_distance, (int, float)):
                        amcl_distance_abs_deltas.append(abs(float(a_distance) - float(b_distance)))
                        a_distance_state = float(a_distance) > 0.35
                        b_distance_state = float(b_distance) > 0.35
                        amcl_threshold_state_pairs['n'] += 1
                        amcl_threshold_state_pairs['same'] += a_distance_state == b_distance_state
                    else:
                        amcl_threshold_state_pairs['unknown_pairs'] += 1
                    a_lifecycle_anomaly = a_evidence.get('planner_lifecycle_state_id') not in (None, 3)
                    b_lifecycle_anomaly = b_evidence.get('planner_lifecycle_state_id') not in (None, 3)
                    lifecycle_anomaly_predicate_pairs['n'] += 1
                    lifecycle_anomaly_predicate_pairs['same'] += a_lifecycle_anomaly == b_lifecycle_anomaly
                    for side, evidence in (('left', a_evidence), ('right', b_evidence)):
                        state = evidence.get('planner_lifecycle_state_id')
                        if state not in (None, 3):
                            planner_lifecycle_non_normal_counts[side] += 1
                    mechanisms['same_belief'] += a.get('belief_before_action') == b.get('belief_before_action')
                    a_rank = (a.get('decision') or {}).get('ranking', [])
                    b_rank = (b.get('decision') or {}).get('ranking', [])
                    a_ids = [item.get('action_id') for item in a_rank]
                    b_ids = [item.get('action_id') for item in b_rank]
                    mechanisms['same_candidate_set'] += set(a_ids) == set(b_ids)
                    mechanisms['same_candidate_order'] += a_ids == b_ids
                    left_action = a.get('selected_action')
                    right_action = b.get('selected_action')
                    mechanisms['different_action'] += left_action != right_action
                    action_pairs[f'{left_action or "<none>"} -> {right_action or "<none>"}'] += 1
                    a_ranks = {item.get('action_id'): index + 1 for index, item in enumerate(a_rank)}
                    b_ranks = {item.get('action_id'): index + 1 for index, item in enumerate(b_rank)}
                    if left_action in b_ranks:
                        cross_rank_sums['left_action_in_right_ranking'] += b_ranks[left_action]
                        cross_rank_counts['left_action_in_right_ranking'] += 1
                    if right_action in a_ranks:
                        cross_rank_sums['right_action_in_left_ranking'] += a_ranks[right_action]
                        cross_rank_counts['right_action_in_left_ranking'] += 1
                    if a.get('fault_behavior_observed') is True and b.get('fault_behavior_observed') is True:
                        common_failed['episode_pairs'] += 1
                        common_failed['left_strict_success'] += bool(a.get('episode_success'))
                        common_failed['right_strict_success'] += bool(b.get('episode_success'))
                        common_failed['left_repair_action_success'] += bool(a.get('recovery_success'))
                        common_failed['right_repair_action_success'] += bool(b.get('recovery_success'))
                        common_failure_by_seed[seed]['n'] += 1
                        common_failure_by_seed[seed]['difference_sum'] += (
                            int(bool(a.get('episode_success'))) - int(bool(b.get('episode_success')))
                        )
                        common_failure_by_seed[seed]['repair_action_difference_sum'] += (
                            int(bool(a.get('recovery_success'))) - int(bool(b.get('recovery_success')))
                        )
                a_rate = sum(bool(row.get('episode_success')) for row in left_rows) / len(left_rows)
                b_rate = sum(bool(row.get('episode_success')) for row in right_rows) / len(right_rows)
                seed_differences[seed] = a_rate - b_rate
                seed_cost_differences[seed] = intervention_cost_mean(left_rows) - intervention_cost_mean(right_rows)

            common_seed_differences = {
                seed: value['difference_sum'] / value['n']
                for seed, value in common_failure_by_seed.items() if value['n']
            }
            common_repair_action_seed_differences = {
                seed: value['repair_action_difference_sum'] / value['n']
                for seed, value in common_failure_by_seed.items() if value['n']
            }
            by_family[family] = {
                'strict_joint_success_left_minus_right': seed_bootstrap(seed_differences, salt=100 * comparison_index + family_index),
                'intervention_cost_mean_left_minus_right': seed_bootstrap(seed_cost_differences, salt=200 * comparison_index + family_index),
                'common_behavior_failure_pairs': {
                    'pair_count': common_failed['episode_pairs'],
                    'left_strict_success_count': common_failed['left_strict_success'],
                    'right_strict_success_count': common_failed['right_strict_success'],
                    'left_rate': common_failed['left_strict_success'] / common_failed['episode_pairs'] if common_failed['episode_pairs'] else None,
                    'right_rate': common_failed['right_strict_success'] / common_failed['episode_pairs'] if common_failed['episode_pairs'] else None,
                    'seed_cluster_left_minus_right': seed_bootstrap(common_seed_differences, salt=1000 + 100 * comparison_index + family_index),
                },
                'common_behavior_failure_repair_action_pairs': {
                    'pair_count': common_failed['episode_pairs'],
                    'left_repair_action_success_count': common_failed['left_repair_action_success'],
                    'right_repair_action_success_count': common_failed['right_repair_action_success'],
                    'left_rate': common_failed['left_repair_action_success'] / common_failed['episode_pairs'] if common_failed['episode_pairs'] else None,
                    'right_rate': common_failed['right_repair_action_success'] / common_failed['episode_pairs'] if common_failed['episode_pairs'] else None,
                    'seed_cluster_left_minus_right': seed_bootstrap(common_repair_action_seed_differences, salt=2000 + 100 * comparison_index + family_index),
                },
                'mechanism': {
                    **dict(mechanisms),
                    'action_pair_counts': dict(action_pairs),
                    'same_candidate_set_rate': mechanisms['same_candidate_set'] / mechanisms['episode_pairs'] if mechanisms['episode_pairs'] else None,
                    'same_candidate_order_rate': mechanisms['same_candidate_order'] / mechanisms['episode_pairs'] if mechanisms['episode_pairs'] else None,
                    'same_belief_rate': mechanisms['same_belief'] / mechanisms['episode_pairs'] if mechanisms['episode_pairs'] else None,
                    'same_online_evidence_rate': mechanisms['same_online_evidence'] / mechanisms['episode_pairs'] if mechanisms['episode_pairs'] else None,
                    'same_online_evidence_schema_rate': mechanisms['same_online_evidence_schema'] / mechanisms['episode_pairs'] if mechanisms['episode_pairs'] else None,
                    'same_nav2_parameter_readbacks_rate': mechanisms['same_nav2_parameter_readbacks'] / mechanisms['episode_pairs'] if mechanisms['episode_pairs'] else None,
                    'same_amcl_status_flags_rate': mechanisms['same_amcl_status_flags'] / mechanisms['episode_pairs'] if mechanisms['episode_pairs'] else None,
                    'online_evidence_field_mismatch_counts': dict(evidence_field_mismatches),
                    'planner_lifecycle_non_normal_counts': dict(planner_lifecycle_non_normal_counts),
                    'amcl_distance_abs_delta_m': {
                        'n': len(amcl_distance_abs_deltas),
                        'mean': sum(amcl_distance_abs_deltas) / len(amcl_distance_abs_deltas) if amcl_distance_abs_deltas else None,
                        'max': max(amcl_distance_abs_deltas) if amcl_distance_abs_deltas else None,
                    },
                    'same_amcl_distance_threshold_state': {
                        'n': amcl_threshold_state_pairs['n'],
                        'same': amcl_threshold_state_pairs['same'],
                        'rate': amcl_threshold_state_pairs['same'] / amcl_threshold_state_pairs['n'] if amcl_threshold_state_pairs['n'] else None,
                        'unknown_pairs': amcl_threshold_state_pairs['unknown_pairs'],
                        'threshold_m': 0.35,
                    },
                    'same_planner_lifecycle_anomaly_predicate_rate': (
                        lifecycle_anomaly_predicate_pairs['same'] / lifecycle_anomaly_predicate_pairs['n']
                        if lifecycle_anomaly_predicate_pairs['n'] else None
                    ),
                    'mean_left_action_rank_in_right_ranking': (
                        cross_rank_sums['left_action_in_right_ranking'] / cross_rank_counts['left_action_in_right_ranking']
                        if cross_rank_counts['left_action_in_right_ranking'] else None
                    ),
                    'mean_right_action_rank_in_left_ranking': (
                        cross_rank_sums['right_action_in_left_ranking'] / cross_rank_counts['right_action_in_left_ranking']
                        if cross_rank_counts['right_action_in_left_ranking'] else None
                    ),
                    'cross_rank_denominators': dict(cross_rank_counts),
                },
            }

        for seed in seeds:
            left_success = sum(
                bool(row.get('episode_success'))
                for family in FAMILIES
                for row in selected[(left, seed, family)]['rows']
            ) / (len(FAMILIES) * int(protocol['expected_run']['fault_repetitions']))
            right_success = sum(
                bool(row.get('episode_success'))
                for family in FAMILIES
                for row in selected[(right, seed, family)]['rows']
            ) / (len(FAMILIES) * int(protocol['expected_run']['fault_repetitions']))
            overall_seed_differences[seed] = left_success - right_success
            left_costs = [
                row for family in FAMILIES
                for row in selected[(left, seed, family)]['rows']
            ]
            right_costs = [
                row for family in FAMILIES
                for row in selected[(right, seed, family)]['rows']
            ]
            overall_seed_cost_differences[seed] = intervention_cost_mean(left_costs) - intervention_cost_mean(right_costs)
        paired[f'{left}_minus_{right}'] = {
            'overall_strict_joint_success': seed_bootstrap(overall_seed_differences, salt=comparison_index),
            'overall_intervention_cost_mean_left_minus_right': seed_bootstrap(overall_seed_cost_differences, salt=10 + comparison_index),
            'family_details': by_family,
        }

    try:
        bt_audit = json.loads(BT_AUDIT.read_text())
    except (OSError, ValueError):
        bt_audit = {'audit_missing': True}
    return {
        'protocol_id': protocol['protocol_id'],
        'protocol_sha256': hashlib.sha256(PROTOCOL.read_bytes()).hexdigest(),
        'seed_count': len(seeds),
        'family_count': len(FAMILIES),
        'method_family': family_metrics,
        'paired': paired,
        'nav2_engineering_reference': {
            'bt_audit': bt_audit,
            'interpretation': 'faulted pre-action NavigateToPose is a Nav2 engineering reference, not an equal-action algorithm baseline',
            'executed_tree_nodes_inferred_from_status_alone': False,
        },
        'selected_cells': [
            {'method': method_id, 'seed': seed, 'fault_family': family,
             'path': selected[(method_id, seed, family)]['path']}
            for method_id in method_ids for seed in seeds for family in FAMILIES
        ],
    }


def main() -> None:
    protocol = json.loads(PROTOCOL.read_text())
    if protocol.get('protocol_id') != 'eacr_supplementary_B_v1':
        raise ValueError('wrong or missing frozen B protocol')
    expected_methods = {
        'static_m0': 'eacr_static',
        'frozen_m50': 'eacr_evolving',
        'strong_rule': 'eacr_strong_rule',
    }
    actual_methods = {key: value.get('baseline') for key, value in protocol.get('methods', {}).items()}
    if actual_methods != expected_methods:
        raise ValueError(f'wrong B method mapping: {actual_methods}')
    if len(protocol.get('seeds', [])) != 10 or len(set(protocol['seeds'])) != 10:
        raise ValueError('B protocol must contain exactly 10 unique frozen seeds')
    if int(protocol.get('expected_run', {}).get('fault_repetitions', 0)) != 4:
        raise ValueError('B protocol must preserve four repeats per cell')
    selected, excluded = select_cells(protocol)
    result = summarize(protocol, selected)
    result['excluded_attempts'] = excluded
    result['analysis_script_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(OUT)


if __name__ == '__main__':
    main()
