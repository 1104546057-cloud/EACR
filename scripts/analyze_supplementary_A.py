#!/usr/bin/env python3
"""Analyze frozen supplementary A cells paired to selected original Static/M50 cells."""
from __future__ import annotations

import hashlib
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / 'results/supplementary_protocol_A_v1.json'
ORIGINAL = ROOT / 'results/phase4_final_aggregate.json'
NEW_DIR = ROOT / 'results/supplementary_original_strong_rule'
OUT = ROOT / 'results/supplementary_A_aggregate.json'
FAMILIES = ('localization', 'costmap', 'planner', 'control')
METHODS = ('eacr_static_m0', 'eacr_evolving_m50', 'eacr_strong_rule')


def load_valid(path: Path, seed: int, family: str, baseline: str | None = None) -> list[dict] | None:
    try:
        record = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    rows = record.get('episodes', [])
    if record.get('protocol_compliant') is not True or record.get('seed') != seed:
        return None
    if baseline is not None and record.get('baseline') != baseline:
        return None
    if len(rows) != 4 or any(r.get('fault_family') != family or r.get('episode_evidence_valid') is not True for r in rows):
        return None
    return rows


def select() -> tuple[dict, dict]:
    protocol = json.loads(PROTOCOL.read_text())
    if protocol['protocol_id'] != 'eacr_supplementary_A_v1':
        raise ValueError('wrong protocol')
    aggregate = json.loads(ORIGINAL.read_text())
    if hashlib.sha256(ORIGINAL.read_bytes()).hexdigest() != protocol['original_aggregate_sha256']:
        raise ValueError('original aggregate changed')
    original = {(c['method'], c['seed'], c['fault_family']): c['path']
                for c in aggregate['cell_metrics']}
    selected = {}
    excluded = []
    malformed_paths = set()
    for method in METHODS:
        for seed in protocol['seeds']:
            for family in FAMILIES:
                key = (method, seed, family)
                if method != 'eacr_strong_rule':
                    p = ROOT / original[key]
                    rows = load_valid(p, seed, family)
                    if rows is None:
                        raise ValueError(f'original selected record invalid: {p}')
                    selected[key] = {'path': str(p.relative_to(ROOT)), 'rows': rows}
                else:
                    paths = sorted(NEW_DIR.glob(f'phase3_gazebo_eacr_strong_rule_{seed}_*.json'))
                    accepted = []
                    for p in paths:
                        try:
                            candidate = json.loads(p.read_text())
                            candidate_family = candidate.get('episodes', [{}])[0].get('fault_family')
                        except (OSError, ValueError, IndexError):
                            if p not in malformed_paths:
                                excluded.append({
                                    'path': str(p.relative_to(ROOT)),
                                    'reason': 'malformed_or_unreadable_json',
                                })
                                malformed_paths.add(p)
                            continue
                        if candidate_family != family:
                            continue
                        rows = load_valid(p, seed, family, method)
                        if rows is not None:
                            accepted.append((p, rows))
                        else:
                            invalid_rows = [
                                {
                                    'episode_id': row.get('episode_id'),
                                    'episode_evidence_valid': row.get('episode_evidence_valid'),
                                    'nominal_reset_success': row.get('nominal_reset_success'),
                                    'nominal_navigation_valid': row.get('nominal_navigation_valid'),
                                    'inject_success': row.get('inject_success'),
                                    'fault_effect_observed': row.get('fault_effect_observed'),
                                    'rollback_success': row.get('rollback_success'),
                                }
                                for row in candidate.get('episodes', [])
                                if row.get('episode_evidence_valid') is not True
                            ]
                            excluded.append({
                                'path': str(p.relative_to(ROOT)),
                                'reason': 'protocol_invalid_or_incomplete',
                                'protocol_compliant': candidate.get('protocol_compliant'),
                                'protocol_gaps': candidate.get('protocol_gaps', []),
                                'invalid_episodes': invalid_rows,
                            })
                    if not accepted:
                        raise ValueError(f'missing valid A cell {key}')
                    p, rows = accepted[0]
                    selected[key] = {'path': str(p.relative_to(ROOT)), 'rows': rows}
                    for extra, _ in accepted[1:]:
                        excluded.append({'path': str(extra.relative_to(ROOT)), 'reason': 'extra_valid_attempt_not_selected'})
    manual_attempt_log = NEW_DIR / 'invalid_attempts.jsonl'
    if manual_attempt_log.exists():
        for line_number, line in enumerate(manual_attempt_log.read_text().splitlines(), start=1):
            if not line.strip():
                continue
            try:
                attempt = json.loads(line)
            except ValueError:
                excluded.append({
                    'path': str(manual_attempt_log.relative_to(ROOT)),
                    'line': line_number,
                    'reason': 'invalid_manual_attempt_log_json',
                })
                continue
            excluded.append({
                'path': str(manual_attempt_log.relative_to(ROOT)),
                'line': line_number,
                'reason': attempt.get('reason', attempt.get('attempt_status', 'manually_logged_incomplete_attempt')),
                'attempt': attempt,
            })
    return selected, {'excluded': excluded, 'protocol': protocol}


