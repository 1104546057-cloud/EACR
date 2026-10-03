#!/usr/bin/env python3
"""Aggregate only valid, lifecycle-ready Gazebo phase-three runs."""

from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]
MAIN_BASELINES = {
    'rule_based_recovery', 'bayesian_fixed_recovery',
    'ig_without_evolving_experience', 'eacr_static', 'eacr_evolving',
}
SEEDS = {20260926, 20260927, 20260928, 20260929, 20260930}
FAMILIES = {'localization', 'costmap', 'planner', 'control'}
sys.path.insert(0, str(WORKSPACE / 'src' / 'eacr_core'))
from eacr_core.metrics import (  # noqa: E402
    brier_score,
    expected_calibration_error,
    mean_time_to_recovery,
    outcome_nll,
    policy_kl,
    recovery_rate,
)

def main() -> None:
    paths = sorted(glob.glob(str(WORKSPACE / 'results' / 'phase3_gazebo_*.json')))
    files = [(path, json.loads(Path(path).read_text())) for path in paths]
    valid_candidates = [
        (path, item) for path, item in files
        if item.get('baseline') in MAIN_BASELINES
        if item.get('gazebo_observation_adapter')
        and not item.get('infrastructure_failure', True)
        and item.get('protocol_compliant') is True
        and (item.get('baseline') != 'eacr_evolving' or all(
            row.get('episode_evidence_valid') and row.get('experience_updated_online')
            for row in item.get('episodes', [])
        ))
    ]
    # Retries are allowed, but only the newest valid record for a frozen
    # baseline/seed/fault cell enters the statistics.
    latest = {}
    for path, item in valid_candidates:
        episodes_for_item = item.get('episodes', [])
        if not episodes_for_item:
            continue
        key = (item.get('baseline'), item.get('seed'), episodes_for_item[0].get('fault_family'))
        if key not in latest or int(item.get('run_id', 0)) > int(latest[key][1].get('run_id', 0)):
            latest[key] = (path, item)
    valid = [item for _, item in latest.values()]
    episodes = [episode for item in valid for episode in item.get('episodes', [])]
    baseline_names = {item.get('baseline') for item in valid}
    seeds = {item.get('seed') for item in valid}
    probabilities = [row.get('predicted_recovery_probability') for row in episodes]
    observations = [bool(row.get('episode_success', False)) for row in episodes]
    usable_predictions = [
        (float(probability), observation)
        for probability, observation in zip(probabilities, observations)
        if probability is not None
    ]
    actions_by_baseline = {}
    for item in valid:
        actions_by_baseline.setdefault(item.get('baseline'), []).extend(
            row.get('selected_action') for row in item.get('episodes', []) if row.get('selected_action')
        )
    def distribution(values):
        total = len(values)
        return {action: values.count(action) / total for action in sorted(set(values))} if total else {}
    rule_distribution = distribution(actions_by_baseline.get('rule_based_recovery', []))
    metrics = {
        'fault_effect_observed_rate': (
            sum(float(row.get('fault_effect_observed', False)) for row in episodes) / len(episodes)
            if episodes else None
        ),
        'fault_behavior_observed_rate': (
            sum(float(row.get('fault_behavior_observed', False)) for row in episodes) / len(episodes)
            if episodes else None
        ),
        'recovery_success_rate': recovery_rate(observations) if episodes else None,
        'sustained_recovery_rate': recovery_rate(
            bool(row.get('episode_success', False)) and row.get('recovery_navigation_status') == 4
            for row in episodes
        ) if episodes else None,
        'intervention_cost_mean': (
            sum(float(row['intervention_cost']) for row in episodes if row.get('intervention_cost') is not None)
            / len([row for row in episodes if row.get('intervention_cost') is not None])
            if any(row.get('intervention_cost') is not None for row in episodes) else None
        ),
        'mttr_sec': mean_time_to_recovery(
            row.get('recovery_navigation_duration_sec') if row.get('episode_success') else None
            for row in episodes
        ),
        'useless_probe_rate': (
            sum(bool(row.get('selected_action', '').startswith('inspect')) and not row.get('episode_success', False) for row in episodes)
            / len(episodes) if episodes else None
        ),
        'outcome_prediction_nll': (
            sum(outcome_nll(probability, observed) for probability, observed in usable_predictions)
            / len(usable_predictions) if usable_predictions else None
        ),
        'brier_score': (
            sum(brier_score(probability, observed) for probability, observed in usable_predictions)
            / len(usable_predictions) if usable_predictions else None
        ),
        'ece': expected_calibration_error(
            [probability for probability, _ in usable_predictions],
            [observed for _, observed in usable_predictions],
        ) if usable_predictions else None,
    }
    metrics['policy_kl_vs_rule'] = {
        baseline: policy_kl(rule_distribution, distribution(actions))
        for baseline, actions in actions_by_baseline.items()
        if rule_distribution
    }
    result = {
        'protocol_id': 'eacr_phase3_v1',
        'source_files': [path for path, _ in latest.values()],
        'valid_run_count': len(valid),
        'valid_candidate_run_count': len(valid_candidates),
        'excluded_infrastructure_run_count': len(files) - len(valid),
        'excluded_noncompliant_run_count': sum(item.get('protocol_compliant') is not True for _, item in files),
        'valid_episode_count': len(episodes),
        'valid_runs_only': True,
        'metrics': metrics,
        'acceptance': {
            'has_lifecycle_ready_runs': bool(valid),
            'has_all_four_fault_families': {row.get('fault_family') for row in episodes} == FAMILIES,
            'has_all_five_baselines': baseline_names == MAIN_BASELINES,
            'has_all_five_seeds': seeds == SEEDS,
            'all_nominal_trials_valid': all(row.get('nominal_navigation_valid') for row in episodes),
            'all_fault_effects_observed': all(row.get('fault_effect_observed') for row in episodes),
            'all_recovery_trials_recorded': all(row.get('recovery_navigation_status') is not None for row in episodes),
            'statistics_ready': set(latest) == {
                (baseline, seed, family)
                for baseline in MAIN_BASELINES for seed in SEEDS for family in FAMILIES
            },
        },
    }
    output = WORKSPACE / 'results' / 'phase3_gazebo_aggregate.json'
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result['acceptance'], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