def ci_seed_bootstrap(values: dict[int, float], *, draws: int = 10000) -> dict:
    seeds = sorted(values)
    observed = sum(values.values()) / len(seeds)
    rng = random.Random(20261008)
    samples = sorted(sum(values[rng.choice(seeds)] for _ in seeds) / len(seeds) for _ in range(draws))
    return {'mean_difference': observed, 'ci95': [samples[int(.025 * draws)], samples[int(.975 * draws) - 1]],
            'positive_seeds': sum(v > 0 for v in values.values()),
            'negative_seeds': sum(v < 0 for v in values.values()),
            'zero_seeds': sum(v == 0 for v in values.values()),
            'seed_differences': values}


def intervention_cost_mean(rows: list[dict]) -> float:
    return sum(float(row.get('intervention_cost') or 0.0) for row in rows) / len(rows) if rows else 0.0


def flatten_evidence(value: dict, prefix: str = '') -> dict[str, object]:
    """Flatten evidence paths so exact value mismatches can be attributed."""
    flattened = {}
    for key, item in value.items():
        path = f'{prefix}.{key}' if prefix else key
        if isinstance(item, dict):
            flattened.update(flatten_evidence(item, path))
        else:
            flattened[path] = item
    return flattened


def summarize(selected: dict, protocol: dict) -> dict:
    seeds = protocol['seeds']
    by_method_family = defaultdict(dict)
    for method in METHODS:
        for family in FAMILIES:
            rows = [r for seed in seeds for r in selected[(method, seed, family)]['rows']]
            failed = [r for r in rows if r.get('fault_behavior_observed') is True]
            recovery_times = [r['time_to_recovery_sec'] for r in rows if r.get('recovery_success') and r.get('time_to_recovery_sec') is not None]
            by_method_family[method][family] = {
                'episodes': len(rows), 'fault_navigation_status_counts': dict(Counter(str(r.get('fault_navigation_status')) for r in rows)),
                'pre_action_nav_success': sum(r.get('fault_navigation_status') == 4 for r in rows),
                'pre_action_nav_success_rate': sum(r.get('fault_navigation_status') == 4 for r in rows) / len(rows),
                'behavior_failed': len(failed),
                'strict_joint_success': sum(bool(r.get('episode_success')) for r in rows),
                'strict_joint_success_rate': sum(bool(r.get('episode_success')) for r in rows) / len(rows),
                'intervention_recovery': sum(bool(r.get('recovery_success')) for r in rows),
                # A successful rollback/reconfiguration only proves that the
                # configuration action ran.  Count it separately from the
                # actual end-to-end recovery, which also requires the
                # independent post-action navigation to succeed.
                'behavior_failed_recovery_action_count': sum(bool(r.get('recovery_success')) for r in failed),
                'behavior_failed_recovery_action_rate': (
                    sum(bool(r.get('recovery_success')) for r in failed) / len(failed)
                    if failed else None
                ),
                'behavior_failed_strict_recovery_count': sum(bool(r.get('episode_success')) for r in failed),
                'behavior_failed_strict_recovery_rate': (
                    sum(bool(r.get('episode_success')) for r in failed) / len(failed)
                    if failed else None
                ),
                'intervention_cost_mean': sum(float(r.get('intervention_cost') or 0) for r in rows) / len(rows),
                'success_conditional_mttr_mean_sec': sum(recovery_times) / len(recovery_times) if recovery_times else None,
                'success_conditional_mttr_n': len(recovery_times),
                'action_counts': dict(Counter(str(r.get('selected_action')) for r in rows)),
                'rule_reason_counts': dict(Counter(str((r.get('decision') or {}).get('reason')) for r in rows)) if method == 'eacr_strong_rule' else {},
            }
    paired = {}
    for left, right in (('eacr_evolving_m50', 'eacr_strong_rule'), ('eacr_evolving_m50', 'eacr_static_m0'), ('eacr_strong_rule', 'eacr_static_m0')):
        seed_diff = {}
        seed_cost_diff = {}
        by_family = {}
        for family in FAMILIES:
            signs = Counter()
            mechanism = Counter()
            common_failure_by_seed = defaultdict(lambda: Counter())
            family_seed_diff = {}
            family_seed_cost_diff = {}
            action_pairs = Counter()
            selected_rank_sums = Counter()
            selected_rank_counts = Counter()
            evidence_field_mismatches = Counter()
            amcl_distance_abs_deltas = []
            amcl_threshold_state_pairs = Counter()
            lifecycle_anomaly_predicate_pairs = Counter()
            lifecycle_non_normal_counts = Counter()
            for seed in seeds:
                lr = selected[(left, seed, family)]['rows']
                rr = selected[(right, seed, family)]['rows']
                family_seed_diff[seed] = (
                    sum(bool(r.get('episode_success')) for r in lr) / len(lr)
                    - sum(bool(r.get('episode_success')) for r in rr) / len(rr)
                )
                family_seed_cost_diff[seed] = intervention_cost_mean(lr) - intervention_cost_mean(rr)
                for a, b in zip(lr, rr, strict=True):
                    if (a.get('fault_id'), a.get('episode_id')) != (b.get('fault_id'), b.get('episode_id')):
                        raise ValueError(f'fault sequence differs: {left}/{right}/{seed}/{family}')
                    mechanism['paired_episodes'] += 1
                    mechanism['same_belief'] += a.get('belief_before_action') == b.get('belief_before_action')
                    a_evidence = a.get('online_evidence') or {}
                    b_evidence = b.get('online_evidence') or {}
                    mechanism['same_online_evidence'] += a_evidence == b_evidence
                    a_flat = flatten_evidence(a_evidence)
                    b_flat = flatten_evidence(b_evidence)
                    mechanism['same_online_evidence_schema'] += set(a_flat) == set(b_flat)
                    a_parameters = a_evidence.get('nav2_parameters')
                    b_parameters = b_evidence.get('nav2_parameters')
                    mechanism['same_nav2_parameter_readbacks'] += (
                        isinstance(a_parameters, dict) and isinstance(b_parameters, dict)
                        and a_parameters == b_parameters
                    )
                    amcl_keys = ('amcl_available', 'amcl_fresh_after_injection')
                    mechanism['same_amcl_status_flags'] += all(
                        key in a_evidence and key in b_evidence and a_evidence[key] == b_evidence[key]
                        for key in amcl_keys
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
                            lifecycle_non_normal_counts[side] += 1
                    a_ranking = (a.get('decision') or {}).get('ranking', [])
                    b_ranking = (b.get('decision') or {}).get('ranking', [])
                    ac = {x['action_id'] for x in a_ranking}
                    bc = {x['action_id'] for x in b_ranking}
                    mechanism['same_candidates'] += ac == bc
                    left_action, right_action = a.get('selected_action'), b.get('selected_action')
                    mechanism['different_action'] += left_action != right_action
                    action_pairs[f'{left_action or "<none>"} -> {right_action or "<none>"}'] += 1
                    a_rank = {row['action_id']: index + 1 for index, row in enumerate(a_ranking)}
                    b_rank = {row['action_id']: index + 1 for index, row in enumerate(b_ranking)}
                    if left_action in b_rank:
                        selected_rank_sums['left_action_in_right_ranking'] += b_rank[left_action]
                        selected_rank_counts['left_action_in_right_ranking'] += 1
                    if right_action in a_rank:
                        selected_rank_sums['right_action_in_left_ranking'] += a_rank[right_action]
                        selected_rank_counts['right_action_in_left_ranking'] += 1
                    if ac == bc:
                        mechanism['same_ranking_order'] += [x['action_id'] for x in a_ranking] == [x['action_id'] for x in b_ranking]
                    if a.get('fault_behavior_observed') and b.get('fault_behavior_observed'):
                        signs['both_behavior_failed'] += 1
                        signs['left_success'] += bool(a.get('episode_success'))
                        signs['right_success'] += bool(b.get('episode_success'))
                        signs['left_action_success'] += bool(a.get('recovery_success'))
                        signs['right_action_success'] += bool(b.get('recovery_success'))
                        common_failure_by_seed[seed]['n'] += 1
                        common_failure_by_seed[seed]['left_success'] += bool(a.get('episode_success'))
                        common_failure_by_seed[seed]['right_success'] += bool(b.get('episode_success'))
                        common_failure_by_seed[seed]['left_action_success'] += bool(a.get('recovery_success'))
                        common_failure_by_seed[seed]['right_action_success'] += bool(b.get('recovery_success'))
                        common_failure_by_seed[seed]['difference_sum'] += (
                            int(bool(a.get('episode_success'))) - int(bool(b.get('episode_success')))
                        )
                        common_failure_by_seed[seed]['action_difference_sum'] += (
                            int(bool(a.get('recovery_success'))) - int(bool(b.get('recovery_success')))
                        )
            common_seed_difference = {
                seed: counts['difference_sum'] / counts['n']
                for seed, counts in common_failure_by_seed.items() if counts['n']
            }
            common_action_seed_difference = {
                seed: counts['action_difference_sum'] / counts['n']
                for seed, counts in common_failure_by_seed.items() if counts['n']
            }
            common_failure_paired = {
                'n_episode_pairs': signs['both_behavior_failed'],
                'left_strict_success': signs['left_success'],
                'right_strict_success': signs['right_success'],
                'left_rate': signs['left_success'] / signs['both_behavior_failed'] if signs['both_behavior_failed'] else None,
                'right_rate': signs['right_success'] / signs['both_behavior_failed'] if signs['both_behavior_failed'] else None,
                'paired_seed_cluster_difference': (
                    ci_seed_bootstrap(common_seed_difference) if common_seed_difference else None
                ),
            }
            common_failure_repair_action_paired = {
                'n_episode_pairs': signs['both_behavior_failed'],
                'left_success': signs['left_action_success'],
                'right_success': signs['right_action_success'],
                'left_rate': signs['left_action_success'] / signs['both_behavior_failed'] if signs['both_behavior_failed'] else None,
                'right_rate': signs['right_action_success'] / signs['both_behavior_failed'] if signs['both_behavior_failed'] else None,
                'paired_seed_cluster_difference': (
                    ci_seed_bootstrap(common_action_seed_difference) if common_action_seed_difference else None
                ),
            }
            mechanism['action_pair_counts'] = dict(action_pairs)
            mechanism['mean_left_action_rank_in_right_ranking'] = (
                selected_rank_sums['left_action_in_right_ranking'] / selected_rank_counts['left_action_in_right_ranking']
                if selected_rank_counts['left_action_in_right_ranking'] else None
            )
            mechanism['mean_right_action_rank_in_left_ranking'] = (
                selected_rank_sums['right_action_in_left_ranking'] / selected_rank_counts['right_action_in_left_ranking']
                if selected_rank_counts['right_action_in_left_ranking'] else None
            )
            mechanism['selected_action_rank_denominators'] = dict(selected_rank_counts)
            mechanism['same_belief_rate'] = mechanism['same_belief'] / mechanism['paired_episodes'] if mechanism['paired_episodes'] else None
            mechanism['same_online_evidence_rate'] = mechanism['same_online_evidence'] / mechanism['paired_episodes'] if mechanism['paired_episodes'] else None
            mechanism['same_online_evidence_schema_rate'] = mechanism['same_online_evidence_schema'] / mechanism['paired_episodes'] if mechanism['paired_episodes'] else None
            mechanism['same_nav2_parameter_readbacks_rate'] = mechanism['same_nav2_parameter_readbacks'] / mechanism['paired_episodes'] if mechanism['paired_episodes'] else None
            mechanism['same_amcl_status_flags_rate'] = mechanism['same_amcl_status_flags'] / mechanism['paired_episodes'] if mechanism['paired_episodes'] else None
            mechanism['same_candidate_set_rate'] = mechanism['same_candidates'] / mechanism['paired_episodes'] if mechanism['paired_episodes'] else None
            mechanism['online_evidence_field_mismatch_counts'] = dict(evidence_field_mismatches)
            mechanism['planner_lifecycle_non_normal_counts'] = dict(lifecycle_non_normal_counts)
            mechanism['amcl_distance_abs_delta_m'] = {
                'n': len(amcl_distance_abs_deltas),
                'mean': sum(amcl_distance_abs_deltas) / len(amcl_distance_abs_deltas) if amcl_distance_abs_deltas else None,
                'max': max(amcl_distance_abs_deltas) if amcl_distance_abs_deltas else None,
            }
            mechanism['same_amcl_distance_threshold_state'] = {
                'n': amcl_threshold_state_pairs['n'],
                'same': amcl_threshold_state_pairs['same'],
                'rate': amcl_threshold_state_pairs['same'] / amcl_threshold_state_pairs['n'] if amcl_threshold_state_pairs['n'] else None,
                'unknown_pairs': amcl_threshold_state_pairs['unknown_pairs'],
                'threshold_m': 0.35,
            }
            mechanism['same_planner_lifecycle_anomaly_predicate_rate'] = (
                lifecycle_anomaly_predicate_pairs['same'] / lifecycle_anomaly_predicate_pairs['n']
                if lifecycle_anomaly_predicate_pairs['n'] else None
            )
            mechanism['same_ranking_order'] = mechanism['same_ranking_order'] / mechanism['same_candidates'] if mechanism['same_candidates'] else None
            by_family[family] = {
                'strict_joint_success': ci_seed_bootstrap(family_seed_diff),
                'intervention_cost_mean_left_minus_right': ci_seed_bootstrap(family_seed_cost_diff),
                'common_behavior_failure': dict(signs),
                'common_failure_paired_strict_success': common_failure_paired,
                'common_failure_paired_repair_action': common_failure_repair_action_paired,
                'mechanism': dict(mechanism),
            }
        for seed in seeds:
            left_rows = [r for family in FAMILIES for r in selected[(left, seed, family)]['rows']]
            right_rows = [r for family in FAMILIES for r in selected[(right, seed, family)]['rows']]
            left_rate = sum(bool(r.get('episode_success')) for r in left_rows) / len(left_rows)
            right_rate = sum(bool(r.get('episode_success')) for r in right_rows) / len(right_rows)
            seed_diff[seed] = left_rate - right_rate
            seed_cost_diff[seed] = intervention_cost_mean(left_rows) - intervention_cost_mean(right_rows)
        paired[f'{left}_minus_{right}'] = {
            'strict_joint_success': ci_seed_bootstrap(seed_diff),
            'intervention_cost_mean_left_minus_right': ci_seed_bootstrap(seed_cost_diff),
            'family_details': by_family,
        }
    return {'protocol_id': protocol['protocol_id'], 'seed_count': len(seeds), 'family_count': 4,
            'method_family': by_method_family, 'paired': paired,
            'selected_cells': [{'method': m, 'seed': s, 'fault_family': f, 'path': item['path']}
                               for (m, s, f), item in sorted(selected.items())]}


def main() -> None:
    selected, metadata = select()
    result = summarize(selected, metadata['protocol'])
    result['excluded_attempts'] = metadata['excluded']
    result['protocol_sha256'] = hashlib.sha256(PROTOCOL.read_bytes()).hexdigest()
    result['analysis_script_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(OUT)


if __name__ == '__main__':
    main()
